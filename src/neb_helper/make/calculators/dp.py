from __future__ import annotations


def make_dp_calculator(spec):
    try:
        from deepmd.calculator import DP
    except ImportError as exc:
        raise RuntimeError("DeepMD calculator requested, but deepmd is not installed.") from exc

    kwargs = dict(spec.kwargs)
    if spec.head is not None:
        kwargs["head"] = spec.head
    return DP(model=spec.model, **kwargs)
