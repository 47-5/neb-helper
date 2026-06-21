from __future__ import annotations

import csv
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from ase.io import read, write

from neb_helper.common.geometry import assert_compatible_pair, mic_displacement
from neb_helper.make.atom_selection import parse_atom_indices, parse_atom_selector
from neb_helper.make.dimer_vector import format_dimer_vector, mask_vector, resolve_atom_indices


@dataclass(frozen=True)
class TsGuessCandidate:
    fraction: float
    structure_path: Optional[Path]
    score: float
    metrics: dict[str, float]


@dataclass(frozen=True)
class TsGuessResult:
    output_dir: Path
    recommended_fraction: float
    recommended_structure: Path
    candidates: list[TsGuessCandidate]
    metrics_path: Optional[Path] = None
    notes_path: Optional[Path] = None
    dimer_vector_path: Optional[Path] = None
    check_path: Optional[Path] = None
    selected_indices: list[int] = field(default_factory=list)
    raw_dimer_norm: Optional[float] = None


@dataclass(frozen=True)
class TsGuessSpec:
    initial: str
    final: str
    output_dir: Path
    atom_indices_1_based: bool = False
    active_atoms: list[int] = field(default_factory=list)
    frozen_atoms: list[int] = field(default_factory=list)
    path: dict[str, Any] = field(default_factory=dict)
    reaction_coordinates: dict[str, Any] = field(default_factory=dict)
    selection: dict[str, Any] = field(default_factory=dict)
    candidate_outputs: dict[str, Any] = field(default_factory=dict)
    dimer_vector: dict[str, Any] = field(default_factory=dict)
    check: dict[str, Any] = field(default_factory=dict)


def load_ts_guess_config(path: Union[str, Path]) -> TsGuessSpec:
    path = Path(path)
    data = _load_mapping(path)
    if not isinstance(data, Mapping):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return ts_guess_spec_from_mapping(data, base_dir=path.parent)


def ts_guess_spec_from_mapping(data: Mapping[str, Any], base_dir: Union[str, Path] = ".") -> TsGuessSpec:
    base_dir = Path(base_dir)
    atom_indices_1_based = _atom_indices_1_based_from_mapping(data)
    output_data = _first_mapping(data, "candidate_outputs", "output")
    output_dir = _resolve_path(output_data.get("directory", "ts_guess"), base_dir)
    return TsGuessSpec(
        initial=str(_resolve_path(data["initial"], base_dir)),
        final=str(_resolve_path(data["final"], base_dir)),
        output_dir=output_dir,
        atom_indices_1_based=atom_indices_1_based,
        active_atoms=parse_atom_indices(
            data.get("active_atoms", []),
            one_based=atom_indices_1_based,
            field_name="active_atoms",
        ),
        frozen_atoms=parse_atom_indices(
            data.get("frozen_atoms", []),
            one_based=atom_indices_1_based,
            field_name="frozen_atoms",
        ),
        path=dict(data.get("path", {})),
        reaction_coordinates=_parse_reaction_coordinates(
            data.get("reaction_coordinates", {}), one_based=atom_indices_1_based
        ),
        selection=dict(data.get("selection", {})),
        candidate_outputs=dict(output_data),
        dimer_vector=_parse_dimer_vector(
            data.get("dimer_vector", {}), one_based=atom_indices_1_based
        ),
        check=dict(data.get("check", {})),
    )


