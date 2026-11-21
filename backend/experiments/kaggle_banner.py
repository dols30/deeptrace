"""Hosted Kaggle evaluation of the real five-detector API and report banner.

No model training, threshold fitting, production changes or media downloads on Mac.
See KAGGLE_BANNER.md; generated notebooks embed a verified, allowlisted source bundle.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import platform
import random
import shlex
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

from experiments.tool_evaluation import assessment, component_flagged, metrics, summarize, workspace_assessment_v2 as workspace_assessment

SEED = 20261112
PROTOCOL_VERSION = 'five_detector_banner_v2'
COMGEN_REV = '17f9ab6c548d9a30f5b22c09e17daee74536b653'
DETECTORS = {'deepfakebench_efficientnet_b4': 'face_manipulation',
             'community_forensics': 'generated_imagery', 'cnn_gan_artifacts': 'generated_imagery',
             'aasist': 'audio_spoof', 'lfcc_lcnn_artifacts': 'audio_spoof'}
DETECTOR_NAMES = {
    'DeepfakeBench EfficientNet-B4':'deepfakebench_efficientnet_b4',
    'Community Forensics ViT-S/384 (frontier fine-tune)':'community_forensics',
    'AASIST':'aasist', 'CNNDetection ResNet-50 (blur/JPEG)':'cnn_gan_artifacts',
    'ASVspoof DF LFCC-LCNN':'lfcc_lcnn_artifacts',
}
CORE = {'deepfakebench_efficientnet_b4', 'community_forensics', 'aasist'}
REPOS = {
    'DeepfakeBench': ('https://github.com/SCLBD/DeepfakeBench.git', 'f188b1c105465e2e5377eb536a95022ae0e4522d'),
    'aasist': ('https://github.com/clovaai/aasist.git', 'a04c9863f63d44471dde8a6abcb3b082b07cd1d1'),
    'CNNDetection': ('https://github.com/PeterWang512/CNNDetection.git', 'ea0b5622365e3a9cd31d1b54b6b5971131a839ab'),
    'asvspoof2021': ('https://github.com/asvspoof-challenge/2021.git', '9b33f5eca887bd3bf629e3fb79428cd9bb7ac972'),
}


def component_identity(component):
    # Existing API preparation-error/no-audio records can omit detector_id.
    # Resolve only a known fixed model name, preserving the raw report unchanged.
    return component.get('detector_id') or DETECTOR_NAMES.get(component.get('model_name'))


def cloud_only():
    if platform.system() == 'Darwin' or not Path('/kaggle/input').is_dir() or not Path('/kaggle/working').is_dir():
        raise RuntimeError('Run inside a hosted Kaggle Notebook. No media or models are downloaded to your Mac.')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temp.replace(path)


def freeze(path, value):
    path = Path(path)
    value = json.loads(json.dumps(value, sort_keys=True, allow_nan=False))
    if path.exists() and json.loads(path.read_text()) != value:
        raise RuntimeError('Frozen inputs/configuration differ. Preserve this run; use a new run directory.')
    write_json(path, value)
    return fingerprint(value)


def fetch_verified(asset, target):
    """Resume only byte ranges the server explicitly confirms; never exceed the fixed size."""
    cloud_only()
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = asset['bytes']
    if target.exists():
        if target.stat().st_size == expected and digest(target) == asset['sha256']:
            return target
        raise RuntimeError('Existing asset does not match the pinned hash: ' + target.name)
    part = target.with_suffix(target.suffix + '.part')
    offset = part.stat().st_size if part.exists() else 0
    if offset > expected:
        raise RuntimeError('Partial file exceeds budget')
    if offset < expected:
        headers = {'User-Agent': 'deeptrace-poc'}
        if offset:
            headers['Range'] = f'bytes={offset}-'
        with urllib.request.urlopen(urllib.request.Request(asset['url'], headers=headers), timeout=120) as response:
            if offset and (response.status != 206 or response.headers.get('Content-Range') != f'bytes {offset}-{expected-1}/{expected}'):
                raise RuntimeError('Server cannot safely resume; partial bytes were preserved')
            length = response.headers.get('Content-Length')
            if length is not None and int(length) != expected - offset:
                raise RuntimeError('Asset size differs from the disclosed download plan')
            if 'text/html' in response.headers.get('Content-Type', ''):
                raise RuntimeError('Received an HTML page instead of the asset')
            with part.open('ab') as stream:
                while chunk := response.read(min(1024 * 1024, expected - offset + 1)):
                    offset += len(chunk)
                    if offset > expected:
                        raise RuntimeError('Download byte limit exceeded')
                    stream.write(chunk)
    if part.stat().st_size != expected or digest(part) != asset['sha256']:
        raise RuntimeError('Asset integrity mismatch; no inference was started for this asset')
    part.replace(target)
    return target


def gpu_info():
    # Torch stays inside subprocesses, including this device probe.
    code = "import json,torch; print(json.dumps({'torch':torch.__version__,'torchvision':__import__('torchvision').__version__,'cuda':torch.version.cuda,'available':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}))"
    result = json.loads(subprocess.check_output([sys.executable, '-c', code], text=True))
    if not result['available']:
        raise RuntimeError('Select an available GPU in Kaggle Settings; no CPU fallback is used.')
    return result


def ensure_torchaudio(gpu):
    """Install only a matching audio wheel if the hosted image lacks a usable one."""
    cloud_only()
    import re
    probe = [sys.executable, '-c', "import torchaudio; print(torchaudio.__version__)"]
    check = subprocess.run(probe, capture_output=True, text=True)
    base = gpu['torch'].split('+')[0]
    parts = base.split('.')
    release = '2.11.0' if len(parts)>=2 and all(p.isdigit() for p in parts[:2]) and tuple(map(int,parts[:2])) >= (2,11) else base
    if check.returncode or check.stdout.strip().split('+')[0] != release:
        if not re.fullmatch(r'\d+\.\d+\.\d+', base) or not re.fullmatch(r'\d+\.\d+', gpu['cuda'] or ''):
            raise RuntimeError('Use a stable CUDA torch runtime with matching torchaudio; no torch replacement is attempted')
        index = 'https://download.pytorch.org/whl/cu'+gpu['cuda'].replace('.', '')
        subprocess.run([sys.executable,'-m','pip','install','--no-deps','--force-reinstall',
                        'torchaudio=='+release,'--index-url',index],check=True)
    version = subprocess.check_output(probe,text=True).strip()
    if version.split('+')[0] != release:
        raise RuntimeError('torchaudio must match the recorded torch compatibility policy')
    return version


def ensure_dlib(runtime):
    """Keep the benchmark dlib version; isolate its source build and retain diagnostics."""
    cloud_only()
    probe = [sys.executable, '-c', "import dlib; assert dlib.__version__ == '19.24.6'; dlib.get_frontal_face_detector(); print(dlib.__version__)"]
    check = subprocess.run(probe, capture_output=True, text=True)
    if check.returncode == 0:
        print('Verified existing dlib 19.24.6; no rebuild.', flush=True)
        return '19.24.6'
    if not all(shutil.which(name) for name in ('g++', 'make')):
        raise RuntimeError('dlib source build requires g++ and make in the hosted runtime')
    # Older upstream CMake projects need a compatible CMake. --no-build-isolation
    # ensures pip uses these tools rather than a separate, unconstrained toolchain.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=:all:',
                    'cmake==3.31.6', 'setuptools==80.9.0', 'wheel==0.45.1'], check=True)
    env = dict(os.environ, CMAKE_BUILD_PARALLEL_LEVEL='1')
    log = Path(runtime)/'dlib-build.log'
    log.parent.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, '-m', 'pip', 'install', '--verbose', '--no-build-isolation',
               '--no-deps', '--force-reinstall', '--no-cache-dir', 'dlib==19.24.6']
    print('Building pinned dlib with one compiler worker; full log:', log, flush=True)
    with log.open('w') as stream:
        result = subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, text=True)
    tail = '\n'.join(log.read_text(errors='replace').splitlines()[-100:])
    print(tail, flush=True)
    if result.returncode:
        raise RuntimeError('dlib build failed. Full compiler output is in '+str(log)+'; paste its last 100 lines. No dataset/model download was started by this build step.')
    subprocess.run(probe, check=True)
    return '19.24.6'


def setup_runtime(runtime, catalog, allow_downloads=False):
    cloud_only()
    runtime = Path(runtime).resolve()
    if not allow_downloads:
        raise RuntimeError('Read the printed byte plan, then set ALLOW_CLOUD_DOWNLOADS=True to fetch assets inside Kaggle.')
    gpu = gpu_info()
    if not all(shutil.which(name) for name in ('ffmpeg', 'ffprobe', 'git')):
        raise RuntimeError('Kaggle runtime needs ffmpeg, ffprobe and git')
    before = gpu.copy()
    # Preserve Kaggle CUDA torch/torchvision. This does not install requirements-models-cpu.txt.
    subprocess.run([sys.executable, '-m', 'pip', 'install', '--only-binary=scikit-image', '-r', str(runtime/'backend/requirements.txt'),
                    'httpx==0.28.1', 'timm==1.0.30', 'safetensors==0.8.0',
                    'librosa==0.10.2.post1', 'soundfile==0.12.1', 'efficientnet-pytorch==0.7.1',
                    ('scikit-image==0.25.2' if sys.version_info[:2] == (3, 13) else 'scikit-image==0.24.0'), 'imutils==0.5.4', 'PyYAML==6.0.2'], check=True)
    ensure_dlib(runtime)
    audio_version = ensure_torchaudio(gpu)
    print('Matching torchaudio:', audio_version, flush=True)
    if gpu_info() != before:
        raise RuntimeError('CUDA torch/torchvision changed during setup; restart and inspect dependency installation')
    for name, (url, revision) in REPOS.items():
        target = runtime/'backend/vendor'/name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            env = dict(os.environ, GIT_LFS_SKIP_SMUDGE='1')
            subprocess.run(['git', 'clone', '--filter=blob:none', '--no-checkout', url, str(target)], check=True, env=env)
            subprocess.run(['git', '-C', str(target), 'checkout', '--detach', revision], check=True, env=env)
        actual = subprocess.check_output(['git', '-C', str(target), 'rev-parse', 'HEAD'], text=True).strip()
        if actual != revision or subprocess.check_output(['git','-C',str(target),'status','--porcelain'],text=True).strip():
            raise RuntimeError('Upstream source differs from pinned clean revision: ' + name)
    for asset in catalog:
        print('Model asset:', asset['destination'], f"{asset['bytes']/1e6:.2f} MB", flush=True)
        fetch_verified(asset, runtime/'backend'/asset['destination'])
    return gpu


def balanced_audio(rows, per_class=40):
    rng = random.Random(SEED)
    chosen = []
    for label in (0, 1):
        groups = defaultdict(list)
        for row in rows:
            if row['label'] == label:
                groups[row['method'] if label else row['speaker']].append(row)
        keys = sorted(groups)
        rng.shuffle(keys)
        for key in keys:
            rng.shuffle(groups[key])
        selected = []
        while len(selected) < per_class:
            added = False
            for key in keys:
                if groups[key]:
                    selected.append(groups[key].pop())
                    added = True
                    if len(selected) == per_class:
                        break
            if not added:
                raise RuntimeError('Insufficient unused evaluation utterances')
        chosen.extend(selected)
    return chosen


def smoke_rows(rows):
    """Twelve fixed files; no outcome-based replacement and no acceptance claim."""
    selected = []
    for category in ('face_manipulation', 'audio_spoof', 'generated_imagery'):
        group = [r for r in rows if r['category'] == category]
        selected.extend([r for r in group if r['label'] == 0][:2])
        fakes = [r for r in group if r['label'] == 1]
        if category == 'generated_imagery':
            selected.extend(next(r for r in fakes if r['method'] == method) for method in ('Sora', 'VEO3'))
        else:
            selected.extend(fakes[:2])
    return selected


def find_input(slug, required, override=None):
    cloud_only()
    if override:
        root = Path(override).resolve()
        if not root.is_relative_to(Path('/kaggle/input').resolve()) or not (root/required).is_file():
            raise RuntimeError('Input override must identify the attached dataset under /kaggle/input')
        return root
    roots = [Path('/kaggle/input')/slug]
    roots += list(Path('/kaggle/input/datasets').glob('*/'+slug))
    for parent in list(roots):
        roots += list((parent/'versions').glob('*'))
    found = sorted({p.resolve() for p in roots if (p/required).is_file()})
    if len(found) != 1 or not found[0].is_relative_to(Path('/kaggle/input').resolve()):
        raise RuntimeError('Attach the pinned dataset; set its exact mounted root if ambiguous: ' + slug)
    return found[0]


def plan_inputs(assets, mode='smoke', face_input=None, audio_input=None):
    cloud_only()
    if mode not in ('smoke', 'full'):
        raise ValueError('RUN_SIZE must be smoke or full')
    assets = Path(assets)
    face_root = find_input('ffpp-core-c23-videos', 'index.csv', face_input)
    audio_root = find_input('asvpoof-2019-dataset-la', 'LA/ASVspoof2019_LA_eval/flac/LA_E_2581583.flac', audio_input)
    facts = json.loads((assets/'selection-facts.json').read_text())
    if digest(face_root/'index.csv') != facts['ffpp_index_sha256']:
        raise RuntimeError('FF++ mounted index differs from pinned version 2')
    protocols = list(audio_root.rglob('ASVspoof2019.LA.cm.eval.trl.txt'))
    if len(protocols) != 1 or digest(protocols[0]) != facts['audio_eval_protocol_sha256']:
        raise RuntimeError('ASVspoof mounted evaluation protocol differs from pinned version 1')
    excluded = set(facts['previous_audio_ids'])
    audio = []
    for line in protocols[0].read_text().splitlines():
        speaker, identifier, _, attack, label = line.split()
        if label not in ('bonafide', 'spoof'):
            raise RuntimeError('Unexpected official audio label')
        if identifier not in excluded:
            source = 'LA/ASVspoof2019_LA_eval/flac/' + identifier + '.flac'
            audio.append(dict(id='asv2019:'+identifier, label=int(label == 'spoof'), category='audio_spoof',
                              source_group='asv2019:'+speaker, speaker=speaker, method=attack, source_path=source))
    audio = balanced_audio(audio)
    face = json.loads((assets/'fresh-face-selection.json').read_text())
    generated = json.loads((assets/'fresh-generated-selection.json').read_text())
    all_rows = face + audio + generated
    selected = smoke_rows(all_rows) if mode == 'smoke' else all_rows
    for row in selected:
        if row['category'] != 'generated_imagery':
            root = face_root if row['category'] == 'face_manipulation' else audio_root
            path = (root/row['source_path']).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise RuntimeError('Selected input missing or unsafe: ' + row['id'])
            size = path.stat().st_size
            if row.get('bytes', size) != size:
                raise RuntimeError('Selected FF++ size differs from pinned metadata')
            row.update(path=str(path), bytes=size)
        if row['bytes'] > 100 * 1024 * 1024:
            raise RuntimeError('A selected file exceeds the app upload limit')
    if len({r['id'] for r in selected}) != len(selected):
        raise RuntimeError('Duplicate selected file IDs')
    plan = {'protocol_version': PROTOCOL_VERSION, 'mode': mode, 'seed': SEED, 'files': selected,
            'class_counts': dict(Counter(str(r['label']) for r in selected)),
            'category_counts': dict(Counter(r['category'] for r in selected)),
            'attached_selected_bytes': sum(r['bytes'] for r in selected if r['category'] != 'generated_imagery'),
            'generated_download_bytes': sum(r['bytes'] for r in selected if r['category'] == 'generated_imagery'),
            'sources': {'ffpp': {'ref': 'abbasaliyev/ffpp-core-c23-videos', 'version': 2, 'index_sha256':facts['ffpp_index_sha256']},
                        'audio': {'ref':'anishsarkar22/asvpoof-2019-dataset-la', 'version':1, 'protocol_sha256':digest(protocols[0])},
                        'generated': {'ref':'OmerXYZ/comgenvid', 'revision':COMGEN_REV, 'metadata_sha256':facts['comgen_metadata_sha256']}},
            'limitations': ['Previously scored utterance IDs and FF++ source sequences excluded; checkpoint training overlap remains unknown.',
                           'Fresh ASVspoof utterances may share speakers with earlier tests; this is not a new speaker-disjoint dataset.',
                           'ComGenVid is non-DPS media; source/prompt independence and creator rights remain limited.',
                           'Whole-file generated-video labels do not label its audio track as spoofed.',
                           'No dedicated joint audio-and-face manipulation benchmark or operational acceptance is established.']}
    print(json.dumps({k:v for k,v in plan.items() if k not in ('files','sources')}, indent=2))
    return plan


def stage_inputs(plan, root, allow_downloads=False, accept_terms=False):
    cloud_only()
    if not allow_downloads or not accept_terms:
        raise RuntimeError('Review sizes and linked source/research terms, then explicitly enable the notebook settings.')
    root = Path(root)
    freeze(root/'selection.json', plan)
    selected = []
    for row in plan['files']:
        item = row.copy()
        if row['category'] == 'generated_imagery':
            from urllib.parse import quote
            # Percent characters in literal repository filenames must also be URL-encoded.
            url = 'https://huggingface.co/datasets/OmerXYZ/comgenvid/resolve/'+COMGEN_REV+'/'+quote(row['source_path'], safe='/')
            path = fetch_verified(dict(row, url=url), root/'generated'/row['source_path'])
        else:
            path = Path(row['path'])
        item['source_sha256'] = digest(path)
        if row['category'] == 'audio_spoof':
            target = root/'wav'/(path.stem+'.wav')
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(path),'-c:a','pcm_s16le',str(target)],check=True,timeout=60)
            path = target
            item['conversion'] = 'Lossless FLAC decode to PCM16 WAV; original channels/sample rate retained'
        item.update(upload_path=str(path), upload_bytes=path.stat().st_size, upload_sha256=digest(path))
        if item['upload_bytes'] > 100*1024*1024:
            raise RuntimeError('Converted upload exceeds app limit')
        selected.append(item)
    freeze(root/'input-receipt.json', selected)
    return selected


def configure_app(runtime, run, aasist_window='full', device='cuda'):
    cloud_only()
    if aasist_window not in ('first', 'full') or device != 'cuda':
        raise ValueError('Use a recorded first/full AASIST policy and CUDA; no silent fallback')
    runtime, run = Path(runtime).resolve(), Path(run).resolve()
    backend = runtime/'backend'
    for key in list(os.environ):
        if key.startswith('DEEPTRACE_'):
            del os.environ[key]
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    py = shlex.quote(sys.executable)
    def command(script, args):
        return py+' '+shlex.quote(str(backend/'scripts/inference'/script))+' '+args+' --device cuda'
    def q(path):
        return shlex.quote(str(backend/path))
    values = {
        'AUTH_ENABLED':'false', 'USE_MOCK_DETECTORS':'false', 'ASSISTANT_PROVIDER':'rules',
        'DEPLOYMENT_MODE':'local', 'VIDEO_MODEL':'efficientnetb4', 'AUDIO_MODEL':'aasist',
        'AASIST_WINDOW_MODE':aasist_window, 'EFFICIENTNET_DECISION_RULE':'ffpp_c23_kaggle_v1',
        'FRAME_INTERVAL_SECONDS':'1', 'MAX_FRAMES':'120', 'DECISION_THRESHOLD':'0.5', 'EXPLAIN':'false',
        'KEEP_UPLOADS':'false', 'UPLOAD_DIR':str(run/'tmp'), 'REPORT_DB_PATH':str(run/'reports.db'),
        'REPORT_MEDIA_DIR':str(run/'stored-media'), 'DATABASE_URL':'sqlite:///'+str(run/'workflow.db'),
        'EFFICIENTNET_COMMAND':command('efficientnetb4.py','--repo '+q('vendor/DeepfakeBench')+' --weights '+q('models/efficientnetb4/effnb4_best.pth')+' --landmarks '+q('models/efficientnetb4/shape_predictor_81_face_landmarks.dat')+' --frames {frames_dir}'),
        'SCENE_COMMAND':command('commfor.py','--weights '+q('models/commfor/frontier.safetensors')+' --config '+q('models/commfor/config.json')+' --revision 16db135220b318d811b207db576d90368980b595 --frames {frames_dir}'),
        'AASIST_COMMAND':command('aasist.py','--repo '+q('vendor/aasist')+' --weights '+q('models/aasist/AASIST.pth')+' --variant aasist --audio {audio_path}'),
        'GAN_ARTIFACT_COMMAND':command('cnn_artifacts.py','--repo '+q('vendor/CNNDetection')+' --weights '+q('models/cnn_artifacts/blur_jpg_prob0.5.pth')+' --frames {frames_dir}'),
        'VOCODER_ARTIFACT_COMMAND':command('lfcc_lcnn.py','--repo '+q('vendor/asvspoof2021')+' --weights '+q('models/lfcc_lcnn/df_trained_network.pt')+' --audio {audio_path}'),
    }
    for key,value in values.items():
        os.environ['DEEPTRACE_'+key] = value
    # Descriptive ReviewChecks/SoftNet never drive the banner and are left unconfigured.
    # No network server or public listener is launched; TestClient exercises the real HTTP routes.
    from deeptrace.config import Settings, settings
    desired = Settings(_env_file=None)
    storage_fields = {'upload_dir', 'report_db_path', 'report_media_dir', 'database_url'}
    current_values, desired_values = settings.model_dump(), desired.model_dump()
    if any(current_values[k] != desired_values[k] for k in current_values.keys() - storage_fields):
        raise RuntimeError('A different DeepTrace profile is already imported. Restart the kernel to change it.')
    from deeptrace.db.session import reset_engine
    reset_engine()
    for key in storage_fields:
        setattr(settings, key, getattr(desired, key))
    from deeptrace.main import app
    from fastapi.testclient import TestClient
    return TestClient(app), values


def core_assessment(report):
    """Replay the same component outputs through the real report builder with artifacts omitted."""
    from deeptrace.reporting import build_report
    from deeptrace.schemas import AdvisoryReport
    parsed = AdvisoryReport.model_validate(report)
    core = [c for c in parsed.components if component_identity(c.model_dump()) in CORE]
    rebuilt = build_report(parsed.media, core, review_checks=parsed.review_checks)
    return assessment(rebuilt.model_dump(mode='json'))


def evaluate_file(client, row):
    result = {k:v for k,v in row.items() if k not in ('path','upload_path')}
    result.update(report_generated=False, report_retrieved=False, workspace_retrieved=False)
    started = time.monotonic()
    try:
        path = Path(row['upload_path'])
        if digest(path) != row['upload_sha256']:
            raise RuntimeError('Uploaded input changed since receipt')
        with path.open('rb') as stream:
            response = client.post('/v1/analyze', files={'file':(path.name, stream, mimetypes.guess_type(path.name)[0])})
        response.raise_for_status()
        report = response.json()
        result.update(report_generated=True, report=report, report_assessment=assessment(report))
        if len(report['components']) != len(DETECTORS) or {component_identity(c) for c in report['components']} != set(DETECTORS):
            raise RuntimeError('API did not return all five expected detector identities')
        result['core_only_report_assessment'] = core_assessment(report)
        saved = client.get('/v1/reports/'+report['report_id'])
        saved.raise_for_status()
        if saved.json() != report:
            raise RuntimeError('Saved report differs from upload response')
        result['report_retrieved'] = True
        if report.get('analysis_id'):
            workspace = client.get('/v1/analyses/'+report['analysis_id'])
            workspace.raise_for_status()
            workflow = workspace.json()
            lookup = {(c['model_name'],c['component']):component_identity(c) for c in report['components']}
            primary = workspace_assessment(workflow, lookup)
            core_names = {c['model_name'] for c in report['components'] if component_identity(c) in CORE}
            core_workflow = dict(workflow, model_runs=[r for r in workflow['model_runs'] if r['model_name'] in core_names],
                                 findings=[f for f in workflow['findings'] if f['model_name'] in core_names])
            result.update(workspace_retrieved=True, workspace=workflow, assessment=primary,
                          core_only_assessment=workspace_assessment(core_workflow, lookup))
        else:
            raise RuntimeError('No persisted workspace returned for this upload')
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)[:1000]
        # A report-only response cannot stand in for a missing investigator workspace.
        if 'assessment' not in result:
            result['assessment'] = {'decision':'error', 'flagging_detectors':[], 'missing_checks':5}
    result['elapsed_seconds'] = round(time.monotonic()-started, 3)
    return result


def run_evaluation(client, rows, run, protocol):
    cloud_only()
    run = Path(run)
    key = freeze(run/'protocol.json', protocol)
    results = []
    for i,row in enumerate(rows, 1):
        target = run/'records'/(hashlib.sha256(row['id'].encode()).hexdigest()+'.json')
        if target.exists():
            record = json.loads(target.read_text())
            if record.get('protocol_fingerprint') != key or record['id'] != row['id'] or record['upload_sha256'] != row['upload_sha256']:
                raise RuntimeError('Cached record belongs to a different protocol/input')
        else:
            print(f"Screening {i}/{len(rows)}: {row['id']}",flush=True)
            record = dict(evaluate_file(client,row), protocol_fingerprint=key)
            write_json(target,record)
        results.append(record)
        print(f"{i}/{len(rows)}: {record['assessment']['decision']} ({record['elapsed_seconds']} s)",flush=True)
        export_results(results, run, expected=len(rows), mode=protocol['mode'])
    return export_results(results, run, expected=len(rows), mode=protocol['mode'])


def export_results(records, run, expected, mode):
    run = Path(run)
    result = summarize(records)
    result.update(protocol_version=PROTOCOL_VERSION, mode=mode, expected_files=expected,
                  evaluated_files=len(records), run_complete=len(records)==expected,
                  timing_seconds=sum(r['elapsed_seconds'] for r in records))
    if mode == 'smoke' or len(records) != expected:
        result['overall']['subset_numeric_targets_met'] = None
        for value in result['by_category'].values():
            value['subset_numeric_targets_met'] = None
    causes = []
    for detector in DETECTORS:
        relevant = []
        statuses = Counter()
        for record in records:
            components = record.get('report',{}).get('components',[])
            component = next((c for c in components if component_identity(c)==detector),None)
            if component:
                statuses[component['status']] += 1
            else:
                statuses['missing_report'] += 1
            if record['category'] == DETECTORS[detector]:
                view = assessment({'components':[component], 'anomalies':[]}) if component else {'decision':'error'}
                relevant.append(dict(record,assessment=view))
        contributions = [r for r in records if detector in r['assessment'].get('flagging_detectors',[])]
        causes.append(dict(detector_id=detector, statuses=dict(statuses), flagged_files=len(contributions),
                           genuine_files_flagged=sum(r['label']==0 for r in contributions),
                           sole_flagger_genuine_files=sum(r['label']==0 and len(r['assessment']['flagging_detectors'])==1 for r in contributions)))
        if relevant:
            result.setdefault('per_detector_on_appropriate_category',{})[detector] = metrics(relevant)
    result['flag_contributions'] = causes
    reports = [dict(r,assessment=r.get('report_assessment', {'decision':'error'})) for r in records]
    result['report_overview'] = summarize(reports)
    result['primary_banner'] = 'investigator_workspace'
    result['banner_disagreements'] = [r['id'] for r in records if r.get('workspace_retrieved') and r['assessment']['decision'] != r['report_assessment']['decision']]
    baseline = [dict(r,assessment=r.get('core_only_assessment', {'decision':'error'})) for r in records]
    result['same_outputs_without_artifact_checks'] = summarize(baseline)
    result['comparison_note'] = 'Diagnostic replay of identical component outputs with CNNDetection/LFCC omitted; same AASIST window policy. Not a separate historical Docker run or a fitted ensemble.'
    if mode == 'smoke' or len(records) != expected:
        for value in result.get('per_detector_on_appropriate_category',{}).values():
            value['subset_numeric_targets_met'] = None
        counterfactual = result['same_outputs_without_artifact_checks']
        report_overview = result['report_overview']
        for value in [counterfactual['overall'], *counterfactual['by_category'].values(), report_overview['overall'], *report_overview['by_category'].values()]:
            value['subset_numeric_targets_met'] = None
    result['workflow_success'] = sum(all(r.get(k) for k in ('report_generated','report_retrieved','workspace_retrieved')) for r in records)
    result['files_with_missing_checks'] = sum(bool(r['assessment'].get('missing_checks')) for r in records)
    result['files_with_limited_face_coverage'] = sum(bool(r.get('report_assessment',{}).get('limited_face_coverage')) for r in records)
    write_json(run/'summary.json',result)
    csv_rows = []
    for row in records:
        decision = row['assessment']['decision']
        csv_rows.append(dict(id=row['id'],category=row['category'],source_group=row['source_group'],method=row['method'],label=row['label'],
                             decision=decision,report_overview_decision=row.get('report_assessment',{}).get('decision','error'),flagging_detectors=';'.join(row['assessment'].get('flagging_detectors',[])),
                             false_alarm=row['label']==0 and decision=='flagged',missed_manipulation=row['label']==1 and decision=='not_flagged',
                             incomplete=decision not in ('flagged','not_flagged'),missing_checks=row['assessment'].get('missing_checks',0),
                             report_generated=row['report_generated'],report_retrieved=row['report_retrieved'],workspace_retrieved=row['workspace_retrieved'],
                             elapsed_seconds=row['elapsed_seconds'],upload_sha256=row['upload_sha256']))
    with (run/'per-file.csv').open('w',newline='') as stream:
        writer = csv.DictWriter(stream,fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)
    return result


def protocol_snapshot(runtime, plan, receipt, settings):
    runtime = Path(runtime)
    manifest = json.loads((runtime/'source-manifest.json').read_text())
    for name,expected in manifest['files'].items():
        if digest(runtime/name) != expected:
            raise RuntimeError('Pinned runtime source changed: '+name)
    return {'version':PROTOCOL_VERSION, 'mode':plan['mode'], 'plan_sha256':fingerprint(plan),
            'input_receipt_sha256':fingerprint(receipt), 'settings':settings, 'sources':manifest,
            'models':{str(p.relative_to(runtime)):digest(p) for p in (runtime/'backend/models').rglob('*') if p.is_file() and p.suffix in ('.pth','.pt','.safetensors','.dat','.json')},
            'upstream':REPOS, 'gpu':gpu_info(),
            'environment':json.loads(subprocess.check_output([sys.executable,'-m','pip','list','--format=json'],text=True)),
            'ffmpeg':subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
            'report_banner_rule':assessment({'components':[], 'anomalies':[]})['rule_version'],
            'workspace_banner_rule':workspace_assessment({'model_runs':[], 'findings':[]})['rule_version'],
            'selection_limitations':plan['limitations']}


def export_archive(run, target):
    """Only evidence, never input media, checkpoints, databases, caches or credentials."""
    run = Path(run)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('selection.json','input-receipt.json','protocol.json','summary.json','per-file.csv'):
            path = run/name
            if path.is_file():
                archive.write(path, path.relative_to(run))
        for path in sorted((run/'records').glob('*.json')):
            archive.write(path,path.relative_to(run))
    return Path(target)
