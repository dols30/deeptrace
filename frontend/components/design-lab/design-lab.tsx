'use client';
import {useEffect, useState} from 'react';
import {AudioTrace} from '../trace/audio-trace';
import {CaseStatus} from '../trace/case-status';
import {EvidenceTimeline} from '../trace/evidence-timeline';
import {FRAMES, LANES} from '../trace/fixture';
import {FrameStrip} from '../trace/frame-strip';
import {MediaScanner} from '../trace/media-scanner';
import {SignalConvergence} from '../trace/signal-convergence';
import {ScannerEvidence, ScannerToolbar, TraceHero, sequenceStates, useFrameScanner, useSequence} from '../trace/trace-hero';
import {MARK_CONCEPTS, MarkConcept, TraceDivider, TraceLoader, TraceMark, TraceWordmark} from '../trace/trace-mark';
import {ScrollStory} from './scroll-story';

type Direction = 'combined' | 'signal' | 'scanner' | 'timeline';
type Motion = 'normal' | 'reduced';
type Theme = 'dark' | 'light';
type Type = 'technical' | 'editorial' | 'grotesk';

const DIRECTIONS: {id: Direction; name: string; line: string}[] = [
  {id: 'combined', name: 'A + B · Convergence + scanner', line: 'The three lines are the identity; the frame-by-frame scanner is the proof underneath.'},
  {id: 'signal', name: 'A · Signal convergence', line: 'Three detector streams are the brand.'},
  {id: 'scanner', name: 'B · Forensic scanner', line: 'The media under analysis is the brand.'},
  {id: 'timeline', name: 'C · Investigation timeline', line: 'Evidence accumulating over time is the brand.'},
];

function Segmented<T extends string>({label, value, options, onChange}: {label: string; value: T; options: {id: T; name: string}[]; onChange: (value: T) => void}) {
  return (
    <fieldset className="trace-segmented">
      <legend>{label}</legend>
      <div>
        {options.map(option => (
          <button key={option.id} type="button" aria-pressed={value === option.id} onClick={() => onChange(option.id)}>{option.name}</button>
        ))}
      </div>
    </fieldset>
  );
}

function SignalHero({mark, reduced}: {mark: MarkConcept; reduced: boolean}) {
  const {step, done, replay} = useSequence(6, 900, reduced);
  return (
    <div className="trace-hero trace-hero-signal">
      <div className="trace-hero-copy">
        <TraceWordmark concept={mark} size={34} />
        <h1>Three signals.<br />One investigation.</h1>
        <p>DeepTrace runs three independent forensic models on a recording and hands their separate results to an investigator.</p>
        <button type="button" className="trace-button ghost" onClick={replay} disabled={!done}>Replay analysis</button>
      </div>
      <SignalConvergence states={sequenceStates(step)} />
    </div>
  );
}

function ScannerHero({reduced}: {reduced: boolean}) {
  const scanner = useFrameScanner(reduced);
  return (
    <div className="trace-hero trace-hero-scanner">
      <div className="trace-hero-copy">
        <span className="trace-kicker">Forensic scanner</span>
        <h1>Trace the evidence.</h1>
        <p>Every overlay corresponds to something a model actually reads: the sampled frame, the centre crop, the aligned face, the scored audio window.</p>
        <ScannerToolbar scanner={scanner} reduced={reduced} />
      </div>
      <div className="trace-scanner-stack">
        <MediaScanner frame={scanner.frame} layers={scanner.layers} onFrame={scanner.setFrame} />
        <ScannerEvidence scanner={scanner} />
      </div>
    </div>
  );
}

function TimelineHero() {
  const [time, setTime] = useState(5.4);
  return (
    <div className="trace-hero trace-hero-timeline">
      <div className="trace-hero-copy">
        <span className="trace-kicker">Investigation timeline</span>
        <h1>Analyze the media. Inspect the evidence. Make the decision.</h1>
      </div>
      <div className="trace-timeline-layout">
        <MediaScanner frame={Math.min(FRAMES.length - 1, Math.floor(time))} layers={['face']} onFrame={index => setTime(FRAMES[index] + 0.4)} />
        <CaseStatus />
      </div>
      <EvidenceTimeline time={time} onTime={setTime} />
    </div>
  );
}