def generate_ts_guess(spec: Union[TsGuessSpec, Mapping[str, Any], str, Path]) -> TsGuessResult:
    if isinstance(spec, (str, Path)):
        spec = load_ts_guess_config(spec)
    elif isinstance(spec, Mapping):
        spec = ts_guess_spec_from_mapping(spec)

    initial = read(spec.initial)
    final = read(spec.final)
    assert_compatible_pair(initial, final, left_label="initial", right_label="final")
    final.set_cell(initial.cell, scale_atoms=False)
    final.set_pbc(initial.get_pbc())

    active_atoms = _resolve_active_atoms(spec, len(initial))
    fractions = _normalize_fractions(spec.path.get("fractions", [0.70, 0.75, 0.78, 0.80]))
    dimer_data = spec.dimer_vector
    tangent_fractions = (
        _normalize_fractions(dimer_data.get("tangent_fractions", [fractions[0], fractions[-1]]))
        if _parse_bool(dimer_data.get("enabled", False), "dimer_vector.enabled")
        else []
    )
    build_fractions = _sorted_unique([*fractions, *tangent_fractions])

    structures = {
        fraction: _build_candidate_structure(initial, final, spec, active_atoms, fraction)
        for fraction in build_fractions
    }

    output_dir = Path(spec.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidates = _score_candidates(structures, fractions, spec, active_atoms)
    recommended = min(candidates, key=lambda item: (item.score, abs(item.fraction - _prefer_fraction(spec, item.fraction))))

    candidates = _write_candidate_structures(candidates, structures, recommended.fraction, spec, output_dir)
    recommended_path = _write_recommended_structure(structures[recommended.fraction], recommended.fraction, spec, output_dir)
    metrics_path = _write_metrics(candidates, recommended.fraction, output_dir / str(spec.candidate_outputs.get("metrics", "metrics.csv")))
    notes_path = _write_notes(candidates, recommended.fraction, spec, output_dir / str(spec.candidate_outputs.get("notes", "notes.md")))

    dimer_vector_path = None
    check_path = None
    selected_indices: list[int] = []
    raw_dimer_norm: Optional[float] = None
    if _parse_bool(dimer_data.get("enabled", False), "dimer_vector.enabled"):
        dimer_vector_path, selected_indices, raw_dimer_norm, vector = _write_dimer_vector(
            structures, structures[recommended.fraction], spec, output_dir, active_atoms
        )
        if _parse_bool(spec.check.get("enabled", True), "check.enabled"):
            check_path = _write_direction_check(structures[recommended.fraction], vector, spec, output_dir)

    return TsGuessResult(
        output_dir=output_dir,
        recommended_fraction=recommended.fraction,
        recommended_structure=recommended_path,
        candidates=candidates,
        metrics_path=metrics_path,
        notes_path=notes_path,
        dimer_vector_path=dimer_vector_path,
        check_path=check_path,
        selected_indices=selected_indices,
        raw_dimer_norm=raw_dimer_norm,
    )


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="neb-helper tsguess",
        description="Generate TS candidate structures and optional CP2K DIMER_VECTOR from IS/FS endpoints.",
    )
    parser.add_argument("config", help="YAML or JSON config file.")
    args = parser.parse_args(argv)

    result = generate_ts_guess(args.config)
    print(f"Wrote {len(result.candidates)} TS candidate(s) to {result.output_dir}")
    print(f"Recommended fraction {result.recommended_fraction:.6g}: {result.recommended_structure}")
    if result.metrics_path:
        print(f"Metrics: {result.metrics_path}")
    if result.notes_path:
        print(f"Notes: {result.notes_path}")
    if result.dimer_vector_path:
        print(f"DIMER_VECTOR: {result.dimer_vector_path}")
        print(f"Selected {len(result.selected_indices)} atom(s); raw direction norm {result.raw_dimer_norm:.6g} A")
    if result.check_path:
        print(f"Direction check: {result.check_path}")
    return 0


