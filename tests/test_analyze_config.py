from __future__ import annotations

from pathlib import Path

import yaml
from ase import Atoms
from ase.io import write

from neb_helper import analyze_neb_from_config, load_analyze_config


def test_analyze_accepts_yaml_config_with_relative_paths(tmp_path: Path) -> None:
    _write_energy_file(tmp_path / "band.ener")
    _write_images(tmp_path)
    config_path = tmp_path / "analyze.yaml"
    _write_yaml(
        config_path,
        {
            "input": {
                "energy_file": "band.ener",
                "xyz_glob": "image_*.xyz",
                "image_count": 3,
                "energy_unit": "ev",
                "relative": True,
            },
            "plot": {
                "smooth": False,
                "dpi": 72,
            },
            "output": {
                "image": "out/profile.png",
                "summary": "out/result.txt",
                "write_summary": True,
                "write_xyz": True,
                "xyz": "out/images.xyz",
            },
        },
    )

    config = load_analyze_config(config_path)
    assert config.energy_file == tmp_path / "band.ener"
    assert config.output_image == tmp_path / "out" / "profile.png"

    data, summary = analyze_neb_from_config(config_path)

    assert len(data.energies) == 3
    assert summary.forward_barrier == 1.0
    assert summary.reverse_barrier == 0.75
    assert summary.reaction_energy == 0.25
    assert (tmp_path / "out" / "profile.png").exists()
    assert (tmp_path / "out" / "result.txt").exists()
    assert (tmp_path / "out" / "images.xyz").exists()


def _write_energy_file(path: Path) -> None:
    path.write_text("# step E0 E1 E2 d01 d12\n0 0.0 1.0 0.25 1.0 1.0\n", encoding="utf-8")


def _write_images(tmp_path: Path) -> None:
    for index, x in enumerate((0.0, 1.0, 2.0)):
        atoms = Atoms("H", positions=[(x, 0.0, 0.0)], pbc=False)
        write(tmp_path / f"image_{index:03d}.xyz", atoms, format="xyz")


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
