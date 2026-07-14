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
