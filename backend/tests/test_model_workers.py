"""Warm model workers and parallel detector orchestration. No checkpoints or torch needed."""
import ast
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from deeptrace.analyzers import runner
from deeptrace.analyzers.audio import AudioCommandAnalyzer
from deeptrace.analyzers.video import SceneVideoAnalyzer
from deeptrace.config import settings
from deeptrace.schemas import MediaMetadata

INFERENCE = Path(__file__).parents[1] / "scripts" / "inference"

FAKE_RUNNER = '''
import argparse
import os

CALLS = 0


def main(argv=None):
    global CALLS
    CALLS += 1
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail", action="store_true")
    parser.add_argument("--frames")
    parser.add_argument("--audio")
    args = parser.parse_args(argv)
    if args.fail:
        raise ValueError("runner refused input")
    print("third-party progress output")  # must never reach the protocol stream
    if args.audio:
        return {"fake_probability": 0.7, "model_version": "fake@1", "checkpoint": "fake#sha256=0",
            "samples": [{"start_time": 0, "end_time": 2, "fake_probability": 0.7}]}
    if args.frames:
        return {"model_version": "fake@1", "checkpoint": "fake#sha256=0", "samples": [
            {"path": "frame_000001.jpg", "fake_probability": 0.2},
            {"path": "frame_000002.jpg", "fake_probability": 0.9}]}
    return {"pid": os.getpid(), "calls": CALLS}


if __name__ == "__main__":
    import json
    import sys
    from contextlib import redirect_stdout
    with redirect_stdout(sys.stderr):
        payload = main()
    print(json.dumps(payload))
'''


@pytest.fixture
def runner_dir(tmp_path, monkeypatch):
    directory = tmp_path / "inference"
    directory.mkdir()
    shutil.copy(INFERENCE / "worker.py", directory / "worker.py")
    (directory / "fake.py").write_text(FAKE_RUNNER)
    monkeypatch.setattr(settings, "model_workers", True)
    yield directory
    runner.shutdown_workers()


def call(directory, *args):
    return json.loads(runner.run_command([sys.executable, str(directory / "fake.py"), *args], timeout=30))


def test_warm_worker_keeps_one_process_between_requests(runner_dir):
    first, second = call(runner_dir), call(runner_dir)
    assert first["pid"] == second["pid"] != os.getpid()
    assert (first["calls"], second["calls"]) == (1, 2)


def test_runner_error_is_reported_like_a_failed_subprocess_and_worker_survives(runner_dir):
    before = call(runner_dir)
    with pytest.raises(subprocess.CalledProcessError) as error:
        call(runner_dir, "--fail")
    assert "ValueError: runner refused input" in error.value.stderr
    assert call(runner_dir)["pid"] == before["pid"]


def test_bad_arguments_are_reported_not_fatal(runner_dir):
    with pytest.raises(subprocess.CalledProcessError) as error:
        call(runner_dir, "--unknown-flag")
    assert "rejected its arguments" in error.value.stderr
    assert call(runner_dir)["calls"] >= 1


def test_crashed_worker_is_restarted(runner_dir):
    first = call(runner_dir)
    os.kill(first["pid"], signal.SIGKILL)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(first["pid"], 0)
        except ProcessLookupError:
            break
        time.sleep(0.02)
    second = call(runner_dir)
    assert second["pid"] != first["pid"]
    assert second["calls"] == 1


def test_disabled_workers_use_one_shot_subprocesses(runner_dir, monkeypatch):
    monkeypatch.setattr(settings, "model_workers", False)
    first, second = call(runner_dir), call(runner_dir)
    assert first["pid"] != second["pid"]
    assert first["calls"] == second["calls"] == 1


def test_scripts_without_a_worker_fall_back_to_subprocess(runner_dir):
    (runner_dir / "worker.py").unlink()
    first, second = call(runner_dir), call(runner_dir)
    assert first["pid"] != second["pid"]


def test_unstartable_worker_falls_back_to_subprocess(runner_dir):
    (runner_dir / "worker.py").write_text("raise SystemExit(3)\n")
    assert call(runner_dir)["calls"] == 1


