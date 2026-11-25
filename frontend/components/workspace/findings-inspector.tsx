import {clock, type Disposition, type Finding} from '../../lib/workflow';
import {EMPTY_FINDINGS} from '../guide/tour-copy';
import {Terms} from '../terms';

const DISPOSITIONS: {value: Disposition; label: string}[] = [
  {value: 'agree', label: 'Agree with this flag'},
  {value: 'disagree', label: 'Disagree with this flag'},
  {value: 'uncertain', label: 'Uncertain'},
  {value: 'needs_expert_review', label: 'Request expert review'},
];

const DETECTOR_TASKS: {match: RegExp; label: string}[] = [
  {match: /CNNDetection/i, label: 'GAN artifacts'},
  {match: /LFCC-LCNN/i, label: 'Vocoder artifacts'},
  {match: /efficientnet|xception|effort/i, label: 'Face manipulation'},
  {match: /community forensics|commfor|scene/i, label: 'AI-generated video'},
  {match: /aasist|nes2net/i, label: 'Synthetic speech'},
];

export function detectorTask(modelName: string) {
  return DETECTOR_TASKS.find(item => item.match.test(modelName))?.label ?? modelName;
}

export type FindingRun = {key: string; modelName: string; start: number; end: number | null; peak: number; items: {finding: Finding; index: number}[]};

export function findingRuns(findings: Finding[]): FindingRun[] {
  const runs: FindingRun[] = [];
  findings.forEach((finding, index) => {
    const run = runs.findLast(item => item.modelName === finding.model_name);
    const runEnd = run ? run.end ?? run.start : 0;
    if (run && finding.start_time <= runEnd + 0.05) {
      run.items.push({finding, index});
      run.end = Math.max(runEnd, finding.end_time ?? finding.start_time);
      run.peak = Math.max(run.peak, finding.raw_score);
      return;
    }
    runs.push({key: finding.id, modelName: finding.model_name, start: finding.start_time, end: finding.end_time, peak: finding.raw_score, items: [{finding, index}]});
  });
  return runs.sort((a, b) => a.start - b.start);
}

export function FindingsInspector({
  technical = false,
  findings,
  selected,
  note,
  saveState,
  onSelect,
  onNote,
  onDisposition,
}: {
  technical?: boolean;
  findings: Finding[];
  selected: Finding | null;
  note: string;
  saveState: string;
  onSelect: (finding: Finding) => void;
  onNote: (value: string) => void;
  onDisposition: (value: Disposition) => void;
}) {
  return <section className="findings-pane" aria-label="Flagged material" data-tour="finding">
    <header className="pane-head">
      <h2>Flagged material</h2>
      <span>{findings.length}</span>
    </header>
    {!findings.length && <p className="workspace-empty" data-tour="disposition">{technical ? EMPTY_FINDINGS : 'No review items were returned. Check the screening summary for any checks that did not complete.'}</p>}
    <ol className="finding-runs">{findingRuns(findings).map(run => <li key={run.key} className="finding-run">
      <header>
        <strong>{detectorTask(run.modelName)}</strong>
        <span>{clock(run.start)} – {clock(run.end)} · {run.items.length} {run.items.length === 1 ? 'window' : 'windows'}{technical && ` · peak ${run.peak.toFixed(2)}`}</span>
      </header>
      <ol>{run.items.map(({finding, index}) => <li key={finding.id}><button type="button" className={finding.id === selected?.id ? 'selected' : ''} onClick={() => onSelect(finding)}><span className={`modality ${finding.modality}`}>{finding.modality === 'video' ? 'V' : 'A'}</span><span className="finding-label">Finding {index + 1}<small>{clock(finding.start_time)} – {clock(finding.end_time)}</small></span>{technical && <b>{finding.raw_score.toFixed(2)}</b>}</button></li>)}</ol>
    </li>)}</ol>
    {selected && <article className="finding-card">
      <p className="finding-kicker">Possible {selected.modality === 'video' ? 'visual' : 'audio'} manipulation signal</p>
      <p className="finding-detector">{detectorTask(selected.model_name)}</p>
      <p>{clock(selected.start_time)} – {clock(selected.end_time)}</p>
      {!technical && <p>Review this flagged material in context. The flag does not prove manipulation or identify an edited region.</p>}
      {technical && <>
      <dl>
        <div><dt>Model screening score</dt><dd>{selected.raw_score.toFixed(2)}</dd></div>
        <div><dt>Decision threshold</dt><dd>{selected.threshold.toString()}</dd></div>
        <div><dt>Estimated probability</dt><dd>{selected.calibrated_probability == null ? 'Not available' : selected.calibrated_probability.toFixed(2)}</dd></div>
        <div><dt>Model</dt><dd>{selected.model_name} {selected.model_version}</dd></div>
      </dl>
      <p className="threshold-note">Development threshold; not yet DPS-validated.</p>
      <details className="technical-finding-output"><summary>Raw detector output</summary><dl>
        <div><dt>Score scope</dt><dd>{selected.score_scope}</dd></div>
        <div><dt>Preprocessing version</dt><dd>{selected.preprocessing_version}</dd></div>
        <div><dt>Raw logits</dt><dd>{selected.raw_logits?.length ? selected.raw_logits.map(value => value.toString()).join(', ') : 'Not available'}</dd></div>
        <div><dt>Normalized score</dt><dd>{selected.normalized_score == null ? 'Not available' : selected.normalized_score.toString()}</dd></div>
      </dl></details>
      <Terms/>
      </>}
      <fieldset data-tour="disposition">
        <legend>How do you assess this flag?</legend>
        {DISPOSITIONS.map(item => <label key={item.value}><input type="radio" name="disposition" value={item.value} checked={selected.human_disposition === item.value} onChange={() => onDisposition(item.value)}/>{item.label}</label>)}
      </fieldset>
      <label className="stack">Comment<textarea value={note} onChange={event => onNote(event.target.value)} maxLength={4000} aria-label="Investigator comment on this finding"/></label>
      {!!selected.reviews.length && <ol className="review-history">{selected.reviews.map(review => <li key={review.id}><span>{review.previous_value ?? 'unset'} → {review.new_value}</span><small>{review.actor_id}</small>{review.comment && <p>{review.comment}</p>}</li>)}</ol>}
      <p aria-live="polite">{saveState}</p>
    </article>}
  </section>;
}
