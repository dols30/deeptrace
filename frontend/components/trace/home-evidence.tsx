'use client';
import {useEffect, useRef, useState} from 'react';
import {clock} from '../../lib/workflow';
import {AudioTrace} from './audio-trace';
import {AASIST_WINDOW, FRAMES} from './fixture';
import {FrameStrip} from './frame-strip';
import {MediaScanner} from './media-scanner';

export function HomeEvidence() {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [visible, setVisible] = useState(false);
  const section = useRef<HTMLElement>(null);
  const scores = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
    setPlaying(!motion.matches);
    const onMotionChange = () => { if (motion.matches) setPlaying(false); };
    motion.addEventListener('change', onMotionChange);
    const observer = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), {threshold: 0.15});
    if (section.current) observer.observe(section.current);
    return () => {
      motion.removeEventListener('change', onMotionChange);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    if (!playing || !visible) return;
    const timer = window.setInterval(() => {
      if (!document.hidden) setFrame(value => (value + 1) % FRAMES.length);
    }, 1000);
    return () => window.clearInterval(timer);
  }, [playing, visible]);

  const selectFrame = (value: number) => {
    setPlaying(false);
    setFrame(value);
  };

  useEffect(() => {
    scores.current?.querySelectorAll<HTMLOListElement>('.trace-strip ol').forEach(list => {
      const selected = list.children[frame] as HTMLElement | undefined;
      if (selected) list.scrollLeft = Math.max(0, selected.offsetLeft - (list.clientWidth - selected.offsetWidth) / 2);
    });
  }, [frame]);

  return <section ref={section} className="trace home-evidence" data-motion="reduced" aria-labelledby="evidence-title">
    <div className="container">
      <header className="home-evidence-heading">
        <h2 id="evidence-title">Trace the evidence.</h2>
      </header>
      <div className="home-evidence-grid">
        <div className="home-evidence-media">
          <header className="home-frame-meta">
            <strong aria-live={playing ? 'off' : 'polite'}>Frame {frame + 1} of {FRAMES.length}</strong>
            <span>{clock(FRAMES[frame])}</span>
            <span>1 sample per second</span>
          </header>
          <MediaScanner frame={frame} layers={['crop', 'face']} onFrame={selectFrame}/>
          <div className="home-frame-controls">
            <button type="button" className="secondary-button" disabled={frame === 0} onClick={() => selectFrame(frame - 1)}>Previous frame</button>
            <button type="button" className="secondary-button home-frame-play" onClick={() => setPlaying(value => !value)}>{playing ? 'Pause frames' : 'Play frames'}</button>
            <button type="button" className="secondary-button" disabled={frame === FRAMES.length - 1} onClick={() => selectFrame(frame + 1)}>Next frame</button>
            <label>Selected frame<input type="range" min={0} max={FRAMES.length - 1} step={1} value={frame} aria-label="Selected example frame" aria-valuetext={`Frame ${frame + 1} at ${clock(FRAMES[frame])}`} onChange={event => selectFrame(Number(event.target.value))}/></label>
          </div>
        </div>
        <div className="home-evidence-scores" ref={scores}>
          <FrameStrip lane="synthetic" frame={frame} onFrame={selectFrame}/>
          <FrameStrip lane="face" frame={frame} onFrame={selectFrame}/>
          <section className="home-audio-evidence" aria-label="Example speech screening">
            <header><h3>Speech spoofing</h3><span>AASIST</span></header>
            <p>Analyzed window: first {AASIST_WINDOW.toFixed(2)} seconds</p>
            <AudioTrace playhead={FRAMES[frame]}/>
          </section>
        </div>
      </div>
    </div>
  </section>;
}
