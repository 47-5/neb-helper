from __future__ import annotations

import glob
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

import matplotlib.pyplot as plt
import numpy as np


HARTREE_TO_EV = 27.211386245988
OUTPUT_XYZ_NAMES = {"neb_traj.xyz", "opted_neb_traj.xyz"}


def natural_sort_key(value: str | Path) -> list[object]:
    """Sort paths with embedded numbers in human order."""
    text = str(value)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


def parse_ase_index(index: str | int) -> str | int:
    if isinstance(index, str):
        stripped = index.strip()
        if re.fullmatch(r"[+-]?\d+", stripped):
            return int(stripped)
        return stripped
    return index


def import_ase_io():
    try:
        from ase.io import read, write
    except ImportError as exc:
        raise RuntimeError(
            "ASE is required for reading xyz/traj structures. "
            "Install neb-helper with its dependencies or run in an environment where ASE is available."
        ) from exc
    return read, write


def import_ase_atoms():
    try:
        from ase import Atoms
    except ImportError as exc:
        raise RuntimeError(
            "ASE is required for reading CP2K restart structures. "
            "Install neb-helper with its dependencies or run in an environment where ASE is available."
        ) from exc
    return Atoms


@dataclass
class NEBData:
    energies: np.ndarray
    distances: np.ndarray
    images: Optional[List[object]] = None
    source: str = ""

    @property
    def path(self) -> np.ndarray:
        return path_from_distances(self.energies, self.distances)


@dataclass
class BarrierSummary:
    forward_barrier: float
    reverse_barrier: float
    reaction_energy: float
    peak_index: int
    peak_energy: float


def path_from_distances(energies: Sequence[float], distances: Sequence[float] | None) -> np.ndarray:
    energies_array = np.asarray(energies, dtype=float)
    if distances is None:
        return np.arange(len(energies_array), dtype=float)

    distance_array = np.asarray(distances, dtype=float)
    if len(distance_array) == len(energies_array):
        return distance_array
    if len(distance_array) != len(energies_array) - 1:
        raise ValueError(
            f"Expected {len(energies_array) - 1} segment distances or "
            f"{len(energies_array)} path coordinates, got {len(distance_array)}."
        )
    return np.concatenate(([0.0], np.cumsum(distance_array)))


def summarize_barrier(energies: Sequence[float]) -> BarrierSummary:
    energy_array = np.asarray(energies, dtype=float)
    if energy_array.ndim != 1 or len(energy_array) == 0:
        raise ValueError("energies must be a non-empty 1D sequence.")

    peak_index = int(np.argmax(energy_array))
    peak_energy = float(energy_array[peak_index])
    return BarrierSummary(
        forward_barrier=peak_energy - float(energy_array[0]),
        reverse_barrier=peak_energy - float(energy_array[-1]),
        reaction_energy=float(energy_array[-1] - energy_array[0]),
        peak_index=peak_index,
        peak_energy=peak_energy,
    )


def parse_numeric_line(line: str) -> Optional[np.ndarray]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    try:
        return np.array([float(token) for token in stripped.split()], dtype=float)
    except ValueError:
        return None


def infer_image_count_from_ener_values(values: Sequence[float]) -> int:
    value_count = len(values)
    if value_count < 1 or value_count % 2 == 0:
        raise ValueError(
            "Cannot infer image count from the energy line. "
            "Expected N energies followed by N-1 distances."
        )
    return (value_count + 1) // 2


def read_neb_energy(
    energy_file_path: str | Path | None = None,
    glob_str: str = "example/*.ener",
    inedx: int = -1,
    image_number: int | None = None,
    relative: bool = True,
    energy_unit: str = "hartree",
) -> tuple[np.ndarray, np.ndarray]:
    """Read a CP2K-style NEB .ener file.

    The selected row is expected to contain:
    step, image_1_energy, ..., image_N_energy, segment_1_distance, ..., segment_N-1_distance
    """
    energy_file = find_single_file(energy_file_path, glob_str)
    rows = []
    for line in Path(energy_file).read_text(encoding="utf-8", errors="ignore").splitlines():
        parsed = parse_numeric_line(line)
        if parsed is not None:
            rows.append(parsed)
    if not rows:
        raise ValueError(f"No numeric rows found in {energy_file}.")

    selected_row = rows[inedx]
    values = selected_row[1:]
    if image_number is None:
        image_number = infer_image_count_from_ener_values(values)
    if len(values) < image_number:
        raise ValueError(
            f"Energy row has only {len(values)} values after the step column; "
            f"cannot read {image_number} images."
        )

    energies = np.array(values[:image_number], dtype=float)
    unit = energy_unit.lower()
    if unit in {"hartree", "ha", "a.u.", "au"}:
        energies = energies * HARTREE_TO_EV
    elif unit not in {"ev", "electronvolt", "electronvolts"}:
        raise ValueError(f"Unsupported energy unit: {energy_unit}")

    if relative:
        energies = energies - energies[0]

    distances = np.array(values[image_number:], dtype=float)
    if len(distances) != image_number - 1:
        raise ValueError(
            f"Expected {image_number - 1} distances for {image_number} images, got {len(distances)}."
        )
    return energies, distances


