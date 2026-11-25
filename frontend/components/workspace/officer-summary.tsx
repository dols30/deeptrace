import {formatBytes} from '../../lib/api';
import {clock, type AnalysisDetail, type Finding} from '../../lib/workflow';
import {Terms} from '../terms';
import {detectorTask} from './findings-inspector';
import {ReviewChecks} from '../review-checks';
import {audioCoverage, coverageDescription, formatScreeningNote, limitedFaceCoverage} from '../../lib/report-presentation';

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

export function OfficerSummary({analysis, selectedId, onReviewFinding}: {
  analysis: AnalysisDetail;
  selectedId?: string;
  onReviewFinding?: (finding: Finding) => void;
}) {
  const demo = analysis.development_mock || analysis.model_runs.some(run => run.development_mock);
  const applicable = analysis.model_runs.filter(run => run.status !== 'not_applicable');
  const incomplete = !applicable.length || applicable.some(run => !completed(run) || limitedFaceCoverage(run));
  const hasFlags = analysis.findings.length > 0 || analysis.model_runs.some(run => flagged(analysis, run));
  const firstFinding = analysis.findings.reduce<Finding | undefined>((first, finding) =>
    !first || finding.start_time < first.start_time ? finding : first, undefined);
  const duration = Math.max(1, analysis.media.duration_seconds ?? 0, ...analysis.findings.map(item => item.end_time ?? item.start_time ?? 0));
  const lanes = new Map<string, {finding: Finding; index: number}[]>();
  analysis.findings.forEach((finding, index) => {
    const label = detectorTask(finding.model_name);
    const lane = lanes.get(label) ?? [];
    lane.push({finding, index});
    lanes.set(label, lane);
  });
  const title = demo ? 'Demonstration results only'
    : hasFlags ? 'Signs of possible manipulation flagged'
    : incomplete ? 'Screening incomplete' : 'No signs of manipulation flagged';
  return <section className="officer-summary screening-summary" aria-labelledby="screening-summary-title">
    <header className="screening-status">
      <div>
        <h2 id="screening-summary-title"><span aria-hidden="true" className={hasFlags && !demo ? 'screening-flag' : undefined}>{hasFlags && !demo ? '⚑' : '○'}</span>{title}</h2>
        <p>{demo ? 'Demonstration values cannot be used to assess this recording.'
          : hasFlags ? 'Authenticity has not been established. Findings require qualified review.'
          : incomplete ? 'One or more checks have missing or limited coverage.'
          : 'Authenticity has not been established. Manipulation may still be present.'}</p>
      </div>
      {!demo && firstFinding && onReviewFinding && <button className="secondary-button" type="button" onClick={() => onReviewFinding(firstFinding)}>Review findings <span aria-hidden="true">↓</span></button>}
    </header>
    <div className="screening-results">
      <section className="screening-findings" aria-labelledby="screening-findings-title">
        <header><h3 id="screening-findings-title">Flagged moments</h3>{!demo && !!analysis.findings.length && <span>{analysis.findings.length} {analysis.findings.length === 1 ? 'finding' : 'findings'}</span>}</header>
        {!demo && lanes.size > 0 ? <>
          <div className="screening-axis"><span>{clock(0)}</span><span>{clock(duration / 2)}</span><span>{clock(duration)}</span></div>
          {[...lanes].map(([label, items]) => {
            const rowEnds: number[] = [];
            return <div className="screening-lane" key={label}>
              <h4>{label}</h4>
              <div className="screening-track">
                {items.toSorted((a, b) => a.finding.start_time - b.finding.start_time).map(({finding, index}) => {
                  const start = Math.max(0, Math.min(.97, (finding.start_time || 0) / duration));
                  const end = Math.min(1, Math.max(start + .03, (finding.end_time ?? finding.start_time ?? 0) / duration));
                  const nextRow = rowEnds.findIndex(value => value <= start);
                  const row = nextRow < 0 ? rowEnds.length : nextRow;
                  rowEnds[row] = end;
                  return <div className="screening-marker" key={finding.id ?? index} style={{gridRow: row + 1, width: `${(end - start) * 100}%`, marginInlineStart: `${start * 100}%`}}>
                    <button id={`finding-${finding.id}`} type="button" title={`Finding ${index + 1} · ${clock(finding.start_time)}`}
                      aria-label={`Finding ${index + 1}, ${label} at ${clock(finding.start_time)}`}
                      aria-pressed={selectedId === finding.id} disabled={!onReviewFinding} onClick={() => onReviewFinding?.(finding)}>{index + 1}</button>
                  </div>;
                })}
              </div>
            </div>;
          })}
          <p className="screening-observation">{observation((analysis.findings.find(item => item.id === selectedId) ?? analysis.findings[0]).model_name)}</p>
        </> : <p className="screening-observation">{demo ? 'Findings are hidden for demonstration values.' : hasFlags ? 'A check flagged this recording without returning a specific timestamp. Review the full recording.' : 'No flagged moments were returned.'}</p>}
      </section>
      <section className="screening-checks" aria-labelledby="screening-checks-title">
        <h3 id="screening-checks-title">Detector results</h3>
        <ul className="officer-checks">{analysis.model_runs.map(run => {
          const state = demo ? 'demo' : run.status === 'not_applicable' ? 'skipped' : !completed(run) ? 'missing' : flagged(analysis, run) ? 'flagged' : limitedFaceCoverage(run) ? 'limited' : 'checked';
          const labels = {demo: 'Demonstration only', skipped: 'Not applicable to this recording', missing: 'No usable result', flagged: 'Flagged for review', limited: 'Limited coverage', checked: 'Nothing flagged in checked material'};
          return <li key={run.id}>
            <strong>{detectorTask(run.model_name)}</strong>
            <span className={`screening-outcome ${state}`}><span aria-hidden="true">{state === 'flagged' ? '⚑' : state === 'checked' ? '○' : '—'}</span> {labels[state]}</span>
            {completed(run) && !demo && run.modality === 'audio' && (run.coverage || /aasist/i.test(run.model_name)) && <small>{run.coverage ? audioCoverage(run) : <>Only the opening {Math.min(analysis.media.duration_seconds ?? 4.0375, 4.0375).toFixed(2)} seconds were screened.{(analysis.media.duration_seconds == null || analysis.media.duration_seconds > 4.0375) && ' Later audio was not checked.'}</>}</small>}
            {!demo && run.coverage?.mode === 'face_alignment_v1' && <small>{coverageDescription(run)}</small>}
          </li>;
        })}</ul>
        {!demo && hasFlags && incomplete && <p className="screening-observation">Some checks did not return a usable result or have limited coverage. See Technical details.</p>}
      </section>
    </div>
  </section>;
}

