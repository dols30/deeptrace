import json
import sys
from pathlib import Path

from deeptrace.analyzers import CombinedVideoAnalyzer, EfficientNetVideoAnalyzer, EffortVideoAnalyzer, Nes2NetAudioAnalyzer, SceneVideoAnalyzer
from deeptrace.schemas import MediaMetadata


def metadata(kind="video"):
    return MediaMetadata(filename="sample.mp4", media_kind=kind, content_type="video/mp4" if kind == "video" else "audio/wav",
        size_bytes=1, sha256="0" * 64)


def test_effort_contract(tmp_path: Path):
    bridge = tmp_path / "bridge.py"
    bridge.write_text("import json; print(json.dumps({'model_version':'abc','checkpoint':'ff.pth#sha256=x','samples':[{'fake_probability':.2},{'fake_probability':.8}]}))")
    result = EffortVideoAnalyzer(f"{sys.executable} {bridge} --frames {{frames_dir}}", 1.0).analyze(tmp_path, metadata())
    assert result.status == "functional"
    assert result.synthetic_confidence == 0.5
    assert result.timestamps_seconds == [1.0]


def test_nes2net_contract(tmp_path: Path):
    bridge = tmp_path / "bridge.py"
    bridge.write_text("import json; print(json.dumps({'model_version':'def','checkpoint':'asv.pt#sha256=y','fake_probability':.7}))")
    result = Nes2NetAudioAnalyzer(f"{sys.executable} {bridge} --audio {{audio_path}}").analyze(tmp_path / "a.wav", metadata("audio"))
    assert result.status == "functional"
    assert result.synthetic_confidence == 0.7
    assert result.anomalies[0].code == "ELEVATED_SPOOF_SCORE"


def test_unconfigured_models_fail_closed(tmp_path: Path):
    assert EffortVideoAnalyzer(None).analyze(tmp_path, metadata()).status == "unavailable"
    assert Nes2NetAudioAnalyzer(None).analyze(tmp_path, metadata("audio")).status == "unavailable"


def test_paths_with_spaces_remain_one_argument():
    from deeptrace.analyzers.base import command_args
    assert command_args('python "bridge script.py" --audio {audio_path}',
        audio_path='/tmp/file with spaces.wav') == [
        'python', 'bridge script.py', '--audio', '/tmp/file with spaces.wav']


def test_efficientnet_explainability_is_disabled_by_default(tmp_path):
    command = "python runner.py --frames {frames_dir} --explain --explain-dir {explain_dir} --device cpu"
    args = EfficientNetVideoAnalyzer(command)._runner_command(tmp_path / "frames")
    assert args == ["python", "runner.py", "--frames", str(tmp_path / "frames"), "--device", "cpu"]
    assert not (tmp_path / "attribution").exists()


def test_efficientnet_explainability_flags_are_added_when_enabled(tmp_path):
    command = "python runner.py --frames {frames_dir} --device cpu"
    args = EfficientNetVideoAnalyzer(command, explain=True)._runner_command(tmp_path / "frames")
    assert args == ["python", "runner.py", "--frames", str(tmp_path / "frames"), "--device", "cpu",
        "--explain", "--explain-dir", str(tmp_path / "attribution")]
    assert (tmp_path / "attribution").is_dir()


def test_missing_executable_fails_closed(tmp_path):
    assert Nes2NetAudioAnalyzer('/missing/deeptrace-python {audio_path}').analyze(
        tmp_path, metadata('audio')).status == 'error'
    assert EffortVideoAnalyzer('/missing/deeptrace-python {frames_dir}').analyze(
        tmp_path, metadata()).status == 'error'


def test_skipped_frames_preserve_timestamps(tmp_path):
    bridge = tmp_path / 'bridge.py'
    bridge.write_text("import json; print(json.dumps({'samples':[{'path':'frame_000009.jpg','fake_probability':0.9}], 'notes':['coverage note']}))")
    result = EffortVideoAnalyzer(f'{sys.executable} {bridge}', 2).analyze(tmp_path, metadata())
    assert result.timestamps_seconds == [16]
    assert 'coverage note' in result.notes


