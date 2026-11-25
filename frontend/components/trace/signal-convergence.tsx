import {DECISION_RULE, EVENTS, LANES, LANE_SCORE, LaneId, score2} from './fixture';
import {Terms} from '../terms';

export type LaneState = 'idle' | 'running' | 'done';

const LANE_Y: Record<LaneId, number> = {synthetic: 46, face: 120, audio: 194};
const NODE = {x: 390, y: 120};

function verdictLine(lane: LaneId, value: number | null) {
  if (value == null) return 'no score';
  if (lane === 'audio') return `${value >= DECISION_RULE ? 'At or above' : 'Below'} 0.50; first 4.04 s screened`;
  const flagged = EVENTS.filter(event => event.lane === lane).length;
  const mean = value >= DECISION_RULE ? 'Average at or above 0.50' : 'Average below 0.50';
  return `${mean}; ${flagged ? `${flagged} frames meet the rule` : 'no frames meet the rule'}`;
}

const LABELS: Record<LaneId, {name: string; short: string}> = {
  synthetic: {name: 'Generated imagery', short: 'Imagery'},
  face: {name: 'Face manipulation', short: 'Face'},
  audio: {name: 'Speech spoofing', short: 'Speech'},
};

function lanePath(y: number) {
  return y === NODE.y ? `M0 ${y}H${NODE.x}` : `M0 ${y}H250C330 ${y} 360 ${NODE.y} ${NODE.x} ${NODE.y}`;
}

export function DetectorReadouts({states, example = false}: {states: Record<LaneId, LaneState>; example?: boolean}) {
  return <>
    <ol className="trace-readouts">
      {LANES.map(lane => {
        const value = LANE_SCORE[lane.id];
        const done = states[lane.id] === 'done';
        const flagged = lane.id === 'audio' ? value != null && value >= DECISION_RULE : EVENTS.some(event => event.lane === lane.id);
        return <li key={lane.id} className={`trace-lane-${lane.id}`}>
          <span className="trace-swatch" aria-hidden="true" />
          <div>
            <b>{LABELS[lane.id].name}</b>
            <small>{lane.model}</small>
          </div>
          <strong>{done ? score2(value) : '—'}</strong>
          <em className={done && flagged ? 'at-rule' : ''}>{done ? verdictLine(lane.id, value) : 'pending'}</em>
        </li>;
      })}
    </ol>
    <p className="trace-footnote">Uncalibrated model scores, not probabilities. Results are never combined.{example && ' This example uses a threshold of 0.50.'}</p>
    {example && <Terms />}
  </>;
}

export function SignalConvergence({states, showReadouts = true, example = false, animateFlow = false}: {states: Record<LaneId, LaneState>; showReadouts?: boolean; example?: boolean; animateFlow?: boolean}) {
  const complete = LANES.every(lane => states[lane.id] === 'done');
  return (
    <figure className={`trace-convergence ${complete ? 'complete' : ''}`}>
      {example && <p className="trace-example-label">Example screening results</p>}
      <div className="trace-convergence-diagram">
      <svg viewBox="0 0 640 240" role="img" aria-label={`Three independent analyses. ${LANES.map(lane => `${lane.label}: ${states[lane.id]}`).join('. ')}. ${complete ? 'Their separate results are assembled as evidence for human review.' : ''}`}>
        {LANES.map(lane => (
          <g key={lane.id} className={`trace-lane trace-lane-${lane.id} ${states[lane.id]}`}>
            <path className="trace-lane-path" d={lanePath(LANE_Y[lane.id])} />
            {(states[lane.id] === 'running' || animateFlow) && <path className="trace-flow" d={lanePath(LANE_Y[lane.id])} aria-hidden="true" />}
            <text x="0" y={LANE_Y[lane.id] - 10}>{lane.short} · {states[lane.id] === 'done' ? 'complete' : states[lane.id] === 'running' ? 'analysing' : 'waiting'}</text>
          </g>
        ))}
        <path className={`trace-out ${complete ? 'done' : ''}`} d={`M${NODE.x} ${NODE.y}H640`} />
        <circle className="trace-node" cx={NODE.x} cy={NODE.y} r={complete ? 8 : 5} />
        <text className="trace-node-label" x={NODE.x + 18} y={NODE.y - 12}>{complete ? 'HUMAN REVIEW' : 'AWAITING ANALYSES'}</text>
        {complete && <text className="trace-node-sub" x={NODE.x + 18} y={NODE.y + 24}>3 separate results<tspan x={NODE.x + 18} dy="16">for human review</tspan></text>}
      </svg>
      {example && <div className="trace-diagram-labels" aria-hidden="true">
        {LANES.map(lane => <span key={lane.id} className="trace-input-label" style={{top: `${LANE_Y[lane.id] / 240 * 100}%`}}>{LABELS[lane.id].short}<small>Complete</small></span>)}
        <span className="trace-review-label">Human review<small>3 separate results</small></span>
      </div>}
      </div>
      {showReadouts && (
        <figcaption>
          <DetectorReadouts states={states} example={example} />
        </figcaption>
      )}
    </figure>
  );
}
