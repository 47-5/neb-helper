from __future__ import annotations

import csv
from pathlib import Path
from typing import Union

from .pbc import max_mic_jump, outside_fractional_span


def collect_diagnostics(images):
    rows = []
    for index, image in enumerate(images):
        min_scaled, max_scaled, outside = outside_fractional_span(image)
        row = {
            "image": index,
            "min_scaled_pbc": min_scaled,
            "max_scaled_pbc": max_scaled,
            "outside_box_before_output_wrap": outside,
            "max_mic_jump_from_previous": "",
        }
        if index > 0:
            row["max_mic_jump_from_previous"] = max_mic_jump(images[index - 1], image)
        rows.append(row)
    return rows


def write_diagnostics(rows, path: Union[str, Path]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
