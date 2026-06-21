"""Stable Python API for scripts and IDE users.

The command-line interface is useful for one-off shell workflows. This module
collects the same high-level operations behind importable functions so that
small Python scripts, notebooks, and IDE run configurations can drive NEB
workflows without going through argparse.
"""

from __future__ import annotations

from .make import load_config, make_neb_path
from .result import (
    BarrierSummary,
    DimerGuessConfig,
    DimerGuessFile,
    DimerGuessResult,
    NEBData,
    SliceBandResult,
    SliceImageRecord,
    TsGuessCandidate,
    TsGuessResult,
    TsGuessSpec,
    analyze_neb,
    analyze_neb_files,
    generate_dimer_guess,
    generate_dimer_guess_from_config,
    generate_ts_guess,
    load_dimer_guess_config,
    load_ts_guess_config,
    read_neb_energy,
    slice_band,
    summarize_barrier,
)

__all__ = [
    "BarrierSummary",
    "DimerGuessConfig",
    "DimerGuessFile",
    "DimerGuessResult",
    "NEBData",
    "SliceBandResult",
    "SliceImageRecord",
    "TsGuessCandidate",
    "TsGuessResult",
    "TsGuessSpec",
    "analyze_neb",
    "analyze_neb_files",
    "generate_dimer_guess",
    "generate_dimer_guess_from_config",
    "generate_ts_guess",
    "load_config",
    "load_dimer_guess_config",
    "load_ts_guess_config",
    "make_neb_path",
    "read_neb_energy",
    "slice_band",
    "summarize_barrier",
]