def find_single_file(path: str | Path | None, glob_str: str) -> Path:
    if path is not None:
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(resolved)
        return resolved

    matches = sorted((Path(match) for match in glob.glob(glob_str)), key=natural_sort_key)
    if not matches:
        raise FileNotFoundError(f"No files matched {glob_str!r}.")
    return matches[0]


def parse_fortran_float(token: str) -> float:
    return float(token.replace("D", "E").replace("d", "e"))


def unquote_cp2k_token(token: str) -> str:
    return token.strip().strip('"').strip("'")


def parse_cp2k_periodic(value: str) -> tuple[bool, bool, bool]:
    upper = value.upper()
    if upper in {"NONE", "FALSE", "F", "0"}:
        return (False, False, False)
    return ("X" in upper, "Y" in upper, "Z" in upper)


def parse_cp2k_coord_line(line: str) -> tuple[str | None, list[float]] | None:
    tokens = line.split()
    if len(tokens) < 3:
        return None

    try:
        return None, [parse_fortran_float(token) for token in tokens[:3]]
    except ValueError:
        pass

    if len(tokens) < 4:
        return None
    try:
        return unquote_cp2k_token(tokens[0]), [parse_fortran_float(token) for token in tokens[1:4]]
    except ValueError:
        return None


def map_cp2k_kind_symbols(raw_symbols: Sequence[str], kind_element_map: dict[str, str]) -> list[str]:
    symbols = []
    for raw_symbol in raw_symbols:
        symbol = unquote_cp2k_token(raw_symbol)
        symbols.append(kind_element_map.get(symbol, symbol))
    return symbols


def make_atoms_from_restart(
    symbols: Sequence[str],
    positions: Sequence[Sequence[float]],
    cell: np.ndarray | None,
    pbc: tuple[bool, bool, bool],
) -> object:
    Atoms = import_ase_atoms()
    kwargs = {"symbols": list(symbols), "positions": np.asarray(positions, dtype=float)}
    if cell is not None:
        kwargs["cell"] = np.asarray(cell, dtype=float)
        kwargs["pbc"] = pbc
    elif any(pbc):
        kwargs["pbc"] = pbc
    return Atoms(**kwargs)


def read_cp2k_restart_images(restart_file: str | Path) -> list[object]:
    """Read the last stored NEB band from a CP2K restart file.

    CP2K BAND restart files store each replica as a pure coordinate block under
    MOTION/BAND/REPLICA. The atom labels and cell are taken from SUBSYS.
    """
    restart_path = Path(restart_file)
    if not restart_path.exists():
        raise FileNotFoundError(restart_path)

    lines = restart_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    section_stack: list[str] = []
    replica_blocks: list[list[list[float]]] = []
    symbol_candidates: list[list[str]] = []
    kind_element_map: dict[str, str] = {}

    current_coord_context: set[str] | None = None
    current_coord_positions: list[list[float]] = []
    current_coord_symbols: list[str] = []
    current_cell_vectors: dict[str, list[float]] | None = None
    current_cell_pbc: tuple[bool, bool, bool] | None = None
    current_kind: str | None = None
    cell: np.ndarray | None = None
    pbc = (False, False, False)

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        upper = stripped.upper()
        if upper.startswith("&END"):
            tokens = stripped.split()
            section_name = tokens[1].upper() if len(tokens) > 1 else ""

            if section_name == "COORD" and current_coord_context is not None:
                if "REPLICA" in current_coord_context:
                    replica_blocks.append(current_coord_positions)
                elif current_coord_symbols:
                    symbol_candidates.append(current_coord_symbols)
                current_coord_context = None
                current_coord_positions = []
                current_coord_symbols = []

            if section_name == "CELL" and current_cell_vectors is not None:
                if {"A", "B", "C"}.issubset(current_cell_vectors):
                    cell = np.array(
                        [current_cell_vectors["A"], current_cell_vectors["B"], current_cell_vectors["C"]],
                        dtype=float,
                    )
                if current_cell_pbc is not None:
                    pbc = current_cell_pbc
                current_cell_vectors = None
                current_cell_pbc = None

            if section_name == "KIND":
                current_kind = None

            if section_stack:
                if section_name and section_name in section_stack:
                    while section_stack and section_stack[-1] != section_name:
                        section_stack.pop()
                    if section_stack:
                        section_stack.pop()
                else:
                    section_stack.pop()
            continue

        if stripped.startswith("&"):
            tokens = stripped.split()
            section_name = tokens[0][1:].upper()
            section_stack.append(section_name)

            if section_name == "COORD":
                current_coord_context = set(section_stack[:-1])
                current_coord_positions = []
                current_coord_symbols = []
            elif section_name == "CELL":
                current_cell_vectors = {}
                current_cell_pbc = None
            elif section_name == "KIND" and len(tokens) > 1:
                current_kind = unquote_cp2k_token(tokens[1])
            continue

        if current_coord_context is not None:
            parsed = parse_cp2k_coord_line(stripped)
            if parsed is not None:
                symbol, coords = parsed
                current_coord_positions.append(coords)
                if symbol is not None:
                    current_coord_symbols.append(symbol)
            continue

        if current_cell_vectors is not None:
            tokens = stripped.split()
            if not tokens:
                continue
            key = tokens[0].upper()
            if key in {"A", "B", "C"} and len(tokens) >= 4:
                try:
                    current_cell_vectors[key] = [parse_fortran_float(token) for token in tokens[1:4]]
                except ValueError:
                    pass
            elif key == "PERIODIC" and len(tokens) >= 2:
                current_cell_pbc = parse_cp2k_periodic(tokens[1])
            continue

        if current_kind is not None:
            tokens = stripped.split()
            if len(tokens) >= 2 and tokens[0].upper() == "ELEMENT":
                kind_element_map[current_kind] = unquote_cp2k_token(tokens[1])

    if not replica_blocks:
        raise ValueError(f"No BAND/REPLICA coordinate blocks found in {restart_path}.")
    if not symbol_candidates:
        raise ValueError(f"No labelled SUBSYS/COORD block found in {restart_path}; cannot assign atom symbols.")

    raw_symbols = symbol_candidates[-1]
    symbols = map_cp2k_kind_symbols(raw_symbols, kind_element_map)
    atom_count = len(symbols)
    if atom_count == 0:
        raise ValueError(f"No atom symbols found in {restart_path}.")

    images = []
    for replica_index, positions in enumerate(replica_blocks):
        if len(positions) != atom_count:
            raise ValueError(
                f"Replica {replica_index} has {len(positions)} atoms, "
                f"but SUBSYS/COORD has {atom_count} atom labels."
            )
        images.append(make_atoms_from_restart(symbols, positions, cell, pbc))
    return images


