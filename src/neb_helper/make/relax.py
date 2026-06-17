from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ase.constraints import FixAtoms
from ase.optimize import BFGS, FIRE

from .calculators import make_calculator
from .pbc import sanitize_image
from .progress import optimizer_logfile, progress_print


def relax_images(images, spec):
    if not spec.relax.enabled:
        return images

    calculator_spec = spec.relax.calculator
    if (calculator_spec.type or "none").lower() in {"none", "off", "false"}:
        raise ValueError("relax.enabled is true, but relax.calculator.type is none.")

    indices = list(range(len(images)) if spec.relax.relax_endpoints else range(1, len(images) - 1))
    fixed_indices = _fixed_indices(spec)
    optimizer_cls = _optimizer_class(spec.relax.optimizer)
    progress_print(
        spec.relax.log_to_screen,
        "[relax] start: "
        f"images={len(indices)}, optimizer={spec.relax.optimizer}, "
        f"steps={spec.relax.steps}, fmax={spec.relax.fmax}",
    )

    for progress_index, image_index in enumerate(indices, start=1):
        image = images[image_index]
        constraints = []
        if fixed_indices:
            constraints.append(FixAtoms(indices=fixed_indices))
        image.set_constraint(constraints)
        image.calc = make_calculator(calculator_spec)

        progress_print(
            spec.relax.log_to_screen,
            f"[relax] image {image_index:03d} ({progress_index}/{len(indices)})",
        )
        trajectory = _image_specific_path(spec.relax.trajectory, image_index)
        logfile_path = _image_specific_path(spec.relax.logfile, image_index)
        try:
            with optimizer_logfile(logfile_path, spec.relax.log_to_screen) as logfile:
                optimizer = optimizer_cls(
                    image,
                    maxstep=spec.relax.maxstep,
                    trajectory=trajectory,
                    logfile=logfile,
                )
                optimizer.run(fmax=spec.relax.fmax, steps=spec.relax.steps)
        finally:
            image.calc = None

        if spec.pbc.wrap_policy == "always":
            sanitize_image(
                image,
                ref_cell=images[0].cell,
                ref_pbc=images[0].get_pbc(),
                eps=spec.pbc.eps,
            )
    return images


def _fixed_indices(spec) -> List[int]:
    fixed = set(spec.frozen_atoms)
    if spec.relax.freeze_active:
        fixed.update(spec.active_atoms)
        for torsion in spec.torsions:
            fixed.update(torsion.dihedral)
            fixed.update(torsion.rotating_group)
    return sorted(fixed)


def _optimizer_class(name: str):
    lowered = name.lower()
    if lowered == "bfgs":
        return BFGS
    if lowered == "fire":
        return FIRE
    raise ValueError(f"Unsupported optimizer: {name}")


def _image_specific_path(path: Optional[str], image_index: int):
    if path is None or path == "":
        return None
    if path == "-":
        return "-"
    path_obj = Path(path)
    suffix = path_obj.suffix
    stem = path_obj.stem
    parent = path_obj.parent
    return str(parent / f"{stem}_{image_index:03d}{suffix}")
