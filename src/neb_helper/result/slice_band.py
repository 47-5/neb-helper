from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
from ase.io import write

from .band_io import read_image_map, require_images


@dataclass(frozen=True)
class SliceImageRecord:
    output_index: int
    source_left_index: int
    source_right_index: int
    segment_fraction: float
    source_path_fraction: float
    path_distance_A: float


@dataclass(frozen=True)
class SliceBandResult:
    output_dir: Path
    source_indices: list[int]
    output_images: list[object]
    records: list[SliceImageRecord]
    band_path: Path | None
    trajectory_path: Path | None
    source_map_path: Path | None


def slice_band(
    *,
    source: str | Path,
    start_index: int,
    end_index: int,
    prefix: str = "image",
    suffix: str = ".xyz",
    output_dir: str | Path | None = None,
    output_prefix: str = "image",
    output_format: str = "xyz",
    resample_n_images: int | None = None,
    trajectory: str | None = "neb_sliced_path.xyz",
    band_file: str | None = "band.txt",
    source_map: str | None = "source_map.csv",
) -> SliceBandResult:
    source_indices = _inclusive_range(start_index, end_index)
    image_map = read_image_map(source, prefix=prefix, suffix=suffix)
    source_images = require_images(image_map, source_indices)
    _validate_images(source_images, source_indices)

    output_dir = Path(output_dir) if output_dir else Path(source) / _default_output_dir(start_index, end_index)
    output_dir.mkdir(parents=True, exist_ok=True)

    if resample_n_images is None:
        output_images = [image.copy() for image in source_images]
        records = _copy_records(source_images, source_indices)
    else:
        if resample_n_images < 0:
            raise ValueError(f"--resample-n-images must be >= 0, got {resample_n_images}.")
        output_images, records = _resample_images(
            source_images,
            source_indices,
            n_output_images=resample_n_images + 2,
        )

    for output_index, image in enumerate(output_images):
        path = output_dir / f"{output_prefix}_{output_index:03d}.xyz"
        write(str(path), image, format=output_format)

    trajectory_path = None
    if trajectory:
        trajectory_path = output_dir / trajectory
        write(str(trajectory_path), output_images, format=output_format)

    band_path = None
    if band_file:
        band_path = output_dir / band_file
        _write_band_file(band_path, output_prefix, len(output_images))

    source_map_path = None
    if source_map:
        source_map_path = output_dir / source_map
        _write_source_map(source_map_path, records)

    return SliceBandResult(
        output_dir=output_dir,
        source_indices=source_indices,
        output_images=output_images,
        records=records,
        band_path=band_path,
        trajectory_path=trajectory_path,
        source_map_path=source_map_path,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = slice_band(
        source=args.source,
        start_index=args.range[0],
        end_index=args.range[1],
        prefix=args.prefix,
        suffix=args.suffix,
        output_dir=args.output_dir,
        output_prefix=args.output_prefix,
        output_format=args.output_format,
        resample_n_images=args.resample_n_images,
        trajectory=args.trajectory,
        band_file=args.band_file,
        source_map=args.source_map,
    )
    print(
        f"Wrote {len(result.output_images)} sliced image(s) from "
        f"{result.source_indices[0]} -> {result.source_indices[-1]} to {result.output_dir}"
    )
    if result.band_path:
        print(f"Wrote CP2K band file: {result.band_path}")
    if result.trajectory_path:
        print(f"Wrote trajectory: {result.trajectory_path}")
    if result.source_map_path:
        print(f"Wrote source map: {result.source_map_path}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neb-helper slice",
        description="Crop and optionally resample a segment of an existing NEB image band.",
    )
    parser.add_argument("--source", default=".", help="Directory containing image_000.xyz-style files.")
    parser.add_argument("--prefix", default="image", help="Input image filename prefix before the numeric index.")
    parser.add_argument("--suffix", default=".xyz", help="Input image filename suffix, with or without the leading dot.")
    parser.add_argument(
        "--range",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        required=True,
        help="Inclusive 0-based source image range. START may be greater than END to reverse the path.",
    )
    parser.add_argument("--output-dir", help="Output directory. Default: SOURCE/slice_START_END.")
    parser.add_argument("--output-prefix", default="image", help="Output image prefix. Default: image.")
    parser.add_argument("--format", dest="output_format", default="xyz", help="ASE output format. Default: xyz.")
    parser.add_argument(
        "--resample-n-images",
        type=int,
        help="Number of intermediate images in the resampled slice. Omit to copy source images exactly.",
    )
    parser.add_argument(
        "--trajectory",
        default="neb_sliced_path.xyz",
        help="Multi-frame trajectory filename. Use an empty string to disable. Default: neb_sliced_path.xyz.",
    )
    parser.add_argument(
        "--band-file",
        default="band.txt",
        help="CP2K BAND replica snippet filename. Use an empty string to disable. Default: band.txt.",
    )
    parser.add_argument(
        "--source-map",
        default="source_map.csv",
        help="CSV mapping output images back to source positions. Use an empty string to disable.",
    )
    return parser


def _inclusive_range(start: int, end: int) -> list[int]:
    step = 1 if end >= start else -1
    return list(range(start, end + step, step))


def _validate_images(images: Sequence[object], source_indices: Sequence[int]) -> None:
    if not images:
        raise ValueError("At least one source image is required.")
    reference = images[0]
    symbols = reference.get_chemical_symbols()
    pbc = reference.get_pbc()
    cell = reference.cell.array
    for image, index in zip(images[1:], source_indices[1:]):
        if len(image) != len(reference):
            raise ValueError(f"Image {index} has {len(image)} atoms; expected {len(reference)}.")
        if image.get_chemical_symbols() != symbols:
            raise ValueError(f"Image {index} uses a different atom order.")
        if not np.array_equal(image.get_pbc(), pbc):
            raise ValueError(f"Image {index} uses different PBC flags.")
        if np.any(pbc) and not np.allclose(image.cell.array, cell, atol=1.0e-6):
            raise ValueError(f"Image {index} uses a different cell.")
    if np.any(pbc) and abs(float(np.linalg.det(cell))) < 1.0e-12:
        raise ValueError("PBC images require a non-singular cell for MIC resampling.")


def _copy_records(source_images: Sequence[object], source_indices: Sequence[int]) -> list[SliceImageRecord]:
    n_images = len(source_indices)
    if n_images == 1:
        cumulative = np.asarray([0.0], dtype=float)
    else:
        cumulative = np.concatenate(([0.0], np.cumsum(_segment_lengths(source_images))))
    total_length = float(cumulative[-1]) if len(cumulative) else 0.0
    denominator = max(1, n_images - 1)

    records: list[SliceImageRecord] = []
    for output_index, source_index in enumerate(source_indices):
        if total_length > 0.0:
            source_path_fraction = float(cumulative[output_index]) / total_length
        else:
            source_path_fraction = output_index / denominator
        records.append(
            SliceImageRecord(
                output_index=output_index,
                source_left_index=source_index,
                source_right_index=source_index,
                segment_fraction=0.0,
                source_path_fraction=source_path_fraction,
                path_distance_A=float(cumulative[output_index]),
            )
        )
    return records


def _resample_images(
    source_images: Sequence[object],
    source_indices: Sequence[int],
    *,
    n_output_images: int,
) -> tuple[list[object], list[SliceImageRecord]]:
    if n_output_images < 2:
        raise ValueError("A resampled slice must contain at least two endpoint images.")
    if len(source_images) == 1:
        raise ValueError("Cannot resample a one-image slice into multiple images.")

    segment_lengths = _segment_lengths(source_images)
    cumulative = np.concatenate(([0.0], np.cumsum(segment_lengths)))
    total_length = float(cumulative[-1])
    if total_length <= 0.0:
        raise ValueError("Cannot resample a zero-length path segment.")

    targets = np.linspace(0.0, total_length, n_output_images)
    output_images: list[object] = []
    records: list[SliceImageRecord] = []
    for output_index, target in enumerate(targets):
        segment_index = _target_segment(cumulative, float(target))
        left = source_images[segment_index]
        right = source_images[segment_index + 1]
        segment_start = float(cumulative[segment_index])
        segment_length = float(segment_lengths[segment_index])
        fraction = 0.0 if segment_length <= 0.0 else (float(target) - segment_start) / segment_length
        fraction = min(1.0, max(0.0, fraction))

        displacement = _mic_displacement(
            left.get_positions(),
            right.get_positions(),
            left.cell.array,
            left.get_pbc(),
        )
        image = left.copy()
        image.set_cell(source_images[0].cell, scale_atoms=False)
        image.set_pbc(source_images[0].get_pbc())
        image.set_positions(left.get_positions() + fraction * displacement)
        output_images.append(image)
        records.append(
            SliceImageRecord(
                output_index=output_index,
                source_left_index=source_indices[segment_index],
                source_right_index=source_indices[segment_index + 1],
                segment_fraction=float(fraction),
                source_path_fraction=float(target) / total_length,
                path_distance_A=float(target),
            )
        )
    return output_images, records


def _segment_lengths(images: Sequence[object]) -> np.ndarray:
    lengths = []
    for left, right in zip(images, images[1:]):
        displacement = _mic_displacement(
            left.get_positions(),
            right.get_positions(),
            left.cell.array,
            left.get_pbc(),
        )
        lengths.append(float(np.sqrt(np.sum(displacement * displacement))))
    return np.asarray(lengths, dtype=float)


def _target_segment(cumulative: np.ndarray, target: float) -> int:
    if np.isclose(target, cumulative[-1]):
        return len(cumulative) - 2
    index = int(np.searchsorted(cumulative, target, side="right") - 1)
    return min(max(index, 0), len(cumulative) - 2)


def _mic_displacement(pos_a, pos_b, cell, pbc) -> np.ndarray:
    pos_a = np.asarray(pos_a, dtype=float)
    pos_b = np.asarray(pos_b, dtype=float)
    pbc = np.asarray(pbc, dtype=bool)
    delta = pos_b - pos_a
    if not np.any(pbc):
        return delta
    cell = np.asarray(cell, dtype=float)
    delta_frac = delta @ np.linalg.inv(cell)
    for axis, is_periodic in enumerate(pbc):
        if is_periodic:
            delta_frac[..., axis] -= np.round(delta_frac[..., axis])
    return delta_frac @ cell


def _write_band_file(path: Path, output_prefix: str, n_images: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(n_images):
            handle.write("&REPLICA\n")
            handle.write(f"  COORD_FILE_NAME {output_prefix}_{index:03d}.xyz\n")
            handle.write("&END REPLICA\n")


def _write_source_map(path: Path, records: Sequence[SliceImageRecord]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "output_index",
                "source_left_index",
                "source_right_index",
                "segment_fraction",
                "source_path_fraction",
                "path_distance_A",
            ],
        )
        writer.writeheader()
        for record in records:
            writer.writerow(
                {
                    "output_index": record.output_index,
                    "source_left_index": record.source_left_index,
                    "source_right_index": record.source_right_index,
                    "segment_fraction": f"{record.segment_fraction:.12g}",
                    "source_path_fraction": f"{record.source_path_fraction:.12g}",
                    "path_distance_A": f"{record.path_distance_A:.12g}",
                }
            )


def _default_output_dir(start_index: int, end_index: int) -> str:
    return f"slice_{start_index:03d}_{end_index:03d}"


if __name__ == "__main__":
    raise SystemExit(main())

