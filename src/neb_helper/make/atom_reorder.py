from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from neb_helper.common.geometry import mic_displacement


def pairwise_mic_distances(ref_positions, target_positions, cell, pbc) -> np.ndarray:
    delta = mic_displacement(
        ref_positions[:, None, :],
        target_positions[None, :, :],
        cell,
        pbc,
    )
    return np.linalg.norm(delta, axis=2)


def reorder_target_by_reference(reference, target):
    ref_symbols = reference.get_chemical_symbols()
    target_symbols = target.get_chemical_symbols()
    if len(reference) != len(target):
        raise ValueError(
            f"Atom count mismatch: reference has {len(reference)}, target has {len(target)}."
        )
    if Counter(ref_symbols) != Counter(target_symbols):
        raise ValueError(
            "Composition mismatch: reference and target must contain the same elements "
            "with the same counts."
        )

    try:
        from scipy.optimize import linear_sum_assignment
    except ImportError as exc:
        raise RuntimeError(
            "Endpoint atom reordering needs scipy for robust atom matching. Install "
            "scipy in the Python environment used to run nebmake."
        ) from exc

    ref_by_symbol = defaultdict(list)
    target_by_symbol = defaultdict(list)
    for index, symbol in enumerate(ref_symbols):
        ref_by_symbol[symbol].append(index)
    for index, symbol in enumerate(target_symbols):
        target_by_symbol[symbol].append(index)

    target_order = [None] * len(reference)
    match_distances = np.zeros(len(reference), dtype=float)
    ref_positions = reference.get_positions()
    target_positions = target.get_positions()

    for symbol in sorted(ref_by_symbol):
        ref_indices = np.asarray(ref_by_symbol[symbol], dtype=int)
        target_indices = np.asarray(target_by_symbol[symbol], dtype=int)
        distances = pairwise_mic_distances(
            ref_positions[ref_indices],
            target_positions[target_indices],
            reference.cell.array,
            reference.get_pbc(),
        )
        row_ind, col_ind = linear_sum_assignment(distances)
        for row, col in zip(row_ind, col_ind):
            ref_index = int(ref_indices[row])
            target_index = int(target_indices[col])
            target_order[ref_index] = target_index
            match_distances[ref_index] = distances[row, col]

    reordered = target[target_order]
    reordered.set_cell(target.cell, scale_atoms=False)
    reordered.set_pbc(target.get_pbc())
    return reordered, match_distances, target_order


def distance_stats(distances) -> dict:
    distances = np.asarray(distances, dtype=float)
    if len(distances) == 0:
        return {"count": 0, "max": 0.0, "rms": 0.0}
    return {
        "count": int(len(distances)),
        "max": float(np.max(distances)),
        "rms": float(np.sqrt(np.mean(distances**2))),
    }


def validate_max_distance(distances, max_distance, *, field_name: str) -> None:
    if max_distance is None:
        return
    stats = distance_stats(distances)
    if stats["max"] > max_distance:
        raise ValueError(
            f"Maximum matched distance is {stats['max']:.6f} A, larger than "
            f"{field_name}={max_distance:.6f} A. Check that the two endpoint "
            "structures represent the intended atom correspondence."
        )


def write_mapping_csv(path, symbols, target_order, distances) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write("reference_index,target_index,symbol,distance_A\n")
        for ref_index, target_index in enumerate(target_order):
            handle.write(
                f"{ref_index},{target_index},{symbols[ref_index]},"
                f"{distances[ref_index]:.10f}\n"
            )

