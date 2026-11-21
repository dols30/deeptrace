import {clock} from '../../lib/workflow';
import {AASIST_WINDOW, AUDIO_SCORE, CLIP_SECONDS, DECISION_RULE, WAVEFORM, score2} from './fixture';

export function AudioTrace({analysed = true, playhead}: {analysed?: boolean; playhead?: number}) {
  const windowPct = (AASIST_WINDOW / CLIP_SECONDS) * 100;
  return (
    <figure className={`trace-audio ${analysed ? 'analysed' : ''}`} aria-label={`Audio track, ${CLIP_SECONDS} seconds. AASIST scores only the first ${AASIST_WINDOW.toFixed(2)} seconds${analysed ? `, file-level model score ${score2(AUDIO_SCORE)}` : ''}.`}>
      <div className="trace-wave" style={{'--window': `${windowPct}%`} as React.CSSProperties}>
        {analysed && <div className="trace-window"><span>AASIST INPUT · {clock(0)}–{clock(AASIST_WINDOW)}</span></div>}
        <div className="trace-bars" aria-hidden="true">
          {WAVEFORM.map((height, index) => (
            <i key={index} className={(index / WAVEFORM.length) * CLIP_SECONDS < AASIST_WINDOW ? 'in' : 'out'} style={{height: `${(height * 100).toFixed(1)}%`}} />
          ))}
        </div>
        {playhead != null && <div className="trace-playhead" style={{left: `${(playhead / CLIP_SECONDS) * 100}%`}} aria-hidden="true" />}
      </div>
      {analysed && (
        <figcaption>
          <span>File-level model score: <b>{score2(AUDIO_SCORE)}</b> ({AUDIO_SCORE >= DECISION_RULE ? 'at or above 0.50' : 'below 0.50'})</span>
          <span className="trace-muted">Audio after {AASIST_WINDOW.toFixed(2)} seconds is not analyzed by this model.</span>
        </figcaption>
      )}
    </figure>
  );
}
