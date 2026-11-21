'use client';
import {PointerEvent, ReactNode, useEffect, useRef, useState} from 'react';
import {AudioTrace} from './audio-trace';
import {FRAMES, LaneId} from './fixture';
import {FrameStrip} from './frame-strip';
import {MediaScanner, ScannerLayer} from './media-scanner';
import {LaneState, SignalConvergence} from './signal-convergence';
import {MarkConcept, TraceWordmark} from './trace-mark';

export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    const query = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!query) return;
    setReduced(query.matches);
    const update = () => setReduced(query.matches);
    query.addEventListener?.('change', update);
    return () => query.removeEventListener?.('change', update);
  }, []);
  return reduced;
}

export function useSequence(length: number, interval: number, reduced: boolean) {
  const [step, setStep] = useState(reduced ? length : 0);
  const [run, setRun] = useState(0);
  useEffect(() => {
    if (reduced) { setStep(length); return; }
    setStep(0);
    const timer = setInterval(() => setStep(current => {
      if (current >= length) { clearInterval(timer); return current; }
      return current + 1;
    }), interval);
    return () => clearInterval(timer);
  }, [length, interval, reduced, run]);
  return {step, done: step >= length, replay: () => setRun(value => value + 1)};
}

export function sequenceStates(step: number): Record<LaneId, LaneState> {
  const state = (index: number): LaneState => step <= index * 2 ? (step === index * 2 ? 'running' : 'idle') : 'done';
  return {synthetic: state(0), face: state(1), audio: state(2)};
}

export function useFrameScanner(reduced = false) {
  const [frame, setFrame] = useState(5);
  const [layers, setLayers] = useState<ScannerLayer[]>(['crop', 'face']);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    if (!playing || reduced) return;
    const timer = setInterval(() => setFrame(current => {
      if (current >= FRAMES.length - 1) { setPlaying(false); return current; }
      return current + 1;
    }), 700);
    return () => clearInterval(timer);
  }, [playing, reduced]);
  return {
    frame, setFrame, layers, playing,
    toggle: (layer: ScannerLayer) => setLayers(current => current.includes(layer) ? current.filter(item => item !== layer) : [...current, layer]),
    play: () => { if (frame >= FRAMES.length - 1) setFrame(0); setPlaying(value => !value); },
  };
}

export type FrameScanner = ReturnType<typeof useFrameScanner>;

const SCAN_PASS_MS = 1200;

function useHoverScanner(reduced: boolean, entered: boolean) {
  const [frame, setFrameState] = useState(5);
  const [playing, setPlaying] = useState(false);
  const frameRef = useRef(5);
  const introDone = useRef(false);
  const introRunning = useRef(false);
  const setFrame = (next: number) => { frameRef.current = next; setFrameState(next); };

  useEffect(() => {
    if (reduced || !entered || introDone.current) return;
    introDone.current = true;
    introRunning.current = true;
    setFrame(0);
    setPlaying(true);
  }, [reduced, entered]);

  useEffect(() => {
    if (!playing || reduced) return;
    const timer = setInterval(() => {
      if (introRunning.current && frameRef.current >= FRAMES.length - 1) {
        introRunning.current = false;
        setPlaying(false);
        clearInterval(timer);
        return;
      }
      setFrame((frameRef.current + 1) % FRAMES.length);
    }, SCAN_PASS_MS);
    return () => clearInterval(timer);
  }, [playing, reduced]);

  const start = () => { if (reduced) return; introRunning.current = false; setPlaying(true); };
  const stop = () => { introRunning.current = false; setPlaying(false); };
  return {frame, setFrame, playing, start, stop, toggle: () => (playing ? stop() : start())};
}

function useRevealOnScroll(reduced: boolean) {
  const stageRef = useRef<HTMLDivElement>(null);
  const evidenceRef = useRef<HTMLDivElement>(null);
  const [leaving, setLeaving] = useState(false);
  const [entered, setEntered] = useState(reduced);

  useEffect(() => {
    if (reduced || typeof IntersectionObserver === 'undefined') { setEntered(true); return; }
    const stage = stageRef.current;
    const evidence = evidenceRef.current;
    if (!stage || !evidence) return;
    const stageObserver = new IntersectionObserver(([entry]) => setLeaving(entry.intersectionRatio < 0.6), {threshold: [0, 0.6, 1]});
    const evidenceObserver = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setEntered(true);
      evidenceObserver.disconnect();
    }, {threshold: 0.2});
    stageObserver.observe(stage);
    evidenceObserver.observe(evidence);
    return () => { stageObserver.disconnect(); evidenceObserver.disconnect(); };
  }, [reduced]);

  return {stageRef, evidenceRef, leaving, entered};
}

