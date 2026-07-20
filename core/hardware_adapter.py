from __future__ import annotations


def resolve_yolo_device(requested, torch_module) -> tuple[str, str]:
    """规范化 YOLO 设备参数，并在设备不可用时安全回退。"""
    raw = str(requested or "").strip()
    normalized = raw.casefold().replace("cuda:", "")

    try:
        cuda_available = bool(torch_module.cuda.is_available())
        cuda_count = int(torch_module.cuda.device_count()) if cuda_available else 0
    except Exception:
        cuda_available = False
        cuda_count = 0

    fallback = "0" if cuda_count > 0 else "cpu"
    if normalized in {"", "auto", "none", "cuda", "gpu"}:
        return fallback, ""
    if normalized == "cpu":
        return "cpu", ""

    device_ids = []
    for token in normalized.split(","):
        token = token.strip()
        try:
            numeric = float(token)
        except (TypeError, ValueError):
            device_ids = []
            break
        if numeric < 0 or not numeric.is_integer():
            device_ids = []
            break
        device_ids.append(int(numeric))

    if device_ids and cuda_available and all(device_id < cuda_count for device_id in device_ids):
        return ",".join(str(device_id) for device_id in device_ids), ""

    requested_label = raw or "自动"
    fallback_label = "GPU 0" if fallback == "0" else "CPU"
    return fallback, f"设备参数 {requested_label!r} 不可用，已自动切换到 {fallback_label}。"
