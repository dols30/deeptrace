import {clock} from '../../lib/workflow';
import {CLIP_SECONDS, FACE_SCORES, FRAMES} from './fixture';

export type ScannerLayer = 'scan' | 'crop' | 'face';

const SUBJECT_SHIFT = [0, 2, 9, 3, 1, -2, -3, -1, -10, 0];

export function MediaScanner({frame, layers, onFrame, caption}: {
  frame: number;
  layers: ScannerLayer[];
  onFrame?: (frame: number) => void;
  caption?: string;
}) {
  const hasFace = FACE_SCORES[frame] != null;
  const show = (layer: ScannerLayer) => layers.includes(layer);
  return (
    <figure className="trace-scanner">
      <div className="trace-frame" style={{'--shift': `${SUBJECT_SHIFT[frame]}%`} as React.CSSProperties}>
        <div className="trace-subject" aria-hidden="true"><i /><b /></div>
        <div className="trace-hud trace-hud-tl">FRAME {String(frame + 1).padStart(2, '0')} / {FRAMES.length} · {clock(FRAMES[frame])}</div>
        <div className="trace-hud trace-hud-tr">JPEG · 1 FRAME / S</div>
        {show('scan') && <div key={frame} className="trace-scanline" aria-hidden="true" />}
        {show('crop') && <div className="trace-crop" aria-hidden="true"><span>AI-GENERATED · CENTRE CROP 384 PX</span></div>}
        {show('face') && (hasFace
          ? <div className="trace-facebox" aria-hidden="true"><span>LARGEST FACE · ALIGNED 256 PX</span></div>
          : <div className="trace-noface">No alignable face. This frame was not scored.</div>)}
      </div>
      <div className="trace-ruler">
        <div className="trace-ruler-track">
          {FRAMES.map((start, index) => (
            <button
              key={start}
              type="button"
              className={`trace-tick ${index === frame ? 'current' : ''}`}
              style={{left: `${(start / CLIP_SECONDS) * 100}%`}}
              onClick={() => onFrame?.(index)}
              disabled={!onFrame}
              aria-label={`Sampled frame ${index + 1} at ${clock(start)}`}
              aria-pressed={index === frame}
            />
          ))}
        </div>
        <div className="trace-ruler-labels" aria-hidden="true">
          <span>{clock(0)}</span><span>{clock(CLIP_SECONDS / 2)}</span><span>{clock(CLIP_SECONDS)}</span>
        </div>
      </div>
      {caption && <figcaption>{caption}</figcaption>}
    </figure>
  );
}
