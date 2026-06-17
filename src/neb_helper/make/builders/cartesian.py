from __future__ import annotations

from ..pbc import mic_displacement


def build_mic_linear(initial, final, n_images: int):
    pos_i = initial.get_positions()
    displacement = mic_displacement(
        pos_i,
        final.get_positions(),
        initial.cell.array,
        initial.get_pbc(),
    )

    images = []
    total = n_images + 2
    for index in range(total):
        fraction = index / (total - 1)
        image = initial.copy()
        image.set_positions(pos_i + fraction * displacement)
        images.append(image)
    return images