def test_no_faces_abstains(tmp_path):
    bridge = tmp_path / 'bridge.py'
    bridge.write_text("print('{\"samples\": [], \"notes\": [\"No faces\"]}')")
    result = EffortVideoAnalyzer(f'{sys.executable} {bridge}').analyze(tmp_path, metadata())
    assert result.status == 'unavailable'
    assert result.synthetic_confidence is None


def test_nan_score_rejected(tmp_path):
    bridge = tmp_path / 'bridge.py'
    bridge.write_text("print('{\"fake_probability\": NaN}')")
    result = Nes2NetAudioAnalyzer(f'{sys.executable} {bridge}').analyze(tmp_path, metadata('audio'))
    assert result.status == 'error'


def test_audio_coverage_notes_propagate(tmp_path):
    bridge = tmp_path / 'bridge.py'
    bridge.write_text("print('{\"fake_probability\": 0.7, \"notes\": [\"First four seconds only\"]}')")
    result = Nes2NetAudioAnalyzer(f'{sys.executable} {bridge}').analyze(tmp_path, metadata('audio'))
    assert 'First four seconds only' in result.notes


def frame_bridge(tmp_path, name, scores, notes=()):
    bridge = tmp_path / f'{name}.py'
    samples = [{'path': f'frame_{i:06d}.jpg', 'fake_probability': s} for i, s in enumerate(scores, 1)]
    bridge.write_text(f"import json; print(json.dumps({{'model_version': '{name}', 'samples': {samples!r}, 'notes': {list(notes)!r}}}))")
    return f'{sys.executable} {bridge} --frames {{frames_dir}}'


def test_scene_alerts_on_video_mean_not_single_frames(tmp_path):
    noisy_real = SceneVideoAnalyzer(frame_bridge(tmp_path, 'real', [0.1, 0.8, 0.1, 0.1])).analyze(tmp_path, metadata())
    assert noisy_real.status == 'functional' and noisy_real.synthetic_confidence == 0.275
    assert noisy_real.anomalies == [] and noisy_real.timestamps_seconds == []

    generated = SceneVideoAnalyzer(frame_bridge(tmp_path, 'fake', [0.9, 0.95, 0.3])).analyze(tmp_path, metadata())
    assert [a.code for a in generated.anomalies] == ['ELEVATED_GENERATED_SCENE_SCORE']
    assert generated.timestamps_seconds == [0.0, 1.0]


def test_combined_scores_generated_video_without_faces(tmp_path):
    face = EffortVideoAnalyzer(frame_bridge(tmp_path, 'face', [], ['Skipped 3 of 3 frames without an alignable face.']))
    scene = SceneVideoAnalyzer(frame_bridge(tmp_path, 'scene', [0.9, 0.8, 0.7]))
    result = CombinedVideoAnalyzer(face, scene).analyze(tmp_path, metadata())
    assert result.status == 'functional'
    assert result.synthetic_confidence == 0.8
    assert result.model_name == f'{face.model_name} + {scene.model_name}'
    assert any(note.startswith('Face model was unavailable') for note in result.notes)


def test_combined_takes_max_and_merges_frames(tmp_path):
    face = EffortVideoAnalyzer(frame_bridge(tmp_path, 'face', [0.2, 0.9]))
    scene = SceneVideoAnalyzer(frame_bridge(tmp_path, 'scene', [0.7, 0.1, 0.6]))
    result = CombinedVideoAnalyzer(face, scene).analyze(tmp_path, metadata())
    assert result.synthetic_confidence == max(0.55, round(1.4 / 3, 6))
    assert [s.raw_score for s in result.samples] == [0.7, 0.9, 0.6]
    assert result.model_version == 'face=face; scene=scene'
    assert [a.code for a in result.anomalies] == ['ELEVATED_FRAME_SCORE']


def test_combined_falls_back_to_face_when_scene_fails(tmp_path):
    face = EffortVideoAnalyzer(frame_bridge(tmp_path, 'face', [0.3]))
    result = CombinedVideoAnalyzer(face, SceneVideoAnalyzer('/missing/python {frames_dir}')).analyze(tmp_path, metadata())
    assert result.status == 'functional' and result.synthetic_confidence == 0.3
    assert result.model_name == face.model_name
    assert any('screening was error' in note for note in result.notes)
