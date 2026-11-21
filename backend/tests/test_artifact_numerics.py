"""Optional ML-environment checks: numerical compatibility and spotting time alignment."""
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'scripts/inference'))


def test_legacy_fft_matches_direct_dft_and_lfcc_dct():
    torch = pytest.importorskip('torch')
    np = pytest.importorskip('numpy')
    from lfcc_compat import install
    original_stft = torch.stft
    install(torch)
    try:
        value = torch.tensor([[1.,2.,3.,4.]], dtype=torch.float64)
        output = torch.rfft(value,1,onesided=False).numpy()
        expected = np.fft.fft(value.numpy())
        np.testing.assert_allclose(output[...,0],expected.real,atol=1e-12)
        np.testing.assert_allclose(output[...,1],expected.imag,atol=1e-12)
        repo = Path(__file__).parents[1]/'vendor/asvspoof2021/LA/Baseline-LFCC-LCNN'
        if not repo.exists(): pytest.skip('Pinned upstream source is optional')
        sys.path.insert(0,str(repo))
        from sandbox.util_dsp import dct
        from scipy.fft import dct as reference_dct
        np.testing.assert_allclose(dct(value,norm='ortho').numpy(), reference_dct(value.numpy(),norm='ortho'),atol=1e-12)
    finally:
        torch.stft = original_stft


def test_spotting_smoothing_mapping_and_static_abstention():
    np = pytest.importorskip('numpy')
    pytest.importorskip('scipy')
    from softnet import spot_intervals
    intervals, threshold = spot_intervals(np.ones(60))
    assert intervals == [] and threshold == 1
    values = np.zeros(120)
    values[50:60] = 1
    intervals, _ = spot_intervals(values)
    assert intervals
    assert all(i['end_time']-i['start_time'] == pytest.approx(.4) for i in intervals)
    assert intervals[0]['peak_time'] == pytest.approx(54/30,abs=1/30)