export function ScannerToolbar({scanner, reduced}: {scanner: FrameScanner; reduced: boolean}) {
  return (
    <div className="trace-toolbar" role="group" aria-label="Scanner overlays">
      {(['scan', 'crop', 'face'] as ScannerLayer[]).map(layer => (
        <button key={layer} type="button" aria-pressed={scanner.layers.includes(layer)} onClick={() => scanner.toggle(layer)}>
          {layer === 'scan' ? 'Scan line' : layer === 'crop' ? 'AI crop' : 'Face'}
        </button>
      ))}
      <button type="button" onClick={scanner.play} disabled={reduced}>{scanner.playing ? 'Pause' : 'Step through frames'}</button>
    </div>
  );
}

export function ScannerEvidence({scanner}: {scanner: {frame: number; setFrame: (frame: number) => void}}) {
  return <>
    <FrameStrip lane="synthetic" frame={scanner.frame} onFrame={scanner.setFrame} />
    <FrameStrip lane="face" frame={scanner.frame} onFrame={scanner.setFrame} />
    <AudioTrace playhead={FRAMES[scanner.frame]} />
  </>;
}

export function TraceHero({mark = 'converge', reduced, eyebrow, actions, note}: {mark?: MarkConcept; reduced: boolean; eyebrow?: ReactNode; actions?: ReactNode; note?: ReactNode}) {
  const {step, done, replay} = useSequence(6, 900, reduced);
  const {stageRef, evidenceRef, leaving, entered} = useRevealOnScroll(reduced);
  const scanner = useHoverScanner(reduced, entered);
  const layers: ScannerLayer[] = scanner.playing ? ['scan', 'crop', 'face'] : ['crop', 'face'];

  const onConvergenceHover = () => { if (done && !reduced) replay(); };
  const onScannerEnter = (event: PointerEvent<HTMLDivElement>) => { if (event.pointerType !== 'touch') scanner.start(); };
  const onScannerLeave = (event: PointerEvent<HTMLDivElement>) => { if (event.pointerType !== 'touch') scanner.stop(); };
  const onScannerTap = (event: PointerEvent<HTMLDivElement>) => {
    if (event.pointerType === 'touch' && !(event.target as HTMLElement).closest('button')) scanner.toggle();
  };
  const scrollToEvidence = () => evidenceRef.current?.scrollIntoView?.({behavior: reduced ? 'auto' : 'smooth', block: 'start'});

  return (
    <div className="trace-combined">
      <div ref={stageRef} className={`trace-stage ${leaving ? 'leaving' : ''}`}>
        <div className="trace-hero trace-hero-signal">
          <div className="trace-hero-copy">
            {eyebrow ?? <TraceWordmark concept={mark} size={34} />}
            <h1>Three signals.<br />One investigation.</h1>
            {actions && <div className="trace-actions">{actions}</div>}
            {note}
          </div>
          <div className="trace-convergence-hover" onPointerEnter={onConvergenceHover}>
            <SignalConvergence states={sequenceStates(step)} />
          </div>
        </div>
        <button type="button" className="trace-scroll-cue" onClick={scrollToEvidence} aria-label="Scroll to the frame-by-frame evidence">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 9l6 6 6-6" /></svg>
        </button>
      </div>
      <div ref={evidenceRef} className={`trace-combined-evidence ${entered ? 'entered' : ''}`}>
        <div className="trace-combined-head">
          <span className="trace-kicker">Frame by frame</span>
          <h2>Trace the evidence.</h2>
        </div>
        <div className={`trace-combined-grid ${scanner.playing ? 'playing' : ''}`} onPointerEnter={onScannerEnter} onPointerLeave={onScannerLeave} onPointerUp={onScannerTap}>
          <MediaScanner frame={scanner.frame} layers={layers} onFrame={scanner.setFrame} />
          <div className="trace-scanner-stack"><ScannerEvidence scanner={scanner} /></div>
        </div>
      </div>
    </div>
  );
}
