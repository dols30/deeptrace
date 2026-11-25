import type {ReactNode} from 'react';
import {formatBytes, formatModelScore, type ComponentResult, type Report} from '../lib/api';
import {Terms} from './terms';
import {assessment, audioCoverage, coverageDescription, label, observation, outcome, score, time} from '../lib/report-presentation';
import {ReviewChecks} from './review-checks';

function Facts({items}: {items: [string, ReactNode][]}) {
  return <dl className="report-facts">{items.map(([name, value]) => <div key={name} className={name === 'SHA-256' ? 'report-fact-wide' : undefined}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>;
}

export function ReportOverview({report}: {report: Report}) {
  const result = assessment(report);
  const observations = report.anomalies.filter(item => !['METADATA_WARNING', 'MODEL_DISAGREEMENT'].includes(item.code));
  return <div className="report-content">
    {report.processing && Object.values({media:report.processing.media_storage,workspace:report.processing.workflow_storage,history:report.processing.report_storage}).some(value => value === 'unavailable') && <p className="form-error" role="alert">Some results could not be saved. Download this report before leaving. See the examination record for details.</p>}
    <section className={`report-assessment ${result.tone}`} aria-labelledby="authenticity-title">
      <span className="report-assessment-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
          {result.tone === 'review' ? <path d="M6 21V4m0 0c4-4 8 4 12 0v10c-4 4-8-4-12 0"/> : result.tone === 'incomplete' ? <><circle cx="12" cy="12" r="8"/><path d="M12 11v5m0-9v.1"/></> : <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></>}
        </svg>
      </span>
      <div className="report-assessment-copy">
        <h2 id="authenticity-title">{result.title}</h2>
        <p>{result.summary}</p>
        {result.tone === 'review' && result.missing > 0 && <p className="report-coverage">{result.missing} check{result.missing === 1 ? '' : 's'} did not return a usable result.</p>}
        <small>Advisory screening · requires qualified review</small>
      </div>
    </section>
    <div className="report-overview-card">
      <div className="report-overview-grid">
      <section className="report-overview-section" aria-labelledby="report-checks-title">
        <header className="report-panel-heading"><h2 id="report-checks-title">Detector checks</h2></header>
        <ul className="report-check-list">{report.components.map((component, index) => {
          const status = outcome(component);
          return <li key={`${component.detector_id ?? component.model_name}-${index}`}>
            <div><h3>{label(component, index)}</h3>
              {component.status === 'functional' && component.component === 'audio' && (component.coverage || /aasist/i.test(component.model_name)) && <p>{audioCoverage(component,report.media.duration_seconds)}</p>}
              {component.coverage?.mode === 'face_alignment_v1' && <p>{coverageDescription(component)}</p>}
              {component.status === 'functional' && component.component === 'video' && !component.coverage && component.num_samples != null && <p>{component.num_samples} samples checked</p>}
            </div>
            <span className={`report-state ${status.tone}`}>{status.text}</span>
          </li>;
        })}</ul>
      </section>
      <section className="report-overview-section" aria-labelledby="report-observations-title">
        <header className="report-panel-heading"><h2 id="report-observations-title">Findings</h2><span>{observations.length}</span></header>
        {observations.length ? <ul className="report-observation-list">{observations.map((item, index) => {
          const copy = observation(item.code, item.description);
          return <li key={`${item.code}-${index}`}><h3>{copy.title}</h3><p>{copy.description}</p></li>;
        })}</ul> : <p className="report-empty">No specific findings returned.</p>}
        <section className="report-next" aria-labelledby="report-next-title"><h2 id="report-next-title">Next step</h2><p>{result.next}</p></section>
      </section>
      </div>
    </div>
  </div>;
}

function DetectorEvidence({component, index}: {component: ComponentResult; index: number}) {
  const value = score(component);
  const notes = [...new Set([...(component.notes ?? []), ...(component.limitations ?? [])])];
  const validated = component.threshold_validated ?? component.threshold_validation?.validated ?? false;
  return <article className="report-detector">
    <header className="report-panel-heading"><h3>{label(component, index)}</h3><span className={`report-state ${component.status === 'functional' ? 'neutral' : 'incomplete'}`}>{component.status.replaceAll('_', ' ')}</span></header>
    <div className="report-panel-body">
      <Facts items={[
        ['Model score', <><strong className="report-model-score">{value == null ? 'Not available' : value.toFixed(3)}</strong><span className="report-value-note">Uncalibrated</span></>],
        ['Decision threshold', <>{component.threshold == null ? 'Not reported' : component.threshold.toString()}<span className="report-value-note">{validated ? 'Validation recorded' : 'Not DPS-validated'}</span></>],
        ['Estimated probability', component.calibrated_probability == null ? 'Not available' : formatModelScore(component.calibrated_probability)],
        ['Model', component.detector_name ?? component.model_name],
        ['Version', component.model_version],
        ['Samples reported', component.num_samples ?? component.samples?.length ?? 'Not reported'],
        ...(component.coverage ? [['Screened coverage', coverageDescription(component)] as [string,ReactNode]] : []),
      ]}/>
      <details className="report-detail"><summary>Processing and limitations</summary>
        <Facts items={[
          ['Checkpoint', component.checkpoint ?? 'Not reported'],
          ['Aggregation', component.aggregation_method ?? 'Not reported'],
          ['Threshold source', component.threshold_source ?? 'Not reported'],
          ['Threshold validation dataset', component.threshold_validation?.dataset ?? 'Not reported'],
          ['Validation target FPR', component.threshold_validation?.target_fpr == null ? 'Not reported' : formatModelScore(component.threshold_validation.target_fpr)],
          ['Detector status', component.detector_status ?? 'Not reported'],
          ['Operational status', component.operational_status ?? 'Not reported'],
          ['Review threshold', component.thresholds?.review == null ? 'Not reported' : component.thresholds.review.toString()],
          ['Flag threshold', component.thresholds?.flag == null ? 'Not reported' : component.thresholds.flag.toString()],
          ['Flagged timestamps', component.timestamps_seconds.length ? component.timestamps_seconds.map(time).join(', ') : 'None returned'],
        ]}/>
        {!!notes.length && <ul className="report-text-list">{notes.map(note => <li key={note}>{note}</li>)}</ul>}
      </details>
      {!!component.samples?.length && <details className="report-detail"><summary>Sample results ({component.samples.length})</summary>
        <div className="report-table-scroll"><table className="report-sample-table"><thead><tr><th scope="col">Reported time</th><th scope="col">Model score</th><th scope="col">Raw logits</th></tr></thead><tbody>{component.samples.map((sample, sampleIndex) => <tr key={sampleIndex}>
          <td>{time(sample.start_time)}{sample.end_time != null ? ` – ${time(sample.end_time)}` : ''}</td><td>{sample.raw_score.toFixed(3)}</td><td>{sample.raw_logits?.length ? sample.raw_logits.join(', ') : 'Not reported'}</td>
        </tr>)}</tbody></table></div>
      </details>}
    </div>
  </article>;
}

export function ReportTechnical({report}: {report: Report}) {
  return <div className="report-content report-technical-content">
    <section className="report-panel report-media-card" aria-labelledby="report-media-title"><header className="report-panel-heading"><h2 id="report-media-title">File and provenance</h2></header><div className="report-panel-body"><Facts items={[
      ['File', report.media.filename], ['Media type', report.media.media_kind], ['File size', formatBytes(report.media.size_bytes)],
      ['Duration', report.media.duration_seconds == null ? 'Not available' : `${report.media.duration_seconds.toFixed(2)} seconds`],
      ['Container', report.media.container ?? 'Not reported'], ['Report ID', report.report_id], ['Generated', report.generated_at],
      ['SHA-256', report.media.sha256],
    ]}/></div></section>
    <section className="report-panel report-technical-section" aria-labelledby="report-evidence-title"><header className="report-panel-heading"><h2 id="report-evidence-title">Independent detector results</h2></header>
      <div className="report-panel-body"><p className="report-technical-note">No cross-detector average is calculated. Model scores are uncalibrated.</p>
      <div className="report-detector-grid">{report.components.map((component, index) => <DetectorEvidence key={`${component.detector_id ?? component.model_name}-${index}`} component={component} index={index}/>)}</div></div>
    </section>
    <ReviewChecks checks={report.review_checks}/>
    <div className="report-record-card">
    <section className="report-record-section" aria-labelledby="report-anomalies-title"><header className="report-panel-heading"><h2 id="report-anomalies-title">Recorded observations</h2><span>{report.anomalies.length}</span></header>
      {report.anomalies.length ? <ul className="report-technical-observations">{report.anomalies.map((item, index) => <li key={`${item.code}-${index}`}><header><code>{item.code}</code><span>{item.component} · {item.severity}</span></header><p>{item.description}</p></li>)}</ul> : <p className="report-empty">None returned.</p>}
    </section>
    <section className="report-record-section" aria-labelledby="report-methods-title"><header className="report-panel-heading"><h2 id="report-methods-title">Examination record</h2></header><div className="report-panel-body report-documentation-body">
      <section><h3>Automated summary</h3><p>{report.summary}</p></section>
      <section><h3>Scope and review</h3><p>{report.examination_scope}</p><p>{report.review_status}</p></section>
      {report.processing && <section><h3>Processing record</h3><Facts items={Object.entries(report.processing).map(([key,value]) => [key.replaceAll('_',' '),String(value)])}/></section>}
      <section><h3>Methods</h3>{report.methods.length ? <ul className="report-text-list">{report.methods.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>Not recorded.</p>}</section>
      <section><h3>Limitations</h3><p>{report.disclaimer}</p>{!!report.limitations.length && <ul className="report-text-list">{report.limitations.map((item, index) => <li key={index}>{item}</li>)}</ul>}</section>
      {!!Object.keys(report.integrity).length && <section><h3>Integrity record</h3><Facts items={Object.entries(report.integrity).map(([key, value]) => [key.replaceAll('_', ' '), value])}/></section>}
      <section><h3>Recommended action</h3><p>{report.recommended_action}</p></section>
      {!!report.references.length && <details className="report-detail"><summary>Reporting references</summary>{report.references.map((item, index) => <p key={index}><a href={/^https:\/\//.test(item.url) ? item.url : undefined} target="_blank" rel="noopener noreferrer">{item.organization}: {item.title}</a> · {item.version}<br/>{item.application}</p>)}</details>}
      <Terms/>
      <details className="report-detail"><summary>Structured report data</summary><pre className="report-json">{JSON.stringify(report, null, 2)}</pre></details>
    </div></section>
    </div>
  </div>;
}
