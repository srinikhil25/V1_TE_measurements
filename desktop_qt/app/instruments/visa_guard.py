"""Serialised, retrying access to VISA instrument sessions (SAF-6).

Every driver wraps the session it opens in a :class:`GuardedResource`. The
wrapper adds two things to ``write`` / ``query`` / ``read``:

* **One lock per instrument address**, shared by every session to that
  address in this process. The Seebeck run thread, the I-V sweep, the GUI
  thread's emergency heater-off and the cleanup path can therefore never
  interleave commands on the same instrument. Multi-command sequences that
  must not be split (close a scanner channel *then* read it; re-assert
  remote *then* set the heater voltage) hold the lock for the whole sequence
  via :meth:`GuardedResource.transaction`.

* **One retry on a VISA timeout**, then the original error is raised so the
  caller's existing failure handling runs ("fail hard"). Before a retried
  query the device is cleared (IEEE-488 Selected Device Clear) so a late
  reply to the first attempt cannot be read as the answer to the second.
  The Matsusada P4K-80M is never sent a device clear; its retries are
  plain re-sends. Every command this app sends is an idempotent setpoint or
  a reading, so a re-send is safe. No retry once a stop was requested
  (:func:`set_abort_check`), so Stop / Abort waits for one timeout at most.

* **Instrument health**: the last failure of each instrument (which
  command, and why) is kept in a process-wide registry, so a run that ends
  on an instrument fault can say which instrument failed and how
  (:func:`instrument_health`, :func:`failure_summary`).

The lock is per address, not per GPIB board: NI-VISA already serialises
transfers on one board, and a board-wide lock would make the heater-off
command wait behind a slow thermocouple read on another instrument.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Any, Callable, ContextManager, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

VI_ERROR_TMO = -1073807339

#: Longest time a caller waits for another thread's command on the same
#: instrument before giving up with :class:`InstrumentBusyError`. Must exceed
#: the slowest legitimate transaction (two timed-out attempts of a 20 s read).
DEFAULT_LOCK_WAIT_S = 60.0

_locks: Dict[str, threading.RLock] = {}
_locks_guard = threading.Lock()


class InstrumentBusyError(RuntimeError):
    """Another thread held the instrument for longer than the lock wait."""


# ── instrument health registry ─────────────────────────────────────────────
_health: Dict[str, Dict[str, Any]] = {}
_health_guard = threading.Lock()


def _describe_error(exc: Optional[BaseException]) -> str:
    if exc is None:
        return "failed"
    if is_timeout(exc):
        return "no answer (timeout)"
    if isinstance(exc, InstrumentBusyError):
        return "busy in another thread"
    text = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return text[:160]


def _note(address: str, name: str, ok: bool, what: str = "",
          exc: Optional[BaseException] = None) -> None:
    key = _key(address)
    with _health_guard:
        h = _health.setdefault(key, {"name": name, "address": address,
                                     "consecutive_failures": 0, "failures": 0,
                                     "last_error": None, "last_error_at": None})
        h["name"] = name
        if ok:
            h["consecutive_failures"] = 0
        else:
            h["consecutive_failures"] += 1
            h["failures"] += 1
            h["last_error"] = f"{_describe_error(exc)} on {what}" if what else _describe_error(exc)
            h["last_error_at"] = time.time()


def report_failure(instrument: Any, what: str, exc: BaseException) -> None:
    """Record a failure that happened outside the VISA call itself (e.g. a
    reply that could not be parsed). No-op for unguarded objects."""
    if isinstance(instrument, GuardedResource):
        _note(instrument._address, instrument._name, False, what, exc)


def instrument_health() -> Dict[str, Dict[str, Any]]:
    """Snapshot {ADDRESS: {name, address, consecutive_failures, failures,
    last_error, last_error_at}} of every instrument used since the last reset."""
    with _health_guard:
        return {k: dict(v) for k, v in _health.items()}


def reset_instrument_health() -> None:
    """Forget past failures — called at the start of every run."""
    with _health_guard:
        _health.clear()


def failure_summary(only_current: bool = True) -> str:
    """One line per failing instrument, e.g.
    "Keithley 2700 (GPIB0::16::INSTR): no answer (timeout) on query(':READ?')".
    ``only_current`` limits it to instruments whose LAST call failed."""
    lines = []
    for h in instrument_health().values():
        if h["last_error"] and (h["consecutive_failures"] or not only_current):
            lines.append(f"{h['name']} ({h['address']}): {h['last_error']}")
    return "; ".join(lines)


def set_abort_check(instrument: Any, check: Optional[Callable[[], bool]]) -> None:
    """While ``check()`` is True, a timed-out command is not retried — a stop
    request then waits for one timeout at most. No-op for unguarded objects."""
    if isinstance(instrument, GuardedResource):
        object.__setattr__(instrument, "_abort_check", check)


def _key(resource_name: str) -> str:
    return str(resource_name or "").strip().upper()


def instrument_lock(resource_name: str) -> threading.RLock:
    """The process-wide lock for one instrument address (created on first use)."""
    key = _key(resource_name)
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = _locks[key] = threading.RLock()
        return lock


def is_timeout(exc: BaseException) -> bool:
    """True for a VISA I/O timeout (VI_ERROR_TMO), however pyvisa wraps it."""
    code = getattr(exc, "error_code", None)
    try:
        if code is not None and int(code) == VI_ERROR_TMO:
            return True
    except (TypeError, ValueError):
        pass
    return "VI_ERROR_TMO" in str(exc)


class GuardedResource:
    """Thread-safe, retry-once proxy around a pyvisa resource.

    Attributes not defined here (``timeout``, ``read_termination``,
    ``write_termination``, ``resource_name`` …) are read from and written to
    the wrapped resource, so drivers use it exactly like the raw session.
    """

    _OWN = frozenset({"_res", "_name", "_address", "_lock", "_clear_on_timeout",
                      "_lock_wait_s", "_abort_check", "stats"})

    def __init__(self, resource: Any, name: str = "", *,
                 address: str = "",
                 clear_on_timeout: bool = True,
                 lock_wait_s: float = DEFAULT_LOCK_WAIT_S):
        # Prefer the opened resource's own name; some backends (pyvisa-sim on
        # an address it doesn't know) leave it unset, so the configured address
        # the driver opened is the fallback.
        own = getattr(resource, "resource_name", None)
        address = own if isinstance(own, str) and own else (address or name)
        object.__setattr__(self, "_res", resource)
        object.__setattr__(self, "_name", name or str(address))
        object.__setattr__(self, "_address", str(address))
        object.__setattr__(self, "_abort_check", None)
        object.__setattr__(self, "_lock", instrument_lock(address))
        object.__setattr__(self, "_clear_on_timeout", clear_on_timeout)
        object.__setattr__(self, "_lock_wait_s", lock_wait_s)
        object.__setattr__(self, "stats", {"timeouts": 0, "recovered": 0, "failed": 0})

    # ── attribute pass-through ──────────────────────────────────────────────
    def __getattr__(self, item):
        return getattr(object.__getattribute__(self, "_res"), item)

    def __setattr__(self, key, value):
        if key in GuardedResource._OWN:
            object.__setattr__(self, key, value)
        else:
            setattr(self._res, key, value)

    @property
    def raw(self) -> Any:
        """The wrapped pyvisa resource."""
        return self._res

    # ── locking ─────────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def transaction(self) -> Iterator["GuardedResource"]:
        """Hold this instrument for a multi-command sequence (re-entrant)."""
        if not self._lock.acquire(timeout=self._lock_wait_s):
            raise InstrumentBusyError(
                f"{self._name}: instrument busy in another thread for more than "
                f"{self._lock_wait_s:g} s")
        try:
            yield self
        finally:
            self._lock.release()

    # ── guarded I/O ─────────────────────────────────────────────────────────
    def _aborting(self) -> bool:
        try:
            return bool(self._abort_check and self._abort_check())
        except Exception:
            return False

    def _call(self, op: str, args, kwargs, retry: bool):
        what = f"{op}({args[0]!r})" if args else f"{op}()"
        try:
            out = self._call_inner(op, what, args, kwargs, retry)
        except Exception as exc:
            _note(self._address, self._name, False, what, exc)
            raise
        _note(self._address, self._name, True)
        return out

    def _call_inner(self, op: str, what: str, args, kwargs, retry: bool):
        fn = getattr(self._res, op)
        with self.transaction():
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not (retry and is_timeout(exc)):
                    raise
                self.stats["timeouts"] += 1
                if self._aborting():
                    logger.warning("%s: %s timed out — not retried (stop requested)",
                                   self._name, what)
                    raise
                logger.warning("%s: %s timed out — retrying once", self._name, what)
                if op != "write" and self._clear_on_timeout:
                    try:
                        self._res.clear()
                    except Exception as clr_exc:
                        logger.warning("%s: device clear failed: %s", self._name, clr_exc)
                time.sleep(0.05)
                try:
                    out = fn(*args, **kwargs)
                except Exception as exc2:
                    self.stats["failed"] += 1
                    logger.error("%s: %s failed again after retry: %s", self._name, what, exc2)
                    raise
                self.stats["recovered"] += 1
                logger.info("%s: %s succeeded on retry", self._name, what)
                return out

    def write(self, message, *args, retry: bool = True, **kwargs):
        return self._call("write", (message, *args), kwargs, retry)

    def query(self, message, *args, retry: bool = True, **kwargs):
        return self._call("query", (message, *args), kwargs, retry)

    def read(self, *args, retry: bool = True, **kwargs):
        return self._call("read", args, kwargs, retry)

    def clear(self):
        with self.transaction():
            return self._res.clear()

    def close(self):
        # Waits for any in-flight command on this session before closing it.
        with self.transaction():
            return self._res.close()

    def __repr__(self) -> str:
        return f"<GuardedResource {self._name}>"


def guard(resource: Any, name: str = "", **kwargs) -> GuardedResource:
    """Wrap an opened pyvisa resource (idempotent)."""
    if isinstance(resource, GuardedResource):
        return resource
    return GuardedResource(resource, name, **kwargs)


def write_once(instrument: Any, message: str):
    """Write without the automatic retry — for callers that run their own
    bounded retry loop (the heater-off sequence)."""
    if isinstance(instrument, GuardedResource):
        return instrument.write(message, retry=False)
    return instrument.write(message)


def transaction(instrument: Any) -> ContextManager[Any]:
    """``with transaction(inst):`` — holds the lock of a guarded session; a
    no-op context for anything else (test fakes, ``None``)."""
    if isinstance(instrument, GuardedResource):
        return instrument.transaction()
    return contextlib.nullcontext(instrument)