function technicalRunStatus(run: ModelRun) {
  if (run.development_mock) return 'Demonstration only';
  if (run.status === 'not_applicable') return 'Not applicable';
  if (run.status === 'error') return 'Check failed';
  if (!completed(run)) return 'No usable result';
  return limitedFaceCoverage(run) ? 'Limited coverage' : 'Completed';
}

export function TechnicalResults({analysis}: {analysis: AnalysisDetail}) {
  return <section className="technical-results technical-workbench" aria-labelledby="technical-results-title">
    <header>
      <h2 id="technical-results-title">Technical details</h2>
      <p>Each detector reports a separate screening score. Scores are uncalibrated.</p>
    </header>
    <section className="technical-block" aria-labelledby="detector-evidence-title">
      <div className="technical-block-heading">
        <h3 id="detector-evidence-title">Detector evidence</h3>
        <p>Thresholds shown here are development rules.</p>
      </div>
      {analysis.model_runs.length ? <div className="report-table-scroll">
        <table className="technical-evidence-table">
          <thead><tr><th scope="col">Detector</th><th scope="col">Run status</th><th scope="col">Model score</th><th scope="col">Decision threshold</th></tr></thead>
          <tbody>{analysis.model_runs.map(run => <tr key={run.id}>
            <th scope="row">
              <details className="technical-run-detail">
                <summary>{detectorTask(run.model_name)}</summary>
                <dl>
                  <div><dt>Model</dt><dd>{run.model_name}</dd></div>
                  <div><dt>Version</dt><dd>{run.model_version}</dd></div>
                  <div><dt>Estimated probability</dt><dd>{run.calibrated_probability == null ? 'Not available' : run.calibrated_probability.toFixed(2)}</dd></div>
                  <div><dt>Preprocessing version</dt><dd>{run.preprocessing_version}</dd></div>
                  <div><dt>Calibration version</dt><dd>{run.calibration_version ?? 'Not fitted'}</dd></div>
                  {run.coverage && <div><dt>Screened coverage</dt><dd>{coverageDescription(run)}</dd></div>}
                </dl>
                {!!run.notes.length && <ul>{run.notes.map((note, index) => <li key={index}>{formatScreeningNote(note)}</li>)}</ul>}
              </details>
            </th>
            <td>{technicalRunStatus(run)}</td>
            <td>{run.raw_score != null && Number.isFinite(run.raw_score) ? run.raw_score.toFixed(2) : 'Not available'}</td>
            <td>{run.threshold.toString()}</td>
          </tr>)}</tbody>
        </table>
      </div> : <p className="technical-empty">No detector runs were recorded for this analysis.</p>}
    </section>
    <section className="technical-block" aria-labelledby="technical-media-title">
      <div className="technical-block-heading"><h3 id="technical-media-title">Media metadata</h3></div>
      <div className="technical-block-body">
        <dl className="technical-file technical-media-facts">
          <div><dt>Filename</dt><dd>{analysis.media.filename}</dd></div>
          <div><dt>Media type</dt><dd>{analysis.media.content_type}</dd></div>
          <div><dt>Duration</dt><dd>{clock(analysis.media.duration_seconds)}</dd></div>
          <div><dt>File size</dt><dd>{formatBytes(analysis.media.size_bytes)}</dd></div>
          <div><dt>Container</dt><dd>{analysis.media.container ?? 'Not available'}</dd></div>
        </dl>
        <details className="technical-finding-output"><summary>File identifiers</summary><dl className="technical-file">
          <div><dt>Analysis ID</dt><dd>{analysis.id}</dd></div>
          <div className="technical-hash"><dt>SHA-256</dt><dd>{analysis.media.sha256}</dd></div>
        </dl></details>
      </div>
    </section>
    <ReviewChecks checks={analysis.review_checks}/>
    <details className="technical-finding-output technical-glossary"><summary>Glossary</summary><Terms/></details>
  </section>;
}
