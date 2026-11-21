"""Legacy real/imaginary FFT layout used by the pinned ASVspoof baseline."""


def install(torch):
    if not hasattr(torch, 'rfft'):
        def rfft(value, signal_ndim, normalized=False, onesided=True):
            dims = tuple(range(-signal_ndim, 0))
            operation = torch.fft.rfftn if onesided else torch.fft.fftn
            return torch.view_as_real(operation(value, dim=dims, norm='ortho' if normalized else 'backward'))
        torch.rfft = rfft
    original_stft = torch.stft

    def stft(*args, **kwargs):
        kwargs.setdefault('return_complex', False)
        return original_stft(*args, **kwargs)

    torch.stft = stft
