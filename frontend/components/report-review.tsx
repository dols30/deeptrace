'use client';
import Link from 'next/link';
import {useEffect, useRef, useState} from 'react';
import {TraceLoadingMark} from './trace/trace-mark';
import {
  finalizeCaseReport, getAnalysis, getAnalysisMedia, getCaseReport, REPORT_SECTIONS,
  reportDiff, requestChanges, restoreRevision, saveCaseReport, STATUS_LABEL,
  submitCaseReport, type AnalysisDetail, type CaseReport, type Finding,
} from '../lib/workflow';
import {useAuth} from './auth';
import {GuideButton, GuidedTour} from './guide/guided-tour';
import {EMPTY_FINDINGS, guideForSurface, userKeyFromToken} from './guide/tour-copy';

import {FindingPicker} from './workspace/findings-inspector';
import {ReportSectionText} from './workspace/screening-draft';

const HUMAN_KEYS = new Set(['investigator_assessment', 'items_requiring_additional_review', 'reviewer_notes']);

export function ReportReview({id}: {id: string}) {
  const auth = useAuth();
  const mediaRef = useRef<HTMLVideoElement & HTMLAudioElement>(null);
  const [analysis, setAnalysis] = useState<AnalysisDetail | null>(null);
  const [report, setReport] = useState<CaseReport | null>(null);
  const [mediaUrl, setMediaUrl] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState('');
  const [changeNote, setChangeNote] = useState('');
  const [diff, setDiff] = useState<Awaited<ReturnType<typeof reportDiff>> | null>(null);
  const saveTimer = useRef<number | null>(null);
  const expire = useRef(auth.expire);
  expire.current = auth.expire;
  const selected = analysis?.findings.find(item => item.id === selectedId) ?? analysis?.findings[0] ?? null;

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
      })
      .catch(reason => {
        if (!active) return;
        if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') expire.current();
        else setError(reason instanceof Error ? reason.message : 'The review page could not be loaded.');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false;
      if (url) URL.revokeObjectURL(url);
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
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
  }

  function scheduleSave(next: CaseReport['current']) {
    if (!auth.token) return;
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      setSaveState('Saving draft…');
      void saveCaseReport(id, next, auth.token).then(saved => {
        setReport(saved);
        setSaveState('Draft saved.');
      }).catch(reason => setSaveState(reason instanceof Error ? reason.message : 'Could not save draft.'));
    }, 800);
  }

  function editSection(key: string, text: string) {
    if (!report) return;
    const origin = text === report.ai_original[key]?.text ? report.ai_original[key].origin : 'human';
    const current = {...report.current, [key]: {text, origin}};
    setReport({...report, current});
    scheduleSave(current);
  }

  if (loading) return <section className="empty-panel" aria-live="polite"><TraceLoadingMark/> <h2>Loading report review</h2><p>Fetching the recording and the draft.</p></section>;
  if (error && !analysis) return <section className="empty-panel"><h2>Review unavailable</h2><p>{error}</p></section>;
  if (!analysis || !report) return null;
  const investigator = auth.role === 'analyst' || auth.role === 'investigator';
  const guide = guideForSurface(auth.role, 'review', analysis.status);
  const userKey = userKeyFromToken(auth.token);
  const editable = ['AI_SCREENING_COMPLETE', 'INVESTIGATOR_REVIEW', 'CHANGES_REQUESTED'].includes(analysis.status) && investigator;
  const aiSections = REPORT_SECTIONS.filter(section => !HUMAN_KEYS.has(section.key));

  return <div className="review-layout">
    <section className="review-analysis" aria-label="Analysis" data-tour="review-evidence">
      <div className="workspace-title"><h2>Analysis</h2><Link className="text-button" href={`/analyses/${id}`}>Back to screening</Link></div>
      <p className="case-meta"><span className={`workflow-badge ${analysis.status}`}>{STATUS_LABEL[analysis.status] ?? analysis.status}</span><span>{analysis.media.filename}</span></p>
      {analysis.media.media_kind === 'video'
        ? <video ref={mediaRef} src={mediaUrl} controls onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)}/>
        : <audio ref={mediaRef} src={mediaUrl} controls onTimeUpdate={event => setCurrentTime(event.currentTarget.currentTime)}/>}
      <label className="stack">Seek<input type="number" min={0} step={0.1} value={Number(currentTime.toFixed(1))} onChange={event => seek(Number(event.target.value))} aria-label="Seek to seconds"/></label>
      {analysis.findings.length
        ? <FindingPicker findings={analysis.findings} selected={selected} onSelect={selectFinding}/>
        : <p>{EMPTY_FINDINGS}</p>}
    </section>
    <section className="report-editor" aria-label="Human report">
      <div className="workspace-title"><h2>Human report</h2><span>{saveState}</span></div>
      <div className="detector-toolbar"><GuideButton tourId={guide.tourId} userKey={userKey}/></div>
      <p>Write the investigator sections here. The AI draft stays visible and is never overwritten.</p>
      <details className="report-detail"><summary>Original screening draft</summary>
        {aiSections.map(section => <article key={section.key} className="ai-reference">
          <h3>{section.label}</h3><ReportSectionText text={report.ai_original[section.key]?.text}/>
        </article>)}
      </details>
      {REPORT_SECTIONS.filter(section => HUMAN_KEYS.has(section.key)).map(section => {
        const current = report.current[section.key] ?? {text: '', origin: 'human' as const};
        const canEdit = analysis.status !== 'FINALIZED' && (auth.role === 'supervisor'
          ? analysis.status === 'SUPERVISOR_REVIEW' && section.key === 'reviewer_notes'
          : editable && section.key !== 'reviewer_notes');
        return <label key={section.key} className="stack"><span>{section.label} <i className={current.origin === 'ai' ? 'origin-ai' : 'origin-human'}>{current.origin === 'ai' ? 'AI-generated' : 'Human-authored'}</i></span><textarea value={current.text} disabled={!canEdit} onChange={event => editSection(section.key, event.target.value)}/></label>;
      })}
      <div className="report-editor-actions" data-tour={auth.role === 'supervisor' ? 'supervisor-actions' : 'review-submit'}>
        {editable && <button type="button" className="primary-button" onClick={() => void submitCaseReport(id, auth.token).then(setAnalysis)}>Submit for review</button>}
        <button type="button" className="secondary-button" onClick={() => auth.token && reportDiff(id, auth.token).then(setDiff)}>Compare with AI original</button>
        {auth.role === 'supervisor' && analysis.status === 'SUPERVISOR_REVIEW' && <>
          <label className="stack">Request changes<textarea value={changeNote} onChange={event => setChangeNote(event.target.value)} aria-label="Requested changes"/></label>
          <button type="button" className="secondary-button" onClick={() => auth.token && requestChanges(id, changeNote, auth.token).then(setAnalysis)}>Request changes</button>
          <button type="button" className="primary-button" onClick={() => auth.token && finalizeCaseReport(id, auth.token).then(setAnalysis)}>Finalize</button>
        </>}
      </div>
      {diff && <div className="diff-grid">{diff.filter(item => item.changed).map(item => <article key={item.section}><h3>{item.label}</h3><div><strong>AI original</strong><p>{item.ai_text || 'Empty'}</p></div><div><strong>Current version</strong><p>{item.current_text || 'Empty'}</p></div></article>)}{!diff.some(item => item.changed) && <p>The current draft matches the AI original.</p>}</div>}
      <h3>Version history</h3>
      <ul>{report.revisions.map(revision => <li key={revision.id}><span>{revision.kind.replaceAll('_', ' ')} · {revision.author}</span>{editable && <button type="button" className="text-button" onClick={() => auth.token && restoreRevision(id, revision.id, auth.token).then(setReport)}>Restore</button>}</li>)}</ul>
      {error && <p role="alert">{error}</p>}
    </section>
    <GuidedTour tourId={guide.tourId} userKey={userKey} autoStart={guide.autoStart}/>
  </div>;
}
