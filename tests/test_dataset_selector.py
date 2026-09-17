from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import Dataset
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.log_repository import LogRepository
from backend.services.dataset_service import DatasetService


ROOT = Path(__file__).resolve().parent.parent


def test_get_all_datasets_is_not_limited_to_first_page():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, future=True)
    repository = DatasetRepository(session_factory)
    service = DatasetService(
        paths=SimpleNamespace(),
        session_factory=session_factory,
        dataset_repository=repository,
        log_repository=LogRepository(session_factory),
    )

    with session_factory() as session:
        for index in range(105):
            session.add(
                Dataset(
                    name=f"dataset-{index:03d}",
                    modality="image",
                    status="created",
                    storage_path=f"dataset-{index:03d}",
                )
            )
        session.add(
            Dataset(
                name="deleted-dataset",
                modality="image",
                status="deleted",
                storage_path="deleted-dataset",
                is_deleted=True,
            )
        )
        session.commit()

    assert len(service.get_datasets(1, 100, "")["items"]) == 100
    result = service.get_all_datasets()
    assert result["total"] == 105
    assert len(result["items"]) == 105


def test_sample_generation_uses_unpaged_dataset_signal():
    qml = (ROOT / "ui" / "views" / "SampleGenView.qml").read_text(encoding="utf-8")
    assert "getAllDatasets" in qml
    assert "onAllDatasetsUpdated" in qml
    assert "getDatasets(1, 100" not in qml


def test_combo_box_has_mouse_draggable_scrollbar():
    qml = (ROOT / "ui" / "StableComboBox.qml").read_text(encoding="utf-8")
    assert "ScrollBar.vertical" in qml
    assert "interactive: true" in qml
    assert "ScrollIndicator.vertical" not in qml


def test_training_terminal_tasks_refresh_and_delete_backend_record():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    status_handler = qml.split("function onTrainingStatusUpdated", 1)[1].split(
        "function onEvaluationStatusUpdated", 1
    )[0]
    delete_handler = qml.split("function deleteTrainingQueueItem", 1)[1].split(
        "function syncHistoryFromTrainingTask", 1
    )[0]

    assert 'backendService.getTrainingTasks(0, "")' in status_handler
    assert "backendService.deleteTask(taskId)" in delete_handler
    assert "onClicked: root.deleteTrainingQueueItem(index)" in qml


def test_device_parameter_uses_friendly_labels_without_changing_values():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")

    assert 'if (raw.toLowerCase() === "cpu") return "cpu"' in qml
    assert 'if (raw === "0") return "显卡1"' in qml
    assert 'if (raw === "1") return "显卡2"' in qml
    assert 'if (raw === "0,1") return "双显卡"' in qml
    assert "model: _optionLabels" in qml
    assert 'paramEditModel.setProperty(index, "value", _opts[currentIndex])' in qml


def test_evaluation_waits_for_all_selected_results():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    start_eval = qml.split("function startEvaluation()", 1)[1].split(
        "id: algoParamsPopup", 1
    )[0]
    result_handler = qml.split("function onEvaluationResultsUpdated", 1)[1].split(
        "Component.onCompleted", 1
    )[0]

    assert "property int expectedEvalResultCount" in qml
    assert "function fetchCompletedEvaluationResults()" in qml
    assert "root.expectedEvalResultCount = root.expectedEvalResultCount + 1" in start_eval
    assert start_eval.index("activeEvalSourceModel.append") < start_eval.index("backendService.startEvaluationTask")
    assert "root.hasEvalResult(resultId, evalTaskId, targetDatasetId, modelName)" in result_handler
    assert "root.fetchCompletedEvaluationResults()" in qml
    assert "evalResultModel.count >= root.expectedEvalResultCount" in result_handler


def test_evaluation_keeps_completed_task_pending_until_result_arrives():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    task_handler = qml.split("function onEvaluationTasksUpdated", 1)[1].split(
        "function onEvaluationResultsUpdated", 1
    )[0]
    completed_branch = task_handler.split('if (it.status === "completed")', 1)[1].split(
        '} else if (it.status === "failed")', 1
    )[0]
    result_handler = qml.split("function onEvaluationResultsUpdated", 1)[1].split(
        "Component.onCompleted", 1
    )[0]

    assert "backendService.getEvaluationResults(taskId)" in completed_branch
    assert "pendingEvalTaskIds" not in completed_branch
    assert "root.pendingEvalTaskIds = remainingIds" in result_handler


def test_evaluation_restore_refetches_missing_results():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    restore_handler = qml.split("function onSettingValueLoaded", 1)[1].split(
        "function onEvaluationScenariosUpdated", 1
    )[0]

    assert "function hasEvalResultForTask(evalTaskId)" in qml
    assert "!root.hasEvalResultForTask(restoredTaskId)" in restore_handler
    assert "root.pendingEvalTaskIds = restoredPendingIds" in restore_handler
    assert "root.isEvaluating = restoredPendingIds.length > 0" in restore_handler
    assert 'backendService.getEvaluationTasks("")' in restore_handler


def test_training_selectors_survive_page_navigation():
    qml = (ROOT / "ui" / "views" / "EvaluateView.qml").read_text(encoding="utf-8")
    dataset_handler = qml.split("function onDatasetsUpdated", 1)[1].split(
        "function onTrainingCompatibilityUpdated", 1
    )[0]
    algorithm_handler = qml.split("function onAlgorithmsUpdated", 1)[1].split(
        "function onAlgorithmBindingsUpdated", 1
    )[0]
    visible_handler = qml.split("onVisibleChanged:", 1)[1].split(
        "function refreshPage", 1
    )[0]
    refresh_handler = qml.split("function refreshPage", 1)[1].split(
        "Component.onDestruction", 1
    )[0]

    assert "previousDatasetId" in dataset_handler
    assert "datasetCombo.currentIndex = datasetModel.count > 0 ? restoredDatasetIndex : -1" in dataset_handler
    assert "if (!hasTrainingOrEvaluation) return" in algorithm_handler
    assert 'backendService.getAlgorithms("", "")' in visible_handler
    assert 'backendService.getAlgorithms("", "")' in refresh_handler
