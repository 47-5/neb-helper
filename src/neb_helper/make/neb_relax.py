from __future__ import annotations

import inspect
from pathlib import Path
from typing import List, Optional

import numpy as np
from ase.constraints import FixAtoms
from ase.io import write
from ase.mep.neb import NEB
from ase.optimize import BFGS, FIRE

from .batch_evaluators import UnsupportedBatchEvaluator, make_batch_evaluator
from .batched_neb import BatchedNEB
from .calculators import make_calculator
from .pbc import mic_displacement, sanitize_image, sanitize_images
from .progress import optimizer_logfile, progress_print
from .validate import collect_diagnostics, write_diagnostics
from .writers import write_outputs


def relax_neb_band(images, spec):
    if not spec.neb_relax.enabled:
        return images

    calculator_spec = spec.neb_relax.calculator
    if (calculator_spec.type or "none").lower() in {"none", "off", "false"}:
        raise ValueError("neb_relax.enabled is true, but neb_relax.calculator.type is none.")

    fixed_indices = _fixed_indices(spec)
    constraints = [FixAtoms(indices=fixed_indices)] if fixed_indices else []
    for image in images:
        image.set_constraint(constraints)

    batch_evaluator = _make_batch_evaluator_if_requested(spec)
    if batch_evaluator is None:
        _attach_calculators(images, spec)
        evaluator_name = "ase"
    else:
        evaluator_name = getattr(batch_evaluator, "name", "batch")

    neb = _make_neb(images, spec, batch_evaluator=batch_evaluator)
    optimizer_cls = _optimizer_class(spec.neb_relax.optimizer)
    progress_print(
        spec.neb_relax.log_to_screen,
        "[neb_relax] start: "
        f"images={len(images)}, optimizer={spec.neb_relax.optimizer}, "
        f"steps={spec.neb_relax.steps}, fmax={spec.neb_relax.fmax}, "
        f"climb={spec.neb_relax.climb}, method={spec.neb_relax.method}, "
        f"force_evaluator={evaluator_name}",
    )
    try:
        with optimizer_logfile(
            _output_path(spec.output.directory, spec.neb_relax.logfile),
            spec.neb_relax.log_to_screen,
        ) as logfile:
            optimizer = optimizer_cls(
                neb,
                maxstep=spec.neb_relax.maxstep,
                trajectory=_output_path(spec.output.directory, spec.neb_relax.trajectory),
                logfile=logfile,
            )
            recorder = NebRelaxRecorder(images, spec, optimizer)
            if recorder.enabled:
                optimizer.attach(recorder, interval=1)
            optimizer.run(fmax=spec.neb_relax.fmax, steps=spec.neb_relax.steps)
    finally:
        for image in images:
            image.calc = None

    progress_print(spec.neb_relax.log_to_screen, "[neb_relax] finished")

    if spec.pbc.wrap_policy == "always":
        sanitize_images(
            images,
            ref_cell=images[0].cell,
            ref_pbc=images[0].get_pbc(),
            eps=spec.pbc.eps,
        )
    return images


class NebRelaxRecorder:
    def __init__(self, images, spec, optimizer):
        self.images = images
        self.spec = spec
        self.optimizer = optimizer
        self.energy_path = _output_path(spec.output.directory, spec.neb_relax.energy_log)
        self.image_paths = _image_trajectory_paths(images, spec)
        self.write_current_outputs = bool(spec.neb_relax.write_current_outputs)
        self.current_output_interval = max(1, int(spec.neb_relax.current_output_interval))
        self.enabled = bool(self.energy_path or self.image_paths or self.write_current_outputs)
        self._reset_outputs()

    def __call__(self) -> None:
        step = self.optimizer.nsteps
        if self.energy_path:
            self._write_energy_line(step)
        if self.image_paths:
            self._write_image_trajectories()
        if self._should_write_current_outputs(step):
            self._write_current_outputs()

    def _should_write_current_outputs(self, step: int) -> bool:
        if not self.write_current_outputs:
            return False
        return step % self.current_output_interval == 0

    def _reset_outputs(self) -> None:
        paths = []
        if self.energy_path:
            paths.append(Path(self.energy_path))
        paths.extend(self.image_paths)
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                path.unlink()

    def _write_energy_line(self, step: int) -> None:
        energies = _current_band_energies(self.images, self.optimizer)
        distances = _band_rms_mic_distances(self.images)
        line = f"{step:10d}"
        line += "".join(f"{energy:20.9f}" for energy in energies)
        line += "".join(f"{distance:20.9f}" for distance in distances)
        line += "\n"
        with Path(self.energy_path).open("a", encoding="utf-8") as handle:
            handle.write(line)

    def _write_image_trajectories(self) -> None:
        fmt = self.spec.neb_relax.image_trajectory_format
        for image, path in zip(self.images, self.image_paths):
            traj_image = image.copy()
            traj_image.calc = None
            if self.spec.pbc.output_wrap:
                sanitize_image(
                    traj_image,
                    ref_cell=self.images[0].cell,
                    ref_pbc=self.images[0].get_pbc(),
                    eps=self.spec.pbc.eps,
                )
            write(str(path), traj_image, format=fmt, append=True)

    def _write_current_outputs(self) -> None:
        snapshots = []
        for image in self.images:
            snapshot = image.copy()
            snapshot.calc = None
            snapshots.append(snapshot)
        write_outputs(snapshots, self.spec)
        if self.spec.output.diagnostics:
            write_diagnostics(
                collect_diagnostics(snapshots),
                Path(self.spec.output.directory) / self.spec.output.diagnostics,
            )


