import type {ReactNode} from 'react';
import {formatBytes, formatModelScore, type ComponentResult, type Report} from '../lib/api';
import {Terms} from './terms';
import {assessment, audioCoverage, coverageDescription, label, formatScreeningNote, observation, outcome, score, time} from '../lib/report-presentation';
import {ReviewChecks} from './review-checks';

function Facts({items}: {items: [string, ReactNode][]}) {
  return <dl className="report-facts">{items.map(([name, value]) => <div key={name} className={name === 'SHA-256' ? 'report-fact-wide' : undefined}><dt>{name}</dt><dd>{value}</dd></div>)}</dl>;
}

export function ReportOverview({report}: {report: Report}) {
  const result = assessment(report);
  const observations = report.anomalies.filter(item => !['METADATA_WARNING', 'MODEL_DISAGREEMENT'].includes(item.code));
  return <div className="report-content">
    {report.processing && Object.values({media:report.processing.media_storage,workspace:report.processing.workflow_storage,history:report.processing.report_storage}).some(value => value === 'unavailable') && <p className="form-error" role="alert">Some results could not be saved. Download this report before leaving. See the examination record for details.</p>}
    <section className="screening-status" aria-labelledby="authenticity-title">
      <div>
        <h2 id="authenticity-title"><span aria-hidden="true" className={result.tone === 'review' ? 'screening-flag' : undefined}>{result.tone === 'review' ? '⚑' : '○'}</span>{result.title}</h2>
        <p>{result.summary}</p>
        {result.tone === 'review' && result.missing > 0 && <p>{result.missing} check{result.missing === 1 ? '' : 's'} did not return a usable result.</p>}
        <p>Advisory screening · requires qualified review</p>
      </div>
    </section>
    <div className="screening-results report-screening-results">
      <section className="screening-findings" aria-labelledby="report-observations-title">
        <header><h3 id="report-observations-title">Findings</h3><span>{observations.length}</span></header>
        {observations.length ? <ul className="report-observation-list">{observations.map((item, index) => {
          const copy = observation(item.code, item.description);
          return <li key={`${item.code}-${index}`}><h4>{copy.title}</h4><p>{copy.description}</p></li>;
        })}</ul> : <p className="report-empty">No specific findings returned.</p>}
        <section className="report-next" aria-labelledby="report-next-title"><h3 id="report-next-title">Next step</h3><p>{result.next}</p></section>
      </section>
      <section className="screening-checks" aria-labelledby="report-checks-title">
        <h3 id="report-checks-title">Detector results</h3>
        <ul className="officer-checks">{report.components.map((component, index) => {
          const status = outcome(component);
          return <li key={`${component.detector_id ?? component.model_name}-${index}`}>
            <strong>{label(component, index)}</strong>
            <span className={`screening-outcome ${status.tone === 'review' ? 'flagged' : status.tone === 'incomplete' ? 'missing' : status.text === 'No flags' ? 'checked' : 'skipped'}`}><span aria-hidden="true">{status.tone === 'review' ? '⚑' : status.text === 'No flags' ? '○' : '—'}</span> {status.text === 'No flags' ? 'Nothing flagged in checked material' : status.text === 'Flagged' ? 'Flagged for review' : status.text}</span>
              {component.status === 'functional' && component.component === 'audio' && (component.coverage || /aasist/i.test(component.model_name)) && <small>{audioCoverage(component,report.media.duration_seconds)}</small>}
              {component.coverage?.mode === 'face_alignment_v1' && <small>{coverageDescription(component)}</small>}
              {component.status === 'functional' && component.component === 'video' && !component.coverage && component.num_samples != null && <small>{component.num_samples} samples checked</small>}
          </li>;
        })}</ul>
      </section>

    </div>
  </div>;
}

