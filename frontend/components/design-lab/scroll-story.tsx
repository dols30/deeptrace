'use client';
import {useEffect, useRef, useState} from 'react';
import {AudioTrace} from '../trace/audio-trace';
import {CaseStatus} from '../trace/case-status';
import {LANES, LaneId} from '../trace/fixture';
import {FrameStrip} from '../trace/frame-strip';
import {MediaScanner, ScannerLayer} from '../trace/media-scanner';
import {LaneState, SignalConvergence} from '../trace/signal-convergence';

const STEPS = [
  {kicker: 'DeepTrace', title: 'Can you trust what you see and hear?', body: 'Follow one recording through the system. Scroll to advance the investigation.'},
  {kicker: 'Intake', title: 'Media enters.', body: 'The file is hashed on receipt. That hash identifies the bytes, not their authenticity.'},
  {kicker: 'Sampling', title: 'One frame per second.', body: 'Both visual detectors read the same sampled JPEG frames. Nothing between samples is analysed.'},
  {kicker: 'Analysis 1 of 3', title: 'Does the whole frame look generated?', body: 'Community Forensics scores a centre crop of each frame. The file score is the mean of those frame scores.'},
  {kicker: 'Face', title: 'A face is found and aligned.', body: 'Only the largest face is used. Frames with no alignable face are skipped, not scored as zero.'},
  {kicker: 'Analysis 2 of 3', title: 'Was the face manipulated?', body: 'EfficientNet-B4 scores each aligned face. Frames at or above 0.50 become findings an investigator must review.'},
  {kicker: 'Separation', title: 'The audio leaves the video.', body: 'Speech is extracted as mono 16 kHz audio and analysed on its own.'},
  {kicker: 'Analysis 3 of 3', title: 'Is the speech synthetic?', body: 'AASIST reads only the first 4.04 seconds and returns one score for the file. It does not mark where in the audio a problem is.'},
  {kicker: 'Convergence', title: 'Three signals. One investigation.', body: 'The results meet as evidence, side by side. They are never averaged into a single verdict.'},
  {kicker: 'Human review', title: 'An investigator decides.', body: 'Each finding is dispositioned by a person, written up, and finalised by a supervisor. The model never concludes.'},
];

function laneStates(step: number): Record<LaneId, LaneState> {
  const state = (start: number): LaneState => step < start ? 'idle' : step === start ? 'running' : 'done';
  return {synthetic: state(3), face: state(5), audio: state(7)};
}

function scannerLayers(step: number): ScannerLayer[] {
  if (step === 2) return ['scan'];
  if (step === 3) return ['scan', 'crop'];
  if (step === 4 || step === 5) return ['face'];
  return [];
}

export function ScrollStory() {
  const [step, setStep] = useState(0);
  const refs = useRef<(HTMLElement | null)[]>([]);

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) setStep(Number((entry.target as HTMLElement).dataset.step));
    }, {rootMargin: window.innerWidth <= 980 ? '-76% 0px -18% 0px' : '-45% 0px -45% 0px'});
    refs.current.forEach(node => node && observer.observe(node));
    return () => observer.disconnect();
  }, []);

  const states = laneStates(step);
  const scene = step >= 9 ? 'case' : step === 8 ? 'converge' : 'media';
  return (
    <section className="trace-story" aria-label="Scroll-driven investigation">
      <div className="trace-story-stage" data-scene={scene} data-step={step}>
        <div className="trace-rail" aria-hidden="true">
          {LANES.map(lane => <span key={lane.id} className={`trace-lane-${lane.id} ${states[lane.id]}`}><b>{lane.short}</b><i /></span>)}
        </div>
        {scene === 'media' && (
          <div className="trace-scene">
            <div className={`trace-media-stack ${step >= 1 ? 'entered' : ''} ${step >= 6 ? 'separated' : ''}`}>
              <MediaScanner frame={step >= 4 ? 5 : Math.max(0, step - 1)} layers={scannerLayers(step)} />
              <div className="trace-media-audio">{step >= 6 && <AudioTrace analysed={step >= 7} />}</div>
            </div>
            {step === 3 && <FrameStrip lane="synthetic" frame={2} />}
            {step === 5 && <FrameStrip lane="face" frame={5} />}
          </div>
        )}
        {scene === 'converge' && <div className="trace-scene"><SignalConvergence states={states} /></div>}
        {scene === 'case' && <div className="trace-scene"><CaseStatus /></div>}
      </div>
      <ol className="trace-story-steps">
        {STEPS.map((item, index) => (
          <li key={item.title} data-step={index} ref={node => { refs.current[index] = node; }} className={index === step ? 'active' : ''}>
            <span>{item.kicker}</span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
