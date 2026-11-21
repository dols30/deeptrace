"""Optional numerical tests, run in the separate model environment."""
import sys
from pathlib import Path
import wave

import pytest

np = pytest.importorskip('numpy')
pytest.importorskip('librosa')
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts/inference'))
from review_signals import audio_checks
from review_math import block_boundary_ratio


def test_local_noise_floor_changes_survive_a_global_energy_shift(tmp_path):
    generator=np.random.default_rng(42)
    samples=np.concatenate([generator.normal(0,level,16000) for level in [.02,.001,.02]])
    path=tmp_path/'synthetic-noise.wav'
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
        output.writeframes((samples*32767).astype('<i2').tobytes())
    results={item['technique']:item for item in audio_checks(path,30,np)}
    assert results['background_noise']['measurements']['level_changes'] >= 2
    assert results['background_noise']['intervals'][0]['start_time'] == 1
    assert results['mel_spectrogram']['measurements']['mel_bands'] == 64
    assert not any(item['validated'] for item in results.values())
    assert 'no vocoder was identified' in results['vocoder']['summary']


def test_native_grid_measurement_distinguishes_grid_from_a_smooth_ramp():
    ramp=np.tile(np.arange(64,dtype=float),(64,1))
    yy,xx=np.indices((64,64))
    blocks=((yy//8+xx//8)%2)*255
    assert block_boundary_ratio(ramp,np) == pytest.approx(1,abs=.0001)
    assert block_boundary_ratio(blocks,np) > 10
