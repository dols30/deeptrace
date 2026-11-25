import {formatBytes} from '../../lib/api';
import {clock, type AnalysisDetail, type Finding} from '../../lib/workflow';
import {Terms} from '../terms';
import {detectorTask, findingRuns} from './findings-inspector';
import {ReviewChecks} from '../review-checks';
import {audioCoverage, coverageDescription, limitedFaceCoverage} from '../../lib/report-presentation';

type ModelRun = AnalysisDetail['model_runs'][number];

function completed(run: ModelRun) {
  return run.status === 'functional' && run.raw_score != null && Number.isFinite(run.raw_score);
}

function flagged(analysis: AnalysisDetail, run: ModelRun) {
  return analysis.findings.some(finding => finding.model_name === run.model_name && finding.modality === run.modality)
    || (completed(run) && run.raw_score! >= run.threshold);
}

function observation(modelName: string) {
  switch (detectorTask(modelName)) {
    case 'Face manipulation': return 'The face check flagged sampled images for closer review. Compare facial appearance with the surrounding recording.';
    case 'AI-generated video': return 'The whole-image check flagged sampled images for closer review. Examine the scene in context.';
    case 'Synthetic speech': return 'The speech check flagged the analyzed audio for closer review. Listen to this section and compare it with the recording’s source.';
    case 'GAN artifacts': return 'The image check flagged patterns associated with generated imagery. Review the scene and its source.';
    case 'Vocoder artifacts': return 'The spectral check flagged audio windows for possible synthetic or converted speech. Listen to the marked sections.';
    default: return 'This check flagged material for closer review. Examine it alongside the surrounding recording.';
  }
}

export function OfficerSummary({analysis, onReviewFinding}: {analysis: AnalysisDetail; onReviewFinding?: (finding: Finding) => void}) {
  const demo = analysis.development_mock || analysis.model_runs.some(run => run.development_mock);
  const applicable = analysis.model_runs.filter(run => run.status !== 'not_applicable');
  const incomplete = !applicable.length || applicable.some(run => !completed(run) || limitedFaceCoverage(run));
  const hasFlags = analysis.findings.length > 0 || analysis.model_runs.some(run => flagged(analysis, run));
  const moments = findingRuns(analysis.findings);
  const momentList = (items: typeof moments) => <ol className="officer-moments">{items.map(moment => <li key={moment.key}>
    <div><h4>{detectorTask(moment.modelName)}</h4><p>{observation(moment.modelName)}</p></div>
    {onReviewFinding
      ? <button type="button" className="secondary-button" onClick={() => onReviewFinding(moment.items[0].finding)} aria-label={`Review ${detectorTask(moment.modelName)} at ${clock(moment.start)}`}>
          Review {clock(moment.start)}{moment.end != null && moment.end > moment.start ? ` – ${clock(moment.end)}` : ''}
        </button>
      : <span>{clock(moment.start)}{moment.end != null && moment.end > moment.start ? ` – ${clock(moment.end)}` : ''}</span>}
  </li>)}</ol>;
  const title = demo ? 'Demonstration results only'
    : hasFlags ? 'Signs of possible manipulation flagged'
    : incomplete ? 'Screening incomplete' : 'No signs of manipulation flagged';
  return <section className={`officer-summary ${hasFlags && !demo ? 'has-flags' : ''}`} aria-labelledby="screening-summary-title">
    <p className="card-label">Advisory screening result</p>
    <h2 id="screening-summary-title">{title}</h2>
    <p className="officer-lede">{demo
      ? 'These are demonstration values. They cannot be used to assess this recording.'
      : hasFlags ? 'Automated checks identified material for you to review. This does not prove the recording was manipulated.'
      : incomplete ? 'One or more checks are missing or have limited coverage. Do not treat this as a clear result.'
      : 'The completed checks did not flag the material they screened. Manipulation may still be present.'}</p>
    <p className="officer-caution">Authenticity has not been established. A qualified reviewer must assess the recording.</p>
    <ul className="officer-checks">{analysis.model_runs.map(run => <li key={run.id}>
      <strong>{detectorTask(run.model_name)}</strong>
      <span>{demo ? 'Demonstration only' : run.status === 'not_applicable' ? 'Not applicable to this recording' : !completed(run) ? 'No usable result' : flagged(analysis, run) ? 'Flagged for review' : limitedFaceCoverage(run) ? 'Limited coverage' : 'Nothing flagged in checked material'}</span>
      {completed(run) && !demo && run.modality === 'audio' && (run.coverage || /aasist/i.test(run.model_name)) && <small>{run.coverage ? audioCoverage(run) : <>Only the opening {Math.min(analysis.media.duration_seconds ?? 4.0375, 4.0375).toFixed(2)} seconds were screened.{(analysis.media.duration_seconds == null || analysis.media.duration_seconds > 4.0375) && ' Later audio was not checked.'}</>}</small>}
      {!demo && run.coverage?.mode === 'face_alignment_v1' && <small>{coverageDescription(run)}</small>}
      {completed(run) && !demo && run.modality === 'video' && <small>Selected images were checked. This is not a check of every moment in the video.</small>}
    </li>)}</ul>
    {!demo && hasFlags && incomplete && <p className="officer-caution">Some checks did not return a usable result or have limited coverage. Review the available findings and the gaps in Technical details.</p>}
    {!demo && hasFlags && <section className="officer-observations" aria-labelledby="officer-observations-title">
      <h3 id="officer-observations-title">What needs your attention</h3>
      {moments.length ? <>
        {momentList(moments.slice(0, 3))}
        {moments.length > 3 && <details><summary>Show {moments.length - 3} more flagged sections</summary>{momentList(moments.slice(3))}</details>}
      </> : <p>A check flagged this recording without returning a specific timestamp. Review the full recording.</p>}
    </section>}
    <div className="officer-next"><h3>What to do next</h3><p>{demo ? 'Run the configured detectors on approved public or synthesized media.' : hasFlags
      ? 'Play the marked portions, record your assessment of each finding, and request expert review if you are unsure.'
      : 'Review the recording and its source. If the result is incomplete or you still have concerns, request a qualified forensic review.'} Document your reasoning in Review report.</p></div>
  </section>;
}

