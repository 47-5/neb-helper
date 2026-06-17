from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


@dataclass
class CalculatorSpec:
    type: str = "none"
    model: Optional[str] = None
    head: Optional[str] = None
    device: Optional[str] = None
    dtype: Optional[str] = None
    kwargs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BackgroundSpec:
    method: str = "mic_linear"
    idpp: bool = False


@dataclass
class EndpointReorderSpec:
    enabled: bool = False
    mode: str = "final_by_initial"
    output: Optional[str] = None
    mapping: Optional[str] = None
    copy_reference_cell: bool = True
    max_distance: Optional[float] = None
    output_format: Optional[str] = None


@dataclass
class WaypointSpec:
    file: str
    image: Optional[int] = None
    fraction: Optional[float] = None
    atoms: Optional[List[int]] = None
    active_atoms_only: bool = True


@dataclass
class TorsionSpec:
    name: str = "torsion"
    dihedral: List[int] = field(default_factory=list)
    rotating_group: List[int] = field(default_factory=list)
    start_deg: Optional[float] = None
    end_deg: Optional[float] = None
    values_deg: Optional[List[float]] = None
    apply_endpoints: bool = False


@dataclass
class RelaxSpec:
    enabled: bool = False
    calculator: CalculatorSpec = field(default_factory=CalculatorSpec)
    steps: int = 100
    fmax: float = 0.2
    maxstep: float = 0.05
    optimizer: str = "BFGS"
    relax_endpoints: bool = False
    freeze_active: bool = True
    logfile: Optional[str] = None
    trajectory: Optional[str] = None
    log_to_screen: bool = True


@dataclass
class NebRelaxSpec:
    enabled: bool = False
    calculator: CalculatorSpec = field(default_factory=CalculatorSpec)
    force_evaluator: str = "auto"
    force_batch_size: Optional[int] = None
    steps: int = 200
    fmax: float = 0.1
    maxstep: float = 0.05
    optimizer: str = "BFGS"
    climb: bool = False
    method: str = "improvedtangent"
    k: float = 0.1
    parallel: bool = False
    remove_rotation_and_translation: bool = False
    shared_calculator: Union[bool, str] = "auto"
    freeze_active: bool = False
    logfile: Optional[str] = "neb_relax.log"
    trajectory: Optional[str] = "neb_relax.traj"
    log_to_screen: bool = True
    energy_log: Optional[str] = "neb_relax.ener"
    write_image_trajectories: bool = True
    image_trajectory_suffix: str = "_neb_traj.xyz"
    image_trajectory_format: str = "extxyz"
    write_current_outputs: bool = False
    current_output_interval: int = 1

@dataclass
class DimerVectorSpec:
    enabled: bool = False
    file: Optional[str] = "dimer_vector.inc"
    image: Union[int, str] = "auto"
    atoms: Union[str, List[int], None] = "active"
    zero_frozen_atoms: bool = True
    normalize: bool = True
    scale: float = 1.0


@dataclass
class PBCSpec:
    wrap_policy: str = "never"
    output_wrap: bool = False
    fail_if_outside: bool = False
    eps: float = 1.0e-12
    tol: float = 1.0e-8


@dataclass
class OutputSpec:
    directory: str = "."
    images_prefix: str = "image"
    trajectory: str = "neb_initial_path.xyz"
    cp2k_band: str = "band.txt"
    diagnostics: str = "diagnostics.csv"
    write_vasp: bool = False
    save_initial_guess: bool = True
    initial_guess_directory: str = "initial_guess"


@dataclass
class PathSpec:
    initial: str
    final: str
    n_images: int = 3
    atom_indices_1_based: bool = False
    active_atoms: List[int] = field(default_factory=list)
    frozen_atoms: List[int] = field(default_factory=list)
    endpoint_reorder: EndpointReorderSpec = field(default_factory=EndpointReorderSpec)
    background: BackgroundSpec = field(default_factory=BackgroundSpec)
    waypoints: List[WaypointSpec] = field(default_factory=list)
    torsions: List[TorsionSpec] = field(default_factory=list)
    relax: RelaxSpec = field(default_factory=RelaxSpec)
    neb_relax: NebRelaxSpec = field(default_factory=NebRelaxSpec)
    dimer_vector: DimerVectorSpec = field(default_factory=DimerVectorSpec)
    pbc: PBCSpec = field(default_factory=PBCSpec)
    output: OutputSpec = field(default_factory=OutputSpec)