function Carryover({direction, mark}: {direction: Direction; mark: MarkConcept}) {
  return (
    <div className="trace-carry">
      <article>
        <span className="trace-kicker">Loading</span>
        <TraceLoader />
      </article>
      <article>
        <span className="trace-kicker">Analysis</span>
        {(direction === 'signal' || direction === 'combined') && <SignalConvergence states={{synthetic: 'done', face: 'done', audio: 'running'}} showReadouts={false} />}
        {direction === 'scanner' && <FrameStrip lane="face" frame={5} />}
        {direction === 'timeline' && <EvidenceTimeline />}
      </article>
      <article>
        <span className="trace-kicker">Report header</span>
        <div className="trace-report-head">
          <TraceMark concept={mark} size={22} />
          <ol><li>Three analyses</li><li>Evidence</li><li>Human review</li></ol>
        </div>
        <TraceDivider />
        <p className="trace-muted">The divider reuses the mark geometry to separate model output from the investigator&apos;s sections.</p>
      </article>
      {direction === 'combined' && (
        <article>
          <span className="trace-kicker">Case workspace · later</span>
          <EvidenceTimeline />
          <p className="trace-muted">The investigation timeline belongs inside the case workspace, next to findings and dispositions, rather than on the landing page.</p>
        </article>
      )}
    </div>
  );
}

