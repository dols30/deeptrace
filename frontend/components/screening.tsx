'use client';
import {useEffect, useRef, useState, type CSSProperties} from 'react';
import {analyze, formatBytes, type Report} from '../lib/api';
import {getModelInfo} from '../lib/workflow';
import {useAuth} from './auth';
import {CaseChat} from './case-chat';
import {analysisMethods, methodsForMedia, type ModelInformationData} from './model-information';
import {ReportView} from './report';
import {TraceLoadingMark} from './trace/trace-mark';

const MODEL_NAMES: Record<string, string> = {
  efficientnetb4: 'EfficientNet-B4',
  effort: 'Effort',
  community_forensics: 'Community Forensics',
  aasist: 'AASIST',
  'aasist-l': 'AASIST-L',
  nes2net: 'NES2Net',
  'cnndetection resnet-50': 'CNNDetection',
  'lfcc-lcnn (asvspoof df)': 'LFCC-LCNN',
  'softnet (casme micro s1)': 'SOFTNet',
};

export function Screening() {
  const auth = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState('');
  const [report, setReport] = useState<Report | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInformationData | null>(null);
  const lock = useRef(false);
  const input = useRef<HTMLInputElement>(null);

  const token = auth.token;
  useEffect(() => {
    if (!token) return;
    let active = true;
    getModelInfo(token).then(info => {
      if (active) setModelInfo(info);
    }).catch(() => {
      if (active) setModelInfo(null);
    });
    return () => { active = false; };
  }, [token]);

  useEffect(() => {
    if (!file) {
      setPreview('');
      return;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const configuredModels = busy && modelInfo ? analysisMethods(modelInfo).filter(method => method.configured) : [];
  const applicableTasks = new Set(busy && file && modelInfo
    ? methodsForMedia(modelInfo, file.type.startsWith('video') ? 'video' : 'audio').map(method => method.task)
    : []);

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
          {configuredModels.length > 0 && <ul className="screening-model-list" role="list" aria-label="Configured models">
            {configuredModels.map((method, index) => (
              <li key={method.task} title={method.task} style={{'--model-index': index} as CSSProperties}>
                {MODEL_NAMES[method.model.toLowerCase()] ?? method.model}
                {!applicableTasks.has(method.task) && <small>Video only</small>}
              </li>
            ))}
          </ul>}
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
      {report?.analysis_id && token && <CaseChat key={report.analysis_id} analysisId={report.analysis_id} />}
    </>
  );
}