def _build_candidate_structure(initial, final, spec: TsGuessSpec, active_atoms: Sequence[int], fraction: float):
    method = str(spec.path.get("method", "active_idpp")).strip().lower().replace("-", "_")
    base = str(spec.path.get("base", "initial")).strip().lower()
    image = _base_image(initial, final, fraction, base)

    displacement = mic_displacement(
        initial.get_positions(),
        final.get_positions(),
        initial.cell.array,
        initial.get_pbc(),
    )
    positions = image.get_positions()
    positions[list(active_atoms)] = initial.get_positions()[list(active_atoms)] + fraction * displacement[list(active_atoms)]
    image.set_positions(positions)

    if method in {"active_idpp", "idpp", "idpp_like"}:
        _refine_active_idpp_like(initial, final, image, active_atoms, fraction, spec.path.get("idpp", {}))
    elif method not in {"active_linear", "linear", "mic_linear"}:
        raise ValueError(
            "path.method must be active_idpp, idpp_like, active_linear, linear, or mic_linear; "
            f"got {spec.path.get('method')!r}."
        )
    return image


def _base_image(initial, final, fraction: float, base: str):
    if base in {"initial", "is"}:
        return initial.copy()
    if base in {"final", "fs"}:
        return final.copy()
    if base in {"linear", "mic_linear"}:
        displacement = mic_displacement(
            initial.get_positions(), final.get_positions(), initial.cell.array, initial.get_pbc()
        )
        image = initial.copy()
        image.set_positions(initial.get_positions() + fraction * displacement)
        return image
    raise ValueError("path.base must be initial, final, or linear.")


def _refine_active_idpp_like(initial, final, image, active_atoms: Sequence[int], fraction: float, data: Mapping[str, Any]) -> None:
    active = list(active_atoms)
    if len(active) < 2:
        return
    steps = int(data.get("steps", 200))
    max_step = float(data.get("max_step", data.get("maxstep", 0.03)))
    tolerance = float(data.get("tolerance", 1.0e-5))
    tether_weight = float(data.get("tether_weight", 0.02))

    cell = initial.cell.array
    pbc = initial.get_pbc()
    initial_pos = initial.get_positions()
    final_pos = final.get_positions()
    linear_target = initial_pos + fraction * mic_displacement(initial_pos, final_pos, cell, pbc)

    pairs: list[tuple[int, int, float, float]] = []
    for offset, i in enumerate(active):
        for j in active[offset + 1 :]:
            d0 = _distance(initial_pos, i, j, cell, pbc)
            d1 = _distance(final_pos, i, j, cell, pbc)
            target = max((1.0 - fraction) * d0 + fraction * d1, 1.0e-6)
            weight = 1.0 / max(target, 1.0) ** 4
            pairs.append((i, j, target, weight))

    if not pairs:
        return

    active_array = np.asarray(active, dtype=int)
    for _ in range(steps):
        positions = image.get_positions()
        grad = np.zeros_like(positions)
        for i, j, target, weight in pairs:
            vector = mic_displacement(positions[i], positions[j], cell, pbc)
            dist = float(np.linalg.norm(vector))
            if dist < 1.0e-10:
                continue
            coeff = 2.0 * weight * (dist - target) / dist
            g = coeff * vector
            grad[i] -= g
            grad[j] += g

        if tether_weight > 0.0:
            grad[active_array] += 2.0 * tether_weight * (positions[active_array] - linear_target[active_array])

        active_grad = grad[active_array]
        max_grad = float(np.max(np.linalg.norm(active_grad, axis=1)))
        if max_grad < tolerance:
            break
        scale = min(max_step / max_grad, 1.0)
        positions[active_array] -= scale * active_grad
        image.set_positions(positions)


def _score_candidates(structures: Mapping[float, object], fractions: Sequence[float], spec: TsGuessSpec, active_atoms: Sequence[int]) -> list[TsGuessCandidate]:
    result: list[TsGuessCandidate] = []
    for fraction in fractions:
        atoms = structures[fraction]
        metrics = _candidate_metrics(atoms, fraction, spec, active_atoms)
        result.append(TsGuessCandidate(fraction=fraction, structure_path=None, score=metrics["score"], metrics=metrics))
    return result


