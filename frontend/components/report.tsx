'use client';
import {useEffect,useRef,useState} from 'react';
import Link from 'next/link';
import {
  addComment,completeReview,formatBytes,getNotebook,getReportMedia,
  listComments,saveNotebook,startReview,submitReport,type Report,type ReviewComment,
} from '../lib/api';
import {useAuth} from './auth';
import {createReportPdf} from '../lib/report-pdf';
import {ReportOverview, ReportTechnical} from './report-content';

export function ReportView({report:r,onReset}:{report:Report;onReset:()=>void}) {
  const auth=useAuth();
  const heading=useRef<HTMLElement>(null);
  const [reportView,setReportView]=useState<'overview'|'technical'>('overview');
  const [workflow,setWorkflow]=useState(r.workflow_status??'draft');
  const [reviewMessage,setReviewMessage]=useState('');
  const [mediaUrl,setMediaUrl]=useState('');
  const [comments,setComments]=useState<ReviewComment[]>([]);
  const [comment,setComment]=useState('');
  const [notebook,setNotebook]=useState('');
  const [notebookMessage,setNotebookMessage]=useState('');
  useEffect(()=>{heading.current?.focus({preventScroll:true});heading.current?.scrollIntoView({block:'start'});setReportView('overview');setWorkflow(r.workflow_status??'draft');},[r]);
  useEffect(()=>{if(auth.role!=='supervisor'||workflow==='draft'||!auth.token)return;let active=true;let url='';getReportMedia(r.report_id,auth.token).then(blob=>{if(active){url=URL.createObjectURL(blob);setMediaUrl(url);}}).catch(()=>setReviewMessage('Media could not be loaded.'));return()=>{active=false;if(url)URL.revokeObjectURL(url);setMediaUrl('');};},[auth.role,auth.token,r.report_id,workflow]);
  useEffect(()=>{if(!auth.token)return;let active=true;Promise.all([listComments(r.report_id,auth.token),getNotebook(r.report_id,auth.token)]).then(([nextComments,note])=>{if(active){setComments(nextComments);setNotebook(note.body);}}).catch(()=>{if(active)setNotebookMessage('Workspace unavailable.');});return()=>{active=false;};},[auth.token,r.report_id]);
  function download(){const url=URL.createObjectURL(createReportPdf({...r,workflow_status:workflow}));const a=document.createElement('a');a.href=url;a.download=`deeptrace-${r.report_id}.pdf`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  async function send(){if(!auth.token)return;setReviewMessage('Sending…');try{await submitReport(r.report_id,auth.token);setWorkflow('submitted');setReviewMessage('Sent for review.');}catch(e){setReviewMessage(e instanceof Error?e.message:'Could not send report.');}}
  async function beginReview(){if(!auth.token)return;setReviewMessage('Starting…');try{await startReview(r.report_id,auth.token);setWorkflow('in_review');setReviewMessage('Review started.');}catch(e){setReviewMessage(e instanceof Error?e.message:'Could not start review.');}}
  async function finishReview(){if(!auth.token)return;setReviewMessage('Saving…');try{await completeReview(r.report_id,auth.token);setWorkflow('reviewed');setReviewMessage('Review complete.');}catch(e){setReviewMessage(e instanceof Error?e.message:'Could not complete review.');}}
  async function postComment(e:React.FormEvent){e.preventDefault();if(!auth.token||!comment.trim())return;try{const next=await addComment(r.report_id,comment.trim(),auth.token);setComments(items=>[...items,next]);setComment('');}catch(e){setReviewMessage(e instanceof Error?e.message:'Could not add comment.');}}
  async function storeNotebook(){if(!auth.token)return;setNotebookMessage('Saving…');try{await saveNotebook(r.report_id,notebook,auth.token);setNotebookMessage('Saved.');}catch(e){setNotebookMessage(e instanceof Error?e.message:'Could not save notebook.');}}
  return <section className={`report screening-report report-${reportView}`} ref={heading} tabIndex={-1} aria-label="Screening report">
    <header className="screening-report-heading">
      <div>
        <p className="screening-report-reference">Report <code>{r.report_id.slice(0,8)}</code>{r.owner && <span> · {r.owner}</span>}</p>
        <h1>{r.media.filename}</h1>
        <p className="screening-report-meta">{r.media.media_kind === 'video' ? 'Video' : 'Audio'} · {formatBytes(r.media.size_bytes)}{r.media.duration_seconds != null && ` · ${r.media.duration_seconds.toFixed(2)} seconds`}</p>
      </div>
      <span className={`workflow-badge ${workflow}`}>{workflow.replaceAll('_',' ')}</span>
    </header>
    <div className="report-actions">
      {auth.role==='analyst'&&workflow==='draft'&&<button className="primary-button review-button" onClick={send}>Send for review</button>}
      {auth.role==='supervisor'&&workflow==='submitted'&&<button className="primary-button review-button" onClick={beginReview}>Start review</button>}
      {auth.role==='supervisor'&&workflow==='in_review'&&<button className="primary-button review-button" onClick={finishReview}>Complete review</button>}
      <button className="secondary-button" onClick={download}>Download PDF</button>
      {r.analysis_id&&<Link className="secondary-button review-button" data-tour="open-case" href={`/analyses/${r.analysis_id}`}>Open workspace</Link>}
      <button className="text-button" onClick={onReset}>New screening</button>
    </div>
    {!!reviewMessage && <p className="report-review-message" aria-live="polite">{reviewMessage}</p>}
    {auth.role==='supervisor'&&workflow!=='draft'&&mediaUrl&&<div className="review-media">{r.media.media_kind==='video'?<video src={mediaUrl} controls/>:<audio src={mediaUrl} controls/>}</div>}
    <div className="report-view-control" role="radiogroup" aria-label="Report detail level">
      <label><input type="radio" name={`report-view-${r.report_id}`} value="overview" checked={reportView==='overview'} onChange={()=>setReportView('overview')}/><span>Overview</span></label>
      <label><input type="radio" name={`report-view-${r.report_id}`} value="technical" checked={reportView==='technical'} onChange={()=>setReportView('technical')}/><span>Technical detail</span></label>
    </div>
    {reportView === 'overview' ? <ReportOverview report={r}/> : <ReportTechnical report={r}/>}
    {auth.token&&<section className="report-review-workspace" aria-labelledby="report-review-title">
      <header className="report-section-heading"><h2 id="report-review-title">Review notes</h2></header>
      <div className="report-notes-grid">
        <article className="report-panel">
          <header className="report-panel-heading"><h3>Comments</h3><span>Shared</span></header>
          <div className="report-panel-body">
            <ul className="report-comment-list">{comments.length ? comments.map(item=><li key={item.comment_id}>
              <header><strong>{item.author}</strong><span>{item.author_role} · {new Date(item.created_at).toLocaleString()}</span></header><p>{item.body}</p>
            </li>) : <li className="report-empty">No comments yet.</li>}</ul>
            <form className="report-comment-form" onSubmit={postComment}>
              <label className="stack">Comment<textarea value={comment} onChange={e=>setComment(e.target.value)} maxLength={2000} aria-label="Add a review comment"/></label>
              <button className="secondary-button" disabled={!comment.trim()}>Post</button>
            </form>
          </div>
        </article>
        <article className="report-panel">
          <header className="report-panel-heading"><h3>Analysis notebook</h3><span>Private</span></header>
          <div className="report-panel-body report-private-notes">
            <label className="stack">Notes<textarea value={notebook} onChange={e=>{setNotebook(e.target.value);setNotebookMessage('');}} maxLength={10000} aria-label="Private analysis notebook"/></label>
            <div className="report-notebook-actions"><span aria-live="polite">{notebookMessage}</span><button className="secondary-button" onClick={storeNotebook}>Save notes</button></div>
          </div>
        </article>
      </div>
    </section>}
  </section>;
}
