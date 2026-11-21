"""Build the hosted Kaggle development/holdout notebook. No downloads during build."""
import argparse
import json
from pathlib import Path
from experiments.build_kaggle_banner import build


def notebook(assets):
    assets = Path(assets)
    source = json.loads(build(assets).read_text())
    boot = ''.join(source['cells'][1]['source']).replace('deeptrace-banner-runtime-coverage-dlib-v4','deeptrace-adaptation-runtime-dlib-v2')
    intro = '''# DeepTrace: reduce scene false alarms with a held-out video experiment

Research only. This notebook leaves production settings unchanged. It trains only the final **Community Forensics linear classifier**; the pretrained ViT remains frozen. The independent face, AASIST, CNNDetection and LFCC-LCNN weights and rules stay fixed. GPU is used for ViT feature extraction and app inference; the small head fit uses CPU.

Attach the same ASVspoof2019 LA v1 and FF++ c23 v2 Kaggle inputs as before. Enable Internet and an available GPU. Read the FF++ and ComGenVid terms in the original banner notebook. No full dataset is downloaded to your Mac. Existing Kaggle model caches are hash checked and reused: up to **462,832,401 bytes** for all model/config assets; the complete generated-video selection is **442,679,641 bytes**, plus dependencies/source. This is the same selected media, not an additional corpus. Train/dev/test media budgets are printed before transfer. dlib stays at 19.24.6: a separate one-worker build uses pinned CMake 3.31.6/setuptools 80.9.0/wheel 0.45.1 with full diagnostics in dlib-build.log. Working installed dlib is reused. Generated clips are cached under this experiment; files elsewhere in a different runtime may need transferring again.

The fixed 240-file manifest is split by source group, stratified by FF++ manipulation method and generated source. Already observed smoke files and their related groups go to **training only**. Exact group/file lists are frozen before any learning. This is a new train/dev/test experiment, not a new claim that the original 240 files are all untouched test data. Checkpoint training overlap and unknown prompt/source relationships remain limitations.

Training uses MSVD genuine, Sora/Veo3 generated clips, and genuine FF++ talking-head hard negatives. Manipulated faces and audio are not relabelled as fully generated imagery. Loss weights give each class, then each source group/video equal influence; correlated frames do not become independent evaluation samples. The existing 1-second/120-frame JPEG preparation and exact scene preprocessing are shared with the app.

One fixed learning rate (0.001), weight decay (0.01), and epochs 10/30/100 are declared in advance. Development selects an epoch and raw-logit boundary maximizing generated-video recall subject to **≤5% false alarms separately on genuine FF++ and MSVD**. This small development cap is an optimization constraint, not a population guarantee. The complete five-detector baseline and candidate banners are compared on the same untouched test files only after the candidate is frozen. Missing/error/limited coverage stays in the denominator. A candidate may fail; no automatic deployment or accuracy claim follows. Do not refit after seeing test results.
'''
    config = '''from experiments import commfor_adaptation as ca
FACE_INPUT = None
AUDIO_INPUT = None
ALLOW_CLOUD_DOWNLOADS = False
ACCEPT_SOURCE_TERMS = False
RUN = Path('/kaggle/working/deeptrace-scene-adaptation-v1')
CATALOG = json.loads((ASSETS/'model-assets.json').read_text())
PLAN = kb.plan_inputs(ASSETS, 'full', FACE_INPUT, AUDIO_INPUT)
SPLIT = ca.partition(PLAN)
kb.freeze(RUN/'split.json', SPLIT)
print(json.dumps(SPLIT['counts'], indent=2))
print('Model/config maximum:', sum(x['bytes'] for x in CATALOG), 'bytes')
for name,rows in SPLIT['rows'].items():
    print(name, len(rows), 'files; generated transfer:', sum(r['bytes'] for r in rows if r['category']=='generated_imagery'), 'bytes')
print('No media/model transfer yet. Test content is not opened during training/development.')
'''
    setup = '''if not ALLOW_CLOUD_DOWNLOADS or not ACCEPT_SOURCE_TERMS:
    raise RuntimeError('Review sizes/terms, enable both flags, and rerun configuration first.')
GPU = kb.setup_runtime(RUNTIME, CATALOG, ALLOW_CLOUD_DOWNLOADS)
print(GPU)
# Stage only examples with known scene labels. The complete heldout app test comes later.
TRAIN = kb.stage_inputs(ca.subplan(PLAN,[r for r in SPLIT['rows']['train'] if ca.scene_label(r) is not None]), RUN/'train-inputs', True, True)
DEV = kb.stage_inputs(ca.subplan(PLAN,[r for r in SPLIT['rows']['dev'] if ca.scene_label(r) is not None]), RUN/'dev-inputs', True, True)
PROTOCOL = {'version':ca.VERSION,'split':SPLIT,'train':TRAIN,'dev':DEV,'epochs':list(ca.EPOCHS),'learning_rate':.001,'weight_decay':.01,'dev_fpr_cap_per_real_source':.05,
            'sources':json.loads((RUNTIME/'source-manifest.json').read_text()),'gpu':GPU}
kb.freeze(RUN/'development-protocol.json', PROTOCOL)
CANDIDATE = ca.fit(RUNTIME, TRAIN, DEV, RUN, PROTOCOL)
DEVELOPMENT = json.loads((RUN/'development.json').read_text())
print(json.dumps({k:DEVELOPMENT[k] for k in ('baseline_development','selected_development','candidate','promotion_allowed')},indent=2))
print('Candidate frozen:', CANDIDATE)
'''
    test = '''# Opens the fixed holdout after candidate selection; do not use its results to retune.
COMPARISON = ca.evaluate_holdout(RUNTIME, PLAN, SPLIT, RUN, ALLOW_CLOUD_DOWNLOADS, ACCEPT_SOURCE_TERMS)
print(json.dumps(COMPARISON, indent=2))
'''
    export = '''import zipfile
RESULTS = Path('/kaggle/working/deeptrace-adaptation-results.zip')
# Evidence + tiny research head only. No source media, caches, DB, credentials or base models.
with zipfile.ZipFile(RESULTS,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in ('split.json','development-protocol.json','development.json','holdout-opened.json','comparison.json','baseline-results.zip','candidate-results.zip','candidate/adaptation.json','candidate/head.safetensors'):
        path=RUN/name
        if path.is_file(): archive.write(path,name)
from IPython.display import FileLink, display
print('Results:',RESULTS,RESULTS.stat().st_size,'bytes')
display(FileLink(str(RESULTS)))
print('Save a Kaggle version with outputs; temporary runtime files are not a backup.')
'''
    cells = []
    for i,(kind,text) in enumerate([('markdown',intro),('code',boot),('code',config),('code',setup),('code',test),('code',export)]):
        cell = dict(cell_type=kind,id='adaptation-'+str(i),metadata={},source=text.splitlines(keepends=True))
        if kind == 'code':
            compile(text,'cell-'+str(i),'exec')
            cell.update(execution_count=None,outputs=[])
        cells.append(cell)
    source['cells'] = cells
    target = assets/'04_Kaggle_Scene_Adaptation_Heldout.ipynb'
    target.write_text(json.dumps(source,indent=1)+'\n')
    print('Adaptation notebook:',target,target.stat().st_size,'bytes')
    return target


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('assets',type=Path)
    notebook(parser.parse_args().assets)
