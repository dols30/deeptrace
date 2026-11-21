'use client';
import {useEffect, useRef, useState} from 'react';
import {TraceLoadingMark} from './trace/trace-mark';
import {
  addCaseComment, getAnalysis, getAnalysisMedia, getCaseReport, resolveCaseComment, reviewFinding,
  type AnalysisDetail, type CaseReport, type Disposition, type Finding,
} from '../lib/workflow';
import {useAuth} from './auth';
import {GuidedTour} from './guide/guided-tour';
import {guideForSurface, userKeyFromToken} from './guide/tour-copy';
import {ActivityNotes} from './workspace/activity-notes';
import {CaseCommand} from './workspace/case-command';
import {FindingsInspector} from './workspace/findings-inspector';
import {
  BOOKMARK_BODY, bookmarksFor, captureFrame, forgetBookmark, rememberBookmark, type FrameBookmark,
} from './workspace/frame-bookmarks';
import {MediaCanvas} from './workspace/media-canvas';
import {ScreeningDraft} from './workspace/screening-draft';
import {OfficerSummary, TechnicalResults} from './workspace/officer-summary';

export function AnalysisWorkspace({id}: {id: string}) {
  const auth = useAuth();
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const [view, setView] = useState<'summary' | 'technical'>('summary');
  const technical = view === 'technical';
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [report, setReport] = useState<CaseReport | null>(null);
  const [mediaUrl, setMediaUrl] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [note, setNote] = useState('');
  const [comment, setComment] = useState('');
  const [replyTo, setReplyTo] = useState<string | null>(null);
  const [overlay, setOverlay] = useState(false);
  const [opacity, setOpacity] = useState(0.55);
  const [currentTime, setCurrentTime] = useState(0);
  const [saveState, setSaveState] = useState('');
  const [windowIndex, setWindowIndex] = useState(0);
  const [bookmarks, setBookmarks] = useState<FrameBookmark[]>([]);
  const [bookmarkMessage, setBookmarkMessage] = useState('');
  const [bookmarking, setBookmarking] = useState(false);
  const selected = analysis?.findings.find(item => item.id === selectedId) ?? analysis?.findings[0] ?? null;
  const expire = useRef(auth.expire);
  expire.current = auth.expire;

  useEffect(() => {
    if (!auth.token) return;
    let active = true;
    let url = '';
    setLoading(true);
    Promise.all([getAnalysis(id, auth.token), getCaseReport(id, auth.token), getAnalysisMedia(id, auth.token)])
      .then(([next, draft, blob]) => {
        if (!active) return;
        url = URL.createObjectURL(blob);
        setAnalysis(next);
        setReport(draft);
        setMediaUrl(url);
        setSelectedId(next.findings[0]?.id ?? null);
        setBookmarks(bookmarksFor(id, next.comments));
        setError('');
      })
      .catch(reason => {
        if (!active) return;
        if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') expire.current();
        else setError(reason instanceof Error ? reason.message : 'The analysis could not be loaded.');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [auth.token, id]);

  function seek(seconds: number) {
    const node = mediaRef.current;
    if (!node) return;
    node.currentTime = Math.max(0, seconds);
    setCurrentTime(node.currentTime);
  }

  function selectFinding(finding: Finding) {
    setSelectedId(finding.id);
    seek(finding.start_time);
    setOverlay(Boolean(finding.attribution?.available));
    const stored = finding.attribution?.metadata?.windows;
    if (Array.isArray(stored) && stored.length) {
      let best = 0;
      stored.forEach((item, index) => {
        const delta = typeof item === 'object' && item && 'score_delta' in item ? Number(item.score_delta) : 0;
        const current = typeof stored[best] === 'object' && stored[best] && 'score_delta' in stored[best] ? Number(stored[best].score_delta) : 0;
        if (delta > current) best = index;
      });
      setWindowIndex(best);
    }
  }

  async function saveDisposition(disposition: Disposition) {
    if (!auth.token || !selected) return;
    setSaveState('Saving assessment…');
    try {
      const updated = await reviewFinding(id, selected.id, disposition, note, auth.token);
      setAnalysis(current => current ? {...current, status: disposition === 'needs_expert_review' ? 'EXPERT_REVIEW_REQUESTED' : current.status === 'AI_SCREENING_COMPLETE' ? 'INVESTIGATOR_REVIEW' : current.status, findings: current.findings.map(item => item.id === updated.id ? updated : item)} : current);
      setNote('');
      setSaveState('Assessment saved.');
    } catch (reason) {
      setSaveState(reason instanceof Error ? reason.message : 'Could not save assessment.');
    }
  }

  async function postComment(event: React.FormEvent) {
    event.preventDefault();
    if (!auth.token || !comment.trim()) return;
    try {
      const created = await addCaseComment(id, {
        body: comment.trim(), finding_id: selected?.id, parent_id: replyTo, timestamp_seconds: currentTime,
      }, auth.token);
      setAnalysis(current => current ? {...current, comments: [...current.comments, created]} : current);
      setComment('');
      setReplyTo(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not add comment.');
    }
  }

  async function bookmark() {
    if (!auth.token || bookmarking) return;
    const time = mediaRef.current?.currentTime ?? currentTime;
    const image = captureFrame(mediaRef.current);
    setBookmarking(true);
    setBookmarkMessage('Saving frame…');
    try {
      const created = await addCaseComment(id, {
        body: BOOKMARK_BODY, timestamp_seconds: time, finding_id: selected?.id,
      }, auth.token);
      const entry = {id: created.id, time: created.timestamp_seconds ?? time, image};
      rememberBookmark(id, entry);
      setBookmarks(current => [...current.filter(item => item.id !== entry.id), entry].sort((a, b) => a.time - b.time));
      setAnalysis(current => current ? {...current, comments: [...current.comments, created]} : current);
      setBookmarkMessage(image ? 'Frame bookmarked.' : analysis?.media.media_kind === 'video' ? 'Timestamp saved. A picture is stored when the video frame can be read.' : 'Timestamp bookmarked.');
    } catch (reason) {
      setBookmarkMessage(reason instanceof Error ? reason.message : 'Could not bookmark this frame.');
    } finally {
      setBookmarking(false);
    }
  }

  function removeBookmark(bookmarkId: string) {
    forgetBookmark(id, bookmarkId);
    setBookmarks(current => current.filter(item => item.id !== bookmarkId));
    setBookmarkMessage('Removed from the frame strip. The case note remains.');
  }

  function resolve(commentId: string) {
    if (!auth.token) return;
    resolveCaseComment(id, commentId, auth.token).then(updated => {
      setAnalysis(current => current ? {...current, comments: current.comments.map(entry => entry.id === updated.id ? updated : entry)} : current);
    }).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not update the note.'));
  }

  if (loading) return <section className="empty-panel" aria-live="polite"><TraceLoadingMark/> <h2>Loading analysis</h2><p>Fetching media, findings, and the draft report.</p></section>;
  if (error && !analysis) return <section className="empty-panel"><h2>Analysis unavailable</h2><p>{error}</p></section>;
  if (!analysis || !report) return null;
  const guide = guideForSurface(auth.role, 'case', analysis.status);
  const userKey = userKeyFromToken(auth.token);
  const duration = analysis.media.duration_seconds ?? Math.max(1, ...analysis.findings.map(item => item.end_time ?? item.start_time));
  const heatmap = Array.isArray(selected?.attribution?.metadata?.heatmap) ? selected.attribution.metadata.heatmap as number[][] : null;
  const cropJpeg = typeof selected?.attribution?.metadata?.crop_jpeg_base64 === 'string' ? selected.attribution.metadata.crop_jpeg_base64 : null;
  const temporal = Array.isArray((selected?.attribution?.metadata?.views as {temporal_importance?: number[]})?.temporal_importance)
    ? (selected?.attribution?.metadata?.views as {temporal_importance: number[]}).temporal_importance : null;
  const explainedFrames = analysis.findings.filter(finding => finding.modality === 'video' && Array.isArray(finding.attribution?.metadata?.heatmap));
  const explainedIndex = explainedFrames.findIndex(finding => finding.id === selected?.id);
  const videoRun = analysis.model_runs.find(run => run.modality === 'video' && run.model_name === selected?.model_name);
  const audioRun = analysis.model_runs.find(run => run.modality === 'audio' && run.model_name === selected?.model_name);
  const rawWindows = selected?.attribution?.metadata?.windows;
  const parsedWindows = Array.isArray(rawWindows) ? rawWindows.flatMap(item => {
    if (!item || typeof item !== 'object' || !('score_delta' in item) || !('start' in item) || !('end' in item)) return [];
    return [{
      start: Number(item.start), end: Number(item.end), score_delta: Number(item.score_delta),
      fill: 'fill' in item && typeof item.fill === 'string' ? item.fill : undefined,
    }];
  }) : [];
  const windows = parsedWindows.length ? parsedWindows : null;
  const activeWindow = windows?.length ? windows[Math.min(windowIndex, windows.length - 1)] : null;
  const displayedFill = typeof selected?.attribution?.metadata?.displayed_fill === 'string' ? selected.attribution.metadata.displayed_fill : activeWindow?.fill;
  const rankingsAgree = selected?.attribution?.metadata?.fill_rankings_agree;
  const igRecord = recordOrNull(selected?.attribution?.metadata?.integrated_gradients);
  const attentionRecord = recordOrNull(selected?.attribution?.metadata?.attention);

  return <div className="case-workspace">
    {analysis.development_mock && <p className="mock-banner">Development mock adapter. These values are not model predictions.</p>}
    <CaseCommand caseId={analysis.id} filename={analysis.media.filename} status={analysis.status} mediaKind={analysis.media.media_kind} duration={duration} tourId={guide.tourId} userKey={userKey}/>
    <div className="analysis-tabs" role="tablist" aria-label="Analysis views" onKeyDown={event => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const next = event.key === 'Home' ? 'summary' : event.key === 'End' ? 'technical' : technical ? 'summary' : 'technical';
      setView(next);
      document.getElementById(`analysis-tab-${next}`)?.focus();
    }}>
      <button type="button" role="tab" id="analysis-tab-summary" aria-selected={!technical} aria-controls="analysis-view-panel" tabIndex={technical ? -1 : 0} onClick={() => setView('summary')}>Officer summary</button>
      <button type="button" role="tab" id="analysis-tab-technical" aria-selected={technical} aria-controls="analysis-view-panel" tabIndex={technical ? 0 : -1} onClick={() => setView('technical')}>Technical details</button>
    </div>
    <section className="analysis-view" role="tabpanel" id="analysis-view-panel" aria-labelledby={`analysis-tab-${view}`} tabIndex={0}>
    {technical ? <TechnicalResults analysis={analysis}/> : <OfficerSummary analysis={analysis} onReviewFinding={finding => {
      selectFinding(finding);
      mediaRef.current?.focus();
    }}/>}
    <div className="case-grid">
      <MediaCanvas
        technical={technical}
        mediaKind={analysis.media.media_kind}
        mediaUrl={mediaUrl}
        mediaRef={mediaRef}
        currentTime={currentTime}
        duration={duration}
        findings={analysis.findings}
        selectedId={selected?.id ?? null}
        onTime={setCurrentTime}
        onSeek={seek}
        onSelectFinding={selectFinding}
        bookmarks={bookmarks}
        onBookmark={() => void bookmark()}
        onOpenBookmark={seek}
        onRemoveBookmark={removeBookmark}
        bookmarkMessage={bookmarkMessage}
        bookmarking={bookmarking}
        overlay={overlay}
        onOverlay={setOverlay}
        opacity={opacity}
        onOpacity={setOpacity}
        attributionReady={Boolean(selected?.attribution?.available || heatmap)}
        explainedIndex={explainedIndex}
        explainedCount={explainedFrames.length}
        onStepExplained={index => { const finding = explainedFrames[index]; if (finding) selectFinding(finding); }}
      >
        {technical && selected?.attribution?.available && <div className="attribution-panel">
          <p>{selected.attribution.summary || 'Highlighted areas had greater influence on this model output.'}</p>
          {windows
            ? <p>Masking a span changes the spoof screening score. That change is model sensitivity, not proof the span was synthesized.</p>
            : <p>This visualization indicates model sensitivity, not proof that those pixels were manipulated.</p>}
          {heatmap && cropJpeg && <FaceCompare cropJpeg={cropJpeg} heatmap={heatmap} opacity={overlay ? opacity : 0}/>}
          {heatmap && !cropJpeg && <div className="heatmap" style={{opacity: overlay ? opacity : 1}}>{heatmap.map((row, y) => <div key={y}>{row.map((value, x) => <i key={x} style={{background: `rgba(196, 48, 43, ${value})`}}/>)}</div>)}</div>}
          {windows && activeWindow && <>
            <OcclusionChart windows={windows} active={Math.min(windowIndex, windows.length - 1)} opacity={overlay ? opacity : 0.25} onSelect={index => { setWindowIndex(index); seek(windows[index].start); }}/>
            <p>Masking this 500 ms segment changed the model screening score by {activeWindow.score_delta.toFixed(3)}. Fill: {displayedFill ?? 'stored fill'}.</p>
            {selected.attribution.metadata.repeat_padded === true && <p>Part of the analyzed 4.0375 s input repeats the start of this recording.</p>}
            {selected.attribution.metadata.truncated === true && <p>Attribution covers 0–4.0375 s. Later audio was outside the model input.</p>}
            {rankingsAgree === false && <p>Zeros, local mean, and low-level noise do not rank these windows the same way. The disagreement is stored with the finding.</p>}
          </>}
          {temporal && !windows && <div className="temporal-bars" aria-label="Temporal importance">{temporal.map((value, index) => <i key={index} style={{height: `${Math.max(8, value * 100)}%`}}/>)}</div>}
          {windows && igRecord && <details><summary>Integrated gradients, secondary experiment</summary><p>These bins are not the investigator timeline. {igComparison(igRecord)}</p></details>}
          {windows && attentionRecord && <details><summary>Internal model attention</summary><AttentionNote attention={attentionRecord}/></details>}
          <dl className="attribution-facts">
            {windows
              ? <>
                <div><dt>File screening score</dt><dd>{audioRun?.raw_score == null ? selected.raw_score.toFixed(2) : audioRun.raw_score.toFixed(2)}</dd></div>
                <div><dt>Displayed fill</dt><dd>{displayedFill ?? 'stored fill'}</dd></div>
              </>
              : <>
                <div><dt>Frame screening score</dt><dd>{selected.raw_score.toFixed(2)}</dd></div>
                <div><dt>Video screening score</dt><dd>{videoRun?.raw_score == null ? 'Not available' : videoRun.raw_score.toFixed(2)}</dd></div>
              </>}
            <div><dt>Attribution method</dt><dd>{selected.attribution.method}</dd></div>
            <div><dt>Model version</dt><dd>{selected.model_name} {selected.model_version}</dd></div>
          </dl>
        </div>}
      </MediaCanvas>
      <FindingsInspector technical={technical} findings={analysis.findings} selected={selected} note={note} saveState={saveState} onSelect={selectFinding} onNote={setNote} onDisposition={value => void saveDisposition(value)}/>
    </div>
    <ActivityNotes comments={analysis.comments} comment={comment} replyTo={replyTo} onComment={setComment} onReply={setReplyTo} onSeek={seek} onResolve={resolve} onSubmit={event => void postComment(event)}/>
    {technical && <ScreeningDraft report={report}/>}
    </section>
    <GuidedTour tourId={guide.tourId} userKey={userKey} autoStart={guide.autoStart}/>
    {error && <p role="alert">{error}</p>}
  </div>;
}

function recordOrNull(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) return value as Record<string, unknown>;
  return null;
}

function OcclusionChart({windows, active, opacity, onSelect}: {windows: {score_delta: number}[]; active: number; opacity: number; onSelect: (index: number) => void}) {
  const peak = Math.max(...windows.map(item => Math.abs(item.score_delta)), 1e-6);
  return <div className="occlusion-chart" style={{opacity}} aria-label="Temporal occlusion">{windows.map((item, index) => <button type="button" key={index} className={index === active ? 'selected' : ''} aria-pressed={index === active} onClick={() => onSelect(index)} aria-label={`Masking this 500 ms segment changed the model screening score by ${item.score_delta.toFixed(3)}`}><i style={{height: `${Math.max(8, Math.abs(item.score_delta) / peak * 100)}%`, background: item.score_delta >= 0 ? '#0f5c62' : '#8a5a12'}}/></button>)}</div>;
}

function igComparison(record: Record<string, unknown>) {
  const comparison = 'occlusion_comparison' in record && Array.isArray(record.occlusion_comparison) ? record.occlusion_comparison : [];
  const matched = comparison.filter(item => Boolean(item) && typeof item === 'object' && 'top_sets_match' in item && item.top_sets_match === true).length;
  if (!comparison.length) return 'No comparison with occlusion was stored.';
  return `${matched} of ${comparison.length} top-window comparisons match occlusion. Disagreements stay in the artifact.`;
}

function AttentionNote({attention}: {attention: Record<string, unknown>}) {
  const maps = 'maps' in attention && Array.isArray(attention.maps) ? attention.maps : [];
  const pools = 'pools' in attention && Array.isArray(attention.pools) ? attention.pools : [];
  return <>
    <p>Internal model attention. These weights are not a causal explanation of the screening score, and they are not a timeline.</p>
    <ul>{maps.map((item, index) => {
      if (!item || typeof item !== 'object' || !('name' in item)) return null;
      const role = 'role' in item && typeof item.role === 'string' ? item.role : '';
      return <li key={index}>{String(item.name)}. {role}</li>;
    })}</ul>
    {!!pools.length && <p>{pools.length} graph pools recorded gather indices. After pooling, node 0 is not encoder time 0.</p>}
  </>;
}

function FaceCompare({cropJpeg, heatmap, opacity}: {cropJpeg: string; heatmap: number[][]; opacity: number}) {
  const source = `data:image/jpeg;base64,${cropJpeg}`;
  return <div className="face-compare">
    <figure><figcaption>Original</figcaption><img src={source} alt="Analyzed face crop"/></figure>
    <figure><figcaption>Attribution</figcaption><div className="face-stack"><img src={source} alt="Face crop with model attribution"/><div className="heatmap heatmap-overlay" style={{opacity, gridTemplateRows: `repeat(${heatmap.length}, 1fr)`}}>{heatmap.map((row, y) => <div key={y} style={{gridTemplateColumns: `repeat(${row.length}, 1fr)`}}>{row.map((value, x) => <i key={x} style={{background: `rgba(196, 48, 43, ${value})`}}/>)}</div>)}</div></div></figure>
  </div>;
}