def _candidate_metrics(atoms, fraction: float, spec: TsGuessSpec, active_atoms: Sequence[int]) -> dict[str, float]:
    rc = spec.reaction_coordinates
    selection = spec.selection
    cell = atoms.cell.array
    pbc = atoms.get_pbc()
    metrics: dict[str, float] = {"fraction": float(fraction)}
    score = 0.0

    forming = []
    for pair in rc.get("forming_bonds", []):
        distance = _distance(atoms.get_positions(), pair[0], pair[1], cell, pbc)
        forming.append(distance)
        metrics[_bond_metric_name("forming", pair, spec.atom_indices_1_based)] = distance
    if forming:
        lower, upper = _range(selection.get("forming_range", [2.10, 2.45]), "selection.forming_range")
        target = selection.get("target_forming_distance")
        if target is not None:
            target = float(target)
            width = max((upper - lower) / 2.0, 1.0e-6)
            score += sum(((distance - target) / width) ** 2 for distance in forming)
        else:
            score += sum(_range_penalty(distance, lower, upper) for distance in forming)
        if len(forming) > 1:
            metrics["forming_mean"] = float(np.mean(forming))
            metrics["forming_std"] = float(np.std(forming))
            score += float(selection.get("asymmetry_weight", 0.25)) * metrics["forming_std"] ** 2

    weakening_min = selection.get("weakening_min")
    for pair in rc.get("weakening_bonds", []):
        distance = _distance(atoms.get_positions(), pair[0], pair[1], cell, pbc)
        metrics[_bond_metric_name("weakening", pair, spec.atom_indices_1_based)] = distance
        if weakening_min is not None and distance < float(weakening_min):
            score += ((float(weakening_min) - distance) / 0.25) ** 2

    for pair in rc.get("monitor_bonds", []):
        metrics[_bond_metric_name("monitor", pair, spec.atom_indices_1_based)] = _distance(
            atoms.get_positions(), pair[0], pair[1], cell, pbc
        )

    min_distance = _min_pair_distance(atoms, active_atoms)
    metrics["min_active_pair_distance"] = min_distance
    min_allowed = float(selection.get("min_pair_distance", 0.65))
    if min_distance < min_allowed:
        score += 1000.0 * (min_allowed - min_distance) ** 2

    prefer = selection.get("prefer_fraction")
    if prefer is not None:
        score += float(selection.get("prefer_fraction_weight", 0.05)) * abs(float(fraction) - float(prefer))

    metrics["score"] = float(score)
    return metrics


def _write_candidate_structures(
    candidates: Sequence[TsGuessCandidate],
    structures: Mapping[float, object],
    recommended_fraction: float,
    spec: TsGuessSpec,
    output_dir: Path,
) -> list[TsGuessCandidate]:
    write_all = _parse_bool(spec.candidate_outputs.get("write_all", True), "candidate_outputs.write_all")
    structure_format = spec.candidate_outputs.get("format", None)
    template = str(
        spec.candidate_outputs.get(
            "candidate_template",
            f"ts_guess_{{tag}}{_default_structure_suffix(spec)}",
        )
    )
    output: list[TsGuessCandidate] = []
    for item in candidates:
        structure_path = None
        if write_all:
            tag = _fraction_tag(item.fraction)
            structure_path = output_dir / template.format(tag=tag, fraction=item.fraction)
            write(str(structure_path), structures[item.fraction], format=structure_format)
        elif item.fraction == recommended_fraction:
            structure_path = _recommended_path(item.fraction, spec, output_dir)
        output.append(
            TsGuessCandidate(
                fraction=item.fraction,
                structure_path=structure_path,
                score=item.score,
                metrics=item.metrics,
            )
        )
    return output


def _write_recommended_structure(atoms, fraction: float, spec: TsGuessSpec, output_dir: Path) -> Path:
    path = _recommended_path(fraction, spec, output_dir)
    structure_format = spec.candidate_outputs.get("format", None)
    write(str(path), atoms, format=structure_format)
    return path


