"""Shared helpers; importable without ML dependencies."""
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

PINNED_REVISIONS = {
    'aasist': 'a04c9863f63d44471dde8a6abcb3b082b07cd1d1',
    'DeepfakeBench': 'f188b1c105465e2e5377eb536a95022ae0e4522d',
}

# Process-local caches. A one-shot runner process starts empty, so behaviour is unchanged. A warm
# worker (worker.py) keeps them, so weights load and checkpoints hash once per process. Keys include
# each file's size and mtime, so a replaced checkpoint is reloaded and re-hashed, never served stale.
_LOADED = {}
_CHECKPOINT_IDS = {}
_REVISIONS = {}


def file_key(*paths):
    """Identity of input files for cache keys: resolved path, size and modification time."""
    key = []
    for path in paths:
        resolved = Path(path).resolve()
        stat = resolved.stat()
        key.append((str(resolved), stat.st_size, stat.st_mtime_ns))
    return tuple(key)


def cached(key, load):
    """Return load() once per key for the life of this process. Loaded models must stay read-only."""
    if key not in _LOADED:
        _LOADED[key] = load()
    return _LOADED[key]


def add_sys_path(path):
    """Prepend an upstream source directory once, so warm workers do not grow sys.path per request."""
    path = str(path)
    if path not in sys.path:
        sys.path.insert(0, path)


def checkpoint_id(path):
    path = Path(path)
    key = file_key(path)
    if key in _CHECKPOINT_IDS:
        return _CHECKPOINT_IDS[key]
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    _CHECKPOINT_IDS[key] = f'{path.name}#sha256={digest.hexdigest()}'
    return _CHECKPOINT_IDS[key]


def revision(repo):
    key = str(Path(repo).resolve())
    if key not in _REVISIONS:
        _REVISIONS[key] = _revision(repo)
    return _REVISIONS[key]


def _revision(repo):
    revision_file = Path(repo) / '.deeptrace-revision'
    if revision_file.exists():
        return revision_file.read_text().strip()

    git_dir = Path(repo) / '.git'
    if not git_dir.exists() and Path(repo).name in PINNED_REVISIONS:
        return PINNED_REVISIONS[Path(repo).name]
    git = shutil.which('git')
    if git:
        return subprocess.check_output([git, '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip()
    if git_dir.is_file():
        marker = git_dir.read_text().strip()
        if not marker.startswith('gitdir: '):
            raise RuntimeError(f'Unsupported Git metadata: {git_dir}')
        git_dir = (git_dir.parent / marker.removeprefix('gitdir: ')).resolve()

    head = (git_dir / 'HEAD').read_text().strip()
    if not head.startswith('ref: '):
        return head

    ref = head.removeprefix('ref: ')
    loose_ref = git_dir / ref
    if loose_ref.exists():
        return loose_ref.read_text().strip()
    packed_refs = git_dir / 'packed-refs'
    if packed_refs.exists():
        for line in packed_refs.read_text().splitlines():
            if line and not line.startswith(('#', '^')):
                commit, name = line.split(' ', 1)
                if name == ref:
                    return commit
    raise RuntimeError(f'Cannot resolve Git revision for {repo}')


def probability(value):
    value = float(value)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Invalid model probability')
    return value


def run(main):
    # Third-party model constructors can print progress. Reserve stdout for JSON.
    from contextlib import redirect_stdout
    try:
        with redirect_stdout(sys.stderr):
            payload = main()
        print(json.dumps(payload, allow_nan=False))
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
