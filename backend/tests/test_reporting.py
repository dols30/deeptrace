from deeptrace.schemas import ComponentResult, MediaMetadata
from deeptrace.reporting import build_report


def test_report_excludes_nonfunctional_scores_and_marks_partial_coverage():
    media = MediaMetadata(filename='sample.mp4', media_kind='video', content_type='video/mp4', size_bytes=4, sha256='a'*64)
    components = [
        ComponentResult(component='video', status='functional', model_name='EfficientNet-B4', model_version='pinned', synthetic_confidence=0.8),
        ComponentResult(component='audio', status='error', model_name='AASIST', model_version='unknown', synthetic_confidence=0.1),
    ]
    report = build_report(media, components)
    assert report.overall_synthetic_confidence is None
    assert report.evidence_summary[0]['model_score'] == 0.8
    assert 'independent' in report.summary
    assert 'incomplete' in report.summary
    assert report.integrity['received_file_hash'] == 'a'*64
    assert report.generated_at.utcoffset().total_seconds() == 0
    assert report.review_status == 'Pending qualified human review'
    assert {r['organization'] for r in report.references} == {'SWGDE', 'LEVA'}
    assert any('draft' in r['version'] for r in report.references)
    assert any('low score does not establish authenticity' in text for text in report.limitations)
    assert build_report(media, components).report_id != report.report_id


def test_stub_never_contributes_to_overall_score():
    media = MediaMetadata(filename='sample.wav', media_kind='audio', content_type='audio/wav', size_bytes=4, sha256='b'*64)
    stub = ComponentResult(component='audio', status='stub', model_name='fixture', model_version='0', synthetic_confidence=0.9)
    assert build_report(media, [stub]).overall_synthetic_confidence is None


def test_report_never_averages_independent_detector_scores():
    media = MediaMetadata(filename='sample.mp4', media_kind='video', content_type='video/mp4', size_bytes=4, sha256='c'*64)
    parts = [
        ComponentResult(component='video', status='functional', model_name='face', model_version='1',
            task='face_manipulation', synthetic_confidence=.9),
        ComponentResult(component='video', status='functional', model_name='scene', model_version='1',
            task='synthetic_video', synthetic_confidence=.6),
        ComponentResult(component='audio', status='functional', model_name='audio', model_version='1',
            task='audio_spoof', synthetic_confidence=.1),
    ]
    report = build_report(media, parts)
    assert report.overall_synthetic_confidence is None
    assert [item['model_score'] for item in report.evidence_summary] == [.9, .6, .1]
    assert not any(item.code == 'MODEL_DISAGREEMENT' for item in report.anomalies)
