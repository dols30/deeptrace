import type {ComponentResult, Report} from './api';

export function audioCoverage(component: Pick<ComponentResult,'coverage'>, duration?:number|null) {
  if (component.coverage && component.coverage.mode !== 'face_alignment_v1') return `${component.coverage.analyzed_seconds.toFixed(2)} of ${component.coverage.duration_seconds.toFixed(2)} seconds screened (${component.coverage.windows} window${component.coverage.windows === 1 ? '' : 's'})`;
  return `Opening ${Math.min(duration ?? 4.0375,4.0375).toFixed(2)} seconds screened`;
}

export function coverageDescription(component: Pick<ComponentResult,'coverage'>, duration?:number|null) {
  const c = component.coverage;
  if (c?.mode !== 'face_alignment_v1') return audioCoverage(component,duration);
  return `${c.frames_scored} of ${c.frames_sampled} sampled frames scored; ${c.frames_without_detected_face} with no detected face; ${c.frames_with_unalignable_face} with a detected face that could not be aligned. No detected face does not establish that no face is present.`;
}

export function limitedFaceCoverage(run: {coverage?:ComponentResult['coverage']; coverage_limited?:boolean; notes?:string[]}) {
  const c = run.coverage;
  if (run.coverage_limited || (c?.mode === 'face_alignment_v1' && c.frames_scored * 2 < c.frames_sampled)) return true;
  // Preserve coverage warnings in older stored runs, which have only runner notes.
  return !!run.notes?.some(note => {
    const match = /^Scored (\d+) of (\d+) sampled frames/.exec(note);
    return note === 'LIMITED_FACE_COVERAGE' || (match != null && Number(match[1]) * 2 < Number(match[2]));
  });
}

function task(component: ComponentResult, index: number) {
  return component.task ?? (component.component === 'audio' ? 'audio_spoof' : /community|commfor|scene/i.test(component.model_name) ? 'synthetic_video' : index === 0 ? 'face_manipulation' : 'synthetic_video');
}

export function label(component: ComponentResult, index: number) {
  if (component.detector_id === 'cnn_gan_artifacts' || /CNNDetection/i.test(component.model_name)) return 'GAN artifacts';
  if (component.detector_id === 'lfcc_lcnn_artifacts' || /LFCC-LCNN/i.test(component.model_name)) return 'Vocoder artifacts';
  return ({face_manipulation: 'Face manipulation', synthetic_video: 'AI-generated imagery', audio_spoof: 'Synthetic speech'})[task(component, index)];
}

export function score(component: ComponentResult) {
  const value = component.raw_score ?? component.synthetic_confidence;
  return value != null && Number.isFinite(value) ? value : null;
}

function flagged(component: ComponentResult) {
  return component.status === 'functional' && (
    component.anomalies?.some(item => item.code.startsWith('ELEVATED_')) ||
    (score(component) != null && component.threshold != null && score(component)! >= component.threshold) ||
    component.timestamps_seconds.length > 0
  );
}

export function outcome(component: ComponentResult) {
  if (component.status === 'stub') return {text: 'Demo only', tone: 'neutral'};
  if (component.status === 'not_applicable') return {text: 'Not applicable', tone: 'neutral'};
  if (flagged(component)) return {text: 'Flagged', tone: 'review'};
  if (component.status !== 'functional' || score(component) == null) return {text: 'Incomplete', tone: 'incomplete'};
  if (component.anomalies?.some(item => item.code === 'LIMITED_FACE_COVERAGE')) return {text: 'Limited coverage', tone: 'incomplete'};
  if (component.threshold == null || !Number.isFinite(component.threshold)) return {text: 'Score only', tone: 'incomplete'};
  return {text: 'No flags', tone: 'neutral'};
}

export function assessment(report: Report) {
  const applicable = report.components.filter(item => item.status !== 'not_applicable');
  const missing = applicable.filter(item => item.status !== 'functional' || score(item) == null || (!flagged(item) && (item.threshold == null || !Number.isFinite(item.threshold)))).length;
  const limited = report.anomalies.some(item => item.code === 'LIMITED_FACE_COVERAGE') || report.components.some(item => item.anomalies?.some(anomaly => anomaly.code === 'LIMITED_FACE_COVERAGE'));
  if (report.components.some(item => item.status === 'stub')) return {tone: 'neutral', title: 'Demonstration results', summary: 'Placeholder results cannot assess this recording.', next: 'Screen an approved recording with the configured detectors.', missing};
  if (report.components.some(flagged) || report.anomalies.some(item => item.code.startsWith('ELEVATED_'))) return {tone: 'review', title: 'Possible manipulation flagged', summary: 'The screening found material that needs closer review.', next: 'Review the flagged material, document your observations, and submit the report for review.', missing};
  if (!applicable.length || missing) return {tone: 'incomplete', title: 'Unable to assess authenticity', summary: 'One or more checks did not return a usable result.', next: 'Repeat the screening or request forensic review before relying on this result.', missing};
  if (limited) return {tone: 'incomplete', title: 'Limited screening coverage', summary: 'Some material could not be assessed by the configured checks.', next: 'Review the coverage gaps and request forensic review where needed.', missing};
  return {tone: 'neutral', title: 'No manipulation detected', summary: 'No manipulation was flagged in the material checked. Authenticity remains unverified.', next: 'Review the recording and its source, then document your assessment.', missing};
}

export function time(value: number) {
  return `${String(Math.floor(value / 60)).padStart(2, '0')}:${(value % 60).toFixed(1).padStart(4, '0')}`;
}

export function observation(code: string, description: string) {
  return ({
    ELEVATED_FRAME_SCORE: {title: 'Face check', description: 'One or more sampled frames were flagged for closer review.'},
    ELEVATED_GENERATED_SCENE_SCORE: {title: 'Generated-image check', description: 'The check flagged sampled images for possible synthetic content.'},
    ELEVATED_SPOOF_SCORE: {title: 'Speech check', description: 'The check flagged the screened audio for possible synthetic or spoofed speech.'},
    ELEVATED_GAN_ARTIFACT_SCORE: {title: 'GAN artifact check', description: 'The image detector flagged learned patterns associated with generated imagery.'},
    ELEVATED_VOCODER_ARTIFACT_SCORE: {title: 'Vocoder artifact check', description: 'The spectral detector flagged audio windows for possible synthetic or converted speech.'},
    LIMITED_FACE_COVERAGE: {title: 'Face coverage', description: 'Too few sampled frames contained a usable face.'},
  } as Record<string, {title: string; description: string}>)[code] ?? {title: code.replaceAll('_', ' ').toLowerCase(), description};
}
