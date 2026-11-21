"""Coverage records observe source detection and preserve upstream detector returns."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from deeptrace.analyzers.video import EfficientNetVideoAnalyzer
from deeptrace.ml.detectors import detection_from_component
from deeptrace.schemas import MediaMetadata

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('face_coverage', ROOT/'scripts/inference/face_coverage.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_source_detection_and_alignment_are_distinct_without_extra_detector_calls():
    values = [[], ['source-face'], [], ['source-face'], ['crop-face']]
    calls = []
    def detector(*args, **kwargs):
        calls.append((args,kwargs))
        return values.pop(0)
    tracker = module.FaceCoverageTracker(detector)
    tracker.begin_frame()
    assert tracker('frame0',1) == []
    tracker.finish_frame(False)
    tracker.begin_frame()
    assert tracker('frame1',1) == ['source-face']
    assert tracker('crop1',1) == []
    tracker.finish_frame(False)
    tracker.begin_frame()
    assert tracker('frame2',1) == ['source-face']
    assert tracker('crop2',1) == ['crop-face']
    tracker.finish_frame(True)
    assert len(calls) == 5
    assert tracker.summary() == dict(mode='face_alignment_v1',frames_sampled=3,
        frames_with_detected_face=2,frames_without_detected_face=1,
        frames_with_unalignable_face=1,frames_scored=1,complete=False)


def run(tmp_path,coverage,scores):
    payload = dict(samples=[dict(path=f'frame_{i:06d}.jpg',fake_probability=s) for i,s in enumerate(scores,1)],coverage=coverage)
    script=tmp_path/'runner.py'
    script.write_text('import json; print(json.dumps('+repr(payload)+'))')
    media=MediaMetadata(filename='v.mp4',media_kind='video',content_type='video/mp4',size_bytes=1,sha256='0'*64)
    return EfficientNetVideoAnalyzer(f'{sys.executable} {script}').analyze(tmp_path,media), media


def test_unscored_faces_remain_unavailable_and_keep_coverage(tmp_path):
    c=dict(mode='face_alignment_v1',frames_sampled=3,frames_with_detected_face=1,
           frames_without_detected_face=2,frames_with_unalignable_face=1,frames_scored=0,complete=False)
    result,_=run(tmp_path,c,[])
    assert result.status=='unavailable' and result.raw_score is None
    assert result.coverage==c


def test_partial_face_coverage_reaches_workflow_metadata(tmp_path):
    c=dict(mode='face_alignment_v1',frames_sampled=4,frames_with_detected_face=2,
           frames_without_detected_face=2,frames_with_unalignable_face=1,frames_scored=1,complete=False)
    result,media=run(tmp_path,c,[.1])
    assert result.status=='functional' and result.raw_score==.1
    assert [a.code for a in result.anomalies]==['LIMITED_FACE_COVERAGE']
    detection=detection_from_component(result,media,preprocessing_version='test')
    assert detection.metadata['coverage']==c
    assert detection.metadata['coverage_limited'] is True
    assert not detection.findings


@pytest.mark.parametrize('change',[dict(frames_scored=2),dict(frames_sampled=True),dict(complete=True),dict(frames_without_detected_face=9)])
def test_inconsistent_coverage_fails_closed(tmp_path,change):
    c=dict(mode='face_alignment_v1',frames_sampled=4,frames_with_detected_face=2,
           frames_without_detected_face=2,frames_with_unalignable_face=1,frames_scored=1,complete=False)
    c.update(change)
    result,_=run(tmp_path,c,[.1])
    assert result.status=='error' and result.raw_score is None
