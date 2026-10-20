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
  a reading, so a re-send is safe.

The lock is per address, not per GPIB board: NI-VISA already serialises
transfers on one board, and a board-wide lock would make the heater-off
command wait behind a slow thermocouple read on another instrument.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from typing import Any, Dict, Iterator

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

    _OWN = frozenset({"_res", "_name", "_lock", "_clear_on_timeout",
                      "_lock_wait_s", "stats"})

    def __init__(self, resource: Any, name: str = "", *,
                 clear_on_timeout: bool = True,
                 lock_wait_s: float = DEFAULT_LOCK_WAIT_S):
        address = getattr(resource, "resource_name", None) or name
        object.__setattr__(self, "_res", resource)
        object.__setattr__(self, "_name", name or str(address))
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
    def _call(self, op: str, args, kwargs, retry: bool):
        fn = getattr(self._res, op)
        with self.transaction():
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                if not (retry and is_timeout(exc)):
                    raise
                self.stats["timeouts"] += 1
                what = f"{op}({args[0]!r})" if args else f"{op}()"
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


def transaction(instrument: Any):
    """``with transaction(inst):`` — holds the lock of a guarded session; a
    no-op context for anything else (test fakes, ``None``)."""
    txn = getattr(instrument, "transaction", None)
    if isinstance(instrument, GuardedResource) and callable(txn):
        return txn()
    return contextlib.nullcontext(instrument)
