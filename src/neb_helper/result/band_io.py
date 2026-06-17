from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from ase.io import read


@dataclass(frozen=True)
class ImageFile:
    index: int
    path: Path


def discover_image_files(
    directory: str | Path,
    *,
    prefix: str = "image",
    suffix: str = ".xyz",
) -> list[ImageFile]:
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"NEB image directory does not exist: {directory}")
    if not directory.is_dir():
        raise NotADirectoryError(f"NEB image source is not a directory: {directory}")

    suffix = _normalize_suffix(suffix)
    pattern = re.compile(
        rf"^{re.escape(prefix)}_(?P<index>\d+){re.escape(suffix)}$",
        flags=re.IGNORECASE,
    )
    image_files: list[ImageFile] = []
    for path in directory.iterdir():
        if not path.is_file():
            continue
        match = pattern.match(path.name)
        if match:
            image_files.append(ImageFile(index=int(match.group("index")), path=path))

    image_files.sort(key=lambda item: item.index)
    if not image_files:
        raise FileNotFoundError(
            f"No files matching {prefix}_*{suffix} were found in {directory}"
        )
    _validate_unique_indices(image_files)
    return image_files


def read_image_map(
    directory: str | Path,
    *,
    prefix: str = "image",
    suffix: str = ".xyz",
) -> dict[int, object]:
    return {
        item.index: read(str(item.path))
        for item in discover_image_files(directory, prefix=prefix, suffix=suffix)
    }


def read_image_series(
    directory: str | Path,
    *,
    prefix: str = "image",
    suffix: str = ".xyz",
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


def _normalize_suffix(suffix: str) -> str:
    if not suffix:
        raise ValueError("Image file suffix cannot be empty.")
    return suffix if suffix.startswith(".") else f".{suffix}"


def _validate_unique_indices(image_files: Sequence[ImageFile]) -> None:
    seen: set[int] = set()
    duplicates: set[int] = set()
    for image_file in image_files:
        if image_file.index in seen:
            duplicates.add(image_file.index)
        seen.add(image_file.index)
    if duplicates:
        raise ValueError(f"Duplicate image indices found: {sorted(duplicates)}")
