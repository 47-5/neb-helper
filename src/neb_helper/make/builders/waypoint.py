from __future__ import annotations

from typing import List

from ase.io import read

from ..pbc import mic_displacement


def apply_waypoint_controls(images, waypoint_specs, active_atoms):
    if not waypoint_specs:
        return images

    control_atoms = _resolve_control_atoms(images, waypoint_specs, active_atoms)
    last_index = len(images) - 1
    controls = [(0, images[0].get_positions()[control_atoms])]
    for order, waypoint in enumerate(waypoint_specs):
        atoms_to_copy = waypoint.atoms or control_atoms
        if list(atoms_to_copy) != list(control_atoms):
            raise ValueError(
                "All waypoint atom sets must match in this first v2 implementation. "
                "Use active_atoms for a shared reaction-center subset."
            )
        image_index = _target_image_index(waypoint, order, len(waypoint_specs), last_index)
        control_positions = _read_control_positions(waypoint.file, control_atoms)
        controls.append((image_index, control_positions))
    controls.append((last_index, images[-1].get_positions()[control_atoms]))

    controls.sort(key=lambda item: item[0])
    _validate_control_indices(controls)

    cell = images[0].cell.array
    pbc = images[0].get_pbc()
    for (start_index, start_pos), (end_index, end_pos) in zip(controls, controls[1:]):
        displacement = mic_displacement(start_pos, end_pos, cell, pbc)
        span = end_index - start_index
        for image_index in range(start_index, end_index + 1):
            fraction = (image_index - start_index) / span if span else 0.0
            positions = images[image_index].get_positions()
            positions[control_atoms] = start_pos + fraction * displacement
            images[image_index].set_positions(positions)
    return images


def _resolve_control_atoms(images, waypoint_specs, active_atoms):
    for waypoint in waypoint_specs:
        if waypoint.atoms:
            return list(waypoint.atoms)
    if all(not waypoint.active_atoms_only for waypoint in waypoint_specs):
        return list(range(len(images[0])))
    if active_atoms:
        return list(active_atoms)
    raise ValueError("waypoints require active_atoms, waypoint.atoms, or active_atoms_only: false.")


def _target_image_index(waypoint, order: int, n_waypoints: int, last_index: int) -> int:
    if waypoint.image is not None:
        image_index = int(waypoint.image)
    elif waypoint.fraction is not None:
        image_index = round(float(waypoint.fraction) * last_index)
    else:
        image_index = round((order + 1) * last_index / (n_waypoints + 1))
    if image_index <= 0 or image_index >= last_index:
        raise ValueError("Waypoint image/fraction must target an intermediate image.")
    return image_index


def _read_control_positions(path: str, atoms_to_copy: List[int]):
    waypoint_atoms = read(path)
    if len(waypoint_atoms) == len(atoms_to_copy):
        return waypoint_atoms.get_positions()
    if len(waypoint_atoms) > max(atoms_to_copy):
        return waypoint_atoms.get_positions()[atoms_to_copy]
    raise ValueError(
        f"Waypoint {path} has {len(waypoint_atoms)} atoms, but cannot map to indices "
        f"{atoms_to_copy}."
    )


def _validate_control_indices(controls):
    seen = set()
    for image_index, _positions in controls:
        if image_index in seen:
            raise ValueError(f"Duplicate waypoint/control image index: {image_index}")
        seen.add(image_index)
