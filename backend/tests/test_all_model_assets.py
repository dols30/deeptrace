"""Asset checks must reject a substituted checkpoint or source revision."""
import hashlib
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('verify_all_models',Path(__file__).parents[1]/'scripts/verify_all_models.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


@pytest.fixture
def assets(tmp_path):
    checkpoint = tmp_path/'model.pth'
    checkpoint.write_bytes(b'approved weights')
    repo = tmp_path/'vendor/CNNDetection'
    repo.mkdir(parents=True)
    (repo/'.deeptrace-revision').write_text('approved-revision\n')
    catalog = {'assets':[{'path':'model.pth','bytes':len(b'approved weights'),
                          'sha256':hashlib.sha256(b'approved weights').hexdigest()}],
               'sources':[{'path':'vendor/CNNDetection','revision':'approved-revision'}]}
    return tmp_path,catalog


def test_verified_files_without_git_metadata(assets):
    assert module.verify(*assets) == []


def test_same_size_checkpoint_substitution_is_rejected(assets):
    root,catalog = assets
    (root/'model.pth').write_bytes(b'tampered weights')
    assert any('SHA-256 mismatch' in error for error in module.verify(root,catalog))


def test_missing_checkpoint_is_reported(assets):
    root,catalog = assets
    (root/'model.pth').unlink()
    assert 'Missing model.pth' in module.verify(root,catalog)


def test_wrong_source_revision_is_rejected(assets):
    root,catalog = assets
    (root/'vendor/CNNDetection/.deeptrace-revision').write_text('unapproved-revision\n')
    assert any('Revision mismatch' in error for error in module.verify(root,catalog))
