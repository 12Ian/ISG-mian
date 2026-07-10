from __future__ import annotations

from typing import Any


def normalize_parameter_type(value: Any) -> str:
    ptype = str(value or "string").lower()
    if ptype == "integer":
        return "int"
    if ptype == "number":
        return "float"
    if ptype == "boolean":
        return "bool"
    return ptype


def normalize_parameter_options(parameter: dict[str, Any]) -> list[Any]:
    options = parameter.get("options")
    if options is None:
        options = parameter.get("options_json")
    if isinstance(options, list):
        return options
    return []


def infer_parameter_bounds(parameter: dict[str, Any]) -> tuple[float | None, float | None]:
    min_value = parameter.get("min_value")
    if min_value is None:
        min_value = parameter.get("min")
    max_value = parameter.get("max_value")
    if max_value is None:
        max_value = parameter.get("max")
    if min_value is not None or max_value is not None:
        return _to_float_or_none(min_value), _to_float_or_none(max_value)

    ptype = normalize_parameter_type(parameter.get("type"))
    if ptype not in {"int", "float"}:
        return None, None

    name = str(parameter.get("name", "")).lower()
    label = str(parameter.get("label", "")).lower()
    key = f"{name} {label}"

    if any(token in key for token in ("learning_rate", "learn_rate", " lr")):
        return 0.000001, 1.0
    if any(token in key for token in ("discriminator_iterations", "n_critic", "critic_iters")):
        return 1.0, 20.0
    if any(token in key for token in ("ratio", "prob", "confidence", "alpha", "mix_ratio")):
        return 0.0, 1.0
    if any(token in key for token in ("strength", "intensity", "amount", "opacity", "blend", "weight")):
        return 0.0, 1.0
    if "epoch" in key:
        return 1.0, 1000.0
    if any(token in key for token in ("iterations", "iteration", "iters", "steps", "step", "n_critic", "critic_iters")):
        return 1.0, 1000.0
    if "batch" in key:
        return 1.0, 4096.0
    if "seed" in key:
        return 0.0, 999999.0
    if any(token in key for token in ("width", "height", "img_size", "image_size", "resolution")):
        return 1.0, 10000.0
    if any(token in key for token in ("window", "hidden_size", "size")):
        return 1.0, 4096.0
    if any(token in key for token in ("angle", "degree", "rotation")):
        return -360.0, 360.0
    if "hue" in key:
        return -180.0, 180.0
    if any(token in key for token in ("scale", "zoom")):
        return 0.1, 5.0
    if "brightness" in key:
        return -1.0, 1.0
    if any(token in key for token in ("contrast", "saturation", "gain", "volume", "amplitude")):
        return 0.0, 3.0
    if any(token in key for token in ("kernel", "radius")):
        return 1.0, 99.0
    if any(token in key for token in ("count", "num_", "layers", "layer")):
        return 1.0, 1000.0
    if any(token in key for token in ("freq", "frequency", "hz")):
        return 0.0, 48000.0
    if "db" in key:
        return -120.0, 120.0
    if "hamming" in key or "hash" in key:
        return 1.0, 64.0
    if "blur_threshold" in key:
        return 1.0, 1000.0
    if "noise_threshold" in key:
        return 0.0, 255.0
    if "zscore_threshold" in key:
        return 1.0, 10.0
    if "snr_threshold" in key:
        return 0.0, 100.0
    if "threshold" in key:
        default = _to_float_or_none(parameter.get("default_value", parameter.get("default")))
        if default is not None and default > 1.0:
            return 0.0, max(default * 10, 1.0)
        return 0.0, 1.0

    default = parameter.get("default_value")
    if default is None:
        default = parameter.get("default")
    default_number = _to_float_or_none(default)
    if default_number is None:
        return 0.0, 1.0
    if default_number < 0:
        span = max(abs(default_number) * 10, 1.0)
        return -span, span
    return 0.0, max(default_number * 10, 1.0)


def normalized_parameter_range(parameter: dict[str, Any]) -> dict[str, Any]:
    min_value, max_value = infer_parameter_bounds(parameter)
    options = normalize_parameter_options(parameter)
    ptype = normalize_parameter_type(parameter.get("type"))
    if not options and ptype == "bool":
        options = [False, True]
    return {"min_value": min_value, "max_value": max_value, "options": options}


def normalize_parameter_value(parameter: dict[str, Any], value: Any) -> Any:
    ptype = normalize_parameter_type(parameter.get("type"))
    range_info = normalized_parameter_range(parameter)
    options = range_info["options"]
    default = parameter.get("default_value", parameter.get("default"))

    if ptype == "select":
        if value in options:
            return value
        value_text = str(value)
        for option in options:
            if str(option) == value_text:
                return option
        return default if default in options else (options[0] if options else default)

    if ptype == "bool":
        if isinstance(value, bool):
            return value
        value_text = str(value).strip().lower()
        if value_text in {"true", "1", "yes", "y", "on"}:
            return True
        if value_text in {"false", "0", "no", "n", "off"}:
            return False
        return bool(default) if isinstance(default, bool) else False

    if ptype in {"int", "float"}:
        number = _to_float_or_none(value)
        if number is None:
            number = _to_float_or_none(default)
        if number is None:
            number = range_info["min_value"] if range_info["min_value"] is not None else 0.0
        if range_info["min_value"] is not None and number < range_info["min_value"]:
            number = range_info["min_value"]
        if range_info["max_value"] is not None and number > range_info["max_value"]:
            number = range_info["max_value"]
        if ptype == "int":
            return int(round(number))
        return float(number)

    if value is None:
        return "" if default is None else str(default)
    return str(value)


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
