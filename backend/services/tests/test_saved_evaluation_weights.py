from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _evaluate_qml() -> str:
    return (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")


def test_evaluation_list_filters_unsaved_weights():
    qml = _evaluate_qml()
    upsert_weight = qml.split("function upsertWeightOption(task)", 1)[1].split(
        "// ================= 后端信号", 1
    )[0]

    assert "!root.isWeightSaved(taskId)" in upsert_weight
    assert "暂无已保存训练权重，请先在训练区保存权重" in qml


def test_saved_weight_ids_survive_queue_clear_and_restart():
    qml = _evaluate_qml()

    assert "property var savedWeightTaskIds: []" in qml
    assert "savedWeightTaskIds: root.savedWeightTaskIds" in qml
    assert "root.savedWeightTaskIds = state.savedWeightTaskIds || []" in qml
    assert "root.markWeightSaved(t.taskId)" in qml
    assert 'root.migrateLegacySavedWeights = !state.hasOwnProperty("savedWeightTaskIds")' in qml