def test_adapters_produce_identical_results_with_and_without_workers(runner_dir, monkeypatch, tmp_path):
    metadata = MediaMetadata(filename="clip.mp4", media_kind="video", content_type="video/mp4",
        size_bytes=1, sha256="a" * 64, duration_seconds=2)
    script = runner_dir / "fake.py"

    class FakeAudio(AudioCommandAnalyzer):
        model_name = "Fake audio"
        command_setting = "UNUSED"

    def results():
        scene = SceneVideoAnalyzer(f'{sys.executable} "{script}" --frames {{frames_dir}}')
        audio = FakeAudio(f'{sys.executable} "{script}" --audio {{audio_path}}')
        return (scene.analyze(tmp_path, metadata).model_dump(), audio.analyze(tmp_path / "a.wav", metadata).model_dump())

    warm = results()
    monkeypatch.setattr(settings, "model_workers", False)
    cold = results()
    assert warm == cold
    assert warm[0]["status"] == warm[1]["status"] == "functional"


def test_every_runner_main_accepts_argv():
    """worker.py calls main(argv); a runner that reads sys.argv would silently ignore the request."""
    for path in INFERENCE.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "main":
                assert [arg.arg for arg in node.args.args] == ["argv"], path.name
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "parse_args" and not node.args and path.name != "worker.py"):
                pytest.fail(f"{path.name} calls parse_args() without argv")


def test_independent_detectors_run_concurrently(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from deeptrace import api
    from deeptrace.db.session import reset_engine
    from deeptrace.main import app

    monkeypatch.setattr(settings, "report_db_path", tmp_path / "deeptrace.db")
    monkeypatch.setattr(settings, "report_media_dir", tmp_path / "report-media")
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{tmp_path / 'workflow.db'}")
    reset_engine()
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "video_model", "efficientnetb4")
    monkeypatch.setattr(settings, "efficientnet_decision_rule", "default_0_5")
    for name in ("gan_artifact_command", "vocoder_artifact_command", "micro_expression_command", "review_signals_command"):
        monkeypatch.setattr(settings, name, None)

    def slow(name, payload):
        script = tmp_path / f"{name}.py"
        script.write_text(f"import json, time; time.sleep(1); print(json.dumps({payload!r}))")
        return f'{sys.executable} "{script}"'

    frames_payload = {"model_version": "fake@1", "samples": [{"path": "frame_000001.jpg", "fake_probability": 0.1}]}
    monkeypatch.setattr(settings, "efficientnet_command", slow("face", frames_payload) + " --frames {frames_dir}")
    monkeypatch.setattr(settings, "scene_command", slow("scene", frames_payload) + " --frames {frames_dir}")
    monkeypatch.setattr(settings, "aasist_command", slow("audio", {"fake_probability": 0.2}) + " --audio {audio_path}")
    monkeypatch.setattr(api, "extract_metadata", lambda *a, **kw: MediaMetadata(filename="test.mp4", media_kind="video",
        content_type="video/mp4", size_bytes=5, sha256="a" * 64, duration_seconds=2))
    monkeypatch.setattr(api, "prepare_video", lambda *a, **kw: (tmp_path, tmp_path / "audio.wav"))
    monkeypatch.setattr(api, "cleanup_prepared", lambda *a: None)
    client = TestClient(app)

    def screen(parallel):
        monkeypatch.setattr(settings, "max_parallel_runners", parallel)
        started = time.monotonic()
        report = client.post("/v1/analyze", files={"file": ("test.mp4", b"video", "video/mp4")}).json()
        return report, time.monotonic() - started

    sequential, sequential_seconds = screen(1)
    parallel, parallel_seconds = screen(3)
    assert sequential_seconds >= 3
    assert parallel_seconds < 2.5
    order = lambda report: [(c["component"], c["task"], c["status"], c["synthetic_confidence"]) for c in report["components"]]
    assert order(parallel) == order(sequential)
    assert [c["task"] for c in parallel["components"]] == ["face_manipulation", "synthetic_video", "audio_spoof"]


def test_cached_provenance_follows_replaced_files(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(INFERENCE))
    import common
    weights = tmp_path / "model.pth"
    weights.write_bytes(b"first")
    first = common.checkpoint_id(weights)
    assert common.checkpoint_id(weights) == first
    weights.write_bytes(b"replaced weights")
    assert common.checkpoint_id(weights) != first
    loads = []
    load = lambda: loads.append(1) or len(loads)
    assert common.cached(("m", common.file_key(weights)), load) == common.cached(("m", common.file_key(weights)), load) == 1
    weights.write_bytes(b"third version of weights")
    assert common.cached(("m", common.file_key(weights)), load) == 2
