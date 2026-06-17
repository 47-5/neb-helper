from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from .calculators.mace import make_mace_calculator


@dataclass
class BatchEvaluation:
    energies: np.ndarray
    forces: np.ndarray


class UnsupportedBatchEvaluator(RuntimeError):
    pass


def make_batch_evaluator(calculator_spec, batch_size: Optional[int] = None):
    batch_size = _normalize_batch_size(batch_size)
    calc_type = (calculator_spec.type or "none").lower()
    if calc_type == "mace":
        return MACEBatchEvaluator(calculator_spec, batch_size=batch_size)
    if calc_type in {"dp", "deepmd", "deepmd-kit"}:
        return DPBatchEvaluator(calculator_spec, batch_size=batch_size)
    raise UnsupportedBatchEvaluator(
        f"No batched force evaluator is implemented for calculator type {calculator_spec.type!r}."
    )


def _normalize_batch_size(batch_size: Optional[int]) -> Optional[int]:
    if batch_size in (None, ""):
        return None
    batch_size = int(batch_size)
    if batch_size == 0:
        return None
    if batch_size < 0:
        raise ValueError("force_batch_size must be a positive integer, 0, or empty.")
    return batch_size


def _iter_chunks(images: Sequence, batch_size: Optional[int]):
    if batch_size is None or batch_size >= len(images):
        yield images
        return
    for start in range(0, len(images), batch_size):
        yield images[start : start + batch_size]


def _concat_evaluations(parts: Sequence[BatchEvaluation]) -> BatchEvaluation:
    if len(parts) == 1:
        return parts[0]
    return BatchEvaluation(
        energies=np.concatenate([part.energies for part in parts], axis=0),
        forces=np.concatenate([part.forces for part in parts], axis=0),
    )


class MACEBatchEvaluator:
    name = "mace-batch"

    def __init__(self, calculator_spec, batch_size: Optional[int] = None):
        self.batch_size = batch_size
        if self.batch_size is not None:
            self.name = f"mace-batch/chunk={self.batch_size}"
        self.calculator = make_mace_calculator(calculator_spec)
        try:
            from mace import data as mace_data
            from mace.tools import torch_geometric
        except ImportError as exc:
            raise UnsupportedBatchEvaluator("MACE batch evaluator needs mace-torch internals.") from exc
        self.mace_data = mace_data
        self.torch_geometric = torch_geometric

    def evaluate(self, images: Sequence) -> BatchEvaluation:
        self._check_images(images)
        try:
            parts = [self._evaluate_chunk(chunk) for chunk in _iter_chunks(images, self.batch_size)]
        except RuntimeError as exc:
            if "out of memory" in str(exc).lower():
                raise RuntimeError(
                    "MACE batch evaluation ran out of GPU memory. "
                    "Set neb_relax.force_batch_size to a smaller value, for example 2 or 1."
                ) from exc
            raise
        return _concat_evaluations(parts)

    def _evaluate_chunk(self, images: Sequence) -> BatchEvaluation:
        batch = self._images_to_batch(images)
        energies = []
        forces = []
        compute_stress = self.calculator.model_type in ["MACE", "EnergyDipoleMACE"] and not self.calculator.use_compile
        for model in self.calculator.models:
            batch_clone = self.calculator._clone_batch(batch)
            out = model(
                batch_clone.to_dict(),
                compute_stress=compute_stress,
                training=self.calculator.use_compile,
                compute_edge_forces=self.calculator.compute_atomic_stresses,
                compute_atomic_stresses=self.calculator.compute_atomic_stresses,
            )
            if out.get("energy") is None or out.get("forces") is None:
                raise RuntimeError("MACE model did not return both energy and forces.")
            energies.append(out["energy"].detach())
            forces.append(out["forces"].detach())

        import torch

        energy = torch.mean(torch.stack(energies, dim=0), dim=0).reshape(len(images))
        force = torch.mean(torch.stack(forces, dim=0), dim=0)
        energy_np = energy.cpu().numpy() * self.calculator.energy_units_to_eV
        force_np = force.cpu().numpy() * (
            self.calculator.energy_units_to_eV / self.calculator.length_units_to_A
        )
        force_np = force_np.reshape(len(images), len(images[0]), 3)
        return BatchEvaluation(energies=np.asarray(energy_np, dtype=float), forces=force_np)

    def _images_to_batch(self, images: Sequence):
        self.calculator.arrays_keys.update({self.calculator.charges_key: "charges"})
        keyspec = self.mace_data.KeySpecification(
            info_keys=self.calculator.info_keys,
            arrays_keys=self.calculator.arrays_keys,
        )
        dataset = []
        for atoms in images:
            config = self.mace_data.config_from_atoms(
                atoms,
                key_specification=keyspec,
                head_name=self.calculator.head,
            )
            dataset.append(
                self.mace_data.AtomicData.from_config(
                    config,
                    z_table=self.calculator.z_table,
                    cutoff=self.calculator.r_max,
                    heads=self.calculator.available_heads,
                )
            )
        data_loader = self.torch_geometric.dataloader.DataLoader(
            dataset=dataset,
            batch_size=len(dataset),
            shuffle=False,
            drop_last=False,
        )
        return next(iter(data_loader)).to(self.calculator.device)

    @staticmethod
    def _check_images(images: Sequence) -> None:
        if not images:
            raise ValueError("No images supplied to MACE batch evaluator.")
        natoms = len(images[0])
        symbols = images[0].get_chemical_symbols()
        for image in images[1:]:
            if len(image) != natoms:
                raise ValueError("All images must have the same atom count for batched MACE NEB.")
            if image.get_chemical_symbols() != symbols:
                raise ValueError("All images must have the same atom order for batched MACE NEB.")


