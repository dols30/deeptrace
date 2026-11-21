import {clock} from '../../lib/workflow';
import {DECISION_RULE, FACE_SCORES, FRAMES, LANES, SYNTHETIC_SCORES, mean, score2} from './fixture';

export function FrameStrip({lane, frame, onFrame}: {lane: 'synthetic' | 'face'; frame?: number; onFrame?: (frame: number) => void}) {
  const meta = LANES.find(item => item.id === lane)!;
  const scores: (number | null)[] = lane === 'face' ? FACE_SCORES : SYNTHETIC_SCORES;
  const scored = scores.filter(value => value != null).length;
  const title = lane === 'face' ? 'Face manipulation' : 'Generated imagery';
  return (
    <section className={`trace-strip trace-lane-${lane}`} aria-label={`${title} frame scores`}>
      <header>
        <b>{title}</b>
        <span>{meta.model}</span>
      </header>
      <ol>
        {FRAMES.map((start, index) => {
          const value = scores[index];
          const state = value == null ? 'abstain' : value >= DECISION_RULE ? 'at-rule' : 'below';
          return (
            <li key={start}>
              <button
                type="button"
                className={`trace-cell ${state} ${index === frame ? 'current' : ''}`}
                style={{'--v': value ?? 0} as React.CSSProperties}
                onClick={() => onFrame?.(index)}
                disabled={!onFrame}
                aria-pressed={index === frame}
                aria-label={`${clock(start)}: ${value == null ? 'no alignable face, not scored' : `model score ${score2(value)}`}`}
              >
                <span>{value == null ? 'N/A' : score2(value)}</span>
              </button>
              <small>{String(index + 1).padStart(2, '0')}</small>
            </li>
          );
        })}
      </ol>
      <p>
        Average score: <b>{score2(mean(scores))}</b> across {scored} scored frame{scored === 1 ? '' : 's'}.
        {lane === 'face' && scored < scores.length ? ` ${scores.length - scored} frame${scores.length - scored === 1 ? '' : 's'} not scored (no alignable face).` : ''}
      </p>
    </section>
  );
}
