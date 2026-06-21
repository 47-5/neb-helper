from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np
from ase.io import write

from neb_helper.common.geometry import assert_compatible_pair, interpolate_mic, mic_displacement
from neb_helper.make.atom_selection import parse_atom_indices, parse_atom_selector
from neb_helper.make.dimer_vector import format_dimer_vector, mask_vector, resolve_atom_indices

from .band_io import read_image_map, require_images


@dataclass(frozen=True)
class DimerGuessFile:
    fraction: float
    structure_path: Path
    vector_path: Path


@dataclass(frozen=True)
class DimerGuessResult:
    output_dir: Path
    left_index: int
    right_index: int
    selected_indices: list[int]
    raw_norm: float
    files: list[DimerGuessFile]


@dataclass(frozen=True)
class DimerGuessConfig:
    source: Path
    left_index: int
    right_index: int
    fractions: list[float]
    prefix: str = "image"
    suffix: str = ".xyz"
    output_dir: Optional[Path] = None
    structure_name: Optional[str] = None
    vector_name: Optional[str] = None
    structure_format: str = "xyz"
    atoms: Optional[Union[str, list[int]]] = "active"
    active_atoms: list[int] = field(default_factory=list)
    frozen_atoms: list[int] = field(default_factory=list)
    zero_frozen_atoms: bool = True
    normalize: bool = True
    scale: float = 1.0


def load_dimer_guess_config(path: Union[str, Path]) -> DimerGuessConfig:
    path = Path(path)
    data = _load_mapping(path)
    return dimer_guess_config_from_mapping(data, base_dir=path.parent)


def dimer_guess_config_from_mapping(data: Mapping[str, Any], base_dir: Union[str, Path] = ".") -> DimerGuessConfig:
    base_dir = Path(base_dir)
    one_based = _atom_indices_1_based_from_mapping(data)
    if "between" not in data:
        raise ValueError("DIMER config must define between: [LEFT, RIGHT].")
    between = list(data["between"])
    if len(between) != 2:
        raise ValueError("DIMER config field between must contain exactly two image indices.")

    fractions_value = data.get("fractions", data.get("fraction", [0.5]))
    fractions = _normalize_fractions(_as_list(fractions_value))
    source = _resolve_path(data.get("source", "."), base_dir)
    output_dir = data.get("output_dir")
    structure_format = data.get("structure_format", data.get("format", "xyz"))

    return DimerGuessConfig(
        source=source,
        left_index=int(between[0]),
        right_index=int(between[1]),
        fractions=fractions,
        prefix=str(data.get("prefix", "image")),
        suffix=str(data.get("suffix", ".xyz")),
        output_dir=_resolve_path(output_dir, base_dir) if output_dir else None,
        structure_name=data.get("structure_name"),
        vector_name=data.get("vector_name"),
        structure_format=str(structure_format),
        atoms=parse_atom_selector(
            data.get("atoms", "active"), one_based=one_based, field_name="atoms"
        ),
        active_atoms=parse_atom_indices(
            data.get("active_atoms", []), one_based=one_based, field_name="active_atoms"
        ),
        frozen_atoms=parse_atom_indices(
            data.get("frozen_atoms", []), one_based=one_based, field_name="frozen_atoms"
        ),
        zero_frozen_atoms=_parse_bool(data.get("zero_frozen_atoms", True), "zero_frozen_atoms"),
        normalize=_parse_bool(data.get("normalize", True), "normalize"),
        scale=float(data.get("scale", 1.0)),
    )


