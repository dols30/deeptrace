'use client';
import {useEffect,useState} from 'react';
import Link from 'next/link';
import {deleteReport,listReports,type ReportSummary} from '../lib/api';
import {useAuth} from './auth';
import {TraceLoadingMark} from './trace/trace-mark';

export function SavedReports(){const auth=useAuth();const [items,setItems]=useState<ReportSummary[]|null>(null);const [error,setError]=useState('');
  function load(){if(!auth.token)return;listReports(auth.token).then(data=>{setItems(data);setError('');}).catch(e=>{if(e instanceof Error&&e.message==='SESSION_EXPIRED')auth.expire();else setError('Could not load reports.');});}
  useEffect(()=>{if(!auth.token)return;load();const timer=window.setInterval(load,10000);const visible=()=>{if(document.visibilityState==='visible')load();};document.addEventListener('visibilitychange',visible);return()=>{window.clearInterval(timer);document.removeEventListener('visibilitychange',visible);};},[auth.token]);
  async function remove(item:ReportSummary){if(!auth.token||!window.confirm(`Delete ${item.filename}?`))return;try{await deleteReport(item.report_id,auth.token);setItems(current=>current?.filter(entry=>entry.report_id!==item.report_id)??[]);}catch(e){if(e instanceof Error&&e.message==='SESSION_EXPIRED')auth.expire();else setError(e instanceof Error?e.message:'Could not delete report.');}}
  if(error)return <p className="form-error">{error}</p>;
  if(items===null)return <section className="empty-panel"><TraceLoadingMark/><h2>Loading</h2></section>;
  if(!items.length)return <section className="empty-panel reports-empty"><span>▤</span><h2>{auth.role==='supervisor'?'Queue clear':'No reports'}</h2>{auth.role==='supervisor'?<button className="secondary-button" onClick={load}>Refresh</button>:<Link className="primary-link" href="/detector">New scan →</Link>}</section>;
  return <section className="reports-panel"><header className="reports-bar"><div><strong>{items.length}</strong><span>{auth.role==='supervisor'?'Assigned':'Saved'}</span></div>{auth.role==='supervisor'?<button onClick={load}>Refresh <span>↻</span></button>:<Link href="/detector">New scan <span>＋</span></Link>}</header><div className="reports-head"><span>Media</span><span>Status</span><span>Evidence</span><span/></div><div className="saved-list">{items.map(item=><div className="saved-row" key={item.report_id}><Link href={`/reports/${item.report_id}`}><div className="saved-type">{item.media_kind==='video'?'VID':'AUD'}</div><div className="saved-detail"><strong>{item.filename}</strong><span>{auth.role==='supervisor'&&`${item.owner} · `}{new Date(item.generated_at).toLocaleDateString()}</span></div><span className={`workflow-badge ${item.workflow_status}`}>{item.workflow_status}</span><b className="confidence-cell"><small>Independent evidence</small><span>View report</span></b><i>›</i></Link><button type="button" className="text-button" onClick={()=>void remove(item)}>Delete</button></div>)}</div></section>;
}
