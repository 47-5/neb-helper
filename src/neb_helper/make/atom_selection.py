from __future__ import annotations

import re
from typing import Any, List, Optional, Union


AtomIndexInput = Union[int, str, list[int], tuple[int, ...], None]


_RANGE_TOKEN = re.compile(r"^(\d+)(?:-(\d+))?$")


def parse_atom_indices(
    value: AtomIndexInput,
    *,
    one_based: bool = False,
    field_name: str = "atom selection",
) -> List[int]:
    """Parse atom index lists into the internal 0-based convention.

    ``one_based=False`` preserves the historical nebmake_v2 behavior.
    ``one_based=True`` is convenient for GaussView-style selections such as
    "1-3,7", which becomes [0, 1, 2, 6].
    """
    if value is None:
        return []
    if isinstance(value, str):
        return _parse_selection(value, one_based=one_based, field_name=field_name)
    if isinstance(value, int):
        return [_convert_index(value, one_based=one_based, field_name=field_name)]
    return [_convert_index(int(index), one_based=one_based, field_name=field_name) for index in value]


def parse_atom_selector(
    value: Any,
    *,
    one_based: bool = False,
    field_name: str = "atom selector",
) -> Optional[Union[str, List[int]]]:
    """Parse fields that also accept selector words such as active/all."""
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        lowered = stripped.lower()
        if lowered in {"active", "all"}:
            return lowered
        return _parse_selection(stripped, one_based=one_based, field_name=field_name)
    if isinstance(value, int):
        return [_convert_index(value, one_based=one_based, field_name=field_name)]
    return [_convert_index(int(index), one_based=one_based, field_name=field_name) for index in value]


def _parse_selection(value: str, *, one_based: bool, field_name: str) -> List[int]:
    text = value.strip()
    if not text:
        return []

    # GaussView commonly emits comma-separated inclusive ranges. Whitespace and
    # semicolons are accepted as separators to make copy/paste forgiving.
    text = re.sub(r"\s*-\s*", "-", text)
    tokens = [token for token in re.split(r"[,;\s]+", text) if token]
    indices: List[int] = []
    for token in tokens:
        match = _RANGE_TOKEN.match(token)
        if not match:
            base = "1-based" if one_based else "0-based"
            raise ValueError(
                f"Invalid {field_name} token {token!r}. "
                f"Use {base} selection syntax like '1-15,17,21-30'."
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        _validate_index(start, one_based=one_based, field_name=field_name, token=token)
        _validate_index(end, one_based=one_based, field_name=field_name, token=token)
        if end < start:
            raise ValueError(f"Descending ranges are not supported in {field_name}: {token!r}.")
        offset = 1 if one_based else 0
        indices.extend(range(start - offset, end - offset + 1))
    return indices


def _convert_index(index: int, *, one_based: bool, field_name: str) -> int:
    _validate_index(index, one_based=one_based, field_name=field_name, token=str(index))
    return index - 1 if one_based else index


def _validate_index(index: int, *, one_based: bool, field_name: str, token: str) -> None:
    minimum = 1 if one_based else 0
    if index < minimum:
        base = "1-based" if one_based else "0-based"
        raise ValueError(f"{field_name} uses {base} indices; got {token!r}.")
