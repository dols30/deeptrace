"""Create a self-contained Kaggle notebook from allowlisted app source and small metadata.

Usage from repository root: backend/.venv/bin/python backend/experiments/build_kaggle_banner.py ASSETS_DIRECTORY
The directory needs the two frozen selection JSONs, source credits and selection-facts.json.
Never packages credentials, checkpoints, model caches, uploaded media or validation results.
"""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def build(assets):
    assets = Path(assets).resolve()
    revision = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    tracked = subprocess.check_output(['git','ls-tree','-r','--name-only',revision],cwd=ROOT,text=True).splitlines()
    selected = [p for p in tracked if ((p.startswith('backend/deeptrace/') or p.startswith('backend/scripts/inference/')) and p.endswith('.py'))
                or p in ('backend/requirements.txt','frontend/lib/report-presentation.ts','frontend/components/workspace/officer-summary.tsx')]
    contents = {p:(ROOT/p).read_bytes() for p in selected}
    overlays = [p for p in selected if contents[p] != subprocess.check_output(['git','show',revision+':'+p],cwd=ROOT)]
    contents['backend/scripts/inference/face_coverage.py']=(ROOT/'backend/scripts/inference/face_coverage.py').read_bytes()
    for name in ('tool_evaluation.py','kaggle_banner.py','commfor_adaptation.py'):
        p='backend/experiments/'+name
        contents[p]=(ROOT/p).read_bytes()
    source_manifest = {'app_commit':revision, 'benchmark_overlay':'Content-hashed working tree and experiment sources; app_commit is the base revision', 'working_tree_overlays':overlays,
                       'files':{name:sha(raw) for name,raw in contents.items()}}
    contents['source-manifest.json']=(json.dumps(source_manifest,indent=2,sort_keys=True)+'\n').encode()
    for name in ('fresh-face-selection.json','fresh-generated-selection.json','selection-facts.json',
                 'model-assets.json','comgenvid-README.md','comgenvid-sora_sampled_videos.csv'):
        contents['setup-assets/'+name]=(assets/name).read_bytes()
    source_manifest['files']={name:sha(raw) for name,raw in contents.items() if name!='source-manifest.json'}
    contents['source-manifest.json']=(json.dumps(source_manifest,indent=2,sort_keys=True)+'\n').encode()
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as archive:
        for name,raw in sorted(contents.items()):
            member=zipfile.ZipInfo(name,date_time=(2026,11,11,0,0,0))
            member.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(member,raw)
    payload=buf.getvalue()
    (assets/'deeptrace-banner-runtime.zip').write_bytes(payload)
    boot='''import base64, hashlib, io, json, platform, stat, sys, zipfile
from pathlib import Path, PurePosixPath
if platform.system() == 'Darwin' or not Path('/kaggle/input').is_dir() or not Path('/kaggle/working').is_dir():
    raise RuntimeError('Import this notebook into hosted Kaggle. No dataset/model download is allowed on your Mac.')
RUNTIME = Path('/kaggle/working/deeptrace-banner-runtime-coverage-dlib-v4')
RUNTIME.mkdir(exist_ok=True)
'''
    boot += 'BUNDLE_SHA256 = '+repr(sha(payload))+'\nBUNDLE_BASE64 = '+repr(base64.b64encode(payload).decode())+'\n'
    boot += '''raw = base64.b64decode(BUNDLE_BASE64, validate=True)
if hashlib.sha256(raw).hexdigest() != BUNDLE_SHA256:
    raise RuntimeError('Embedded source bundle integrity mismatch')
with zipfile.ZipFile(io.BytesIO(raw)) as archive:
    if sum(member.file_size for member in archive.infolist()) > 5_000_000:
        raise RuntimeError('Unexpected expanded source size')
    for member in archive.infolist():
        name = PurePosixPath(member.filename)
        if name.is_absolute() or '..' in name.parts or stat.S_ISLNK(member.external_attr >> 16):
            raise RuntimeError('Unsafe source archive member')
        target = RUNTIME.joinpath(*name.parts)
        data = archive.read(member)
        if target.exists() and target.read_bytes() != data:
            raise RuntimeError('Existing runtime source differs; preserve it and use a clean runtime directory')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
sys.path.insert(0, str(RUNTIME/'backend'))
from experiments import kaggle_banner as kb
ASSETS = RUNTIME/'setup-assets'
print('Verified app commit:', json.loads((RUNTIME/'source-manifest.json').read_text())['app_commit'])
print('Source/setup only:', len(raw), 'bytes. No media or model transfer started.')
'''
    config='''# Attach both pinned datasets with Add Input before this cell.
RUN_SIZE = 'smoke'  # 'smoke': 12 files. Change to 'full' for the fixed 240-file benchmark.
AASIST_WINDOW = 'full'  # Matches the extended five-detector launcher. Freeze before scoring.
FACE_INPUT = None  # Optional exact mounted dataset root; otherwise auto-detect.
AUDIO_INPUT = None
ALLOW_CLOUD_DOWNLOADS = False  # Review the size plan below, then set True for Kaggle-only downloads.
ACCEPT_SOURCE_TERMS = False  # Read FF++ terms and ComGenVid source/creator notes linked above; set True if your use complies.
CATALOG = json.loads((ASSETS/'model-assets.json').read_text())
PLAN = kb.plan_inputs(ASSETS, RUN_SIZE, FACE_INPUT, AUDIO_INPUT)
RUN = Path('/kaggle/working/deeptrace-banner') / (RUN_SIZE+'-aasist-'+AASIST_WINDOW+'-v2')
print('Model/config assets:', sum(item['bytes'] for item in CATALOG), 'bytes (verified cached files are reused).')
print('Additional generated media:', PLAN['generated_download_bytes'], 'bytes.')
print('No network transfer for attached ASVspoof/FF++ media. Public source/Python dependencies are additional.')
'''
    setup='''if not ALLOW_CLOUD_DOWNLOADS or not ACCEPT_SOURCE_TERMS:
    raise RuntimeError('Read the plan/terms, enable the two settings in the previous cell, then rerun it. Nothing downloaded.')
GPU = kb.setup_runtime(RUNTIME, CATALOG, ALLOW_CLOUD_DOWNLOADS)
print(GPU)
RECEIPT = kb.stage_inputs(PLAN, RUN, ALLOW_CLOUD_DOWNLOADS, ACCEPT_SOURCE_TERMS)
CLIENT, APP_SETTINGS = kb.configure_app(RUNTIME, RUN, AASIST_WINDOW)
PROTOCOL = kb.protocol_snapshot(RUNTIME, PLAN, RECEIPT, APP_SETTINGS)
print('Frozen protocol:', kb.freeze(RUN/'protocol.json', PROTOCOL))
print('Ready:', len(RECEIPT), 'files. All five model commands explicitly use --device cuda.')
'''
    run='''# Rerun this cell after an interruption to reuse completed records in this run directory.
# Cached errors remain visible; no automatic replacement of hard samples.
SUMMARY = kb.run_evaluation(CLIENT, RECEIPT, RUN, PROTOCOL)
print(json.dumps({key: SUMMARY[key] for key in ('mode','run_complete','overall','by_category','flag_contributions','workflow_success','files_with_missing_checks','files_with_limited_face_coverage','banner_disagreements','report_overview')}, indent=2))
'''
    export='''RESULTS_ZIP = kb.export_archive(RUN, Path('/kaggle/working')/('deeptrace-banner-'+RUN_SIZE+'-results.zip'))
from IPython.display import FileLink, display
print('Evidence archive:', RESULTS_ZIP, RESULTS_ZIP.stat().st_size, 'bytes')
display(FileLink(str(RESULTS_ZIP)))
print('Save a successful Kaggle version with outputs. Temporary session files alone are not a backup.')
'''
    intro='''# DeepTrace — overall banner with five independent detectors

This notebook tests **both existing overall banners**, using the **investigator workspace banner** as primary. Any persisted finding or functional detector score at its rule flags the workspace; missing usable checks without a flag give an incomplete result; development mocks remain demonstration-only. The upload report overview also checks elevated observations/timestamps and limited face coverage. The workspace now treats limited face coverage as incomplete. The archived v1 rule is preserved for replay; new runs use v2. Disagreements are exported. It never averages model scores, fits thresholds, trains weights or changes the app.

The five checks are **EfficientNet-B4 face manipulation, Community Forensics generated imagery, AASIST speech, CNNDetection GAN artifacts and LFCC-LCNN audio artifacts**. Nonapplicable modalities stay nonapplicable. It submits each file through the actual FastAPI upload route in an isolated in-process TestClient, retrieves the stored report and review workspace, and applies both content-hashed banner rules tested against the actual React workspace and report overview. It does not launch a public server. It checks the initial investigator banner and upload report overview, not supervisor disposition or browser layout.

## Before running

1. Import this file into a **new private Kaggle Notebook**. Enable Internet and an available GPU in Notebook Settings. The runtime needs ffmpeg, ffprobe, git and a compiler/CMake for the pinned dlib package. Python 3.13 uses the pinned scikit-image 0.25.2 binary wheel (0.24.0 is retained on older Python); the face-alignment SimilarityTransform implementation is unchanged between these versions. Source compilation of scikit-image is disabled. Kaggle's CUDA PyTorch/torchvision are kept; no CPU-only torch installation or CPU fallback is used. LFCC requires matching torchaudio: if missing/incompatible, only its matching CUDA wheel is installed with `--no-deps` from the PyTorch wheel index, preserving torch/torchvision. Verify your account quota in Kaggle, not from an assumed weekly allowance.
2. Add Input: [ASVspoof2019 LA](https://www.kaggle.com/datasets/anishsarkar22/asvpoof-2019-dataset-la), **version 1** (~7.66 GB), and [FF++ c23 videos](https://www.kaggle.com/datasets/abbasaliyev/ffpp-core-c23-videos), **version 2** (~10.96 GB). Both stay on Kaggle and are read in place; no full dataset is copied to working storage or downloaded to your Mac.
3. Read [FF++ research terms](https://kaldir.vc.in.tum.de/faceforensics_tos.pdf) and the [ComGenVid publisher card](https://huggingface.co/datasets/OmerXYZ/comgenvid/blob/17f9ab6c548d9a30f5b22c09e17daee74536b653/README.md). Sora clips retain creator/OpenAI rights and were collected for academic benchmarking. Credits/card are bundled; this is no permission for public redistribution.
4. Start with `RUN_SIZE='smoke'` (12 fixed files), inspect the byte plan, then enable the two explicit settings. The full test is 240 fixed files, **40 genuine + 40 manipulated per category**: audio spoof, face manipulation, and fully generated imagery. The latter includes 40 MSVD genuine, 20 Sora and 20 Veo3. Only those selected generated videos are fetched inside Kaggle. The full generated-media payload is **442,679,641 bytes**, and all model/config assets are **462,832,401 bytes**, plus public source and dependencies. No embedding parquet or full video archive is downloaded.
5. After smoke checks, change `RUN_SIZE='full'`, keep the same AASIST policy, and rerun configuration/setup/scoring/export cells. The model cache is reused. The pinned dlib 19.24.6 build uses CMake 3.31.6, setuptools 80.9.0, wheel 0.45.1, one compiler worker and no build isolation; existing working 19.24.6 is reused, and a full dlib-build.log is retained. Setup can take several minutes for dlib; GPU model forwards coexist with CPU FFmpeg/dlib processing. Use smoke elapsed time to budget the full run; no fixed completion time is promised.

## Frozen behavior and interpretation

- Face rule: `ffpp_c23_kaggle_v1`, any aligned frame ≥ **0.9967585206031799**, 1-second sampling, 120-frame cap. Scene/CNNDetection use their existing mean/0.5 policies; AASIST and LFCC use existing 0.5 rules and window observations. Default here is **full-recording AASIST**, as in the extended local launcher. The currently inspected Docker deployment has only three classifiers and first-window AASIST: this notebook's five-model profile is explicit and is not claimed to match that deployment. Use a **new run/kernel** if changing the audio policy; the protocol records it.
- FF++ source sequences previously scored in development/test are excluded. Previous ASVspoof development/test utterance IDs are excluded. Fresh ASVspoof utterances may share earlier test speakers; pretrained-checkpoint training overlap and generated-video source/prompt independence are not established. ComGenVid eligibility is duration 2–20 s, minimum dimension ≥240; source/creator grouping where available and a fixed seed are used before scoring. No filtering based on detector outcomes.
- FLAC is losslessly decoded to app-supported PCM16 WAV without trimming or gain changes. Original and uploaded hashes are stored. Every applicable classifier runs on each file; generated-video audio is not assumed to have a known spoof label.
- Accuracy counts every selected file once. Incomplete/error/demo results cannot count as correct. Both all-genuine and decidable-genuine FPRs are shown so abstentions cannot silently improve results. Flagged partial reports retain missing-check counts.
- Export includes per-file decisions, confusion counts, FPR, recall, status/coverage, saved-report/workspace checks, and each detector's false-alarm contribution. `overall` is the investigator banner; `report_overview` retains the other banner and `banner_disagreements` lists mismatches. Independent detector metrics use only the matching labelled task; unrelated whole-file labels are not reused as audio/face ground truth. A diagnostic replay removes the two artifact checks from the same component outputs to show their effect, retaining the same audio policy.
- No overall AUROC/EER exists for this categorical banner because there is no combined continuous score. The 85% accuracy / <10% FPR check is a descriptive **subset** comparison, not DPS acceptance. Smoke/partial runs suppress that comparison. Correlated sources and the selected balanced category mix limit generalization. Keep per-category results visible.
- Completed records are reused only for the exact protocol/input fingerprints. Errors are retained, not replaced. Save a successful Kaggle version and its small results ZIP. Continuing in a new runtime requires restoring the same run evidence and inputs; there is no automatic overnight resume.
'''
    specs=[('markdown',intro),('code',boot),('code',config),('code',setup),('code',run),('code',export)]
    cells=[]
    for i,(kind,text) in enumerate(specs):
        cell={'cell_type':kind,'id':f'deeptrace-banner-{i}','metadata':{},'source':text.splitlines(keepends=True)}
        if kind=='code':
            compile(text,f'notebook-cell-{i}','exec')
            cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
              'language_info':{'name':'python','version':'3.12'},'kaggle':{'isInternetEnabled':True,'isGpuEnabled':True}},'cells':cells}
    path=assets/'03_Kaggle_Five_Model_Banner_Validate.ipynb'
    path.write_text(json.dumps(notebook,indent=1)+'\n')
    write={'notebook':str(path),'notebook_bytes':path.stat().st_size,'notebook_sha256':sha(path.read_bytes()),
           'bundle_bytes':len(payload),'bundle_sha256':sha(payload),'source_manifest':source_manifest}
    (assets/'build-receipt.json').write_text(json.dumps(write,indent=2)+'\n')
    print(json.dumps({k:v for k,v in write.items() if k!='source_manifest'},indent=2))
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assets',type=Path)
    build(parser.parse_args().assets)
