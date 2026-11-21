import csv, json

import pytest

from experiments.synthetic_video_benchmark import aggregate, load_manifest, run, select_threshold


def write_manifest(path, rows):
    fields = ['video_id','path','label','task','generator','dataset','scenario','degradation','source_id','split','frame_scores','temporal_score']
    with path.open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)


def row(video_id, label, split, scores, degradation='original'):
    return {'video_id': video_id, 'path': f'{video_id}.mp4', 'label': label, 'task': 'synthetic_video',
        'generator': 'unknown', 'dataset': 'fixture', 'scenario': 'general', 'degradation': degradation,
        'source_id': video_id, 'split': split,
        'frame_scores': json.dumps(scores), 'temporal_score': ''}


def test_community_aggregations():
    values = aggregate([.1, .2, .9, 1.0])
    assert values['mean'] == pytest.approx(.55)
    assert values['median'] == pytest.approx(.55)
    assert values['max'] == 1
    assert values['p90'] == 1
    assert values['high_score_fraction'] == .5


def test_variants_cannot_cross_splits(tmp_path):
    manifest = tmp_path / 'manifest.csv'
    first, second = row('same-original', 'real', 'validation', [.1]), row('same-480p', 'real', 'test', [.2], '480p')
    first['source_id'] = second['source_id'] = 'same-source'
    write_manifest(manifest, [first, second])
    with pytest.raises(ValueError, match='split leakage'):
        load_manifest(manifest)


def test_threshold_is_selected_from_validation_only(tmp_path):
    manifest, output = tmp_path / 'manifest.csv', tmp_path / 'results'
    write_manifest(manifest, [row('vr', 'real', 'validation', [.1]), row('vf', 'synthetic', 'validation', [.9]),
        row('tr', 'real', 'test', [.95]), row('tf', 'synthetic', 'test', [.96])])
    run(manifest, output)
    threshold = json.loads((output / 'thresholds.json').read_text())['community_forensics']['target_fpr_10']
    assert threshold == .9
    # Test scores would have selected a different threshold; they must not affect it.
    assert json.loads((output / 'metrics.json').read_text())['community_forensics']['fpr'] == 1.0


def test_unvalidated_model_score_is_not_probability():
    from deeptrace.schemas import ComponentResult
    result = ComponentResult(component='video', status='functional', model_name='m', model_version='1',
        synthetic_confidence=.84, threshold=.5, threshold_source='default_model_decision_rule')
    assert result.raw_score == .84
    assert result.calibrated_probability is None
    assert result.threshold_validated is False
    assert result.detector_status == 'score_only'
    assert result.operational_status == 'threshold_not_validated'


def test_green_yellow_red_are_operational_not_truth_claims():
    from deeptrace.schemas import operational_status
    assert operational_status(.2, .4, .7, validated=True) == 'green_not_flagged'
    assert operational_status(.5, .4, .7, validated=True) == 'yellow_review_recommended'
    assert operational_status(.8, .4, .7, validated=True) == 'red_flagged'
    assert operational_status(.99, .4, .7, validated=False) == 'threshold_not_validated'
    assert 'authentic' not in operational_status(.2, .4, .7, validated=True)
    assert 'confirmed' not in operational_status(.8, .4, .7, validated=True)
