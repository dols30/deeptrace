import io
import json
from pathlib import Path
import zipfile

import pytest

from experiments import kaggle_banner as kb
from experiments.tool_evaluation import workspace_assessment


def test_mac_guard_prevents_downloads_before_network(monkeypatch):
    monkeypatch.setattr(kb.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(kb.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('Network on Mac'))
    with pytest.raises(RuntimeError, match='hosted Kaggle'):
        kb.fetch_verified({'bytes': 100, 'sha256': 'x', 'url': 'https://example.test'}, Path('/tmp/unused'))


def test_frozen_protocol_normalizes_json_and_rejects_changes(tmp_path):
    path = tmp_path/'protocol.json'
    key = kb.freeze(path, {'repo': ('source', 'revision')})
    assert kb.freeze(path, {'repo': ('source', 'revision')}) == key
    with pytest.raises(RuntimeError, match='Frozen'):
        kb.freeze(path, {'repo': ('source', 'changed')})
    assert json.loads(path.read_text()) == {'repo': ['source', 'revision']}


class Response(io.BytesIO):
    def __init__(self, content, headers, status=200):
        super().__init__(content)
        self.headers, self.status = headers, status


def test_bounded_download_resumes_only_confirmed_range(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, 'cloud_only', lambda: None)
    target = tmp_path/'model.pt'
    target.with_suffix('.pt.part').write_bytes(b'ab')
    asset = {'bytes': 6, 'sha256': kb.hashlib.sha256(b'abcdef').hexdigest(), 'url':'https://example.test/file'}
    def open_response(request, **_):
        assert request.get_header('Range') == 'bytes=2-'
        return Response(b'cdef', {'Content-Length':'4', 'Content-Range':'bytes 2-5/6'}, 206)
    monkeypatch.setattr(kb.urllib.request, 'urlopen', open_response)
    assert kb.fetch_verified(asset,target).read_bytes() == b'abcdef'
    monkeypatch.setattr(kb.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('Cached bytes redownloaded'))
    assert kb.fetch_verified(asset,target) == target


def test_bounded_download_refuses_unexpected_size_or_html(monkeypatch, tmp_path):
    monkeypatch.setattr(kb, 'cloud_only', lambda: None)
    asset = {'bytes': 6, 'sha256': 'unused', 'url': 'https://example.test'}
    monkeypatch.setattr(kb.urllib.request, 'urlopen', lambda *a, **kw: Response(b'abcdefg', {'Content-Length':'7'}))
    with pytest.raises(RuntimeError, match='size differs'): kb.fetch_verified(asset,tmp_path/'model')
    monkeypatch.setattr(kb.urllib.request, 'urlopen', lambda *a, **kw: Response(b'abcdef', {'Content-Length':'6','Content-Type':'text/html'}))
    with pytest.raises(RuntimeError, match='HTML'): kb.fetch_verified(asset,tmp_path/'model')
    assert not list(tmp_path.iterdir())


def test_audio_selection_is_balanced_deterministic_and_grouped():
    rows = [dict(id=f'{label}-{i}',label=label,speaker=f's{i%10}',method=f'A{i%8}') for label in (0,1) for i in range(100)]
    selected = kb.balanced_audio(rows)
    assert selected == kb.balanced_audio(rows)
    assert len({r['id'] for r in selected}) == 80
    assert sum(r['label'] for r in selected) == 40
    assert len({r['speaker'] for r in selected if r['label']==0}) == 10
    assert len({r['method'] for r in selected if r['label']==1}) == 8


def test_smoke_contains_both_classes_and_both_generated_sources():
    rows = [dict(id=f'{category}-{label}-{i}',category=category,label=label,method=('Sora' if i%2==0 else 'VEO3'))
            for category in ('face_manipulation','audio_spoof','generated_imagery') for label in (0,1) for i in range(4)]
    selected = kb.smoke_rows(rows)
    assert len(selected) == 12 and sum(r['label'] for r in selected) == 6
    assert {r['method'] for r in selected if r['category']=='generated_imagery' and r['label']} == {'Sora','VEO3'}


def test_false_alarm_attribution_and_report_workspace_disagreement(tmp_path):
    component = dict(detector_id='cnn_gan_artifacts',model_name='CNNDetection',component='video',status='functional',raw_score=.7,threshold=.5,timestamps_seconds=[],anomalies=[])
    record = dict(id='real',label=0,category='generated_imagery',source_group='real',method='MSVD',elapsed_seconds=1,upload_sha256='abc',
                  report_generated=True,report_retrieved=True,workspace_retrieved=True,
                  report={'components':[component]},assessment={'decision':'flagged','flagging_detectors':['cnn_gan_artifacts'],'missing_checks':0},
                  report_assessment={'decision':'incomplete','limited_face_coverage':True},core_only_assessment={'decision':'not_flagged'})
    result = kb.export_results([record],tmp_path,expected=1,mode='smoke')
    assert result['overall']['confusion_matrix_decidable']['fp'] == 1
    assert result['report_overview']['overall']['decision_coverage'] == 0
    assert result['banner_disagreements'] == ['real']
    assert result['files_with_limited_face_coverage'] == 1
    assert next(r for r in result['flag_contributions'] if r['detector_id']=='cnn_gan_artifacts')['sole_flagger_genuine_files'] == 1
    assert result['overall']['subset_numeric_targets_met'] is None
    assert result['per_detector_on_appropriate_category']['cnn_gan_artifacts']['subset_numeric_targets_met'] is None
    assert result['same_outputs_without_artifact_checks']['overall']['subset_numeric_targets_met'] is None
    assert result['workflow_success'] == 1


def test_resume_does_not_rerun_cached_errors_or_ignore_changed_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(kb, 'cloud_only', lambda: None)
    row = dict(id='id',label=1,category='audio_spoof',source_group='s',method='A01',upload_sha256='abc')
    protocol = {'mode':'smoke'}
    calls=[]
    def evaluate(*_):
        calls.append(1)
        return dict(row,report_generated=False,report_retrieved=False,workspace_retrieved=False,assessment={'decision':'error'},elapsed_seconds=1)
    monkeypatch.setattr(kb,'evaluate_file',evaluate)
    kb.run_evaluation(None,[row],tmp_path,protocol)
    kb.run_evaluation(None,[row],tmp_path,protocol)
    assert len(calls)==1
    with pytest.raises(RuntimeError, match='Cached record'):
        kb.run_evaluation(None,[dict(row,upload_sha256='changed')],tmp_path,protocol)


def test_export_archive_excludes_inputs_checkpoints_database_and_secrets(tmp_path):
    (tmp_path/'records').mkdir()
    for name in ('protocol.json','summary.json','records/ok.json','reports.db','.env','secret.mp4','weights.pt'):
        (tmp_path/name).write_text('{}')
    target=kb.export_archive(tmp_path,tmp_path/'results.zip')
    with zipfile.ZipFile(target) as archive:
        assert set(archive.namelist()) == {'protocol.json','summary.json','records/ok.json'}


def test_workflow_banner_causes_map_by_model_and_modality():
    analysis={'model_runs':[{'model_name':'LFCC','modality':'audio','status':'functional','raw_score':.1,'threshold':.5}],
              'findings':[{'model_name':'LFCC','modality':'audio'}]}
    result=workspace_assessment(analysis,{('LFCC','audio'):'lfcc_lcnn_artifacts'})
    assert result['flagging_detectors']==['lfcc_lcnn_artifacts']
    assert result['decision']=='flagged'


def test_unscored_silent_video_audio_retains_known_identity_without_changing_report():
    component={'detector_id':None,'model_name':'AASIST','status':'not_applicable','raw_score':None}
    assert kb.component_identity(component)=='aasist'
    assert component['detector_id'] is None
    assert kb.component_identity({'model_name':'Unknown'}) is None


def test_missing_torchaudio_install_preserves_torch_and_uses_supported_wheel(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=1 if '-c' in args else 0,stdout='')
    monkeypatch.setattr(kb.subprocess,'run',run)
    monkeypatch.setattr(kb.subprocess,'check_output',lambda *a,**kw:'2.11.0+cu130\n')
    assert kb.ensure_torchaudio({'torch':'2.12.0+cu130','cuda':'13.0'})=='2.11.0+cu130'
    pip=calls[1]
    assert '--no-deps' in pip and 'torchaudio==2.11.0' in pip
    assert 'https://download.pytorch.org/whl/cu130' in pip
    assert not any(arg.startswith(('torch==','torchvision==')) for arg in pip)


@pytest.mark.parametrize('python_version, expected', [((3,11),'scikit-image==0.24.0'),((3,12),'scikit-image==0.24.0'),((3,13),'scikit-image==0.25.2')])
def test_image_dependency_uses_python_313_wheel_without_changing_older_runtimes(monkeypatch, tmp_path, python_version, expected):
    from types import SimpleNamespace
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    monkeypatch.setattr(kb,'gpu_info',lambda:{'available':True})
    monkeypatch.setattr(kb.shutil,'which',lambda _: '/usr/bin/tool')
    monkeypatch.setattr(kb,'sys',SimpleNamespace(executable='/usr/bin/python3',version_info=python_version))
    calls=[]
    class StopBeforeInstalling(Exception): pass
    def capture(args,**kwargs):
        calls.append(args)
        raise StopBeforeInstalling()
    monkeypatch.setattr(kb.subprocess,'run',capture)
    with pytest.raises(StopBeforeInstalling):
        kb.setup_runtime(tmp_path,[],allow_downloads=True)
    command=calls[0]
    assert expected in command
    assert '--only-binary=scikit-image' in command
    assert '-q' not in command
    assert not any(arg.startswith(('torch==','torchvision==')) for arg in command)


def test_working_pinned_dlib_is_reused_without_installing(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(kb.subprocess,'run',run)
    assert kb.ensure_dlib(tmp_path)=='19.24.6'
    assert len(calls)==1 and '-c' in calls[0]
    assert 'dlib.__version__' in calls[0][-1]
    assert not list(tmp_path.iterdir())


def test_dlib_build_pins_tools_limits_workers_and_retains_compiler_output(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    monkeypatch.setattr(kb.shutil,'which',lambda _:'/usr/bin/tool')
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        if len(calls)==1:return SimpleNamespace(returncode=1)
        if 'stdout' in kwargs:kwargs['stdout'].write('CMake full diagnostic\n')
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(kb.subprocess,'run',run)
    assert kb.ensure_dlib(tmp_path)=='19.24.6'
    assert calls[1][0][-3:]==['cmake==3.31.6','setuptools==80.9.0','wheel==0.45.1']
    build,options=calls[2]
    assert '--no-build-isolation' in build and '--no-deps' in build and '--verbose' in build
    assert '--force-reinstall' in build and 'dlib==19.24.6' in build
    assert options['env']['CMAKE_BUILD_PARALLEL_LEVEL']=='1'
    assert options['stderr']==kb.subprocess.STDOUT
    assert (tmp_path/'dlib-build.log').read_text()=='CMake full diagnostic\n'
    assert len(calls)==4  # Verify import/version and HOG detector in a fresh process after build.
    assert not any(arg.startswith(('torch==','torchvision==')) for command,_ in calls for arg in command)


def test_dlib_failure_exposes_log_and_stops_before_model_transfer(monkeypatch,tmp_path):
    from types import SimpleNamespace
    monkeypatch.setattr(kb,'cloud_only',lambda:None)
    monkeypatch.setattr(kb.shutil,'which',lambda _:'/usr/bin/tool')
    def run(args,**kwargs):
        if 'stdout' in kwargs:kwargs['stdout'].write('c++: fatal error: compiler killed\n')
        return SimpleNamespace(returncode=0 if 'cmake==3.31.6' in args else 1)
    monkeypatch.setattr(kb.subprocess,'run',run)
    with pytest.raises(RuntimeError,match='dlib-build.log'):
        kb.ensure_dlib(tmp_path)
    assert 'compiler killed' in (tmp_path/'dlib-build.log').read_text()
