"""NEB path builder for CP2K-oriented workflows."""

from .config import load_config

__all__ = ["load_config", "make_neb_path"]


def make_neb_path(spec):
    from .workflow import make_neb_path as _make_neb_path

    return _make_neb_path(spec)