def _recommended_path(fraction: float, spec: TsGuessSpec, output_dir: Path) -> Path:
    name = str(
        spec.candidate_outputs.get(
            "recommended_name",
            f"ts_guess_recommended_{{tag}}{_default_structure_suffix(spec)}",
        )
    )
    return output_dir / name.format(tag=_fraction_tag(fraction), fraction=fraction)


def _default_structure_suffix(spec: TsGuessSpec) -> str:
    output_format = spec.candidate_outputs.get("format")
    if output_format is None:
        return ".cif"
    lowered = str(output_format).strip().lower()
    if lowered in {"cif", "xyz"}:
        return f".{lowered}"
    if lowered == "extxyz":
        return ".xyz"
    return f".{lowered}"


def _write_metrics(candidates: Sequence[TsGuessCandidate], recommended_fraction: float, path: Path) -> Path:
    fieldnames: list[str] = []
    for item in candidates:
        for key in item.metrics:
            if key not in fieldnames:
                fieldnames.append(key)
    if "recommended" not in fieldnames:
        fieldnames.insert(1, "recommended")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in candidates:
            row = dict(item.metrics)
            row["recommended"] = int(item.fraction == recommended_fraction)
            writer.writerow(row)
    return path


def _write_notes(candidates: Sequence[TsGuessCandidate], recommended_fraction: float, spec: TsGuessSpec, path: Path) -> Path:
    lines = [
        "# TS guess summary",
        "",
        f"- Initial: `{spec.initial}`",
        f"- Final: `{spec.final}`",
        f"- Active atoms: `{_format_indices(spec.active_atoms, spec.atom_indices_1_based)}`",
        f"- Recommended fraction: `{recommended_fraction:.6g}`",
        "",
        "| fraction | score | structure |",
        "|---:|---:|---|",
    ]
    for item in candidates:
        marker = " **recommended**" if item.fraction == recommended_fraction else ""
        structure = item.structure_path.name if item.structure_path else ""
        lines.append(f"| {item.fraction:.6g} | {item.score:.6g} | `{structure}`{marker} |")
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "The candidate path is generated from the endpoint structures by moving the active atoms along the endpoint displacement and, by default, applying an IDPP-like distance cleanup inside the active region. Non-active atoms are taken from `path.base`, which defaults to the initial structure.",
            "",
            "The optional DIMER direction is a local path tangent between `dimer_vector.tangent_fractions`; by default only active atom components are retained.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_dimer_vector(
    structures: Mapping[float, object],
    center,
    spec: TsGuessSpec,
    output_dir: Path,
    active_atoms: Sequence[int],
) -> tuple[Path, list[int], float, np.ndarray]:
    data = spec.dimer_vector
    source = str(data.get("source", "local_tangent")).strip().lower().replace("-", "_")
    if source != "local_tangent":
        raise ValueError("Only dimer_vector.source: local_tangent is currently supported by tsguess.")
    candidate_fractions = _normalize_fractions(spec.path.get("fractions", [0.70, 0.75, 0.78, 0.80]))
    tangent_fractions = _normalize_fractions(data.get("tangent_fractions", [candidate_fractions[0], candidate_fractions[-1]]))
    if len(tangent_fractions) != 2:
        raise ValueError("dimer_vector.tangent_fractions must contain exactly two fractions, e.g. [0.70, 0.78].")
    left_fraction, right_fraction = tangent_fractions
    if left_fraction not in structures or right_fraction not in structures:
        raise ValueError("Internal error: tangent structures were not generated.")

    vector = mic_displacement(
        structures[left_fraction].get_positions(),
        structures[right_fraction].get_positions(),
        center.cell.array,
        center.get_pbc(),
    )
    atoms_selector = data.get("atoms", "active")
    if atoms_selector == "active" and not active_atoms:
        raise ValueError("dimer_vector.atoms: active requires a non-empty active_atoms selection in tsguess.")
    selected_indices = resolve_atom_indices(
        len(center),
        atoms=atoms_selector,
        active_atoms=active_atoms,
        frozen_atoms=spec.frozen_atoms,
        zero_frozen_atoms=_parse_bool(data.get("zero_frozen_atoms", True), "dimer_vector.zero_frozen_atoms"),
    )
    vector = mask_vector(vector, selected_indices)

    remove_translation = str(data.get("remove_translation", "active")).strip().lower()
    if remove_translation in {"active", "selected", "true", "yes"} and selected_indices:
        mean = np.mean(vector[selected_indices], axis=0)
        vector[selected_indices] -= mean
    elif remove_translation not in {"none", "false", "no", "all", "active", "selected", "true", "yes"}:
        raise ValueError("dimer_vector.remove_translation must be active, selected, all, none, true, or false.")
    elif remove_translation == "all":
        vector -= np.mean(vector, axis=0)

    raw_norm = float(np.linalg.norm(vector))
    if raw_norm <= 0.0:
        raise ValueError("DIMER_VECTOR is zero after atom selection and translation removal.")
    if _parse_bool(data.get("normalize", True), "dimer_vector.normalize"):
        vector = vector / raw_norm
    vector = vector * float(data.get("scale", 1.0))

    path = output_dir / str(data.get("file", "dimer_vector.inc"))
    comments = [
        "Generated by neb-helper tsguess.",
        "Place this block inside MOTION / GEO_OPT / TRANSITION_STATE / DIMER.",
        f"Direction: local tangent from t={left_fraction:.6g} to t={right_fraction:.6g}.",
        f"Selected atom count: {len(selected_indices)} of {len(center)}.",
        f"Raw selected direction norm: {raw_norm:.12g} A.",
    ]
    path.write_text(format_dimer_vector(vector, comments=comments), encoding="utf-8")
    return path, selected_indices, raw_norm, vector


