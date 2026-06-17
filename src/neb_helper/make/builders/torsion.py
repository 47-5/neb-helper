from __future__ import annotations

import numpy as np
from typing import List


def apply_torsion_controls(images, torsion_specs):
    for torsion in torsion_specs:
        _apply_one_torsion(images, torsion)
    return images


def torsion_active_atoms(torsion_specs) -> List[int]:
    atoms = set()
    for torsion in torsion_specs:
        atoms.update(torsion.dihedral)
        atoms.update(torsion.rotating_group)
    return sorted(atoms)


def _apply_one_torsion(images, torsion) -> None:
    if len(torsion.dihedral) != 4:
        raise ValueError(f"{torsion.name}: dihedral must contain four atom indices.")
    if not torsion.rotating_group:
        raise ValueError(f"{torsion.name}: rotating_group is required.")

    values = _torsion_values(images, torsion)
    for index, value in enumerate(values):
        if value is None:
            continue
        if index in (0, len(images) - 1) and not torsion.apply_endpoints:
            continue
        image = images[index]
        image.set_dihedral(
            *torsion.dihedral,
            angle=float(value),
            indices=torsion.rotating_group,
        )


def _torsion_values(images, torsion):
    total = len(images)
    if torsion.values_deg is not None:
        values = list(torsion.values_deg)
        if len(values) == total:
            return values
        if len(values) == total - 2:
            return [None, *values, None]
        raise ValueError(
            f"{torsion.name}: values_deg length must be {total} or {total - 2}."
        )

    start = torsion.start_deg
    if start is None:
        start = images[0].get_dihedral(*torsion.dihedral, mic=True)
    end = torsion.end_deg
    if end is None:
        end = images[-1].get_dihedral(*torsion.dihedral, mic=True)
    return list(np.linspace(float(start), float(end), total))