def discover_restart_file(directory: Path) -> Path:
    matches = sorted(directory.glob("*.restart"), key=natural_sort_key)
    if not matches:
        raise FileNotFoundError(f"No .restart file found in {directory}.")
    return matches[0]


def discover_energy_file_for_restart(restart_file: str | Path) -> Path:
    restart_path = Path(restart_file)
    paired = restart_path.with_suffix(".ener")
    if paired.exists():
        return paired
    return discover_energy_file(restart_path.parent)


def attach_image_energies(images: Sequence[object] | None, energies: Sequence[float]) -> None:
    if images is None or len(images) != len(energies):
        return
    for image, energy in zip(images, energies):
        info = getattr(image, "info", None)
        if isinstance(info, dict):
            info["energy"] = float(energy)


def resolve_xyz_files(image_path_list: Sequence[str | Path] | None, glob_str: str) -> list[Path]:
    if image_path_list is None:
        files = [Path(match) for match in glob.glob(glob_str)]
        filtered = [path for path in files if path.name.lower() not in OUTPUT_XYZ_NAMES]
        files = filtered or files
    else:
        files = [Path(path) for path in image_path_list]

    files = sorted(files, key=natural_sort_key)
    if not files:
        raise FileNotFoundError(f"No xyz files matched {glob_str!r}.")
    return files


def read_xyz_images(
    image_path_list: Sequence[str | Path] | None = None,
    glob_str: str = "example/*.xyz",
    index: str | int = -1,
) -> list[object]:
    read, _ = import_ase_io()
    files = resolve_xyz_files(image_path_list, glob_str)
    ase_index = parse_ase_index(index)
    return [read(str(path), index=ase_index) for path in files]


def make_neb_traj(
    image_path_list: List[str] | None = None,
    glob_str: str = "example/*.xyz",
    index: str | int = "-1",
    output_path: str | Path = "opted_neb_traj.xyz",
    restart_file: str | Path | None = None,
) -> list[object]:
    """Backward-compatible helper that writes selected xyz images or restart replicas."""
    if restart_file is not None:
        images = read_cp2k_restart_images(restart_file)
        write_images(output_path, images)
        print("restart_file:")
        print(restart_file)
        print(f"wrote: {output_path}")
        return images

    files = resolve_xyz_files(image_path_list, glob_str)
    images = read_xyz_images(files, index=index)
    write_images(output_path, images)
    print("image_path_list:")
    for path in files:
        print(path)
    print(f"wrote: {output_path}")
    return images


