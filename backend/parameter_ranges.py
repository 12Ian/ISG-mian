from __future__ import annotations

import math
import random
from decimal import Decimal
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


def default_parameter_sampling_range(parameter: dict[str, Any]) -> dict[str, Any] | None:
    """为数值参数生成约占完整允许范围三分之一的默认采样区间。"""
    ptype = normalize_parameter_type(parameter.get("type"))
    if ptype not in {"int", "float"}:
        return None
    min_value, max_value = infer_parameter_bounds(parameter)
    default = _to_float_or_none(parameter.get("default_value", parameter.get("default")))
    if min_value is None or max_value is None or default is None:
        return None

    if ptype == "int":
        lower_bound = math.ceil(min_value)
        upper_bound = math.floor(max_value)
        default_value = max(lower_bound, min(int(round(default)), upper_bound))
        if lower_bound >= upper_bound:
            return {"min": default_value, "max": default_value}
        lower = int(round(default_value - (default_value - lower_bound) / 3.0))
        upper = int(round(default_value + (upper_bound - default_value) / 3.0))
        lower = max(lower_bound, min(lower, upper_bound))
        upper = max(lower_bound, min(upper, upper_bound))
        if lower == upper:
            if upper < upper_bound:
                upper += 1
            else:
                lower -= 1
        return {"min": lower, "max": upper}

    default_value = max(min_value, min(default, max_value))
    if min_value >= max_value:
        return {"min": default_value, "max": default_value}
    precision = parameter_display_precision(parameter)
    lower = round(default_value - (default_value - min_value) / 3.0, precision)
    upper = round(default_value + (max_value - default_value) / 3.0, precision)
    return {"min": lower, "max": upper}


def parameter_display_precision(parameter: dict[str, Any]) -> int:
    """根据参数量级返回适合界面输入和展示的小数位数。"""
    if normalize_parameter_type(parameter.get("type")) == "int":
        return 0
    min_value, max_value = infer_parameter_bounds(parameter)
    if min_value is None or max_value is None:
        return 3
    span = abs(max_value - min_value)
    if span >= 10:
        precision = 1
    elif span >= 1:
        precision = 2
    elif span >= 0.1:
        precision = 3
    elif span >= 0.01:
        precision = 4
    elif span >= 0.001:
        precision = 5
    else:
        precision = 6

    for value in (
        min_value,
        max_value,
        _to_float_or_none(parameter.get("default_value", parameter.get("default"))),
    ):
        if value in (None, 0):
            continue
        exponent = Decimal(str(abs(value))).normalize().as_tuple().exponent
        if exponent < 0:
            precision = max(precision, min(-exponent, 6))
    return precision


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
        if ptype == "int":
            integer = int(round(number))
            if range_info["min_value"] is not None:
                integer = max(integer, math.ceil(range_info["min_value"]))
            if range_info["max_value"] is not None:
                integer = min(integer, math.floor(range_info["max_value"]))
            return integer
        if range_info["min_value"] is not None and number < range_info["min_value"]:
            number = range_info["min_value"]
        if range_info["max_value"] is not None and number > range_info["max_value"]:
            number = range_info["max_value"]
        return float(number)

    if value is None:
        return "" if default is None else str(default)
    return str(value)


def normalize_parameter_sampling_value(parameter: dict[str, Any], value: Any) -> Any:
    """规范化任务参数；数值区间会截断到算法边界并自动纠正顺序。"""
    ptype = normalize_parameter_type(parameter.get("type"))
    if ptype not in {"int", "float"} or not isinstance(value, dict):
        return normalize_parameter_value(parameter, value)

    default = parameter.get("default_value", parameter.get("default"))
    lower_raw = value.get("min", value.get("lower", default))
    upper_raw = value.get("max", value.get("upper", lower_raw))
    lower = normalize_parameter_value(parameter, lower_raw)
    upper = normalize_parameter_value(parameter, upper_raw)
    if lower > upper:
        lower, upper = upper, lower
    return {"min": lower, "max": upper}


def parameter_sampling_is_variable(value: Any) -> bool:
    return isinstance(value, dict) and value.get("min") != value.get("max")


def sample_parameter_value(parameter: dict[str, Any], value: Any, *, seed: str) -> Any:
    """从已规范化的数值区间采样；相等上下限按固定值处理。"""
    if not isinstance(value, dict):
        return normalize_parameter_value(parameter, value)

    normalized = normalize_parameter_sampling_value(parameter, value)
    if not isinstance(normalized, dict):
        return normalized
    lower = normalized["min"]
    upper = normalized["max"]
    if lower == upper:
        return lower

    rng = random.Random(seed)
    ptype = normalize_parameter_type(parameter.get("type"))
    if ptype == "int":
        return rng.randint(int(lower), int(upper))
    return rng.uniform(float(lower), float(upper))


def _to_float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
