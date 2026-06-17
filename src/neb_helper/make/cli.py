from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config


TEMPLATE = """initial: initial.cif
final: final.cif
n_images: 10

# False keeps the historical Python/ASE 0-based convention.
# Set true when copying 1-based atom selections from GaussView.
atom_indices_1_based: false

active_atoms: []
frozen_atoms: []

endpoint_reorder:
  # Enable endpoint atom-order correction before compatibility checks.
  enabled: false
  # final_by_initial reorders final to match initial; initial_by_final does the reverse.
  mode: final_by_initial
  # Optional reordered endpoint file. Use a path under output.directory if desired.
  output: final_reordered.cif
  # Optional CSV mapping: reference_index,target_index,symbol,distance_A.
  mapping: final_reorder_mapping.csv
  # Recommended for fixed-cell NEB when CIF cells differ only by tiny roundoff.
  copy_reference_cell: true
  # Optional Angstrom cutoff; leave empty to only print max/RMS distances.
  max_distance:
  # Leave empty so ASE infers the format from output suffix.
  output_format:

background:
  method: mic_linear
  idpp: true

waypoints: []
# Example:
# waypoints:
#   - file: mid_active_atoms.xyz
#     fraction: 0.5
#     active_atoms_only: true

torsions: []
# Example:
# torsions:
#   - name: rotate_fragment
#     dihedral: [10, 12, 13, 48]
#     rotating_group: [48, 49]
#     start_deg: 30.0
#     end_deg: 170.0

relax:
  enabled: false
  calculator:
    type: none
    model:
    head:
    device:
    dtype:
    kwargs: {}
  steps: 100
  fmax: 0.2
  maxstep: 0.05
  optimizer: BFGS
  relax_endpoints: false
  freeze_active: true
  logfile:
  trajectory:
  log_to_screen: true

neb_relax:
  enabled: false
  calculator:
    type: none
    model:
    head:
    device:
    dtype:
    kwargs: {}
  force_evaluator: auto
  # Empty or 0 means evaluate the whole band at once; use 1-4 to reduce GPU memory.
  force_batch_size:
  steps: 200
  fmax: 0.1
  maxstep: 0.05
  optimizer: BFGS
  climb: false
  method: improvedtangent
  k: 0.1
  parallel: false
  remove_rotation_and_translation: false
  shared_calculator: auto
  freeze_active: false
  logfile: neb_relax.log
  trajectory: neb_relax.traj
  log_to_screen: true
  energy_log: neb_relax.ener
  write_image_trajectories: true
  image_trajectory_suffix: _neb_traj.xyz
  image_trajectory_format: extxyz
  write_current_outputs: false
  current_output_interval: 1

dimer_vector:
  enabled: false
  file: dimer_vector.inc
  image: auto
  atoms: active
  zero_frozen_atoms: true
  normalize: true
  scale: 1.0

pbc:
  wrap_policy: never
  output_wrap: false
  fail_if_outside: false
  eps: 1.0e-12
  tol: 1.0e-8

output:
  directory: .
  images_prefix: image
  trajectory: neb_initial_path.xyz
  cp2k_band: band.txt
  diagnostics: diagnostics.csv
  write_vasp: false
  save_initial_guess: true
  initial_guess_directory: initial_guess
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build a CP2K NEB initial path.")
    parser.add_argument("config", nargs="?", help="YAML or JSON config file.")
    parser.add_argument(
        "--write-template",
        metavar="PATH",
        help="Write a starter YAML config and exit.",
    )
    args = parser.parse_args(argv)

    if args.write_template:
        Path(args.write_template).write_text(TEMPLATE, encoding="utf-8")
        print(f"Wrote template config: {args.write_template}")
        return 0

    if not args.config:
        parser.error("config is required unless --write-template is used")

    from .workflow import make_neb_path

    spec = load_config(args.config)
    result = make_neb_path(spec)
    _print_endpoint_reorder_summary(result.get("endpoint_reorder"))
    print(f"Wrote {len(result['output_images'])} images to {result['output_dir']}")
    return 0


def _print_endpoint_reorder_summary(summary) -> None:
    if not summary:
        return
    print(
        "Endpoint reorder: "
        f"{summary['target']} by {summary['reference']} "
        f"({summary['matched_atoms']} atoms, "
        f"max {summary['max_distance']:.6f} A, "
        f"RMS {summary['rms_distance']:.6f} A)"
    )
    if summary.get("output"):
        print(f"Wrote reordered endpoint: {summary['output']}")
    if summary.get("mapping"):
        print(f"Wrote endpoint mapping: {summary['mapping']}")


if __name__ == "__main__":
    raise SystemExit(main())
