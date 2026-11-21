import json
from pathlib import Path
import sys

import pytest

from deeptrace.analyzers.artifacts import GANArtifactAnalyzer, VocoderArtifactAnalyzer
from deeptrace.analyzers.review_signals import analyze_micro_expression
from deeptrace.config import Settings
from deeptrace.schemas import MediaMetadata


def media(kind='video'):
    return MediaMetadata(filename='test.mp4', media_kind=kind, content_type='video/mp4',
        size_bytes=10, sha256='a'*64, duration_seconds=9)


def runner(tmp_path, payload):
    path = tmp_path/'bridge.py'
    path.write_text('import json; print(json.dumps('+repr(payload)+'))')
    return f'{sys.executable} "{path}"'


@pytest.mark.parametrize('analyzer', [GANArtifactAnalyzer, VocoderArtifactAnalyzer])
def test_optional_artifact_paths_fail_closed(tmp_path, analyzer):
    part = analyzer(None).analyze(tmp_path, media())
    assert part.status == 'unavailable' and part.raw_score is None
    assert part.detector_id == analyzer.detector_id
    for command in ('/missing/python', runner(tmp_path, {'fake_probability': 'invalid'})):
        part = analyzer(command).analyze(tmp_path, media())
        assert part.status == 'error' and part.raw_score is None
        assert part.detector_id == analyzer.detector_id


def test_gan_mean_rule_preserves_original_frame_times(tmp_path):
    payload = {'samples': [{'path':'frame_000009.jpg','fake_probability':.9},
        {'path':'frame_000011.jpg','fake_probability':.7}], 'checkpoint':'released#sha256=123'}
    part = GANArtifactAnalyzer(runner(tmp_path, payload), .5).analyze(tmp_path, media())
    assert part.status == 'functional' and part.raw_score == .8
    assert part.timestamps_seconds == [4, 5]
    assert part.checkpoint == 'released#sha256=123'
    assert part.anomalies[0].code == 'ELEVATED_GAN_ARTIFACT_SCORE'
    assert part.calibrated_probability is None and not part.threshold_validated
    payload['samples'][1]['fake_probability'] = .05
    part = GANArtifactAnalyzer(runner(tmp_path, payload)).analyze(tmp_path, media())
    assert not part.anomalies and not part.timestamps_seconds
    from deeptrace.ml.detectors import detection_from_component
    assert not detection_from_component(part, media(), preprocessing_version='gan-v1').findings


def test_vocoder_window_flags_are_independent_of_mean(tmp_path):
    payload = {'fake_probability':.4, 'samples':[
        {'start_time':0,'end_time':4.0375,'fake_probability':.1},
        {'start_time':4.0375,'end_time':8.075,'fake_probability':.2},
        {'start_time':8.075,'end_time':9,'fake_probability':.9}],
        'coverage':{'mode':'full','duration_seconds':9,'analyzed_seconds':9,'windows':3,'complete':True}}
    part = VocoderArtifactAnalyzer(runner(tmp_path,payload)).analyze(tmp_path,media('audio'))
    assert part.raw_score == .4 and part.timestamps_seconds == [8.075]
    assert part.anomalies[0].code == 'ELEVATED_VOCODER_ARTIFACT_SCORE'
    assert part.samples[-1].end_time == 9
    from deeptrace.ml.detectors import detection_from_component
    result = detection_from_component(part, media('audio'), preprocessing_version='lfcc-windows-v1')
    assert result.findings[-1].start_time == 8.075
    assert result.model_name == VocoderArtifactAnalyzer.model_name


def test_spotting_is_review_data_not_fake_score(tmp_path):
    payload = {'technique':'micro_expression','title':'Micro-expression intervals','modality':'video',
        'status':'measured','method':'SOFTNet','summary':'1 candidate interval',
        'measurements':{'checkpoint':'numeric.hdf5#sha256=123'},
        'intervals':[{'start_time':1,'end_time':1.4,'regression_score':1.2}]}
    check = analyze_micro_expression(runner(tmp_path,payload),tmp_path,media())
    assert check.status == 'measured' and check.intervals[0]['regression_score'] == 1.2
    assert 'fake_probability' not in check.model_dump() and not check.validated
    payload['intervals'][0]['end_time'] = .5
    assert analyze_micro_expression(runner(tmp_path,payload),tmp_path,media()).status == 'error'
    assert analyze_micro_expression('/missing/python',tmp_path,media('audio')).status == 'not_applicable'


def test_new_paths_are_off_in_portable_defaults():
    config = Settings(_env_file=None)
    assert config.gan_artifact_command is config.vocoder_artifact_command is config.micro_expression_command is None


def test_runner_help_needs_no_ml_dependencies():
    import subprocess
    scripts = Path(__file__).parents[1]/'scripts/inference'
    for name in ('cnn_artifacts.py', 'lfcc_lcnn.py', 'softnet.py'):
        result = subprocess.run([sys.executable,str(scripts/name),'--help'],capture_output=True,text=True)
        assert result.returncode == 0, result.stderr
