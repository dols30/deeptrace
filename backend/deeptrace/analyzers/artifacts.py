"""Opt-in trained artifact detectors; all inference remains in subprocesses."""
from deeptrace.analyzers.audio import AudioCommandAnalyzer
from deeptrace.analyzers.video import VideoCommandAnalyzer


class GANArtifactAnalyzer(VideoCommandAnalyzer):
    model_name = 'CNNDetection ResNet-50 (blur/JPEG)'
    command_setting = 'DEEPTRACE_GAN_ARTIFACT_COMMAND'
    detector_id = 'cnn_gan_artifacts'
    task = 'synthetic_video'
    scores_faces = False
    face_based = False
    aggregation_method = 'mean_frame_score'

    def analyze(self, path, metadata):
        result = super().analyze(path, metadata)
        for anomaly in result.anomalies:
            if anomaly.code == 'ELEVATED_GENERATED_SCENE_SCORE':
                anomaly.code = 'ELEVATED_GAN_ARTIFACT_SCORE'
                anomaly.description = 'Learned synthesis-artifact scores averaged above the provisional review threshold.'
        return result


class VocoderArtifactAnalyzer(AudioCommandAnalyzer):
    model_name = 'ASVspoof DF LFCC-LCNN'
    command_setting = 'DEEPTRACE_VOCODER_ARTIFACT_COMMAND'
    detector_id = 'lfcc_lcnn_artifacts'
    task = 'audio_spoof'
    aggregation_method = 'mean_nonoverlapping_window_score_v1'

    def analyze(self, path, metadata):
        result = super().analyze(path, metadata)
        for anomaly in result.anomalies:
            if anomaly.code == 'ELEVATED_SPOOF_SCORE':
                anomaly.code = 'ELEVATED_VOCODER_ARTIFACT_SCORE'
                anomaly.description = 'One or more audio windows showed learned spectral patterns associated with synthetic or converted speech.'
        return result
