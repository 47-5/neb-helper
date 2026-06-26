from __future__ import annotations

import csv
from pathlib import Path

import yaml
from ase import Atoms
from ase.io import read, write

from neb_helper import generate_dimer_guess_from_config, generate_ts_guess


def test_tsguess_writes_recommended_structure_metrics_and_dimer_vector(tmp_path: Path) -> None:
    initial_path, final_path = _write_endpoint_pair(tmp_path)
    config_path = tmp_path / "tsguess.yaml"
    _write_yaml(
        config_path,
        {
            "initial": initial_path.name,
            "final": final_path.name,
            "atom_indices_1_based": True,
            "active_atoms": "2-3",
            "path": {
                "method": "active_linear",
                "base": "initial",
                "fractions": [0.25, 0.50],
            },
            "reaction_coordinates": {
                "forming_bonds": [[2, 3]],
            },
            "selection": {
                "prefer_fraction": 0.25,
                "forming_range": [1.35, 1.50],
            },
            "candidate_outputs": {
                "directory": "tsout",
                "format": "xyz",
                "write_all": True,
                "metrics": "metrics.csv",
                "notes": "notes.md",
            },
            "dimer_vector": {
                "enabled": True,
                "source": "local_tangent",
                "tangent_fractions": [0.25, 0.50],
                "atoms": "active",
                "remove_translation": "active",
            },
            "check": {
                "enabled": True,
                "amplitude": 0.5,
            },
        },
    )

    result = generate_ts_guess(config_path)

    assert result.recommended_fraction == 0.25
    assert result.recommended_structure == tmp_path / "tsout" / "ts_guess_recommended_t0p250.xyz"
    assert result.recommended_structure.exists()
    assert result.metrics_path is not None and result.metrics_path.exists()
    assert result.notes_path is not None and result.notes_path.exists()
    assert result.dimer_vector_path is not None and result.dimer_vector_path.exists()
    assert result.check_path is not None and result.check_path.exists()
    assert result.selected_indices == [1, 2]

    recommended = read(result.recommended_structure)
    initial = read(initial_path)
    assert recommended.positions[0].tolist() == initial.positions[0].tolist()

    rows = list(csv.DictReader(result.metrics_path.open(encoding="utf-8")))
    assert [row["recommended"] for row in rows] == ["1", "0"]
    assert "forming_2_3" in rows[0]


def test_dimer_guess_accepts_yaml_config_with_relative_paths(tmp_path: Path) -> None:
    initial_path, final_path = _write_endpoint_pair(tmp_path)
    (tmp_path / "image_000.xyz").write_text(initial_path.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "image_001.xyz").write_text(final_path.read_text(encoding="utf-8"), encoding="utf-8")
    config_path = tmp_path / "dimer.yaml"
    _write_yaml(
        config_path,
        {
            "source": ".",
            "between": [0, 1],
            "fraction": 0.5,
            "atom_indices_1_based": True,
            "active_atoms": "2-3",
            "atoms": "active",
            "output_dir": "dimer_out",
            "format": "xyz",
        },
    )

    result = generate_dimer_guess_from_config(config_path)

    assert result.output_dir == tmp_path / "dimer_out"
    assert result.selected_indices == [1, 2]
    assert len(result.files) == 1
    assert result.files[0].structure_path.exists()
    assert result.files[0].vector_path.exists()


def test_dimer_guess_yaml_accepts_null_prefix(tmp_path: Path) -> None:
    initial_path, final_path = _write_endpoint_pair(tmp_path)
    (tmp_path / "TS9-pos-Replica_nr_1-1.xyz").write_text(initial_path.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "TS9-pos-Replica_nr_2-1.xyz").write_text(final_path.read_text(encoding="utf-8"), encoding="utf-8")
    config_path = tmp_path / "dimer.yaml"
    _write_yaml(
        config_path,
        {
            "source": ".",
            "between": [0, 1],
            "fraction": 0.5,
            "prefix": None,
            "suffix": ".xyz",
            "atom_indices_1_based": True,
            "active_atoms": "2-3",
            "atoms": "active",
            "output_dir": "dimer_out",
            "format": "xyz",
        },
    )

    result = generate_dimer_guess_from_config(config_path)

    assert result.output_dir == tmp_path / "dimer_out"
    assert result.selected_indices == [1, 2]
    assert result.files[0].structure_path.exists()


def _write_endpoint_pair(tmp_path: Path) -> tuple[Path, Path]:
    initial = Atoms(
        "H3",
        positions=[
            (0.0, 0.0, 0.0),
            (1.4, 0.0, 0.0),
            (3.0, 0.0, 0.0),
        ],
        pbc=False,
    )
    final = Atoms(
        "H3",
        positions=[
            (0.0, 0.0, 0.0),
            (1.0, 0.0, 0.0),
            (2.0, 0.0, 0.0),
        ],
        pbc=False,
    )
    initial_path = tmp_path / "is.xyz"
    final_path = tmp_path / "fs.xyz"
    write(initial_path, initial, format="xyz")
    write(final_path, final, format="xyz")
    return initial_path, final_path


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