export function DesignLab() {
  const [direction, setDirection] = useState<Direction>('combined');
  const [mark, setMark] = useState<MarkConcept>('converge');
  const [motion, setMotion] = useState<Motion>('normal');
  const [theme, setTheme] = useState<Theme>('light');
  const [type, setType] = useState<Type>('grotesk');

  useEffect(() => {
    if (window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) setMotion('reduced');
  }, []);

  const reduced = motion === 'reduced';
  return (
    <div className="trace trace-lab" data-theme={theme} data-motion={motion} data-type={type}>
      <header className="trace-bar">
        <div className="trace-bar-title">
          <TraceMark concept={mark} size={22} />
          <b>DeepTrace design lab</b>
          <span>Internal exploration · illustrative data, not a real analysis</span>
        </div>
        <div className="trace-controls">
          <Segmented label="Direction" value={direction} onChange={setDirection} options={DIRECTIONS.map(item => ({id: item.id, name: item.name.split(' · ')[1]}))} />
          <Segmented label="Logo" value={mark} onChange={setMark} options={MARK_CONCEPTS.map(item => ({id: item.id, name: item.name}))} />
          <Segmented label="Motion" value={motion} onChange={setMotion} options={[{id: 'normal', name: 'Normal'}, {id: 'reduced', name: 'Reduced'}]} />
          <Segmented label="Theme" value={theme} onChange={setTheme} options={[{id: 'dark', name: 'Dark'}, {id: 'light', name: 'Light'}]} />
          <Segmented label="Type" value={type} onChange={setType} options={[{id: 'technical', name: 'Technical'}, {id: 'editorial', name: 'Editorial'}, {id: 'grotesk', name: 'Grotesk'}]} />
        </div>
      </header>

      <main className="trace-main">
        <section className="trace-section" aria-labelledby="trace-direction">
          <div className="trace-section-head">
            <h2 id="trace-direction">{DIRECTIONS.find(item => item.id === direction)!.name}</h2>
            <p>{DIRECTIONS.find(item => item.id === direction)!.line}</p>
          </div>
          {direction === 'combined' && <TraceHero key={`${motion}`} mark={mark} reduced={reduced} />}
          {direction === 'signal' && <SignalHero key={`${motion}`} mark={mark} reduced={reduced} />}
          {direction === 'scanner' && <ScannerHero reduced={reduced} />}
          {direction === 'timeline' && <TimelineHero />}
          <Carryover direction={direction} mark={mark} />
        </section>

        <section className="trace-section" aria-labelledby="trace-logos">
          <div className="trace-section-head"><h2 id="trace-logos">Logo concepts</h2><p>Three signals, one trace. Shown at 64, 32 and 16 px and as a browser-tab favicon.</p></div>
          <div className="trace-logos">
            {MARK_CONCEPTS.map(item => (
              <button key={item.id} type="button" className="trace-logo-card" aria-pressed={mark === item.id} onClick={() => setMark(item.id)}>
                <div className="trace-logo-sizes"><TraceMark concept={item.id} size={64} /><TraceMark concept={item.id} size={32} /><TraceMark concept={item.id} size={16} /></div>
                <TraceWordmark concept={item.id} size={24} />
                <div className="trace-favicon" aria-hidden="true"><TraceMark concept={item.id} size={14} /><span>DeepTrace — Case 0042</span></div>
                <b>{item.name}</b>
                <small>{item.idea}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="trace-section" aria-labelledby="trace-detectors">
          <div className="trace-section-head"><h2 id="trace-detectors">Detector visual languages</h2><p>Each detector is drawn at the granularity it actually produces.</p></div>
          <div className="trace-detectors">
            {LANES.map(lane => (
              <article key={lane.id} className={`trace-detector trace-lane-${lane.id}`}>
                <header><span className="trace-swatch" aria-hidden="true" /><b>{lane.label}</b><small>{lane.model}</small></header>
                {lane.id === 'synthetic' && <><MediaScanner frame={3} layers={['crop']} /><FrameStrip lane="synthetic" /></>}
                {lane.id === 'face' && <>
                  <MediaScanner frame={5} layers={['face']} />
                  <FrameStrip lane="face" />
                  <div className="trace-attribution-slot">
                    <b>Attribution slot</b>
                    <p>Renders the stored Grad-CAM for a flagged frame. The lab has no real attribution, so it draws none. Reuse the existing attribution overlay in <code>MediaCanvas</code> here.</p>
                  </div>
                </>}
                {lane.id === 'audio' && <AudioTrace />}
                <dl><div><dt>Output</dt><dd>{lane.granularity}</dd></div><div><dt>Attribution</dt><dd>{lane.attribution}</dd></div></dl>
              </article>
            ))}
          </div>
        </section>

        <section className="trace-section" aria-labelledby="trace-motion">
          <div className="trace-section-head"><h2 id="trace-motion">Motion system</h2><p>Each motion has one meaning. Nothing loops except an active analysis.</p></div>
          <div className="trace-motions">
            <article><div className="trace-motion-demo trace-demo-scan"><i /></div><b>Scan</b><small>Sampling a frame. One pass per frame, linear, 1.2 s.</small></article>
            <article><div className="trace-motion-demo"><svg viewBox="0 0 160 24"><path className="trace-lane-path" d="M0 12h160" /><path className="trace-flow" d="M0 12h160" /></svg></div><b>Flow</b><small>A model is running. Loops only while the analysis is running.</small></article>
            <article><div className="trace-motion-demo"><TraceDivider /></div><b>Converge</b><small>Separate results arriving as evidence. Plays once, 480 ms.</small></article>
            <article><div className="trace-motion-demo trace-demo-state"><span>analysing</span><span>complete</span></div><b>State change</b><small>Text and stroke change, 160 ms. No celebratory animation.</small></article>
          </div>
        </section>

        <section className="trace-section" aria-labelledby="trace-color">
          <div className="trace-section-head"><h2 id="trace-color">Color and type</h2><p>Neutral ink and paper. Detectors differ by line pattern first, hue second. Amber is the only signal color; there is no green.</p></div>
          <div className="trace-swatches">
            {[['Ink', 'var(--trace-ink)'], ['Muted', 'var(--trace-muted)'], ['Line', 'var(--trace-line)'], ['Panel', 'var(--trace-panel)'], ['Trace accent', 'var(--trace-accent)'], ['At or above rule', 'var(--trace-signal)']].map(([name, value]) => (
              <div key={name}><i style={{background: value}} /><b>{name}</b></div>
            ))}
          </div>
          <div className="trace-lane-key">
            {LANES.map(lane => <div key={lane.id} className={`trace-lane-${lane.id}`}><svg viewBox="0 0 120 10" aria-hidden="true"><path className="trace-lane-path" d="M0 5h120" /></svg><span>{lane.label}</span></div>)}
          </div>
          <div className="trace-type">
            <p className="trace-type-display">Can you trust what you see and hear?</p>
            <p>Body copy stays short and literal. A model score is not a probability.</p>
            <p className="trace-type-mono">FRAME 06 / 10 · 00:05.0 · SCORE 0.58 · RULE 0.50 (NOT DPS-VALIDATED)</p>
          </div>
        </section>

        <section className="trace-section" aria-labelledby="trace-story">
          <div className="trace-section-head"><h2 id="trace-story">Scroll-driven investigation</h2><p>One continuous stage. The media object persists while each analysis adds a layer.</p></div>
          <ScrollStory />
        </section>
      </main>
    </div>
  );
}
