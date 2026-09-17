import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from importlib.machinery import ModuleSpec

from plugins.evaluation import yolov5_evaluator


def test_yolov5_val_loader_waits_for_a_concurrent_import_to_finish(monkeypatch):
    module_name = "isg_yolov5_val"
    previous_module = sys.modules.pop(module_name, None)
    entered = threading.Event()
    release = threading.Event()
    execution_count = 0

    class BlockingLoader:
        def create_module(self, _spec):
            return None

        def exec_module(self, module):
            nonlocal execution_count
            execution_count += 1
            module.__file__ = str(yolov5_evaluator._YOLOV5_ROOT / "val.py")
            entered.set()
            assert release.wait(timeout=5)
            module.run = object()

    def fake_spec_from_file_location(name, path):
        return ModuleSpec(name, BlockingLoader(), origin=str(path))

    monkeypatch.setattr(
        yolov5_evaluator.importlib.util,
        "spec_from_file_location",
        fake_spec_from_file_location,
    )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(yolov5_evaluator._load_yolov5_val)
            assert entered.wait(timeout=5)
            second = executor.submit(yolov5_evaluator._load_yolov5_val)
            time.sleep(0.05)
            assert not second.done()
            release.set()

            first_module = first.result(timeout=5)
            second_module = second.result(timeout=5)

        assert execution_count == 1
        assert first_module is second_module
        assert hasattr(second_module, "run")
    finally:
        sys.modules.pop(module_name, None)
        if previous_module is not None:
            sys.modules[module_name] = previous_module