class DPBatchEvaluator:
    name = "deepmd-batch"

    def __init__(self, calculator_spec, batch_size: Optional[int] = None):
        self.spec = calculator_spec
        self.batch_size = batch_size
        if self.batch_size is not None:
            self.name = f"deepmd-batch/chunk={self.batch_size}"
        try:
            from deepmd.infer import DeepPot
        except ImportError as exc:
            raise UnsupportedBatchEvaluator(
                "DeepMD batch evaluator needs deepmd.infer.DeepPot, but deepmd is not installed."
            ) from exc
        kwargs = dict(calculator_spec.kwargs)
        if calculator_spec.head is not None:
            kwargs.setdefault("head", calculator_spec.head)
        try:
            self.deep_pot = DeepPot(calculator_spec.model, **kwargs)
        except TypeError:
            if calculator_spec.head is not None:
                kwargs.pop("head", None)
                self.deep_pot = DeepPot(calculator_spec.model, **kwargs)
            else:
                raise
        self.type_map = self._type_map()

    def evaluate(self, images: Sequence) -> BatchEvaluation:
        self._check_images(images)
        atom_types = self._atom_types(images[0])
        parts = [
            self._evaluate_chunk(chunk, atom_types)
            for chunk in _iter_chunks(images, self.batch_size)
        ]
        return _concat_evaluations(parts)

    def _evaluate_chunk(self, images: Sequence, atom_types: np.ndarray) -> BatchEvaluation:
        coords = np.asarray([image.get_positions().reshape(-1) for image in images], dtype=float)
        cells = None
        if np.any(images[0].get_pbc()):
            cells = np.asarray([image.cell.array.reshape(-1) for image in images], dtype=float)
        result = self.deep_pot.eval(coords, cells, atom_types)
        energies = np.asarray(result[0], dtype=float).reshape(len(images))
        forces = np.asarray(result[1], dtype=float).reshape(len(images), len(images[0]), 3)
        return BatchEvaluation(energies=energies, forces=forces)

    def _type_map(self):
        for name in ("get_type_map", "get_type_map_str"):
            method = getattr(self.deep_pot, name, None)
            if method is not None:
                type_map = method()
                if isinstance(type_map, str):
                    return type_map.split()
                return list(type_map)
        raise UnsupportedBatchEvaluator(
            "DeepMD model did not expose a type map; cannot build atom type indices for batch eval."
        )

    def _atom_types(self, atoms):
        atom_types = []
        for symbol in atoms.get_chemical_symbols():
            try:
                atom_types.append(self.type_map.index(symbol))
            except ValueError as exc:
                raise ValueError(f"Element {symbol!r} not found in DeepMD type map {self.type_map}.") from exc
        return np.asarray(atom_types, dtype=np.int32)

    @staticmethod
    def _check_images(images: Sequence) -> None:
        if not images:
            raise ValueError("No images supplied to DeepMD batch evaluator.")
        natoms = len(images[0])
        symbols = images[0].get_chemical_symbols()
        pbc = images[0].get_pbc()
        for image in images[1:]:
            if len(image) != natoms:
                raise ValueError("All images must have the same atom count for batched DeepMD NEB.")
            if image.get_chemical_symbols() != symbols:
                raise ValueError("All images must have the same atom order for batched DeepMD NEB.")
            if not np.array_equal(image.get_pbc(), pbc):
                raise ValueError("All images must use the same PBC flags for batched DeepMD NEB.")
