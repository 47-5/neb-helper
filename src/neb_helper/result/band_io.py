from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from ase.io import read


@dataclass(frozen=True)
class ImageFile:
    index: int
    source_index: int
    path: Path


@dataclass(frozen=True)
class ImageRecord:
    index: int
    source_index: int
    path: Path
    atoms: object


def discover_image_files(
    directory: str | Path,
    *,
    prefix: str | None = "image_",
    suffix: str | None = ".xyz",
) -> list[ImageFile]:
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"NEB image directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"NEB image source is not a directory: {directory}")

    prefix = _normalize_pattern_part(prefix)
    suffix = _normalize_suffix(suffix)
    pattern = _compile_image_pattern(prefix, suffix)
    matched_files: list[tuple[int, Path]] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            matched_files.append((_image_index_from_match(match), path))

    matched_files.sort(key=lambda item: _natural_sort_key(item[1].name))
    if not matched_files:
        raise FileNotFoundError(
            f"No image files matching {_describe_image_pattern(prefix, suffix)} were found in {directory}"
        )
    return [
        ImageFile(index=index, source_index=source_index, path=path)
        for index, (source_index, path) in enumerate(matched_files)
    ]


def read_image_records(
    directory: str | Path,
    *,
    prefix: str | None = "image_",
    suffix: str | None = ".xyz",
) -> dict[int, ImageRecord]:
    return {
        item.index: ImageRecord(
            index=item.index,
            source_index=item.source_index,
            path=item.path,
            atoms=read(str(item.path)),
        )
        for item in discover_image_files(directory, prefix=prefix, suffix=suffix)
    }


def read_image_map(
    directory: str | Path,
    *,
    prefix: str | None = "image_",
    suffix: str | None = ".xyz",
) -> dict[int, object]:
    return {
        index: record.atoms
        for index, record in read_image_records(directory, prefix=prefix, suffix=suffix).items()
    }


def read_image_series(
    directory: str | Path,
    *,
    prefix: str | None = "image_",
    suffix: str | None = ".xyz",
    require_contiguous: bool = True,
) -> list[object]:
    image_map = read_image_map(directory, prefix=prefix, suffix=suffix)
    indices = sorted(image_map)
    if require_contiguous:
        expected = list(range(indices[0], indices[-1] + 1))
        if indices != expected:
            raise ValueError(
                "Image indices are not contiguous: "
                f"found {indices[0]}..{indices[-1]} with gaps."
            )
    return [image_map[index] for index in indices]


def require_images(image_map: Mapping[int, object], indices: Sequence[int]) -> list[object]:
    missing = [index for index in indices if index not in image_map]
    if missing:
        available = ", ".join(str(index) for index in sorted(image_map))
        raise ValueError(f"Missing image indices {missing}; available indices: {available}")
    return [image_map[index] for index in indices]


def require_image_records(
    image_records: Mapping[int, ImageRecord],
    indices: Sequence[int],
) -> list[ImageRecord]:
    missing = [index for index in indices if index not in image_records]
    if missing:
        available = ", ".join(str(index) for index in sorted(image_records))
        raise ValueError(f"Missing image indices {missing}; available indices: {available}")
    return [image_records[index] for index in indices]


def _compile_image_pattern(prefix: str | None, suffix: str | None) -> re.Pattern[str]:
    cp2k_prefix_pattern = r".*_" if prefix is None else re.escape(prefix)
    standard_prefix_pattern = r".*(?<!\d)" if prefix is None else re.escape(prefix)
    suffix_pattern = r".*" if suffix is None else re.escape(suffix)
    return re.compile(
        rf"^(?:"
        rf"{cp2k_prefix_pattern}(?P<cp2k_index>\d+)-\d+{suffix_pattern}"
        rf"|"
        rf"{standard_prefix_pattern}(?P<standard_index>\d+){suffix_pattern}"
        rf")$",
        flags=re.IGNORECASE,
    )


def _image_index_from_match(match: re.Match[str]) -> int:
    value = match.group("cp2k_index") or match.group("standard_index")
    if value is None:
        raise ValueError(f"Could not parse image index from {match.string!r}.")
    return int(value)


def _natural_sort_key(name: str) -> tuple[tuple[int, object], ...]:
    parts: list[tuple[int, object]] = []
    for part in re.split(r"(\d+)", name.casefold()):
        if part.isdigit():
            parts.append((1, int(part)))
        elif part:
            parts.append((0, part))
    return tuple(parts)


def _normalize_pattern_part(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in {"", "none", "null"}:
        return None
    return text


def _normalize_suffix(suffix: str | None) -> str | None:
    suffix = _normalize_pattern_part(suffix)
    if suffix is None:
        return None
    return suffix if suffix.startswith(".") else f".{suffix}"


def _describe_image_pattern(prefix: str | None, suffix: str | None) -> str:
    prefix_text = "*" if prefix is None else prefix
    suffix_text = "*" if suffix is None else suffix
    if prefix is None and suffix is None:
        return "*<index>*"
    if prefix is None:
        return f"*<index>{suffix_text} or CP2K-style *<index>-N{suffix_text}"
    if suffix is None:
        return f"{prefix_text}<index>* or CP2K-style {prefix_text}<index>-N*"
    return f"{prefix_text}<index>{suffix_text} or CP2K-style {prefix_text}<index>-N{suffix_text}"