function DetectorEvidence({component}: {component: ComponentResult}) {
  const notes = [...new Set([...(component.notes ?? []), ...(component.limitations ?? [])])];
  return <article className="report-detector">
    <div className="report-panel-body">
      <Facts items={[
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
        {!!notes.length && <ul className="report-text-list">{notes.map(note => <li key={note}>{formatScreeningNote(note)}</li>)}</ul>}
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
    <section className="technical-block" aria-labelledby="report-evidence-title">
      <div className="technical-block-heading"><h3 id="report-evidence-title">Detector evidence</h3><p>Scores are uncalibrated. No cross-detector average is calculated.</p></div>
      {report.components.length ? <div className="report-table-scroll"><table className="technical-evidence-table">
        <thead><tr><th scope="col">Detector</th><th scope="col">Outcome</th><th scope="col">Model score</th><th scope="col">Decision threshold</th></tr></thead>
        <tbody>{report.components.map((component, index) => {
          const status = outcome(component);
          const value = score(component);
          const validated = component.threshold_validated ?? component.threshold_validation?.validated ?? false;
          return <tr key={`${component.detector_id ?? component.model_name}-${index}`}>
            <th scope="row"><details className="technical-run-detail"><summary>{label(component, index)}</summary>
              <DetectorEvidence component={component}/>
            </details></th>
            <td><span className={`report-state ${status.tone}`}>{status.text}</span></td>
            <td>{value == null ? 'Not available' : value.toFixed(3)}</td>
            <td>{component.threshold ?? 'Not reported'}{component.threshold != null && <span className="report-value-note">{validated ? 'Validation recorded' : 'Development rule'}</span>}</td>
          </tr>;
        })}</tbody>
      </table></div> : <p className="technical-empty">No detector runs were recorded for this report.</p>}
    </section>
    <section className="report-panel report-media-card" aria-labelledby="report-media-title"><header className="report-panel-heading"><h2 id="report-media-title">File and provenance</h2></header><div className="report-panel-body"><Facts items={[
      ['File', report.media.filename], ['Media type', report.media.media_kind], ['File size', formatBytes(report.media.size_bytes)],
      ['Duration', report.media.duration_seconds == null ? 'Not available' : `${report.media.duration_seconds.toFixed(2)} seconds`],
      ['Container', report.media.container ?? 'Not reported'], ['Generated', report.generated_at],
    ]}/><details className="report-detail"><summary>File identifiers</summary>
      <Facts items={ [['Report ID', report.report_id], ['SHA-256', report.media.sha256]] }/>
    </details></div></section>
    <ReviewChecks checks={report.review_checks}/>
    <div className="report-record-card">
    <section className="report-record-section" aria-labelledby="report-anomalies-title"><header className="report-panel-heading"><h2 id="report-anomalies-title">Recorded observations</h2><span>{report.anomalies.length}</span></header>
      {report.anomalies.length ? <ul className="report-technical-observations">{report.anomalies.map((item, index) => <li key={`${item.code}-${index}`}><header><span>{item.component} · {item.severity}</span></header><p>{item.description}</p><details><summary>Observation code</summary><code>{item.code}</code></details></li>)}</ul> : <p className="report-empty">None returned.</p>}
    </section>
    <section className="report-record-section" aria-labelledby="report-methods-title"><header className="report-panel-heading"><h2 id="report-methods-title">Examination record</h2></header><div className="report-panel-body report-documentation-body">
      <section><h3>Automated summary</h3><p>{report.summary}</p></section>
      <section><h3>Scope and review</h3><p>{report.examination_scope}</p><p>{report.review_status}</p></section>
      {report.processing && <section><h3>Processing record</h3><Facts items={Object.entries(report.processing).map(([key,value]) => [key.replaceAll('_',' '),String(value)])}/></section>}
      <section><h3>Methods</h3>{report.methods.length ? <ul className="report-text-list">{report.methods.map((item, index) => <li key={index}>{formatScreeningNote(item)}</li>)}</ul> : <p>Not recorded.</p>}</section>
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
