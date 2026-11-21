"""Kaggle-only frozen-backbone head adaptation, with source-group train/dev/test separation.

The app is never reconfigured automatically. Test media are staged only after the
head and development-selected boundary have been frozen. No media/model Mac downloads.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import json
import math
from pathlib import Path
import random
import shlex
import sys

from experiments import kaggle_banner as kb
from experiments.tool_evaluation import metrics

VERSION = 'commfor_head_adaptation_v1'
EPOCHS = (10, 30, 100)


def partition(plan):
    """Split source groups, stratifying FF++ methods and generated sources; seen smoke -> train."""
    rows = plan['files']
    if plan['mode'] != 'full' or len({r['id'] for r in rows}) != len(rows):
        raise ValueError('Use the complete fixed unique-file plan')
    seen_groups = {r['source_group'] for r in kb.smoke_rows(rows)}
    groups = defaultdict(list)
    for row in rows:
        groups[row['source_group']].append(row)
    strata = defaultdict(list)
    for group, members in sorted(groups.items()):
        category = members[0]['category']
        methods = sorted({r['method'] for r in members if r['label'] == 1})
        key = (category, tuple(methods) if category != 'audio_spoof' else ())
        # Real MSVD groups have no positive method. They form their own stratum.
        strata[key].append(group)
    assignment = {}
    rng = random.Random(kb.SEED)
    for key, keys in sorted(strata.items()):
        rng.shuffle(keys)
        unseen = [k for k in keys if k not in seen_groups]
        n = max(1, round(len(keys) * .2))
        if len(unseen) < 2 * n:
            raise ValueError('Too few independent groups for train/dev/test: '+str(key))
        for i, group in enumerate(unseen):
            assignment[group] = 'dev' if i < n else 'test' if i < 2*n else 'train'
        for group in keys:
            if group in seen_groups:
                assignment[group] = 'train'
    split = {name: [dict(r, split=name) for r in rows if assignment[r['source_group']] == name]
             for name in ('train', 'dev', 'test')}
    for name, selected in split.items():
        for category in ('face_manipulation', 'generated_imagery', 'audio_spoof'):
            if {r['label'] for r in selected if r['category'] == category} != {0, 1}:
                raise ValueError('A split lacks both classes: '+name+'/'+category)
    return dict(version=VERSION, seed=kb.SEED, rows=split, seen_smoke_groups=sorted(seen_groups),
                counts={name:dict(Counter(r['category']+':'+str(r['label']) for r in selected))
                        for name, selected in split.items()},
                limitations=plan['limitations'] + [
                    'Only this experiment is group-disjoint; pretrained training overlap is unknown.',
                    'Small test strata cannot establish a population false-positive rate below 10%.',
                    'The already observed smoke files and their source groups are training-only.',
                    'Face-manipulated clips have no whole-frame generated-imagery label and are not head-training examples.'])


def subplan(plan, rows):
    return dict(plan, files=rows,
                generated_download_bytes=sum(r['bytes'] for r in rows if r['category']=='generated_imagery'))


def scene_label(row):
    if row['category'] == 'generated_imagery':
        return row['label']
    if row['category'] == 'face_manipulation' and row['label'] == 0:
        return 0  # Genuine talking-head video is a labelled hard negative.
    return None  # Whole-file face/audio spoof labels do not label generated imagery.


def features(runtime, rows, directory):
    kb.cloud_only()
    import numpy as np
    import torch
    import timm
    from safetensors.torch import load_file
    from deeptrace.media import prepare_video, cleanup_prepared
    backend = Path(runtime)/'backend'
    sys.path.insert(0, str(backend/'scripts/inference'))
    import commfor
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA GPU is required; no silent CPU fallback')
    weights = backend/'models/commfor/frontier.safetensors'
    model = timm.create_model('vit_small_patch16_384', pretrained=False, num_classes=1)
    model.load_state_dict({k.removeprefix('vit.'):v for k,v in load_file(str(weights)).items()}, strict=True)
    model.cuda().eval()
    base_sha256 = kb.digest(weights)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    records = []
    for index,row in enumerate(rows,1):
        label = scene_label(row)
        if label is None:
            continue
        cache_key = kb.fingerprint(dict(id=row['id'], input=row['upload_sha256'],
            base=base_sha256, preprocessing=commfor.PREPROCESSING_VERSION, interval=1, max_frames=120))
        target = directory/(cache_key+'.npz')
        if not target.exists():
            if kb.digest(row['upload_path']) != row['upload_sha256']:
                raise RuntimeError('Input changed before feature extraction')
            frames, _ = prepare_video(Path(row['upload_path']), 'ffmpeg', 1, 120)
            try:
                values = []
                with torch.inference_mode():
                    for path in sorted(frames.glob('frame_*.jpg')):
                        tensor = commfor.image_tensor(path)[None].cuda()
                        value = model.forward_head(model.forward_features(tensor), pre_logits=True)
                        values.append(value.float().cpu().numpy()[0])
                array = np.stack(values)
                if array.ndim != 2 or array.shape[1] != model.num_features or not np.isfinite(array).all():
                    raise RuntimeError('Invalid extracted features')
                with target.with_suffix('.tmp').open('wb') as stream:
                    np.savez_compressed(stream, features=array)
                target.with_suffix('.tmp').replace(target)
            finally:
                cleanup_prepared(frames)
        with np.load(target, allow_pickle=False) as saved:
            array = saved['features']
            if array.ndim != 2 or not len(array) or array.shape[1] != model.num_features or not np.isfinite(array).all():
                raise RuntimeError('Invalid cached features')
        records.append(dict(row, scene_label=label, features=array))
        print(f'Features {index}/{len(rows)}: {row["id"]}', flush=True)
    initial = {k:v.detach().cpu().clone() for k,v in model.head.state_dict().items()}
    del model
    torch.cuda.empty_cache()
    return records, initial


def video_scores(records, head, boundary):
    import torch
    scores = []
    with torch.inference_mode():
        for row in records:
            logits = head(torch.as_tensor(row['features'], dtype=torch.float32)).flatten().double()
            # Same shifted sigmoid, per-frame averaging and six-decimal adapter rounding as app.
            score = round(float(torch.sigmoid(logits-boundary).mean()), 6)
            scores.append(dict(id=row['id'], source_group=row['source_group'], category=row['category'],
                               label=row['scene_label'], score=score,
                               assessment={'decision':'flagged' if score >= .5 else 'not_flagged'}))
    return scores


def select_boundary(records, head, cap=.05):
    import numpy as np
    import torch
    with torch.inference_mode():
        logits = np.concatenate([head(torch.as_tensor(r['features'])).detach().numpy().ravel() for r in records])
    candidates = sorted(set(np.quantile(logits, np.linspace(0,1,201)).tolist()+[float(logits.max()+40)]))
    best = None
    for boundary in candidates:
        rows = video_scores(records, head, boundary)
        genuine_sources = {r['category'] for r in rows if r['label']==0}
        if any(sum(r['assessment']['decision']=='flagged' for r in rows if r['label']==0 and r['category']==source)
               / sum(r['label']==0 and r['category']==source for r in rows) > cap for source in genuine_sources):
            continue
        m = metrics(rows)
        rank = (m['manipulation_recall_all_manipulated'], -m['false_positive_rate_all_genuine'], boundary)
        if best is None or rank > best[0]:
            best = rank, boundary, m
    if best is None:
        raise RuntimeError('No development boundary satisfies the declared false-alarm cap')
    return best[1], best[2]


def fit(runtime, train, dev, run, protocol):
    """Train only the linear head; development picks one epoch and decision boundary."""
    kb.cloud_only()
    prior = Path(run)/'development.json'
    if prior.exists():
        saved = json.loads(prior.read_text())
        if kb.fingerprint(saved['protocol']) != kb.fingerprint(protocol):
            raise RuntimeError('Development protocol changed; preserve this run')
        config_path = Path(run)/'candidate/adaptation.json'
        if (json.loads(config_path.read_text()) != saved['candidate']
                or kb.digest(config_path.parent/'head.safetensors') != saved['candidate']['head_sha256']):
            raise RuntimeError('Frozen candidate changed')
        return config_path
    if (Path(run)/'holdout-opened.json').exists():
        raise RuntimeError('Holdout already opened; no more fitting in this experiment')
    import torch
    from safetensors.torch import save_file
    torch.manual_seed(kb.SEED)
    # Cached ViT forwards use the GPU; the tiny deterministic linear fit uses CPU.
    training, initial = features(runtime, train, Path(run)/'features/train')
    development, _ = features(runtime, dev, Path(run)/'features/dev')
    if any({r['scene_label'] for r in part} != {0,1} for part in (training,development)):
        raise ValueError('Both scene classes are required in train and development')
    if {r['source_group'] for r in training} & {r['source_group'] for r in development}:
        raise ValueError('Training/development source leakage')
    head = torch.nn.Linear(initial['weight'].shape[1],1)
    head.load_state_dict(initial, strict=True)
    release_boundary = json.loads((Path(runtime)/'backend/models/commfor/config.json').read_text())['raw_logit_boundary']
    baseline = metrics(video_scores(development, head, release_boundary))
    # Equal class -> equal source group -> equal video -> equal frame contribution.
    groups = {label:{r['source_group'] for r in training if r['scene_label']==label} for label in (0,1)}
    per_group = Counter(r['source_group'] for r in training)
    x = torch.cat([torch.as_tensor(r['features']) for r in training])
    y = torch.cat([torch.full((len(r['features']),1), float(r['scene_label'])) for r in training])
    w = torch.cat([torch.full((len(r['features']),1),1/(2*len(groups[r['scene_label']])*per_group[r['source_group']]*len(r['features']))) for r in training])
    optimizer = torch.optim.AdamW(head.parameters(), lr=.001, weight_decay=.01)
    selected, ledger = None, []
    for epoch in range(1,max(EPOCHS)+1):
        optimizer.zero_grad()
        loss = (torch.nn.functional.binary_cross_entropy_with_logits(head(x),y,reduction='none')*w).sum()
        if not torch.isfinite(loss):
            raise RuntimeError('Non-finite training loss')
        loss.backward()
        optimizer.step()
        if epoch in EPOCHS:
            boundary, validation = select_boundary(development,head)
            rank = (validation['manipulation_recall_all_manipulated'], -validation['false_positive_rate_all_genuine'], -epoch)
            ledger.append(dict(epoch=epoch, loss=float(loss.detach()), boundary=boundary, development=validation))
            if selected is None or rank > selected[0]:
                selected = rank, {k:v.detach().clone() for k,v in head.state_dict().items()}, epoch, boundary, validation
    directory = Path(run)/'candidate'
    directory.mkdir(parents=True, exist_ok=True)
    head_path = directory/'head.safetensors'
    # Never overwrite an evaluated candidate with a newly fitted one.
    if (Path(run)/'holdout-opened.json').exists():
        raise RuntimeError('Holdout already opened; no more fitting in this experiment')
    save_file(selected[1],str(head_path))
    sys.path.insert(0,str(Path(runtime)/'backend/scripts/inference'))
    import commfor
    config = dict(schema=VERSION, base_sha256=kb.digest(Path(runtime)/'backend/models/commfor/frontier.safetensors'),
                  preprocessing_version=commfor.PREPROCESSING_VERSION,head_sha256=kb.digest(head_path),
                  raw_logit_boundary=selected[3], development_protocol_sha256=kb.fingerprint(protocol),
                  selected_epoch=selected[2], calibration_fitted=False, operationally_validated=False)
    kb.freeze(directory/'adaptation.json',config)
    report = dict(protocol=protocol,baseline_development=baseline,candidates=ledger,selected_development=selected[4],
                  candidate=config,promotion_allowed=False,note='Development evidence only. Production settings are unchanged. Test must compare the complete five-detector banner, not just scene recall.')
    kb.freeze(Path(run)/'development.json',report)
    return directory/'adaptation.json'


def evaluate_holdout(runtime, plan, split, run, allow_downloads, accept_terms):
    """Open holdout once after candidate freeze; run baseline/candidate through real API."""
    kb.cloud_only()
    if not allow_downloads or not accept_terms:
        raise RuntimeError('Review sizes/terms and enable both settings before opening holdout')
    run = Path(run)
    config = run/'candidate/adaptation.json'
    report = json.loads((run/'development.json').read_text())
    if (json.loads(config.read_text()) != report['candidate']
            or kb.digest(config.parent/'head.safetensors') != report['candidate']['head_sha256']):
        raise RuntimeError('Candidate changed after development freeze')
    if kb.fingerprint(report['protocol']['split']) != kb.fingerprint(split):
        raise RuntimeError('Split changed after development')
    frozen = dict(candidate=kb.digest(config),head=kb.digest(config.parent/'head.safetensors'),split=kb.fingerprint(split))
    kb.freeze(run/'holdout-opened.json',frozen)
    rows = kb.stage_inputs(subplan(plan,split['rows']['test']),run/'holdout-inputs',allow_downloads,accept_terms)
    results = {}
    for name in ('baseline','candidate'):
        client, values = kb.configure_app(runtime,run/name,'full')
        from deeptrace.config import settings
        baseline_command = settings.scene_command
        if name == 'candidate':
            settings.scene_command += ' --adaptation '+shlex.quote(str(config))
            values['SCENE_COMMAND'] = settings.scene_command
        try:
            protocol = kb.protocol_snapshot(runtime,dict(plan,mode='heldout'),rows,values)
            protocol['adaptation'] = dict(frozen,variant=name)
            with client:
                results[name] = kb.run_evaluation(client,rows,run/name,protocol)
        finally:
            settings.scene_command = baseline_command
        kb.export_archive(run/name,run/(name+'-results.zip'))
    comparison = dict(baseline=results['baseline']['overall'],candidate=results['candidate']['overall'],
                      promotion_allowed=False, poc_acceptance_established=False,
                      note='One fixed small holdout. Inspect per-category recall, scene false alarms, coverage and all model failures before considering promotion. No production setting was changed.')
    kb.freeze(run/'comparison.json',comparison)
    return comparison
