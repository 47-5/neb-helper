from __future__ import annotations

from pathlib import Path

from neb_helper.result.band_io import discover_image_files


def test_discover_image_files_accepts_cp2k_replica_suffix(tmp_path: Path) -> None:
    (tmp_path / "TS9-pos-Replica_nr_1-1.xyz").write_text("", encoding="utf-8")
    (tmp_path / "TS9-pos-Replica_nr_2-1.xyz").write_text("", encoding="utf-8")

    images = discover_image_files(tmp_path, prefix="TS9-pos-Replica_nr_", suffix=".xyz")

    assert [(item.index, item.source_index, item.path.name) for item in images] == [
        (0, 1, "TS9-pos-Replica_nr_1-1.xyz"),
        (1, 2, "TS9-pos-Replica_nr_2-1.xyz"),
    ]


def test_discover_image_files_accepts_null_prefix(tmp_path: Path) -> None:
    (tmp_path / "TS9-pos-Replica_nr_1-1.xyz").write_text("", encoding="utf-8")
    (tmp_path / "TS9-pos-Replica_nr_2-1.xyz").write_text("", encoding="utf-8")
    (tmp_path / "TS9-1.ener").write_text("", encoding="utf-8")

    images = discover_image_files(tmp_path, prefix=None, suffix=".xyz")

    assert [(item.index, item.source_index, item.path.name) for item in images] == [
        (0, 1, "TS9-pos-Replica_nr_1-1.xyz"),
        (1, 2, "TS9-pos-Replica_nr_2-1.xyz"),
    ]


def test_discover_image_files_accepts_null_suffix(tmp_path: Path) -> None:
    (tmp_path / "image_000.xyz").write_text("", encoding="utf-8")
    (tmp_path / "image_001.cif").write_text("", encoding="utf-8")
    (tmp_path / "other_002.xyz").write_text("", encoding="utf-8")

    images = discover_image_files(tmp_path, prefix="image_", suffix=None)

    assert [(item.index, item.source_index, item.path.name) for item in images] == [
        (0, 0, "image_000.xyz"),
        (1, 1, "image_001.cif"),
    ]


def test_discover_image_files_treats_prefix_as_literal(tmp_path: Path) -> None:
    (tmp_path / "image001.xyz").write_text("", encoding="utf-8")
    (tmp_path / "image_002.xyz").write_text("", encoding="utf-8")

    images = discover_image_files(tmp_path, prefix="image", suffix=".xyz")

    assert [(item.index, item.source_index, item.path.name) for item in images] == [
        (0, 1, "image001.xyz"),
    ]


def test_discover_image_files_uses_natural_filename_sort(tmp_path: Path) -> None:
    (tmp_path / "TS9-pos-Replica_nr_10-1.xyz").write_text("", encoding="utf-8")
    (tmp_path / "TS9-pos-Replica_nr_2-1.xyz").write_text("", encoding="utf-8")
    (tmp_path / "TS9-pos-Replica_nr_1-1.xyz").write_text("", encoding="utf-8")

    images = discover_image_files(tmp_path, prefix="TS9-pos-Replica_nr_", suffix=".xyz")

    assert [(item.index, item.source_index, item.path.name) for item in images] == [
        (0, 1, "TS9-pos-Replica_nr_1-1.xyz"),
        (1, 2, "TS9-pos-Replica_nr_2-1.xyz"),
        (2, 10, "TS9-pos-Replica_nr_10-1.xyz"),
    ]