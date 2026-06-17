from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Union

from .atom_selection import parse_atom_indices, parse_atom_selector
from .specs import (
    BackgroundSpec,
    CalculatorSpec,
    DimerVectorSpec,
    EndpointReorderSpec,
    NebRelaxSpec,
    OutputSpec,
    PBCSpec,
    PathSpec,
    RelaxSpec,
    TorsionSpec,
    WaypointSpec,
)


def load_config(path: Union[str, Path]) -> PathSpec:
    path = Path(path)
    data = _load_mapping(path)
    return path_spec_from_mapping(data, base_dir=path.parent)


def path_spec_from_mapping(data: Dict[str, Any], base_dir: Union[str, Path] = ".") -> PathSpec:
    base_dir = Path(base_dir)
    background = BackgroundSpec(**data.get("background", {}))
    endpoint_reorder = _endpoint_reorder_spec_from_mapping(
        data.get("endpoint_reorder", {}), base_dir
    )
    pbc = PBCSpec(**data.get("pbc", {}))
    output = OutputSpec(**data.get("output", {}))
    relax = _relax_spec_from_mapping(data.get("relax", {}))
    neb_relax = _neb_relax_spec_from_mapping(data.get("neb_relax", {}))
    atom_indices_1_based = _atom_indices_1_based_from_mapping(data)
    dimer_vector = _dimer_vector_spec_from_mapping(
        data.get("dimer_vector", {}), one_based=atom_indices_1_based
    )

    waypoints = [
        _waypoint_spec_from_mapping(item, base_dir, one_based=atom_indices_1_based)
        for item in data.get("waypoints", [])
    ]
    torsions = [
        _torsion_spec_from_mapping(item, one_based=atom_indices_1_based)
        for item in data.get("torsions", [])
    ]

    return PathSpec(
        initial=_resolve_path(data["initial"], base_dir),
        final=_resolve_path(data["final"], base_dir),
        n_images=int(data.get("n_images", 3)),
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
        endpoint_reorder=endpoint_reorder,
        background=background,
        waypoints=waypoints,
        torsions=torsions,
        relax=relax,
        neb_relax=neb_relax,
        dimer_vector=dimer_vector,
        pbc=pbc,
        output=output,
    )


def _endpoint_reorder_spec_from_mapping(
    data: Dict[str, Any], base_dir: Path
) -> EndpointReorderSpec:
    parsed = dict(data)
    if "enabled" in parsed:
        parsed["enabled"] = _parse_bool(parsed["enabled"], "endpoint_reorder.enabled")
    if "copy_reference_cell" in parsed:
        parsed["copy_reference_cell"] = _parse_bool(
            parsed["copy_reference_cell"], "endpoint_reorder.copy_reference_cell"
        )
    if "write_reordered_final" in parsed and "output" not in parsed:
        parsed["output"] = parsed.pop("write_reordered_final")
    if "write_mapping" in parsed and "mapping" not in parsed:
        parsed["mapping"] = parsed.pop("write_mapping")
    if parsed.get("output"):
        parsed["output"] = _resolve_path(parsed["output"], base_dir)
    if parsed.get("mapping"):
        parsed["mapping"] = _resolve_path(parsed["mapping"], base_dir)
    return EndpointReorderSpec(**parsed)


def _relax_spec_from_mapping(data: Dict[str, Any]) -> RelaxSpec:
    calculator_data = data.get("calculator", {})
    if isinstance(calculator_data, str):
        calculator_data = {"type": calculator_data}
    calculator = CalculatorSpec(**calculator_data)
    rest = {key: value for key, value in data.items() if key != "calculator"}
    return RelaxSpec(calculator=calculator, **rest)


def _neb_relax_spec_from_mapping(data: Dict[str, Any]) -> NebRelaxSpec:
    calculator_data = data.get("calculator", {})
    if isinstance(calculator_data, str):
        calculator_data = {"type": calculator_data}
    calculator = CalculatorSpec(**calculator_data)
    rest = {key: value for key, value in data.items() if key != "calculator"}
    return NebRelaxSpec(calculator=calculator, **rest)


def _dimer_vector_spec_from_mapping(data: Dict[str, Any], *, one_based: bool) -> DimerVectorSpec:
    parsed = dict(data)
    if "atoms" in parsed:
        parsed["atoms"] = parse_atom_selector(
            parsed["atoms"], one_based=one_based, field_name="dimer_vector.atoms"
        )
    return DimerVectorSpec(**parsed)


def _waypoint_spec_from_mapping(
    data: Dict[str, Any], base_dir: Path, *, one_based: bool
) -> WaypointSpec:
    parsed = _resolve_file_fields(data, base_dir, ["file"])
    if "atoms" in parsed:
        parsed["atoms"] = parse_atom_indices(
            parsed["atoms"], one_based=one_based, field_name="waypoints[].atoms"
        )
    return WaypointSpec(**parsed)


def _torsion_spec_from_mapping(data: Dict[str, Any], *, one_based: bool) -> TorsionSpec:
    parsed = dict(data)
    if "dihedral" in parsed:
        parsed["dihedral"] = parse_atom_indices(
            parsed["dihedral"], one_based=one_based, field_name="torsions[].dihedral"
        )
    if "rotating_group" in parsed:
        parsed["rotating_group"] = parse_atom_indices(
            parsed["rotating_group"],
            one_based=one_based,
            field_name="torsions[].rotating_group",
        )
    return TorsionSpec(**parsed)


def _atom_indices_1_based_from_mapping(data: Dict[str, Any]) -> bool:
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


def _load_mapping(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError(
            "YAML config needs PyYAML. Use a .json config or install PyYAML."
        ) from exc
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"Config file must contain a mapping: {path}")
    return data


def _resolve_file_fields(
    data: Dict[str, Any], base_dir: Path, fields: List[str]
) -> Dict[str, Any]:
    resolved = dict(data)
    for field_name in fields:
        if resolved.get(field_name):
            resolved[field_name] = _resolve_path(resolved[field_name], base_dir)
    return resolved


def _resolve_path(value: str, base_dir: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str((base_dir / path).resolve())