def _image_trajectory_paths(images, spec) -> List[Path]:
    if not spec.neb_relax.write_image_trajectories:
        return []
    suffix = spec.neb_relax.image_trajectory_suffix
    if not suffix:
        return []
    output_dir = Path(spec.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)
    return [
        output_dir / f"{spec.output.images_prefix}_{index:03d}{suffix}"
        for index in range(len(images))
    ]


def _band_rms_mic_distances(images) -> List[float]:
    distances = []
    for left, right in zip(images, images[1:]):
        displacement = mic_displacement(
            left.get_positions(),
            right.get_positions(),
            left.cell.array,
            left.get_pbc(),
        )
        distances.append(float(np.sqrt(np.mean(np.sum(displacement * displacement, axis=1)))))
    return distances


def _current_band_energies(images, optimizer) -> List[float]:
    neb = getattr(optimizer, "atoms", None)
    energies = getattr(neb, "energies", None)
    if energies is not None and len(energies) == len(images):
        return [float(energy) for energy in energies]
    return [float(image.get_potential_energy()) for image in images]


def _make_batch_evaluator_if_requested(spec):
    mode = (spec.neb_relax.force_evaluator or "ase").strip().lower()
    if mode in {"ase", "standard", "default"}:
        return None
    if mode in {"batch", "batched", "auto"}:
        try:
            return make_batch_evaluator(
                spec.neb_relax.calculator,
                batch_size=spec.neb_relax.force_batch_size,
            )
        except UnsupportedBatchEvaluator as exc:
            if mode == "auto":
                progress_print(
                    spec.neb_relax.log_to_screen,
                    f"[neb_relax] batch evaluator unavailable ({exc}); falling back to ASE.",
                )
                return None
            raise
    raise ValueError(
        "Unsupported neb_relax.force_evaluator value "
        f"{spec.neb_relax.force_evaluator!r}; use ase, auto, or batch."
    )


def _attach_calculators(images, spec) -> None:
    # ASE improvedtangent evaluates endpoint energies, so endpoints need calculators too.
    if _use_shared_calculator(spec):
        calculator = make_calculator(spec.neb_relax.calculator)
        for image in images:
            image.calc = calculator
        return

    for image in images:
        image.calc = make_calculator(spec.neb_relax.calculator)


def _use_shared_calculator(spec) -> bool:
    shared = spec.neb_relax.shared_calculator
    if isinstance(shared, str):
        lowered = shared.lower()
        if lowered == "auto":
            calc_type = (spec.neb_relax.calculator.type or "").lower()
            return calc_type in {"mace", "dp", "deepmd", "deepmd-kit"}
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        raise ValueError(f"Unsupported shared_calculator value: {shared}")
    return bool(shared)


def _make_neb(images, spec, batch_evaluator=None):
    neb_cls = BatchedNEB if batch_evaluator is not None else NEB
    requested = {
        "k": spec.neb_relax.k,
        "climb": spec.neb_relax.climb,
        "parallel": spec.neb_relax.parallel,
        "remove_rotation_and_translation": spec.neb_relax.remove_rotation_and_translation,
        "method": spec.neb_relax.method,
        "allow_shared_calculator": _use_shared_calculator(spec),
    }
    signature = inspect.signature(NEB)
    kwargs = {name: value for name, value in requested.items() if name in signature.parameters}
    if batch_evaluator is not None:
        kwargs["force_evaluator"] = batch_evaluator
    return neb_cls(images=images, **kwargs)


def _fixed_indices(spec) -> List[int]:
    fixed = set(spec.frozen_atoms)
    if spec.neb_relax.freeze_active:
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
    raise ValueError(f"Unsupported NEB optimizer: {name}")


def _output_path(output_dir: str, path: Optional[str]):
    if path is None or path == "":
        return None
    if path == "-":
        return "-"
    path_obj = Path(path)
    if path_obj.is_absolute():
        return str(path_obj)
    output_path = Path(output_dir) / path_obj
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return str(output_path)
