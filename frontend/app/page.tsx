'use client';
import Link from 'next/link';
import {SiteHeader} from '../components/header';
import {SiteFooter} from '../components/footer';
import {useAuth} from '../components/auth';
import {SignalConvergence} from '../components/trace/signal-convergence';
import {HomeEvidence} from '../components/trace/home-evidence';

export default function Home() {
  const auth = useAuth();
  return <div className="app-shell marketing-shell home-shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <SiteHeader />
    <main id="main" className="home-page">
      <section className="container home-intro" aria-labelledby="home-title">
        <div className="home-copy">
          <h1 id="home-title">Media screening<br />for investigators.</h1>
          <p>Review audio and video for signs of synthetic manipulation, then document your findings.</p>
          <div className="home-actions">
            <Link className="primary-link" href={auth.token ? '/detector' : '/signin/'}>Start an analysis</Link>
            <a className="home-example-link" href="#evidence-title">Explore the example</a>
          </div>
        </div>
        <section className="trace home-signal" data-motion="normal" aria-label="Illustrative detector results, not a real analysis">
          <SignalConvergence states={{synthetic: 'done', face: 'done', audio: 'done'}} showReadouts={false} animateFlow example />
        </section>
        <a className="home-scroll-cue" href="#evidence-title" aria-label="Scroll to the frame example">
          <svg viewBox="0 0 32 44" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="8" y="2" width="16" height="27" rx="8"/>
            <path className="home-scroll-wheel" d="M16 8v5"/>
            <path d="m11 35 5 4 5-4"/>
          </svg>
        </a>
      </section>
      <HomeEvidence />
      <section className="home-workflow" aria-label="Review workflow">
        <div className="container">
          <ol>
            <li><h3>Upload a recording</h3><p>Use a public or synthesized audio or video file. MP4, MOV, AVI, MP3, WAV, and M4A are supported.</p></li>
            <li><h3>Examine the findings</h3><p>Play the recording, inspect individual model results, and record your assessment.</p></li>
            <li><h3>Prepare the report</h3><p>Add your observations and send the draft to a supervisor for review.</p></li>
          </ol>
        </div>
      </section>
    </main>
    <SiteFooter />
  </div>;
}
