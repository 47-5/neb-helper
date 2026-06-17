from __future__ import annotations

from pathlib import Path

from ase.io import write
from ase.io.vasp import write_vasp

from ..pbc import outside_fractional_span, sanitize_image


def write_outputs(images, spec):
    output_dir = Path(spec.output.directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_images = []
    for index, image in enumerate(images):
        output_image = image.copy()
        output_image.set_cell(images[0].cell, scale_atoms=False)
        output_image.set_pbc(images[0].get_pbc())
        if spec.pbc.output_wrap:
            sanitize_image(
                output_image,
                ref_cell=images[0].cell,
                ref_pbc=images[0].get_pbc(),
                eps=spec.pbc.eps,
            )
        _enforce_inside_box(output_image, spec)
        output_images.append(output_image)

        xyz_path = output_dir / f"{spec.output.images_prefix}_{index:03d}.xyz"
        write(str(xyz_path), output_image, format="xyz")
        if spec.output.write_vasp:
            vasp_dir = output_dir / f"{index:02d}"
            vasp_dir.mkdir(parents=True, exist_ok=True)
            write_vasp(str(vasp_dir / "POSCAR"), output_image)

    if spec.output.trajectory:
        write(str(output_dir / spec.output.trajectory), output_images, format="xyz")

    if spec.output.cp2k_band:
        _write_band_file(output_dir / spec.output.cp2k_band, spec, len(output_images))
    return output_images


def _write_band_file(path: Path, spec, n_images: int) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for index in range(n_images):
            filename = f"{spec.output.images_prefix}_{index:03d}.xyz"
            handle.write("&REPLICA\n")
            handle.write(f"  COORD_FILE_NAME {filename}\n")
            handle.write("&END REPLICA\n")


def _enforce_inside_box(atoms, spec) -> None:
    min_scaled, max_scaled, outside = outside_fractional_span(atoms, tol=spec.pbc.tol)
    if outside and spec.pbc.fail_if_outside:
        state = "after output wrap" if spec.pbc.output_wrap else "with output_wrap disabled"
        raise ValueError(
            f"Image has atoms outside the periodic box {state}: "
            f"min_scaled={min_scaled:.12g}, max_scaled={max_scaled:.12g}"
        )
