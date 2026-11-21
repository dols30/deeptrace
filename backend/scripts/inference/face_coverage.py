"""Observe upstream dlib calls without changing detections, crops or scores."""


class FaceCoverageTracker:
    def __init__(self, detector):
        self.detector = detector
        self.initial_faces = None
        self.counts = dict(mode='face_alignment_v1', frames_sampled=0,
                           frames_with_detected_face=0, frames_without_detected_face=0,
                           frames_with_unalignable_face=0, frames_scored=0)

    def begin_frame(self):
        self.initial_faces = None

    def __call__(self, *args, **kwargs):
        faces = self.detector(*args, **kwargs)
        # Subsequent calls inspect the aligned crop. Only the first call sees the source frame.
        if self.initial_faces is None:
            self.initial_faces = len(faces)
        return faces

    def finish_frame(self, scored):
        if self.initial_faces is None or (scored and not self.initial_faces):
            raise ValueError('Inconsistent face detection coverage')
        self.counts['frames_sampled'] += 1
        if self.initial_faces:
            self.counts['frames_with_detected_face'] += 1
            if not scored:
                self.counts['frames_with_unalignable_face'] += 1
        else:
            self.counts['frames_without_detected_face'] += 1
        self.counts['frames_scored'] += int(scored)

    def summary(self):
        return {**self.counts, 'complete': self.counts['frames_scored'] == self.counts['frames_sampled']}
