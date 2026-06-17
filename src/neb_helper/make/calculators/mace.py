from __future__ import annotations


def make_mace_calculator(spec):
    try:
        from mace.calculators import MACECalculator, mace_mp
    except ImportError as exc:
        raise RuntimeError("MACE calculator requested, but mace-torch is not installed.") from exc

    kwargs = dict(spec.kwargs)
    if spec.head is not None:
        kwargs["head"] = spec.head
    if spec.device is not None:
        kwargs["device"] = spec.device
    if spec.dtype is not None:
        kwargs["default_dtype"] = spec.dtype

    model = spec.model
    if model is None or model.lower().startswith("mace_mp"):
        if model and ":" in model:
            kwargs.setdefault("model", model.split(":", 1)[1])
        return mace_mp(**kwargs)
    return MACECalculator(model_paths=model, **kwargs)