def _write_direction_check(center, vector: np.ndarray, spec: TsGuessSpec, output_dir: Path) -> Path:
    amplitude = float(spec.check.get("amplitude", 0.10))
    path = output_dir / str(spec.check.get("file", "dimer_direction_check_minus_center_plus.xyz"))
    fmt = spec.check.get("format", "xyz")
    minus = center.copy()
    plus = center.copy()
    minus.set_positions(center.get_positions() - amplitude * vector)
    plus.set_positions(center.get_positions() + amplitude * vector)
    write(str(path), [minus, center, plus], format=fmt)
    return path


def _parse_reaction_coordinates(data: Mapping[str, Any], *, one_based: bool) -> dict[str, Any]:
    return {
        "forming_bonds": _parse_bond_list(data.get("forming_bonds", []), one_based=one_based, field_name="reaction_coordinates.forming_bonds"),
        "weakening_bonds": _parse_bond_list(data.get("weakening_bonds", []), one_based=one_based, field_name="reaction_coordinates.weakening_bonds"),
        "monitor_bonds": _parse_bond_list(data.get("monitor_bonds", []), one_based=one_based, field_name="reaction_coordinates.monitor_bonds"),
    }


def _parse_dimer_vector(data: Mapping[str, Any], *, one_based: bool) -> dict[str, Any]:
    parsed = dict(data)
    if "atoms" in parsed:
        parsed["atoms"] = parse_atom_selector(parsed["atoms"], one_based=one_based, field_name="dimer_vector.atoms")
    return parsed


def _parse_bond_list(value: Any, *, one_based: bool, field_name: str) -> list[tuple[int, int]]:
    bonds: list[tuple[int, int]] = []
    for index, pair in enumerate(value or []):
        if not isinstance(pair, Sequence) or isinstance(pair, (str, bytes)) or len(pair) != 2:
            raise ValueError(f"{field_name}[{index}] must be a two-index list such as [578, 594].")
        parsed = parse_atom_indices(list(pair), one_based=one_based, field_name=f"{field_name}[{index}]")
        bonds.append((parsed[0], parsed[1]))
    return bonds


