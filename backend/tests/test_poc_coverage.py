import json
import sys
from pathlib import Path

import pytest

from deeptrace.analyzers.audio import AASISTAudioAnalyzer
from deeptrace.analyzers.review_signals import analyze_review_signals, empty_checks
from deeptrace.config import Settings
from deeptrace.schemas import AdvisoryReport, MediaMetadata

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts/inference"))
from audio_windows import windows
from review_math import closure_intervals, eye_aspect_ratio


def media(kind="audio"):
    return MediaMetadata(filename="example.wav", media_kind=kind, content_type="audio/wav", size_bytes=10, sha256="a"*64, duration_seconds=9)


def runner(tmp_path, payload):
    p=tmp_path/"runner.py"
    p.write_text("import json; print(json.dumps("+repr(payload)+"))")
    return f'{sys.executable} "{p}"'


def window_payload():
    return {"fake_probability":.4, "aggregation_method":"mean_nonoverlapping_window_score_v1",
        "coverage":{"mode":"full", "analyzed_seconds":9, "duration_seconds":9,"windows":3,"complete":True},
        "samples":[{"start_time":a,"end_time":b,"fake_probability":s} for a,b,s in [(0,4.0375,.1),(4.0375,8.075,.2),(8.075,9,.9)]]}


def test_full_windows_cover_remainder_without_padding_timestamps():
    assert list(windows(16000*9,"full")) == [(0,64600),(64600,129200),(129200,144000)]
    assert list(windows(16000*9)) == [(0,64600)]
    assert list(windows(5,"full")) == [(0,5)]
    with pytest.raises(ValueError): list(windows(0,"full"))


def test_window_alert_survives_low_mean_and_preserves_coverage(tmp_path):
    part=AASISTAudioAnalyzer(runner(tmp_path,window_payload()),window_mode="full").analyze(tmp_path,media())
    assert part.status == "functional"
    assert part.raw_score == .4
    assert part.timestamps_seconds == [8.075]
    assert part.samples[-1].end_time == 9
    assert part.coverage["complete"]
    assert part.anomalies[0].code == "ELEVATED_SPOOF_SCORE"
    from deeptrace.ml.detectors import detection_from_component
    part.attribution={"windows":[{"start_time":0,"end_time":.5,"relevance":.1}]}
    detection=detection_from_component(part,media(),preprocessing_version="full-window-v1")
    assert detection.findings[-1].start_time == 8.075
    assert detection.findings[-1].attribution == {}
    assert detection.findings[-1].attribution_method is None


@pytest.mark.parametrize("damage",["gap","duration","mean","overlap","windows"])
def test_false_audio_coverage_claim_fails_closed(tmp_path,damage):
    payload=window_payload()
    if damage == "gap": payload["samples"][1]["start_time"] += .1
    if damage == "duration": payload["coverage"]["duration_seconds"] = 20
    if damage == "mean": payload["fake_probability"] = .99
    if damage == "overlap": payload["samples"][1]["start_time"] = 2
    if damage == "windows": payload["coverage"]["windows"] = 4
    assert AASISTAudioAnalyzer(runner(tmp_path,payload)).analyze(tmp_path,media()).status == "error"


def test_supplementary_contract_and_error_states(tmp_path):
    checks=[item.model_dump() for item in empty_checks(media())]
    checks[-1].update(status="measured",measurements={"level_changes":2})
    result=analyze_review_signals(runner(tmp_path,{"checks":checks}),tmp_path,media())
    assert result[-1].status == "measured"
    assert result[0].status == "not_applicable"
    assert len(analyze_review_signals(None,tmp_path,media())) == 7
    checks[-1]["validated"]=True
    assert analyze_review_signals(runner(tmp_path,{"checks":checks}),tmp_path,media())[-1].status == "error"
    assert analyze_review_signals('/missing/python',tmp_path,media())[-1].status == "error"
    assert analyze_review_signals(runner(tmp_path,{"checks":checks[:-1]}),tmp_path,media())[-1].status == "error"


def test_eye_closures_do_not_bridge_tracking_loss_or_incomplete_blinks():
    points=[(0,0),(1,1),(2,1),(3,0),(2,-1),(1,-1)]
    assert eye_aspect_ratio(points) == pytest.approx(2/3)
    samples=[(0,.3),(.1,.1),(.2,.1),(.3,.3),(.4,.1),(.5,None),(.6,.3),(.7,.1)]
    assert closure_intervals(samples,.2,.15) == [{"start_time":.1,"end_time":.3,"description":"Candidate eye closure"}]


def test_sandbox_profile_requires_real_access_configuration():
    with pytest.raises(ValueError,match="requires authentication"):
        Settings(_env_file=None,deployment_mode="sandbox")
    with pytest.raises(ValueError,match="credentials"):
        Settings(_env_file=None,deployment_mode="sandbox",auth_enabled=True)
    config=Settings(_env_file=None,deployment_mode="sandbox",auth_enabled=True,employee_username="test",employee_password="test-only",jwt_secret="x"*32)
    assert config.auth_enabled


def test_legacy_report_remains_readable():
    from deeptrace.reporting import build_report
    payload=build_report(media(),[]).model_dump()
    payload.pop("review_checks")
    payload.pop("processing")
    restored=AdvisoryReport.model_validate(payload)
    assert restored.review_checks == [] and restored.processing == {}
