from __future__ import annotations

from typing import Sequence

import numpy as np


def mic_displacement(pos_a, pos_b, cell, pbc) -> np.ndarray:
    pos_a = np.asarray(pos_a, dtype=float)
    pos_b = np.asarray(pos_b, dtype=float)
    pbc = np.asarray(pbc, dtype=bool)
    delta = pos_b - pos_a
    if not np.any(pbc):
        return delta

    cell = np.asarray(cell, dtype=float)
    if abs(float(np.linalg.det(cell))) < 1.0e-12:
        raise ValueError("Periodic MIC displacement requires a non-singular cell.")
    delta_frac = delta @ np.linalg.inv(cell)
    for axis, is_periodic in enumerate(pbc):
        if is_periodic:
            delta_frac[..., axis] -= np.round(delta_frac[..., axis])
    return delta_frac @ cell


def image_distance(left, right) -> float:
    displacement = mic_displacement(
        left.get_positions(),
        right.get_positions(),
        left.cell.array,
        left.get_pbc(),
    )
    return float(np.sqrt(np.sum(displacement * displacement)))


def path_segment_lengths(images: Sequence[object]) -> np.ndarray:
    return np.asarray(
        [image_distance(left, right) for left, right in zip(images, images[1:])],
        dtype=float,
    )


def interpolate_mic(left, right, fraction: float):
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"Interpolation fraction must be in [0, 1], got {fraction}.")
    displacement = mic_displacement(
        left.get_positions(),
        right.get_positions(),
        left.cell.array,
        left.get_pbc(),
    )
    image = left.copy()
    image.set_cell(left.cell, scale_atoms=False)
    image.set_pbc(left.get_pbc())
    image.set_positions(left.get_positions() + float(fraction) * displacement)
    return image


def assert_compatible_pair(
    left,
    right,
    *,
    left_label: str = "left image",
    right_label: str = "right image",
    cell_tol: float = 1.0e-6,
) -> None:
    assert_compatible_images(
        [left, right],
        labels=[left_label, right_label],
        cell_tol=cell_tol,
    )


def assert_compatible_images(
    images: Sequence[object],
    *,
    labels: Sequence[str] | None = None,
    cell_tol: float = 1.0e-6,
) -> None:
    if not images:
        raise ValueError("At least one image is required.")
    if labels is None:
        labels = [f"image {index}" for index in range(len(images))]
    if len(labels) != len(images):
        raise ValueError("Image labels must have the same length as images.")

    reference = images[0]
    reference_label = labels[0]
    symbols = reference.get_chemical_symbols()
    pbc = np.asarray(reference.get_pbc(), dtype=bool)
    cell = np.asarray(reference.cell.array, dtype=float)

    for image, label in zip(images[1:], labels[1:]):
        if len(image) != len(reference):
            raise ValueError(
                f"{label} has {len(image)} atoms; expected {len(reference)} from {reference_label}."
            )
        if image.get_chemical_symbols() != symbols:
            raise ValueError(f"{label} uses a different atom order than {reference_label}.")
        if not np.array_equal(image.get_pbc(), pbc):
            raise ValueError(f"{label} uses different PBC flags than {reference_label}.")
        if np.any(pbc) and not np.allclose(image.cell.array, cell, atol=cell_tol):
            raise ValueError(f"{label} uses a different cell than {reference_label}.")

    if np.any(pbc) and abs(float(np.linalg.det(cell))) < 1.0e-12:
        raise ValueError("Periodic MIC operations require a non-singular cell.")
