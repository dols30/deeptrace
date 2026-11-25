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

export function FindingPicker({findings, selected, onSelect}: {
  findings: Finding[];
  selected: Finding | null;
  onSelect: (finding: Finding) => void;
}) {
  const index = Math.max(0, findings.findIndex(finding => finding.id === selected?.id));
  return <div className="finding-picker">
    <label>Finding
      <select value={index} onChange={event => {
        const finding = findings[Number(event.target.value)];
        if (finding) onSelect(finding);
      }}>
        {findings.map((finding, position) => <option value={position} key={finding.id}>
          {position + 1}. {detectorTask(finding.model_name)} · {clock(finding.start_time)}
        </option>)}
      </select>
    </label>
    <div className="finding-picker-nav">
      <button type="button" aria-label="Previous finding" disabled={index === 0} onClick={() => onSelect(findings[index - 1])}>← Previous</button>
      <span aria-live="polite">{index + 1} of {findings.length}</span>
      <button type="button" aria-label="Next finding" disabled={index === findings.length - 1} onClick={() => onSelect(findings[index + 1])}>Next →</button>
    </div>
  </div>;
}

function reviewLabel(value: string | null) {
  return DISPOSITIONS.find(item => item.value === value)?.label ?? 'Not reviewed';
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
  return <div className="finding-review-stack">
    <section className="findings-pane" aria-label="Flagged material" data-tour="finding">
    <header className="pane-head">
      <h2>Flagged material</h2>
      <span>{findings.length}</span>
    </header>
    {!findings.length && <p className="workspace-empty" data-tour="disposition">{technical ? EMPTY_FINDINGS : 'No review items were returned. Check the screening summary for any checks that did not complete.'}</p>}
    {!!findings.length && <FindingPicker findings={findings} selected={selected} onSelect={onSelect}/>}
    {selected && <article className="finding-card">
      <h3 className="finding-detector">{detectorTask(selected.model_name)}</h3>
      <p>{clock(selected.start_time)} – {clock(selected.end_time)}</p>
      {!technical && <p>Review this interval in context before recording your assessment.</p>}
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
      </article>}
    </section>
    {selected && <section className="findings-pane finding-assessment" aria-labelledby="finding-assessment-title">
      <header className="pane-head"><h2 id="finding-assessment-title">Investigator assessment</h2></header>
      <fieldset data-tour="disposition">
        <legend>How do you assess this flag?</legend>
        {DISPOSITIONS.map(item => <label key={item.value}><input type="radio" name="disposition" value={item.value} checked={selected.human_disposition === item.value} onChange={() => onDisposition(item.value)}/>{item.label}</label>)}
      </fieldset>
      <label className="stack">Comment<textarea value={note} onChange={event => onNote(event.target.value)} maxLength={4000} aria-label="Investigator comment on this finding"/></label>
      {!!selected.reviews.length && <ol className="review-history">{selected.reviews.map(review => <li key={review.id}><span>{reviewLabel(review.previous_value)} → {reviewLabel(review.new_value)}</span>{review.comment && <p>{review.comment}</p>}</li>)}</ol>}
      <p aria-live="polite">{saveState}</p>
    </section>}
  </div>;
}
