'use client';
import {useState} from 'react';
import {clock} from '../../lib/workflow';
import {AASIST_WINDOW, AUDIO_SCORE, CLIP_SECONDS, DECISION_RULE, EVENTS, FACE_SCORES, FRAMES, LANES, LaneId, SYNTHETIC_SCORES, score2} from './fixture';

const pct = (value: number) => `${(value / CLIP_SECONDS) * 100}%`;

function readingAt(lane: LaneId, time: number) {
  const index = Math.min(FRAMES.length - 1, Math.floor(time));
  if (lane === 'synthetic') return `Frame ${index + 1}: ${score2(SYNTHETIC_SCORES[index])}`;
  if (lane === 'face') {
    const value = FACE_SCORES[index];
    return value == null ? `Frame ${index + 1}: abstained, no alignable face` : `Frame ${index + 1}: ${score2(value)}`;
  }
  return time <= AASIST_WINDOW ? `Inside scored window · file score ${score2(AUDIO_SCORE)}` : 'Not analysed by AASIST';
}

export function EvidenceTimeline({time: controlled, onTime}: {time?: number; onTime?: (time: number) => void}) {
  const [local, setLocal] = useState(5.4);
  const time = controlled ?? local;
  const setTime = (value: number) => { setLocal(value); onTime?.(value); };
  return (
    <section className="trace-timeline" aria-label="Evidence timeline">
      <div className="trace-tl-grid">
        {LANES.map(lane => (
          <div key={lane.id} className={`trace-tl-row trace-lane-${lane.id}`}>
            <div className="trace-tl-label"><b>{lane.short}</b><small>{lane.label}</small></div>
            <div className="trace-tl-track">
              {lane.id !== 'audio' && FRAMES.map((start, index) => {
                const value = lane.id === 'face' ? FACE_SCORES[index] : SYNTHETIC_SCORES[index];
                return <i key={start} className={`trace-tl-sample ${value == null ? 'abstain' : ''}`} style={{left: pct(start), width: pct(1)}} />;
              })}
              {lane.id === 'audio' && <i className="trace-tl-window" style={{left: 0, width: pct(AASIST_WINDOW)}} />}
              {EVENTS.filter(event => event.lane === lane.id).map(event => (
                <span key={`${event.lane}-${event.start}`} className={`trace-tl-event ${lane.id === 'audio' ? 'file' : ''}`} style={{left: pct(event.start), width: pct(event.end - event.start)}}>
                  {lane.id === 'audio' ? `file score ${score2(event.score)} · not localised` : score2(event.score)}
                </span>
              ))}
              {lane.id === 'synthetic' && !EVENTS.some(event => event.lane === 'synthetic') && <em className="trace-tl-quiet">No frame at or above {DECISION_RULE.toFixed(2)}</em>}
            </div>
            <output className="trace-tl-reading">{readingAt(lane.id, time)}</output>
          </div>
        ))}
        <div className="trace-tl-axis" aria-hidden="true">
          <span />
          <div>{[0, 2, 4, 6, 8, 10].map(value => <small key={value} style={{left: pct(value)}}>{clock(value)}</small>)}</div>
        </div>
        <div className="trace-tl-playhead-layer" aria-hidden="true"><span /><div><i style={{left: pct(time)}} /></div><span /></div>
      </div>
      <label className="trace-scrub">
        <span>Playhead {clock(time)}</span>
        <input type="range" min={0} max={CLIP_SECONDS - 0.1} step={0.1} value={time} onChange={event => setTime(Number(event.target.value))} />
      </label>
    </section>
  );
}
