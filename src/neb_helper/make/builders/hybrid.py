from __future__ import annotations

from ase.mep.neb import NEB

from ..pbc import sanitize_images
from .cartesian import build_mic_linear
from .torsion import apply_torsion_controls
from .waypoint import apply_waypoint_controls


def build_images(initial, final, spec):
    if spec.background.method != "mic_linear":
        raise ValueError(f"Unsupported background method: {spec.background.method}")

    images = build_mic_linear(initial, final, spec.n_images)

    if spec.background.idpp:
        NEB(images=images, method="improvedtangent").interpolate(method="idpp", mic=True)

    if spec.waypoints:
        images = apply_waypoint_controls(images, spec.waypoints, spec.active_atoms)

    if spec.torsions:
        images = apply_torsion_controls(images, spec.torsions)

    if spec.pbc.wrap_policy == "always":
        sanitize_images(
            images,
            ref_cell=initial.cell,
            ref_pbc=initial.get_pbc(),
            eps=spec.pbc.eps,
        )
    return images
