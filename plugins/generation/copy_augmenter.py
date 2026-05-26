from pathlib import Path
import shutil


PARAMETERS = []

def run(payload: dict, context) -> dict:
    """Generate copies of source samples with a suffix."""
    output_dir = Path(payload["output"]["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", [])
    target_count = payload.get("target_count", len(samples))

    outputs = []
    total = target_count
    for idx in range(total):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        source = samples[idx % len(samples)]
        source_path = Path(source["path"])
        target = output_dir / f"copy_{idx:04d}{source_path.suffix}"
        shutil.copy2(source_path, target)
        outputs.append({
            "source_sample_id": source["id"],
            "output_path": str(target),
            "relative_path": target.name,
            "metadata": {"method": "copy"},
            "status": "created",
        })
        context.set_progress((idx + 1) * 100 / total, f"生成 {idx + 1}/{total}")

    return {"ok": True, "outputs": outputs, "logs": []}