def load_from_ener_xyz(
    directory: str | Path,
    energy_file: str | Path | None = None,
    restart_file: str | Path | None = None,
    xyz_glob: str | None = None,
    image_count: int | None = None,
    line_index: int = -1,
    xyz_index: str | int = -1,
    relative: bool = True,
    energy_unit: str = "hartree",
    read_structures: bool = True,
) -> NEBData:
    directory_path = Path(directory)
    if energy_file is None:
        energy_file = discover_energy_file(directory_path)
    energy_path = Path(energy_file)

    if image_count is None:
        energies, distances = read_neb_energy(
            energy_path,
            inedx=line_index,
            image_number=None,
            relative=relative,
            energy_unit=energy_unit,
        )
    else:
        energies, distances = read_neb_energy(
            energy_path,
            inedx=line_index,
            image_number=image_count,
            relative=relative,
            energy_unit=energy_unit,
        )

    images = None
    structure_source = None
    if read_structures:
        if restart_file is not None:
            restart_path = Path(restart_file)
            images = read_cp2k_restart_images(restart_path)
            structure_source = restart_path
        else:
            pattern = xyz_glob or str(directory_path / "*Replica*.xyz")
            if not glob.glob(pattern):
                pattern = str(directory_path / "*.xyz")
            if glob.glob(pattern):
                images = read_xyz_images(glob_str=pattern, index=xyz_index)
                structure_source = pattern
            else:
                restart_path = discover_restart_file(directory_path)
                images = read_cp2k_restart_images(restart_path)
                structure_source = restart_path
        if len(images) != len(energies):
            print(
                f"Warning: read {len(images)} structures but {len(energies)} energies. "
                "The plot will use the .ener distances."
            )
        attach_image_energies(images, energies)

    source = str(energy_path)
    if structure_source is not None:
        source = f"{source} + {structure_source}"
    return NEBData(energies=energies, distances=distances, images=images, source=source)


def discover_energy_file(directory: Path) -> Path:
    matches = sorted(directory.glob("*.ener"), key=natural_sort_key)
    if not matches:
        raise FileNotFoundError(f"No .ener file found in {directory}.")
    return matches[0]


def discover_traj_file(directory: Path) -> Path:
    preferred = directory / "neb.traj"
    if preferred.exists():
        return preferred

    matches = sorted(directory.glob("*.traj"), key=natural_sort_key)
    if not matches:
        raise FileNotFoundError(f"No .traj file found in {directory}.")
    return matches[0]


def get_atoms_energy(atoms: object) -> float:
    try:
        return float(atoms.get_potential_energy())
    except Exception:
        pass

    info = getattr(atoms, "info", {})
    for key in ("energy", "E", "free_energy"):
        if key in info:
            return float(info[key])

    calc = getattr(atoms, "calc", None)
    results = getattr(calc, "results", {}) if calc is not None else {}
    for key in ("energy", "free_energy"):
        if key in results:
            return float(results[key])

    raise ValueError("Could not read potential energy from an ASE Atoms object.")


def infer_images_per_band(frames: Sequence[object], energies: Sequence[float], max_images: int = 64) -> int:
    total = len(frames)
    if total <= 1:
        return total
    if total <= max_images:
        return total

    energy_array = np.asarray(energies, dtype=float)
    upper = min(total, max_images)
    for image_count in range(2, upper + 1):
        if total % image_count != 0:
            continue
        start_energies = energy_array[0::image_count]
        end_energies = energy_array[image_count - 1 :: image_count]
        if np.allclose(start_energies, start_energies[0], atol=1e-6, rtol=1e-10) and np.allclose(
            end_energies, end_energies[0], atol=1e-6, rtol=1e-10
        ):
            return image_count

    raise ValueError(
        f"Could not infer images per NEB band from {total} trajectory frames. "
        "Please pass --images-per-band N."
    )


def select_band_frames(frames: Sequence[object], images_per_band: int, band_index: int = -1) -> list[object]:
    if images_per_band <= 0:
        raise ValueError("images_per_band must be positive.")
    total = len(frames)
    if total < images_per_band:
        raise ValueError(f"Trajectory has {total} frames, fewer than {images_per_band} images per band.")

    complete_bands = total // images_per_band
    if total % images_per_band != 0:
        if band_index != -1:
            raise ValueError(
                f"Trajectory has {total} frames, which is not divisible by {images_per_band}. "
                "Only --band -1 can select the trailing incomplete band."
            )
        start = total - images_per_band
    else:
        if band_index < 0:
            band_index = complete_bands + band_index
        if band_index < 0 or band_index >= complete_bands:
            raise IndexError(f"Band index {band_index} out of range for {complete_bands} bands.")
        start = band_index * images_per_band

    return list(frames[start : start + images_per_band])


def calculate_image_distances(images: Sequence[object], mic: bool = True) -> np.ndarray:
    if len(images) < 2:
        return np.array([], dtype=float)

    distances = []
    for left, right in zip(images[:-1], images[1:]):
        if len(left) != len(right):
            raise ValueError("All NEB images must contain the same number of atoms.")

        delta = right.get_positions() - left.get_positions()
        if mic:
            try:
                from ase.geometry import find_mic

                delta, _ = find_mic(delta, cell=left.cell, pbc=left.pbc)
            except Exception:
                pass
        distances.append(float(np.linalg.norm(delta)))
    return np.array(distances, dtype=float)


