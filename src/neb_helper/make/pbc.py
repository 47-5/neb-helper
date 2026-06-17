from __future__ import annotations

import numpy as np
from typing import Tuple


def assert_compatible_endpoints(initial, final, cell_tol: float = 1.0e-6) -> None:
    if len(initial) != len(final):
        raise ValueError("Initial and final structures must have the same atom count.")
    if initial.get_chemical_symbols() != final.get_chemical_symbols():
        raise ValueError("Initial and final structures must use the same atom order.")
    if not np.array_equal(initial.get_pbc(), final.get_pbc()):
        raise ValueError("Initial and final structures must use the same PBC flags.")
    if not np.allclose(initial.cell.array, final.cell.array, atol=cell_tol):
        raise ValueError("Variable-cell paths are not supported in this v2 workflow.")


def mic_displacement(pos_a, pos_b, cell, pbc) -> np.ndarray:
    pos_a = np.asarray(pos_a, dtype=float)
    pos_b = np.asarray(pos_b, dtype=float)
    cell = np.asarray(cell, dtype=float)
    pbc = np.asarray(pbc, dtype=bool)
    delta_frac = (pos_b - pos_a) @ np.linalg.inv(cell)
    for axis, is_periodic in enumerate(pbc):
        if is_periodic:
            delta_frac[..., axis] -= np.round(delta_frac[..., axis])
    return delta_frac @ cell


def sanitize_image(atoms, ref_cell=None, ref_pbc=None, eps: float = 1.0e-12):
    if ref_cell is not None:
        atoms.set_cell(ref_cell, scale_atoms=False)
    if ref_pbc is not None:
        atoms.set_pbc(ref_pbc)

    pbc = np.asarray(atoms.get_pbc(), dtype=bool)
    if not np.any(pbc):
        return atoms

    scaled = atoms.get_scaled_positions(wrap=False)
    for axis, is_periodic in enumerate(pbc):
        if is_periodic:
            scaled[:, axis] = scaled[:, axis] - np.floor(scaled[:, axis])
            scaled[:, axis] = np.clip(scaled[:, axis], 0.0, 1.0 - eps)
    atoms.set_scaled_positions(scaled)
    return atoms


def sanitize_images(images, ref_cell=None, ref_pbc=None, eps: float = 1.0e-12):
    for image in images:
        sanitize_image(image, ref_cell=ref_cell, ref_pbc=ref_pbc, eps=eps)
    return images


def outside_fractional_span(atoms, tol: float = 1.0e-8) -> Tuple[float, float, bool]:
    pbc = np.asarray(atoms.get_pbc(), dtype=bool)
    scaled = atoms.get_scaled_positions(wrap=False)
    if not np.any(pbc):
        return 0.0, 0.0, False
    periodic = scaled[:, pbc]
    min_scaled = float(np.min(periodic))
    max_scaled = float(np.max(periodic))
    outside = bool(min_scaled < -tol or max_scaled >= 1.0 + tol)
    return min_scaled, max_scaled, outside


def max_mic_jump(prev, current) -> float:
    displacement = mic_displacement(
        prev.get_positions(),
        current.get_positions(),
        prev.cell.array,
        prev.get_pbc(),
    )
    return float(np.max(np.linalg.norm(displacement, axis=1)))