export function TechnicalResults({analysis}: {analysis: AnalysisDetail}) {
  return <section className="technical-results" aria-labelledby="technical-results-title">
    <header><h2 id="technical-results-title">Technical details</h2><p>Independent detector outputs and processing notes. Scores are uncalibrated and are never combined.</p></header>
    <section aria-labelledby="technical-media-title"><h3 id="technical-media-title">Media metadata</h3><dl className="technical-file">
      <div><dt>Filename</dt><dd>{analysis.media.filename}</dd></div>
      <div><dt>Media type</dt><dd>{analysis.media.content_type}</dd></div>
      <div><dt>Duration</dt><dd>{clock(analysis.media.duration_seconds)}</dd></div>
      <div><dt>File size</dt><dd>{formatBytes(analysis.media.size_bytes)}</dd></div>
      <div><dt>Container</dt><dd>{analysis.media.container ?? 'Not available'}</dd></div>
      <div><dt>Analysis ID</dt><dd>{analysis.id}</dd></div>
      <div className="technical-hash"><dt>SHA-256</dt><dd>{analysis.media.sha256}</dd></div>
    </dl></section>
    <div className="technical-models">{analysis.model_runs.map(run => <article key={run.id}>
      <h3>{detectorTask(run.model_name)}</h3>
      <dl>
        <div><dt>Model</dt><dd>{run.model_name}</dd></div>
        <div><dt>Version</dt><dd>{run.model_version}</dd></div>
        <div><dt>Run status</dt><dd>{run.status}</dd></div>
        <div><dt>Model score</dt><dd>{run.raw_score == null ? 'Not available' : run.raw_score.toFixed(2)}</dd></div>
        <div><dt>Decision threshold</dt><dd>{run.threshold.toString()}</dd></div>
        <div><dt>Estimated probability</dt><dd>{run.calibrated_probability == null ? 'Not available' : run.calibrated_probability.toFixed(2)}</dd></div>
        <div><dt>Preprocessing version</dt><dd>{run.preprocessing_version}</dd></div>
        <div><dt>Calibration version</dt><dd>{run.calibration_version ?? 'Not fitted'}</dd></div>
        {run.coverage && <div><dt>Screened coverage</dt><dd>{coverageDescription(run)}</dd></div>}
      </dl>
      <p>Development threshold; not yet DPS-validated.</p>
      {!!run.notes.length && <ul>{run.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>}
    </article>)}</div>
    {!analysis.model_runs.length && <p>No detector run records are available for this analysis.</p>}
    <ReviewChecks checks={analysis.review_checks}/>
    <Terms/>
  </section>;
}
