import Link from 'next/link';
import {EVENTS, LANES, LANE_SCORE, score2} from './fixture';

const CHAIN = [
  {label: 'Model output', note: 'Three separate model scores', state: 'done'},
  {label: 'Supporting evidence', note: 'Frames and windows at or above the rule', state: 'done'},
  {label: 'Attribution', note: 'Grad-CAM (face) and occlusion (audio) when enabled', state: 'available'},
  {label: 'Investigator interpretation', note: 'Disposition of each finding', state: 'current'},
  {label: 'Human conclusion', note: 'Supervisor finalises or requests changes', state: 'pending'},
] as const;

export function CaseStatus() {
  const faceFrames = EVENTS.filter(event => event.lane === 'face').length;
  return (
    <section className="trace-case" aria-label="Illustrative case status">
      <header><span>DEEPTRACE</span><b>CASE 0042</b></header>
      <ul className="trace-case-rows">
        {LANES.map(lane => (
          <li key={lane.id} className={`trace-lane-${lane.id}`}>
            <span className="trace-swatch" aria-hidden="true" />
            <span>{lane.label}</span>
            <code>{score2(LANE_SCORE[lane.id])}</code>
            <em>Complete</em>
          </li>
        ))}
      </ul>
      <div className="trace-case-evidence">
        <b>Evidence available</b>
        <p>{faceFrames} face frames at or above the 0.50 rule · 1 file-level audio score at or above the rule · no AI-generated frames at or above the rule.</p>
      </div>
      <ol className="trace-chain">
        {CHAIN.map(step => <li key={step.label} className={step.state}><b>{step.label}</b><small>{step.note}</small></li>)}
      </ol>
      <div className="trace-case-foot">
        <strong>Review required</strong>
        <Link className="trace-button" href="/queue/">Open investigation</Link>
      </div>
    </section>
  );
}
