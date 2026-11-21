"""Split and lifecycle safeguards do not need torch in the API environment."""
import importlib.util
import json
from pathlib import Path
import sys

import pytest
from experiments import commfor_adaptation as ca
from experiments import kaggle_banner as kb


def plan():
    rows=[]
    for category,method in [('face_manipulation','Deepfakes'),('generated_imagery','Sora'),('generated_imagery','VEO3'),('audio_spoof','spoof')]:
        for i in range(20):
            for label in (0,1):
                # Real/source siblings share a group (even though gen examples here are a toy).
                rows.append(dict(id=f'{category}-{method}-{i}-{label}',category=category,method=method,
                    label=label,source_group=f'{category}-{method}-{i}',bytes=10))
    return dict(mode='full',files=rows,limitations=[])


def test_split_is_deterministic_group_disjoint_and_keeps_seen_smoke_training_only():
    p=plan()
    split=ca.partition(p)
    assert split==ca.partition(p)
    seen={r['source_group'] for r in kb.smoke_rows(p['files'])}
    groups={name:{r['source_group'] for r in rows} for name,rows in split['rows'].items()}
    assert seen <= groups['train']
    assert not groups['train'] & groups['dev']
    assert not groups['train'] & groups['test']
    assert not groups['dev'] & groups['test']
    assert sum(map(len,split['rows'].values()))==len(p['files'])


def test_no_invented_scene_labels_from_face_or_audio_manipulation():
    assert ca.scene_label(dict(category='face_manipulation',label=1)) is None
    assert ca.scene_label(dict(category='audio_spoof',label=1)) is None
    assert ca.scene_label(dict(category='face_manipulation',label=0))==0
    assert ca.scene_label(dict(category='generated_imagery',label=1))==1


def test_no_fitting_after_holdout_opened(tmp_path,monkeypatch):
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    (tmp_path/'holdout-opened.json').write_text('{}')
    with pytest.raises(RuntimeError,match='no more fitting'):
        ca.fit(None,[],[],tmp_path,{})


def test_no_holdout_opening_without_transfer_and_terms_settings(tmp_path,monkeypatch):
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    with pytest.raises(RuntimeError,match='sizes/terms'):
        ca.evaluate_holdout(None,{}, {},tmp_path,False,True)
    assert not (tmp_path/'holdout-opened.json').exists()


def test_saturated_negative_scene_logit_does_not_overflow():
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts/inference'))
    import commfor
    assert commfor.shifted_score(-10000,1.359375)==0
    assert commfor.shifted_score(10000,1.359375)==1
    assert commfor.shifted_score(1.359375,1.359375)==.5


def test_workspace_v2_keeps_limited_coverage_incomplete_and_v1_replay_unchanged():
    from experiments.tool_evaluation import workspace_assessment,workspace_assessment_v2
    cases=json.loads((Path(__file__).parent/'fixtures/tool_workspace_v2_cases.json').read_text())
    for case in cases:
        result=workspace_assessment_v2(case['analysis'])
        assert {k:result[k] for k in case['expected']}==case['expected']
    limited=next(c for c in cases if 'limited' in c['name'])
    assert workspace_assessment(limited['analysis'])['decision']=='not_flagged'
