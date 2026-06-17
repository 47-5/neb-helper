from __future__ import annotations

from .ase_builtin import make_builtin_calculator
from .dp import make_dp_calculator
from .mace import make_mace_calculator


def make_calculator(spec):
    calc_type = (spec.type or "none").lower()
    if calc_type in {"none", "off", "false"}:
        return None
    if calc_type in {"dp", "deepmd", "deepmd-kit"}:
        return make_dp_calculator(spec)
    if calc_type == "mace":
        return make_mace_calculator(spec)
    return make_builtin_calculator(spec)
