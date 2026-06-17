from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ase.io import read, write

from .atom_reorder import (
    distance_stats,
    reorder_target_by_reference,
    validate_max_distance,
    write_mapping_csv,
)
from .builders import build_images
from .dimer_vector import write_dimer_vector_from_images
from .pbc import assert_compatible_endpoints, sanitize_image
from .neb_relax import relax_neb_band
from .relax import relax_images
from .validate import collect_diagnostics, write_diagnostics
from .writers import write_outputs


def make_neb_path(spec):
    initial = read(spec.initial)
    final = read(spec.final)

    initial, final, endpoint_reorder = _prepare_endpoints(initial, final, spec)
    assert_compatible_endpoints(initial, final)
    final.set_cell(initial.cell, scale_atoms=False)
    final.set_pbc(initial.get_pbc())

    if spec.pbc.wrap_policy == "always":
        sanitize_image(initial, eps=spec.pbc.eps)
        sanitize_image(final, ref_cell=initial.cell, ref_pbc=initial.get_pbc(), eps=spec.pbc.eps)

    images = build_images(initial, final, spec)
    initial_guess_output_images = _write_initial_guess_if_requested(images, spec)

    images = relax_images(images, spec)
    images = relax_neb_band(images, spec)

    output_dir = Path(spec.output.directory)
    diagnostics = collect_diagnostics(images)
    if spec.output.diagnostics:
        write_diagnostics(diagnostics, output_dir / spec.output.diagnostics)

    output_images = write_outputs(images, spec)
    dimer_vector = _write_dimer_vector_if_requested(output_images, spec)
    return {
        "images": images,
        "output_images": output_images,
        "dimer_vector": dimer_vector,
        "initial_guess_output_images": initial_guess_output_images,
        "diagnostics": diagnostics,
        "output_dir": output_dir,
        "endpoint_reorder": endpoint_reorder,
    }


def _prepare_endpoints(initial, final, spec):
    reorder_spec = spec.endpoint_reorder
    if not reorder_spec.enabled:
        return initial, final, None

    mode = reorder_spec.mode.strip().lower().replace("-", "_")
    if mode == "final_by_initial":
        reference_name = "initial"
        target_name = "final"
        reference = initial
        target = final
    elif mode == "initial_by_final":
        reference_name = "final"
        target_name = "initial"
        reference = final
        target = initial
    else:
        raise ValueError(
            "endpoint_reorder.mode must be 'final_by_initial' or 'initial_by_final', "
            f"got {reorder_spec.mode!r}."
        )

    reordered, distances, target_order = reorder_target_by_reference(reference, target)
    validate_max_distance(
        distances,
        reorder_spec.max_distance,
        field_name="endpoint_reorder.max_distance",
    )
    if reorder_spec.copy_reference_cell:
        reordered.set_cell(reference.cell, scale_atoms=False)
        reordered.set_pbc(reference.get_pbc())

    output_path = None
    if reorder_spec.output:
        output_path = Path(reorder_spec.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write(str(output_path), reordered, format=reorder_spec.output_format)

    mapping_path = None
    if reorder_spec.mapping:
        mapping_path = Path(reorder_spec.mapping)
        write_mapping_csv(
            mapping_path,
            reference.get_chemical_symbols(),
            target_order,
            distances,
        )

    if target_name == "final":
        final = reordered
    else:
        initial = reordered

    stats = distance_stats(distances)
    return initial, final, {
        "mode": mode,
        "reference": reference_name,
        "target": target_name,
        "output": str(output_path) if output_path else None,
        "mapping": str(mapping_path) if mapping_path else None,
        "matched_atoms": stats["count"],
        "max_distance": stats["max"],
        "rms_distance": stats["rms"],
    }


def _write_initial_guess_if_requested(images, spec):
    if not spec.output.save_initial_guess:
        return None
    if not (spec.relax.enabled or spec.neb_relax.enabled):
        return None

    stage_dir = Path(spec.output.initial_guess_directory)
    if not stage_dir.is_absolute():
        stage_dir = Path(spec.output.directory) / stage_dir
    stage_spec = replace(spec, output=replace(spec.output, directory=str(stage_dir)))
    stage_images = [image.copy() for image in images]
    return write_outputs(stage_images, stage_spec)


def _write_dimer_vector_if_requested(images, spec):
    if not spec.dimer_vector.enabled:
        return None
    if not spec.dimer_vector.file:
        return None

    output_dir = Path(spec.output.directory)
    dimer_path = Path(spec.dimer_vector.file)
    if not dimer_path.is_absolute():
        dimer_path = output_dir / dimer_path

    energy_log = None
    if spec.neb_relax.energy_log:
        energy_log = Path(spec.neb_relax.energy_log)
        if not energy_log.is_absolute():
            energy_log = output_dir / energy_log

    return write_dimer_vector_from_images(
        images,
        dimer_path,
        image=spec.dimer_vector.image,
        atoms=spec.dimer_vector.atoms,
        active_atoms=spec.active_atoms,
        frozen_atoms=spec.frozen_atoms,
        zero_frozen_atoms=spec.dimer_vector.zero_frozen_atoms,
        normalize=spec.dimer_vector.normalize,
        scale=spec.dimer_vector.scale,
        energy_log=energy_log,
        image_prefix=spec.output.images_prefix,
    )
