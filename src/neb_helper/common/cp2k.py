from __future__ import annotations

from pathlib import Path
from typing import Sequence


def write_band_file(
    path: str | Path,
    *,
    prefix: str = "image",
    n_images: int | None = None,
    filenames: Sequence[str] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if filenames is None:
        if n_images is None:
            raise ValueError("write_band_file needs either filenames or n_images.")
        filenames = [f"{prefix}_{index:03d}.xyz" for index in range(n_images)]

    with path.open("w", encoding="utf-8") as handle:
        for filename in filenames:
            handle.write("&REPLICA\n")
            handle.write(f"  COORD_FILE_NAME {filename}\n")
            handle.write("&END REPLICA\n")
    return path
