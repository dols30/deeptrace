import json
from pathlib import Path

import pytest

from experiments.tool_evaluation import assessment, metrics, summarize

CASES = json.loads((Path(__file__).parent / 'fixtures/tool_assessment_cases.json').read_text())


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['name'])
def test_existing_report_overview_contract(case):
    result = assessment(case['report'])
    assert {key: result[key] for key in case['expected']} == case['expected']


def record(identifier, label, decision, category='audio'):
    return dict(id=identifier, label=label, source_group=identifier, category=category,
                assessment={'decision': decision}, report_generated=True)


def test_unavailable_results_stay_in_denominator_and_categories():
    records = [record('real-ok', 0, 'not_flagged'), record('real-fp', 0, 'flagged'),
               record('fake-ok', 1, 'flagged'), record('fake-miss', 1, 'not_flagged'),
               record('fake-error', 1, 'error', 'video'), record('real-incomplete', 0, 'incomplete', 'video')]
    result = summarize(records)
    overall = result['overall']
    assert overall['confusion_matrix_decidable'] == dict(tp=1, tn=1, fp=1, fn=1)
    assert overall['accuracy_counting_incomplete_incorrect'] == 2 / 6
    assert overall['false_positive_rate_all_genuine'] == 1 / 3
    assert overall['false_positive_rate_decidable_genuine'] == .5
    assert overall['manipulation_recall_all_manipulated'] == 1 / 3
    assert overall['abstentions_or_errors_by_label'] == dict(genuine=1, manipulated=1)
    assert result['by_category']['video']['decision_coverage'] == 0
    assert not overall['subset_numeric_targets_met']
    assert not overall['poc_acceptance_established']


def test_target_is_strictly_below_ten_percent_false_alarms():
    records = [record(str(i), 0, 'flagged' if i == 0 else 'not_flagged') for i in range(10)]
    records += [record('f'+str(i), 1, 'flagged') for i in range(10)]
    assert metrics(records)['accuracy_counting_incomplete_incorrect'] == .95
    assert not metrics(records)['subset_numeric_targets_met']
    records[0]['assessment']['decision'] = 'not_flagged'
    assert metrics(records)['subset_numeric_targets_met']
    assert not metrics(records)['poc_acceptance_established']


def test_duplicate_ids_and_invalid_labels_are_rejected():
    with pytest.raises(ValueError): metrics([record('x', 0, 'flagged')] * 2)
    with pytest.raises(ValueError): metrics([record('x', True, 'flagged')])
    with pytest.raises(ValueError): metrics([])


WORKSPACE_CASES = json.loads((Path(__file__).parent / 'fixtures/tool_workspace_cases.json').read_text())


@pytest.mark.parametrize('case', WORKSPACE_CASES, ids=lambda case: case['name'])
def test_persisted_workspace_banner_contract(case):
    from experiments.tool_evaluation import workspace_assessment
    result = workspace_assessment(case['analysis'])
    assert {key: result[key] for key in case['expected']} == case['expected']