def _resolve_active_atoms(spec: TsGuessSpec, n_atoms: int) -> list[int]:
    if spec.active_atoms:
        _validate_indices(spec.active_atoms, n_atoms, "active_atoms")
        return list(spec.active_atoms)
    return list(range(n_atoms))


def _validate_indices(indices: Sequence[int], n_atoms: int, field_name: str) -> None:
    bad = [index for index in indices if index < 0 or index >= n_atoms]
    if bad:
        raise ValueError(f"{field_name} contains atom indices out of range for {n_atoms} atoms: {bad}")


def _distance(positions, i: int, j: int, cell, pbc) -> float:
    return float(np.linalg.norm(mic_displacement(positions[i], positions[j], cell, pbc)))


def _min_pair_distance(atoms, indices: Sequence[int]) -> float:
    selected = list(indices)
    if len(selected) < 2:
        return float("nan")
    positions = atoms.get_positions()
    cell = atoms.cell.array
    pbc = atoms.get_pbc()
    minimum = float("inf")
    for offset, i in enumerate(selected):
        for j in selected[offset + 1 :]:
            minimum = min(minimum, _distance(positions, i, j, cell, pbc))
    return minimum


def _range(value: Sequence[Any], field_name: str) -> tuple[float, float]:
    if len(value) != 2:
        raise ValueError(f"{field_name} must contain [lower, upper].")
    lower, upper = float(value[0]), float(value[1])
    if upper < lower:
        raise ValueError(f"{field_name} upper bound must be >= lower bound.")
    return lower, upper


def _range_penalty(value: float, lower: float, upper: float) -> float:
    width = max(upper - lower, 1.0e-6)
    if value < lower:
        return ((lower - value) / width) ** 2
    if value > upper:
        return ((value - upper) / width) ** 2
    return 0.0


def _bond_metric_name(prefix: str, pair: tuple[int, int], one_based: bool) -> str:
    return f"{prefix}_{_display_index(pair[0], one_based)}_{_display_index(pair[1], one_based)}"


def _display_index(index: int, one_based: bool) -> int:
    return index + 1 if one_based else index


def _format_indices(indices: Sequence[int], one_based: bool) -> str:
    return ",".join(str(_display_index(index, one_based)) for index in indices)


def _fraction_tag(fraction: float) -> str:
    return f"t{fraction:.3f}".replace(".", "p")


def _normalize_fractions(values: Any) -> list[float]:
    if values is None:
        return []
    if isinstance(values, (int, float)):
        values = [values]
    fractions = [float(value) for value in values]
    for value in fractions:
        if value < 0.0 or value > 1.0:
            raise ValueError(f"Fractions must be in [0, 1], got {value}.")
    return fractions


def _sorted_unique(values: Sequence[float]) -> list[float]:
    output: list[float] = []
    for value in sorted(float(item) for item in values):
        if not any(abs(value - existing) < 1.0e-12 for existing in output):
            output.append(value)
    return output


def _prefer_fraction(spec: TsGuessSpec, fallback: float) -> float:
    value = spec.selection.get("prefer_fraction")
    return float(value) if value is not None else fallback


def _load_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("YAML config needs PyYAML. Use a .json config or install PyYAML.") from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def _atom_indices_1_based_from_mapping(data: Mapping[str, Any]) -> bool:
    for key in ("atom_indices_1_based", "atoms_1_based", "one_based", "1_based"):
        if key in data:
            return _parse_bool(data[key], key)
    return False


def _parse_bool(value: Any, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "on"}:
            return True
        if lowered in {"false", "no", "0", "off", ""}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"{field_name} must be a boolean value, got {value!r}.")


def _first_mapping(data: Mapping[str, Any], *keys: str) -> Mapping[str, Any]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, Mapping):
            return value
    return {}


def _resolve_path(value: Union[str, Path], base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


if __name__ == "__main__":
    raise SystemExit(main())
