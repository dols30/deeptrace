"""Legacy real/imaginary FFT layout used by the pinned ASVspoof baseline."""


def install(torch):
    # Idempotent: a warm worker calls this once per request and must not stack stft wrappers.
    if getattr(torch.stft, '_deeptrace_lfcc_compat', False):
        return
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

    stft._deeptrace_lfcc_compat = True
    torch.stft = stft