def load_from_traj(
    traj_file: str | Path,
    images_per_band: int | None = None,
    band_index: int = -1,
    relative: bool = True,
    mic: bool = True,
) -> NEBData:
    read, _ = import_ase_io()
    frames = read(str(traj_file), index=":")
    if not isinstance(frames, list):
        frames = [frames]
    if not frames:
        raise ValueError(f"No frames found in {traj_file}.")

    all_energies = np.array([get_atoms_energy(frame) for frame in frames], dtype=float)
    if images_per_band is None:
        images_per_band = infer_images_per_band(frames, all_energies)

    images = select_band_frames(frames, images_per_band, band_index=band_index)
    energies = np.array([get_atoms_energy(image) for image in images], dtype=float)
    if relative:
        energies = energies - energies[0]
    distances = calculate_image_distances(images, mic=mic)
    return NEBData(energies=energies, distances=distances, images=images, source=str(traj_file))


def load_from_restart(
    restart_file: str | Path,
    energy_file: str | Path | None = None,
    image_count: int | None = None,
    line_index: int = -1,
    relative: bool = True,
    energy_unit: str = "hartree",
) -> NEBData:
    restart_path = Path(restart_file)
    images = read_cp2k_restart_images(restart_path)

    if energy_file is None:
        try:
            energy_path = discover_energy_file_for_restart(restart_path)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Restart file {restart_path} contains structures but not NEB energies. "
                "Pass energy_file=... or put the matching .ener file next to it."
            ) from exc
    else:
        energy_path = Path(energy_file)

    resolved_image_count = image_count or len(images)
    energies, distances = read_neb_energy(
        energy_path,
        inedx=line_index,
        image_number=resolved_image_count,
        relative=relative,
        energy_unit=energy_unit,
    )
    if len(images) != len(energies):
        print(
            f"Warning: read {len(images)} restart images but {len(energies)} energies. "
            "The plot will use the .ener distances."
        )
    attach_image_energies(images, energies)
    return NEBData(
        energies=energies,
        distances=distances,
        images=images,
        source=f"{energy_path} + {restart_path}",
    )


def smooth_curve(x: np.ndarray, y: np.ndarray, points: int = 300) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < 4 or len(np.unique(x)) != len(x):
        return x, y
    try:
        from scipy.interpolate import PchipInterpolator

        xx = np.linspace(float(x[0]), float(x[-1]), points)
        yy = PchipInterpolator(x, y)(xx)
        return xx, yy
    except Exception:
        return x, y


def configure_plot_style(font: str = "Times New Roman") -> None:
    plt.rcParams.update(
        {
            "font.family": "serif",
            "font.serif": [font, "Times", "DejaVu Serif"],
            "mathtext.fontset": "stix",
            "axes.unicode_minus": False,
            "axes.linewidth": 1.4,
            "xtick.direction": "in",
            "ytick.direction": "in",
        }
    )


def plot_neb_result(
    energy: Sequence[float],
    distance: Sequence[float] | None = None,
    save_path: str | Path | None = "neb_result.png",
    dpi: int = 600,
    smooth: bool = True,
    font: str = "Times New Roman",
    annotate: bool = True,
) -> None:
    energies = np.asarray(energy, dtype=float)
    x = path_from_distances(energies, distance)
    summary = summarize_barrier(energies)

    configure_plot_style(font)
    fig, ax = plt.subplots(figsize=(10.0, 5.4))

    if smooth:
        xx, yy = smooth_curve(x, energies)
        ax.plot(xx, yy, color="#111111", linewidth=2.0, zorder=2)
    else:
        ax.plot(x, energies, color="#111111", linewidth=2.0, zorder=2)

    ax.scatter(
        x,
        energies,
        s=36,
        color="#1f4f82",
        edgecolor="#1f4f82",
        linewidth=0.8,
        zorder=3,
    )

    ax.set_xlabel(r"path [$\AA$]", fontsize=18)
    ax.set_ylabel("energy [eV]", fontsize=18)
    ax.grid(True, linestyle="--", linewidth=0.8, color="#d9d9d9", alpha=0.7)
    ax.tick_params(axis="both", which="major", labelsize=15, length=6, width=1.2, top=True, right=True)

    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_linewidth(1.4)
        spine.set_color("#222222")

    x_pad = max((float(x[-1]) - float(x[0])) * 0.04, 0.1)
    y_span = float(np.max(energies) - np.min(energies))
    y_pad = max(y_span * 0.12, 0.08)
    ax.set_xlim(float(x[0]) - x_pad, float(x[-1]) + x_pad)
    ax.set_ylim(float(np.min(energies)) - y_pad, float(np.max(energies)) + y_pad)

    if annotate:
        text = (
            rf"$E_\mathrm{{f}}\approx {summary.forward_barrier:.3f}\ \mathrm{{eV}}$; "
            rf"$E_\mathrm{{r}}\approx {summary.reverse_barrier:.3f}\ \mathrm{{eV}}$; "
            rf"$\Delta E = {summary.reaction_energy:.3f}\ \mathrm{{eV}}$"
        )
        ax.text(0.5, 1.02, text, transform=ax.transAxes, ha="center", va="bottom", fontsize=18)

    fig.tight_layout()
    if save_path is None:
        plt.show()
    else:
        fig.savefig(save_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)


