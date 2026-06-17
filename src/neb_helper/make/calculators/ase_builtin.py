from __future__ import annotations


def make_builtin_calculator(spec):
    calc_type = (spec.type or "").lower()
    kwargs = dict(spec.kwargs)
    if calc_type == "emt":
        from ase.calculators.emt import EMT

        return EMT(**kwargs)
    if calc_type in {"lj", "lennardjones"}:
        from ase.calculators.lj import LennardJones

        return LennardJones(**kwargs)
    raise ValueError(f"Unsupported calculator type: {spec.type}")
