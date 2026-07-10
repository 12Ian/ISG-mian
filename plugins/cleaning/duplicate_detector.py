from pathlib import Path
import hashlib


PARAMETERS = []

def run(payload: dict, context) -> dict:
    """Detect duplicate samples by comparing SHA256 hashes."""
    samples = payload.get("input", {}).get("samples", [])
    if not samples:
        return {"ok": True, "suggestions": [], "logs": []}

    seen = {}
    suggestions = []
    total = len(samples)
    for idx, sample in enumerate(samples):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        context.set_progress((idx + 1) * 100 / total, f"检测重复 {idx + 1}/{total}")
        sha = sample.get("sha256") or sample.get("metadata", {}).get("sha256", "")
        if not sha:
            sha = _file_sha256(sample)
        if sha and sha in seen:
            suggestions.append({
                "sample_id": sample["id"],
                "issue_type": "duplicate",
                "suggested_action": "delete",
                "confidence": 1.0,
                "message": f"Duplicate of sample {seen[sha]}",
                "details": {"duplicate_of": seen[sha], "sha256": sha},
                "output_path": "",
            })
        else:
            seen[sha] = sample["id"]

    return {"ok": True, "suggestions": suggestions, "logs": []}


def _file_sha256(sample: dict) -> str:
    path = sample.get("sample_path") or sample.get("path") or sample.get("file_path")
    if not path:
        return ""
    file_path = Path(path)
    if not file_path.is_file():
        return ""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
