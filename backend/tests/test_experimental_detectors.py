import json, sys
from pathlib import Path

from deeptrace.experimental import DeMambaAdapter, FakeSTormerAdapter
from experiments.face_video_benchmark import load_manifest


def test_experimental_models_are_not_imported_by_production_api():
    source = Path('deeptrace/api.py').read_text()
    assert 'deeptrace.experimental' not in source
    assert 'FakeSTormer' not in source
    assert 'DeMamba' not in source


def test_fakestormer_missing_checkpoint_is_blocked(tmp_path):
    video = tmp_path / 'video.mp4'; video.write_bytes(b'video')
    result = FakeSTormerAdapter('runner --video {video_path}', tmp_path / 'missing.pth').predict_video(video)
    assert result.status == 'blocked'
    assert result.experimental is True
    assert 'missing' in result.error.lower()


def test_fakestormer_json_adapter(tmp_path):
    video = tmp_path / 'video.mp4'; video.write_bytes(b'video')
    checkpoint = tmp_path / 'model.pth'; checkpoint.write_bytes(b'weights')
    bridge = tmp_path / 'bridge.py'
    bridge.write_text("import json; print(json.dumps({'model_score':.82,'model_version':'official','checkpoint':'hash'}))")
    result = FakeSTormerAdapter(f'{sys.executable} {bridge} {{video_path}}', checkpoint).predict_video(video)
    assert result.status == 'score_only' and result.model_score == .82
    assert result.calibrated_probability is None and result.threshold_validated is False
    assert result.experimental is True


def test_demamba_is_explicitly_blocked(tmp_path):
    result = DeMambaAdapter().predict_video(tmp_path / 'video.mp4')
    assert result.status == 'blocked'
    assert result.model_score is None
    assert result.error.startswith('DeMamba: BLOCKED')


def test_face_manifest_groups_degradations_by_source(tmp_path):
    manifest = tmp_path / 'face.csv'
    manifest.write_text('video_id,path,label,task,generator,dataset,scenario,degradation,source_id,split,efficientnet_score,fakestormer_score\n'
        'a,a.mp4,real,face_manipulation,unknown,fixture,general,original,shared,validation,.1,.2\n'
        'b,b.mp4,real,face_manipulation,unknown,fixture,general,480p,shared,test,.1,.2\n')
    import pytest
    with pytest.raises(ValueError, match='split leakage'):
        load_manifest(manifest)