def calculate_barrier(energies: Sequence[float]) -> BarrierSummary:
    """Backward-compatible barrier printer."""
    summary = summarize_barrier(energies)
    print(f"Forward barrier: {summary.forward_barrier:.6f} eV")
    print(f"Reverse barrier: {summary.reverse_barrier:.6f} eV")
    print(f"Reaction energy: {summary.reaction_energy:.6f} eV")
    print(f"Peak image index: {summary.peak_index}")
    return summary


def write_summary(path: str | Path, data: NEBData, summary: BarrierSummary) -> None:
    x = data.path
    lines = [
        "# NEB result",
        f"source: {data.source}",
        f"forward_barrier_eV: {summary.forward_barrier:.8f}",
        f"reverse_barrier_eV: {summary.reverse_barrier:.8f}",
        f"reaction_energy_eV: {summary.reaction_energy:.8f}",
        f"peak_image_index: {summary.peak_index}",
        "",
        "image path_A energy_eV",
    ]
    for index, (path_value, energy_value) in enumerate(zip(x, data.energies)):
        lines.append(f"{index:5d} {path_value:16.8f} {energy_value:16.8f}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_images(path: str | Path, images: Sequence[object] | None) -> None:
    if not images:
        raise ValueError("No images are available to write.")
    output_path = Path(path)
    if output_path.suffix.lower() in {".xyz", ".extxyz"}:
        write_energy_only_extxyz(output_path, images)
        return

    _, write = import_ase_io()
    write(str(output_path), list(images))


def write_energy_only_extxyz(path: str | Path, images: Sequence[object]) -> None:
    lines = []
    for atoms in images:
        symbols = atoms.get_chemical_symbols()
        positions = atoms.get_positions()
        try:
            energy = get_atoms_energy(atoms)
        except ValueError:
            energy = None

        lines.append(str(len(symbols)))
        comment = "Properties=species:S:1:pos:R:3"
        if energy is not None:
            comment = f"{comment} energy={energy:.12f}"
        lines.append(comment)
        for symbol, position in zip(symbols, positions):
            x, y, z = position
            lines.append(f"{symbol:<2} {x:16.8f} {y:16.8f} {z:16.8f}")

    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def default_output_path(input_path: Path, output: str | None) -> Path:
    if output:
        return Path(output)
    if input_path.is_dir():
        return input_path / "neb_result.png"
    return input_path.with_name("neb_result.png")


def load_input(
    input_path: str | Path = ".",
    energy_file: str | Path | None = None,
    traj_file: str | Path | None = None,
    restart_file: str | Path | None = None,
    xyz_glob: str | None = None,
    image_count: int | None = None,
    line_index: int = -1,
    xyz_index: str | int = -1,
    images_per_band: int | None = None,
    band_index: int = -1,
    energy_unit: str = "hartree",
    relative: bool = True,
    mic: bool = True,
) -> NEBData:
    input_path = Path(input_path)

    if restart_file is not None:
        return load_from_restart(
            restart_file,
            energy_file=energy_file,
            image_count=image_count,
            line_index=line_index,
            relative=relative,
            energy_unit=energy_unit,
        )

    if traj_file is not None:
        return load_from_traj(traj_file, images_per_band, band_index, relative=relative, mic=mic)

    if input_path.suffix.lower() == ".traj":
        return load_from_traj(input_path, images_per_band, band_index, relative=relative, mic=mic)

    if input_path.suffix.lower() == ".restart":
        return load_from_restart(
            input_path,
            energy_file=energy_file,
            image_count=image_count,
            line_index=line_index,
            relative=relative,
            energy_unit=energy_unit,
        )

    if energy_file is not None or input_path.suffix.lower() == ".ener":
        energy_file = energy_file or input_path
        directory = Path(energy_file).parent
        return load_from_ener_xyz(
            directory,
            energy_file=energy_file,
            restart_file=restart_file,
            xyz_glob=xyz_glob,
            image_count=image_count,
            line_index=line_index,
            xyz_index=xyz_index,
            relative=relative,
            energy_unit=energy_unit,
        )

    if input_path.is_dir():
        if any(input_path.glob("*.ener")):
            return load_from_ener_xyz(
                input_path,
                energy_file=energy_file,
                restart_file=restart_file,
                xyz_glob=xyz_glob,
                image_count=image_count,
                line_index=line_index,
                xyz_index=xyz_index,
                relative=relative,
                energy_unit=energy_unit,
            )
        if any(input_path.glob("*.restart")):
            return load_from_restart(
                discover_restart_file(input_path),
                energy_file=energy_file,
                image_count=image_count,
                line_index=line_index,
                relative=relative,
                energy_unit=energy_unit,
            )
        return load_from_traj(discover_traj_file(input_path), images_per_band, band_index, relative=relative, mic=mic)

    raise FileNotFoundError(f"Unsupported input: {input_path}")


def analyze_neb(
    input_path: str | Path = ".",
    energy_file: str | Path | None = None,
    traj_file: str | Path | None = None,
    restart_file: str | Path | None = None,
    xyz_glob: str | None = None,
    image_count: int | None = None,
    line_index: int = -1,
    xyz_index: str | int = -1,
    images_per_band: int | None = None,
    band_index: int = -1,
    energy_unit: str = "hartree",
    relative: bool = True,
    mic: bool = True,
    smooth: bool = True,
    output_image: str | Path | None = None,
    dpi: int = 600,
    font: str = "Times New Roman",
    write_summary_file: bool = True,
    summary_path: str | Path | None = None,
    write_xyz_file: bool = False,
    xyz_output_path: str | Path = "neb_traj.xyz",
) -> tuple[NEBData, BarrierSummary]:
    source_path = Path(traj_file or energy_file or restart_file or input_path)
    data = load_input(
        input_path=input_path,
        energy_file=energy_file,
        traj_file=traj_file,
        restart_file=restart_file,
        xyz_glob=xyz_glob,
        image_count=image_count,
        line_index=line_index,
        xyz_index=xyz_index,
        images_per_band=images_per_band,
        band_index=band_index,
        energy_unit=energy_unit,
        relative=relative,
        mic=mic,
    )
    output_path = default_output_path(source_path, str(output_image) if output_image is not None else None)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plot_neb_result(
        data.energies,
        data.distances,
        save_path=output_path,
        dpi=dpi,
        smooth=smooth,
        font=font,
    )
    summary = summarize_barrier(data.energies)

    if write_summary_file:
        resolved_summary_path = Path(summary_path) if summary_path is not None else output_path.with_name("result.txt")
        write_summary(resolved_summary_path, data, summary)
        print(f"Summary: {resolved_summary_path}")

    if write_xyz_file:
        resolved_xyz_output = Path(xyz_output_path)
        if not resolved_xyz_output.is_absolute():
            resolved_xyz_output = output_path.with_name(str(xyz_output_path))
        write_images(resolved_xyz_output, data.images)
        print(f"Trajectory: {resolved_xyz_output}")

    print(f"Source: {data.source}")
    print(f"Images: {len(data.energies)}")
    print(f"Forward barrier: {summary.forward_barrier:.6f} eV")
    print(f"Reverse barrier: {summary.reverse_barrier:.6f} eV")
    print(f"Reaction energy: {summary.reaction_energy:.6f} eV")
    print(f"Figure: {output_path}")
    return data, summary


def analyze_neb_files(
    energy_file: str | Path | None = None,
    restart_file: str | Path | None = None,
    traj_file: str | Path | None = None,
    result_dir: str | Path | None = None,
    xyz_glob: str | None = None,
    image_count: int | None = None,
    line_index: int = -1,
    xyz_index: str | int = -1,
    images_per_band: int | None = None,
    band_index: int = -1,
    energy_unit: str = "hartree",
    relative: bool = True,
    mic: bool = True,
    smooth: bool = True,
    output_image: str | Path | None = None,
    dpi: int = 600,
    font: str = "Times New Roman",
    write_summary_file: bool = True,
    summary_path: str | Path | None = None,
    write_xyz_file: bool = False,
    xyz_output_path: str | Path = "neb_traj.xyz",
) -> tuple[NEBData, BarrierSummary]:
    """Analyze NEB data using explicit file roles.

    Configure exactly one source family:
    - energy_file, optionally with restart_file or xyz_glob, for CP2K .ener data.
    - restart_file alone when the matching .ener file sits next to it.
    - traj_file for an ASE .traj that already contains structures and energies.
    - result_dir to auto-discover files in one directory.
    """
    uses_traj = traj_file is not None
    uses_cp2k_files = energy_file is not None or restart_file is not None
    uses_directory = result_dir is not None
    selected_sources = sum([uses_traj, uses_cp2k_files, uses_directory])
    if selected_sources != 1:
        raise ValueError(
            "Configure exactly one input source family: "
            "energy_file/restart_file, traj_file, or result_dir."
        )

    if uses_traj:
        return analyze_neb(
            input_path=traj_file,
            traj_file=traj_file,
            images_per_band=images_per_band,
            band_index=band_index,
            relative=relative,
            mic=mic,
            smooth=smooth,
            output_image=output_image,
            dpi=dpi,
            font=font,
            write_summary_file=write_summary_file,
            summary_path=summary_path,
            write_xyz_file=write_xyz_file,
            xyz_output_path=xyz_output_path,
        )

    if uses_cp2k_files:
        primary_path = energy_file or restart_file
        return analyze_neb(
            input_path=primary_path,
            energy_file=energy_file,
            restart_file=restart_file,
            xyz_glob=xyz_glob,
            image_count=image_count,
            line_index=line_index,
            xyz_index=xyz_index,
            energy_unit=energy_unit,
            relative=relative,
            mic=mic,
            smooth=smooth,
            output_image=output_image,
            dpi=dpi,
            font=font,
            write_summary_file=write_summary_file,
            summary_path=summary_path,
            write_xyz_file=write_xyz_file,
            xyz_output_path=xyz_output_path,
        )

    return analyze_neb(
        input_path=result_dir,
        xyz_glob=xyz_glob,
        image_count=image_count,
        line_index=line_index,
        xyz_index=xyz_index,
        images_per_band=images_per_band,
        band_index=band_index,
        energy_unit=energy_unit,
        relative=relative,
        mic=mic,
        smooth=smooth,
        output_image=output_image,
        dpi=dpi,
        font=font,
        write_summary_file=write_summary_file,
        summary_path=summary_path,
        write_xyz_file=write_xyz_file,
        xyz_output_path=xyz_output_path,
    )


def build_arg_parser() -> "argparse.ArgumentParser":
    import argparse

    parser = argparse.ArgumentParser(
        prog="neb-helper analyze",
        description="Analyze NEB result files and plot an energy profile.",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=".",
        help="Result directory, .ener file, .traj file, or .restart file. Default: current directory.",
    )
    parser.add_argument("--energy-file", help="Explicit CP2K .ener file.")
    parser.add_argument("--traj-file", help="Explicit ASE .traj file.")
    parser.add_argument("--restart-file", help="Explicit CP2K .restart file for replica structures.")
    parser.add_argument("--xyz-glob", help="Glob pattern for replica xyz files, relative to the result directory if not absolute.")
    parser.add_argument("--image-count", type=int, help="Number of NEB images when it cannot be inferred from .ener data.")
    parser.add_argument("--line-index", type=int, default=-1, help="Numeric .ener line to read. Default: -1, the last line.")
    parser.add_argument("--xyz-index", default="-1", help="ASE index for xyz frames. Default: -1, the last frame.")
    parser.add_argument("--images-per-band", type=int, help="Images per band for ASE trajectory slicing.")
    parser.add_argument("--band-index", type=int, default=-1, help="Band index for ASE trajectory slicing. Default: -1, the last band.")
    parser.add_argument(
        "--energy-unit",
        choices=("hartree", "ev"),
        default="hartree",
        help="Unit used by input energies. CP2K .ener files normally use hartree. Default: hartree.",
    )
    energy_mode = parser.add_mutually_exclusive_group()
    energy_mode.add_argument("--relative", dest="relative", action="store_true", default=True, help="Plot energies relative to image 0. Default.")
    energy_mode.add_argument("--absolute-energy", dest="relative", action="store_false", help="Keep absolute input energies.")
    parser.add_argument("--no-mic", dest="mic", action="store_false", default=True, help="Disable MIC when path distances are computed from structures.")
    parser.add_argument("--no-smooth", dest="smooth", action="store_false", default=True, help="Disable curve smoothing.")
    parser.add_argument("--output-image", help="Output plot path. Default: neb_result.png next to the input.")
    parser.add_argument("--dpi", type=int, default=600, help="Plot DPI. Default: 600.")
    parser.add_argument("--font", default="Times New Roman", help="Matplotlib font family. Default: Times New Roman.")
    parser.add_argument("--no-summary", dest="write_summary_file", action="store_false", default=True, help="Do not write result.txt.")
    parser.add_argument("--summary", dest="summary_path", help="Summary output path. Default: result.txt next to the plot.")
    parser.add_argument("--write-xyz", dest="write_xyz_file", action="store_true", default=False, help="Write the analyzed image structures when available.")
    parser.add_argument("--xyz-output", default="neb_traj.xyz", help="Structure trajectory output path used with --write-xyz. Default: neb_traj.xyz.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    analyze_neb(
        input_path=args.input_path,
        energy_file=args.energy_file,
        traj_file=args.traj_file,
        restart_file=args.restart_file,
        xyz_glob=args.xyz_glob,
        image_count=args.image_count,
        line_index=args.line_index,
        xyz_index=args.xyz_index,
        images_per_band=args.images_per_band,
        band_index=args.band_index,
        energy_unit=args.energy_unit,
        relative=args.relative,
        mic=args.mic,
        smooth=args.smooth,
        output_image=args.output_image,
        dpi=args.dpi,
        font=args.font,
        write_summary_file=args.write_summary_file,
        summary_path=args.summary_path,
        write_xyz_file=args.write_xyz_file,
        xyz_output_path=args.xyz_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
