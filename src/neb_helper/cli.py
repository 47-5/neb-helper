from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import __version__


_COMMANDS = {"make", "analyze", "dimer", "slice"}
_TOP_LEVEL_OPTIONS = {"-h", "--help", "--version"}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)

    if _should_use_legacy_make_dispatch(args):
        from .make.cli import main as make_main

        return make_main(args)

    parser = _build_parser()
    namespace, remaining = parser.parse_known_args(args)

    if namespace.command == "make":
        from .make.cli import main as make_main

        return make_main(remaining)

    if namespace.command == "analyze":
        from .result.analyze import main as analyze_main

        return analyze_main(remaining)

    if namespace.command == "dimer":
        from .result.dimer_guess import main as dimer_main

        return dimer_main(remaining)

    if namespace.command == "slice":
        from .result.slice_band import main as slice_main

        return slice_main(remaining)

    parser.print_help()
    return 0


def _should_use_legacy_make_dispatch(args: list[str]) -> bool:
    if not args:
        return False
    first = args[0]
    if first in _COMMANDS or first in _TOP_LEVEL_OPTIONS:
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="neb-helper",
        description="Tools for NEB path construction, analysis, and derived workflows.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"neb-helper {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="command")
    subparsers.add_parser(
        "make",
        help="Build a CP2K-oriented NEB path from an initial/final structure config.",
        add_help=False,
    )
    subparsers.add_parser(
        "analyze",
        help="Analyze NEB result files and plot an energy profile.",
        add_help=False,
    )
    subparsers.add_parser(
        "dimer",
        help="Generate DIMER guesses from an existing NEB image pair.",
        add_help=False,
    )
    subparsers.add_parser(
        "slice",
        help="Crop and optionally resample a segment of an existing NEB band.",
        add_help=False,
    )
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
