'use client';
import {useEffect, useRef, useState} from 'react';
import {analyze, formatBytes, type Report} from '../lib/api';
import {useAuth} from './auth';
import {ReportView} from './report';
import {TraceLoadingMark} from './trace/trace-mark';

export function Screening() {
  const auth = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const lock = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!file) {
      setPreview('');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const choose = (next: File | null) => {
    if (lock.current) return;
    setFile(next);
    setError('');
    if (input.current) input.current.value = '';
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || lock.current || !auth.ready || (auth.config.enabled && !auth.token)) return;
    if (file.size > 100 * 1024 * 1024) {
      setError('This file exceeds the 100 MB PoC limit.');
      return;
    }
    lock.current = true;
    setBusy(true);
    setError('');
    setReport(null);
    try {
      const nextReport = await analyze(file, auth.token);
      setReport(nextReport);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Analysis failed. Please try again.';
      if (message === 'SESSION_EXPIRED') {
        auth.expire();
        setError('Your session has expired. Please sign in again.');
      } else setError(message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <section className="intake-experience">
        <form className="detector-panel" id="detector-panel" onSubmit={submit} aria-busy={busy}>
        <label
          className={`drop-zone ${drag ? 'dragging' : ''}`}
          hidden={!!file}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            choose(e.dataTransfer.files[0] ?? null);
          }}
        >
          <input
            ref={input}
            type="file"
            aria-label="Choose media file"
            accept=".mp4,.mov,.avi,.mp3,.wav,.m4a,audio/mp4,audio/x-m4a"
            disabled={busy}
            onChange={(e) => choose(e.target.files?.[0] ?? null)}
          />
          <span className="upload-icon" aria-hidden="true">↑</span>
          <strong>Choose or drop a media file</strong>
          <span>MP4, MOV, AVI, MP3, WAV, M4A</span>
          <small>Maximum file size: 100 MB</small>
        </label>

        {file && (
          <>
            <div className="selected-file">
              <div className="file-type">{file.type.startsWith('video') ? 'VID' : 'AUD'}</div>
              <div className="file-copy">
                <strong>{file.name}</strong>
                <span>{file.type || 'Unknown type'} · {formatBytes(file.size)}</span>
              </div>
              <button type="button" className="text-button" disabled={busy} onClick={() => choose(null)}>
                Remove
              </button>
            </div>
            {preview && (
              <div className={`media-preview ${busy ? 'is-scanning' : ''}`}>
                {file.type.startsWith('video')
                  ? <video src={preview} controls preload="metadata" />
                  : <audio src={preview} controls preload="metadata" />}
                {busy && (
                  <div className="trace-scope scan-visual" aria-hidden="true">
                    <div className="trace-scanline" />
                    <div className="scan-readout">Analyzing file</div>
                  </div>
                )}
              </div>
            )}
          </>
        )}

        <p className="detector-checks">Public or synthesized media only. Advisory screening requires human review.</p>
        <button
          className="primary-button"
          disabled={!file || busy || !auth.ready || (auth.config.enabled && !auth.token)}
        >
          {busy ? 'Analyzing…' : 'Analyze file'}
        </button>
        {(error || auth.error) && (
          <p className="form-error" role="alert">{error || auth.error}</p>
        )}
      </form>
      </section>

      {busy && (
        <section className="loading-panel intake-loading" role="status" aria-live="polite">
          <div>
            <TraceLoadingMark size={28} />
            <strong>Analyzing file</strong>
          </div>
        </section>
      )}

      {report && (
        <ReportView
          report={report}
          onReset={() => {
            setReport(null);
            choose(null);
            document.getElementById('detector-panel')?.scrollIntoView({behavior: 'smooth'});
          }}
        />
      )}
    </>
  );
}
