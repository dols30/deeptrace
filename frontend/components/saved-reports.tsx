'use client';

import {useEffect, useState} from 'react';
import Link from 'next/link';
import {deleteReport, listReports, type ReportSummary} from '../lib/api';
import {REPORT_STATUS_LABELS} from '../lib/report-presentation';
import {useAuth} from './auth';
import {TraceLoadingMark} from './trace/trace-mark';

export function SavedReports() {
  const auth = useAuth();
  const [items, setItems] = useState<ReportSummary[] | null>(null);
  const [error, setError] = useState('');

  function load() {
    if (!auth.token) return;
    listReports(auth.token).then(data => {
      setItems(data);
      setError('');
    }).catch(reason => {
      if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') auth.expire();
      else setError('Could not load reports.');
    });
  }

  useEffect(() => {
    if (!auth.token) return;
    load();
    const timer = window.setInterval(load, 10000);
    const visible = () => { if (document.visibilityState === 'visible') load(); };
    document.addEventListener('visibilitychange', visible);
    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [auth.token]);

  async function remove(item: ReportSummary) {
    if (!auth.token || !window.confirm(`Delete ${item.filename}?`)) return;
    try {
      await deleteReport(item.report_id, auth.token);
      setItems(current => current?.filter(entry => entry.report_id !== item.report_id) ?? []);
    } catch (reason) {
      if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') auth.expire();
      else setError(reason instanceof Error ? reason.message : 'Could not delete report.');
    }
  }

  const supervisor = auth.role === 'supervisor';
  return <section className="reports-library" aria-labelledby="reports-title">
    <header className="reports-library-heading">
      <div><h1 id="reports-title">Reports</h1>
        {items && <p>{items.length} {supervisor ? 'assigned' : 'saved'} {items.length === 1 ? 'report' : 'reports'}</p>}
      </div>
      {supervisor ? <button type="button" className="secondary-button" onClick={load}>Refresh</button>
        : <Link className="primary-button" href="/detector">New screening</Link>}
    </header>
    {error ? <p className="form-error" role="alert">{error}</p>
      : items === null ? <section className="empty-panel" aria-live="polite"><TraceLoadingMark/><h2>Loading reports</h2></section>
      : !items.length ? <section className="empty-panel"><h2>{supervisor ? 'No assigned reports' : 'No saved reports'}</h2></section>
      : <ul className="reports-library-list">{items.map(item => <li key={item.report_id}>
        <Link className="reports-library-link" href={`/reports/${item.report_id}`}>
          <div>
            <strong>{item.filename}</strong>
            <p>{item.media_kind === 'video' ? 'Video' : 'Audio'} · {new Date(item.generated_at).toLocaleDateString()}{supervisor && item.owner && ` · ${item.owner}`}</p>
          </div>
          <span className={`workflow-badge ${item.workflow_status}`}>{REPORT_STATUS_LABELS[item.workflow_status] ?? 'Status unavailable'}</span>
        </Link>
        <button type="button" className="text-button" aria-label={`Delete report for ${item.filename}`} onClick={() => void remove(item)}>Delete</button>
      </li>)}</ul>}
  </section>;
}
