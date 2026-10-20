"""Which VISA library the app talks to: the real NI-VISA, or a simulated rig.

Set the environment variable ``TE_VISA_BACKEND`` before starting the app:

* unset / empty      → the default VISA library (NI-VISA on the lab PC)
* ``sim``            → the bundled simulated rig (``sim/te_rig.yaml``, needs pyvisa-sim)
* ``<file>.yaml@sim`` or any other pyvisa backend string → used as given

Simulated runs are real database runs, so the backend is recorded in every
run's provenance (``run_context["visa_backend"]``) and shown in the top bar —
a simulated result can never be mistaken for a measurement.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_VAR = "TE_VISA_BACKEND"
SIM_PROFILE = Path(__file__).with_name("sim") / "te_rig.yaml"


def visa_backend() -> str:
    """The pyvisa backend string in effect ("" = default VISA library)."""
    value = os.environ.get(ENV_VAR, "").strip()
    if value.lower() == "sim":
        return f"{SIM_PROFILE}@sim"
    return value


def is_simulated() -> bool:
    return visa_backend().lower().endswith("@sim")


def resource_manager():
    """A new pyvisa ResourceManager on the configured backend."""
    import pyvisa

    backend = visa_backend()
    return pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
