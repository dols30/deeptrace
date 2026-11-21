"""Check the opt-in all-model assets; never downloads files or analyzes media."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify(root, catalog):
    failures = []
    for item in catalog['assets']:
        path = root/item['path']
        if not path.is_file():
            failures.append('Missing '+item['path'])
        elif path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            failures.append('Size/SHA-256 mismatch: '+item['path'])
    for item in catalog['sources']:
        repo = root/item['path']
        marker = repo/'.deeptrace-revision'
        try:
            if (repo/'.git').exists():
                actual = subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
                subprocess.run(['git','-C',str(repo),'diff','--quiet',actual,'--'],check=True)
            else:
                actual = marker.read_text().strip()
            if actual != item['revision']:
                failures.append('Revision mismatch: '+item['path'])
            if repo.name in ('CNNDetection','asvspoof2021','SoftNet-SpotME'):
                if not marker.is_file() or marker.read_text().strip() != item['revision']:
                    failures.append('Missing/stale revision marker: '+item['path']+'; rerun download_models.sh poc-artifacts')
        except (OSError, subprocess.CalledProcessError):
            failures.append('Missing/modified/unverifiable source: '+item['path'])
    return failures


def runtime():
    sys.path.insert(0,str(ROOT))
    sys.path.insert(0,str(ROOT/'scripts/inference'))
    from deeptrace.config import settings
    for name in ('efficientnet_command','scene_command','aasist_command','gan_artifact_command',
                 'vocoder_artifact_command','micro_expression_command','review_signals_command'):
        if not getattr(settings,name):
            raise SystemExit('Unconfigured command: '+name)
    if settings.aasist_window_mode != 'full' or settings.efficientnet_decision_rule != 'ffpp_c23_kaggle_v1':
        raise SystemExit('Recording coverage/face rule does not match all_models_poc_v1')
    for name in ('torch','torchvision','torchaudio','tensorflow','cv2','dlib','librosa','timm','safetensors'):
        importlib.import_module(name)
    from softnet import load_model
    model = load_model(ROOT/'vendor/SoftNet-SpotME',ROOT/'models/softnet/CASME_micro_s1.hdf5')
    if model.count_params() != 314817:
        raise SystemExit('Unexpected SOFTNet architecture')
    print('Runtime imports, seven configured commands, full audio coverage, face rule and strict SOFTNet load passed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',action='store_true',help='Show required asset sizes without accessing or downloading them')
    parser.add_argument('--runtime',action='store_true',help='Also check the configured model environment; run inside the all-model container')
    args = parser.parse_args()
    catalog = json.loads((ROOT/'model-assets.all.json').read_text())
    if args.plan:
        for item in catalog['assets']:
            print(str(item['bytes']).rjust(12)+' bytes  '+item['path'])
        print('Total required asset bytes:',catalog['asset_bytes'])
        print('Upstream source clones and Python/Docker dependencies are additional. Nothing downloaded.')
        return
    failures = verify(ROOT,catalog)
    if failures:
        raise SystemExit('\n'.join(failures))
    print('All nine asset checksums and five pinned source revisions passed.')
    if args.runtime:
        runtime()


if __name__ == '__main__':
    main()
