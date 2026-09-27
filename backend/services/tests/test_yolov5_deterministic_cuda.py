from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_cuda_workspace_configuration_precedes_app_imports():
    main_source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
    env_config = 'os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")'

    assert env_config in main_source
    assert main_source.index(env_config) < main_source.index("from PySide6.QtGui")


def test_final_validation_does_not_fuse_weights():
    train_source = (
        ROOT / "plugins" / "detection" / "yolov5_core" / "train.py"
    ).read_text(encoding="utf-8")

    assert "model=attempt_load(f, device, fuse=False).half()" in train_source


def test_evaluation_weight_list_only_contains_saved_weights():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    upsert_weight = qml.split("function upsertWeightOption(task)", 1)[1].split(
        "// ================= 后端信号", 1
    )[0]
    saved_check = qml.split("function isWeightSaved(taskId)", 1)[1].split(
        "function findScenarioId", 1
    )[0]

    assert "!root.isWeightSaved(taskId)" in upsert_weight
    assert "return false" in saved_check


def test_saved_weight_ids_are_persisted_independently_of_training_queue():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")

    assert "property var savedWeightTaskIds: []" in qml
    assert "savedWeightTaskIds: root.savedWeightTaskIds" in qml
    assert "root.savedWeightTaskIds = state.savedWeightTaskIds || []" in qml
    assert "root.markWeightSaved(t.taskId)" in qml
    assert 'root.migrateLegacySavedWeights = !state.hasOwnProperty("savedWeightTaskIds")' in qml
    assert "暂无已保存训练权重，请先在训练区保存权重" in qml