def generate_dimer_guess(
    *,
    source: Union[str, Path],
    left_index: int,
    right_index: int,
    fractions: Sequence[float] = (0.5,),
    prefix: str = "image",
    suffix: str = ".xyz",
    output_dir: Optional[Union[str, Path]] = None,
    structure_name: Optional[str] = None,
    vector_name: Optional[str] = None,
    structure_format: str = "xyz",
    atoms: Optional[Union[str, Sequence[int]]] = "active",
    active_atoms: Sequence[int] = (),
    frozen_atoms: Sequence[int] = (),
    zero_frozen_atoms: bool = True,
    normalize: bool = True,
    scale: float = 1.0,
) -> DimerGuessResult:
    fractions = _normalize_fractions(fractions)
    if len(fractions) > 1 and (structure_name or vector_name):
        raise ValueError(
            "Custom structure_name/vector_name are only supported for one fraction. "
            "Use the default fraction-tagged names for multiple guesses."
        )
    if left_index == right_index:
        raise ValueError("DIMER guess needs two distinct image indices.")

    image_map = read_image_map(source, prefix=prefix, suffix=suffix)
    left, right = require_images(image_map, [left_index, right_index])
    assert_compatible_pair(
        left,
        right,
        left_label=f"Image {left_index}",
        right_label=f"Image {right_index}",
    )

    output_dir = Path(output_dir) if output_dir else Path(source) / _default_output_dir(left_index, right_index)
    output_dir.mkdir(parents=True, exist_ok=True)

    displacement = mic_displacement(
        left.get_positions(),
        right.get_positions(),
        left.cell.array,
        left.get_pbc(),
    )
    selected_indices = resolve_atom_indices(
        len(left),
        atoms=atoms,
        active_atoms=active_atoms,
        frozen_atoms=frozen_atoms,
        zero_frozen_atoms=zero_frozen_atoms,
    )
    vector = mask_vector(displacement, selected_indices)
    raw_norm = float(np.linalg.norm(vector))
    if raw_norm <= 0.0:
        raise ValueError(
            "DIMER_VECTOR is zero after atom selection. "
            "Use --atoms all, provide --active-atoms, or use --no-zero-frozen-atoms."
        )
    if normalize:
        vector = vector / raw_norm
    vector = vector * float(scale)

    files: list[DimerGuessFile] = []
    for fraction in fractions:
        structure = interpolate_pair(left, right, fraction)
        structure_path, vector_path = _output_paths(
            output_dir,
            fraction=fraction,
            n_fractions=len(fractions),
            structure_name=structure_name,
            vector_name=vector_name,
        )
        write(str(structure_path), structure, format=structure_format)
        vector_path.write_text(
            format_dimer_vector(
                vector,
                comments=[
                    "Generated by neb-helper.",
                    "Place this block inside MOTION / GEO_OPT / TRANSITION_STATE / DIMER.",
                    f"Direction: MIC/Cartesian({prefix}_{right_index:03d} - {prefix}_{left_index:03d}).",
                    f"TS guess fraction: {fraction:.6g} from {prefix}_{left_index:03d} to {prefix}_{right_index:03d}.",
                    f"Selected atom count: {len(selected_indices)} of {len(left)}.",
                    f"Raw selected direction norm: {raw_norm:.12g} A.",
                ],
            ),
            encoding="utf-8",
        )
        files.append(
            DimerGuessFile(
                fraction=fraction,
                structure_path=structure_path,
                vector_path=vector_path,
            )
        )

    return DimerGuessResult(
        output_dir=output_dir,
        left_index=left_index,
        right_index=right_index,
        selected_indices=selected_indices,
        raw_norm=raw_norm,
        files=files,
    )


def generate_dimer_guess_from_config(config: Union[DimerGuessConfig, str, Path]) -> DimerGuessResult:
    if isinstance(config, (str, Path)):
        config = load_dimer_guess_config(config)
    return generate_dimer_guess(
        source=config.source,
        left_index=config.left_index,
        right_index=config.right_index,
        fractions=config.fractions,
        prefix=config.prefix,
        suffix=config.suffix,
        output_dir=config.output_dir,
        structure_name=config.structure_name,
        vector_name=config.vector_name,
        structure_format=config.structure_format,
        atoms=config.atoms,
        active_atoms=config.active_atoms,
        frozen_atoms=config.frozen_atoms,
        zero_frozen_atoms=config.zero_frozen_atoms,
        normalize=config.normalize,
        scale=config.scale,
    )


def interpolate_pair(left, right, fraction: float):
    if fraction < 0.0 or fraction > 1.0:
        raise ValueError(f"DIMER guess fraction must be in [0, 1], got {fraction}.")
    assert_compatible_pair(left, right)
    return interpolate_mic(left, right, fraction)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.config:
        result = generate_dimer_guess_from_config(args.config)
    else:
        if args.between is None:
            parser.error("--between LEFT RIGHT is required unless a YAML/JSON config file is provided.")
        atoms = parse_atom_selector(
            args.atoms,
            one_based=args.atom_indices_1_based,
            field_name="--atoms",
        )
        active_atoms = parse_atom_indices(
            args.active_atoms,
            one_based=args.atom_indices_1_based,
            field_name="--active-atoms",
        )
        frozen_atoms = parse_atom_indices(
            args.frozen_atoms,
            one_based=args.atom_indices_1_based,
            field_name="--frozen-atoms",
        )

        result = generate_dimer_guess(
            source=args.source,
            left_index=args.between[0],
            right_index=args.between[1],
            fractions=args.fractions or [0.5],
            prefix=args.prefix,
            suffix=args.suffix,
            output_dir=args.output_dir,
            structure_name=args.structure_name,
            vector_name=args.vector_name,
            structure_format=args.structure_format,
            atoms=atoms,
            active_atoms=active_atoms,
            frozen_atoms=frozen_atoms,
            zero_frozen_atoms=args.zero_frozen_atoms,
            normalize=args.normalize,
            scale=args.scale,
        )

    print(
        f"Wrote {len(result.files)} DIMER guess(es) from "
        f"image {result.left_index} -> {result.right_index} to {result.output_dir}"
    )
    print(
        f"Selected {len(result.selected_indices)} atom(s); "
        f"raw direction norm {result.raw_norm:.6g} A"
    )
    for item in result.files:
        print(f"fraction {item.fraction:.6g}: {item.structure_path}")
        print(f"fraction {item.fraction:.6g}: {item.vector_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neb-helper dimer",
        description="Generate DIMER initial structures and CP2K DIMER_VECTOR blocks from an existing NEB image pair.",
    )
    parser.add_argument("config", nargs="?", help="Optional YAML/JSON config file. CLI flags are used when omitted.")
    parser.add_argument("--source", default=".", help="Directory containing image_000.xyz-style files.")
    parser.add_argument("--prefix", default="image", help="Image filename prefix before the numeric index.")
    parser.add_argument("--suffix", default=".xyz", help="Image filename suffix, with or without the leading dot.")
    parser.add_argument(
        "--between",
        nargs=2,
        type=int,
        metavar=("LEFT", "RIGHT"),
        help="0-based image indices defining the DIMER direction LEFT -> RIGHT.",
    )
    parser.add_argument(
        "--fraction",
        dest="fractions",
        action="append",
        type=float,
        help="Interpolation fraction from LEFT to RIGHT. Repeat for multiple guesses. Default: 0.5.",
    )
    parser.add_argument("--output-dir", help="Output directory. Default: SOURCE/dimer_guess_LEFT_RIGHT.")
    parser.add_argument("--structure-name", help="Output structure filename for a single fraction. Default: ts_guess.xyz.")
    parser.add_argument("--vector-name", help="Output DIMER_VECTOR filename for a single fraction. Default: dimer_vector.inc.")
    parser.add_argument("--format", dest="structure_format", default="xyz", help="ASE write format for structures. Default: xyz.")
    parser.add_argument(
        "--atoms",
        default="active",
        help="Atoms used in DIMER_VECTOR: active, all, or an index selection such as 10,12,13.",
    )
    parser.add_argument("--active-atoms", default="", help="Active atom indices used when --atoms active.")
    parser.add_argument("--frozen-atoms", default="", help="Frozen atom indices to zero in the vector by default.")
    parser.add_argument(
        "--atom-indices-1-based",
        action="store_true",
        help="Interpret atom selections as 1-based instead of Python/ASE 0-based.",
    )
    parser.add_argument(
        "--zero-frozen-atoms",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Zero frozen atom components in the DIMER_VECTOR. Default: true.",
    )
    parser.add_argument(
        "--normalize",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Normalize the selected DIMER_VECTOR before applying --scale. Default: true.",
    )
    parser.add_argument("--scale", type=float, default=1.0, help="Scale applied after optional normalization.")
    return parser


def _normalize_fractions(fractions: Sequence[float]) -> list[float]:
    values = [float(value) for value in fractions]
    if not values:
        raise ValueError("At least one DIMER guess fraction is required.")
    for value in values:
        if value < 0.0 or value > 1.0:
            raise ValueError(f"DIMER guess fraction must be in [0, 1], got {value}.")
    return values


def _default_output_dir(left_index: int, right_index: int) -> str:
    return f"dimer_guess_{left_index:03d}_{right_index:03d}"


def _output_paths(
    output_dir: Path,
    *,
    fraction: float,
    n_fractions: int,
    structure_name: Optional[str],
    vector_name: Optional[str],
) -> tuple[Path, Path]:
    if n_fractions == 1:
        return (
            output_dir / (structure_name or "ts_guess.xyz"),
            output_dir / (vector_name or "dimer_vector.inc"),
        )
    tag = _fraction_tag(fraction)
    return output_dir / f"ts_guess_{tag}.xyz", output_dir / f"dimer_vector_{tag}.inc"


def _fraction_tag(fraction: float) -> str:
    return f"f{fraction:.3f}".replace(".", "p")


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


def _resolve_path(value: Union[str, Path], base_dir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


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


if __name__ == "__main__":
    raise SystemExit(main())
