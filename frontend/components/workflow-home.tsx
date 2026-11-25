'use client';
import Link from 'next/link';
import {useEffect, useState} from 'react';
import type {Role} from '../lib/api';
import {useAuth} from './auth';
import {EMPTY_QUEUE} from './guide/tour-copy';
import {PageFrame} from './page-frame';
import {ModelInformation} from './model-information';
import {TraceLoadingMark} from './trace/trace-mark';
import {
  createUser, getAudit, getModelInfo, getQueue, listUsers, STATUS_LABEL,
  type AnalysisSummary,
} from '../lib/workflow';

function useLoad<T>(loader: (token: string) => Promise<T>, token: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    if (!token) return;
    let active = true;
    loader(token).then(value => { if (active) setData(value); }).catch(reason => {
      if (active) setError(reason instanceof Error ? reason.message : 'Could not load this page.');
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [loader, token]);
  return {data, error, loading};
}

function bucket(status: string) {
  if (status === 'UPLOADED' || status === 'PROCESSING' || status === 'AI_SCREENING_COMPLETE') return 'screening';
  if (status === 'INVESTIGATOR_REVIEW' || status === 'CHANGES_REQUESTED') return 'investigator';
  if (status === 'EXPERT_REVIEW_REQUESTED' || status === 'SUPERVISOR_REVIEW') return 'escalation';
  if (status === 'FINALIZED') return 'final';
  return 'other';
}

const FILTERS = [
  {id: 'all', label: 'All open'},
  {id: 'screening', label: 'Screening'},
  {id: 'investigator', label: 'Investigator'},
  {id: 'escalation', label: 'Escalation'},
  {id: 'final', label: 'Final'},
];

export function QueueView() {
  const auth = useAuth();
  const {data, error, loading} = useLoad(getQueue, auth.token);
  if (loading) return <section className="empty-panel"><TraceLoadingMark/><h2>Loading workspace</h2></section>;
  if (error || !data) return <section className="empty-panel"><h2>Workspace unavailable</h2><p>{error}</p></section>;
  return <QueueContent data={data} role={auth.role}/>;
}

export function QueueContent({data, role}: {data: AnalysisSummary[]; role: Role | null}) {
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const needle = query.trim().toLowerCase();
  const visible = data.filter(item => {
    const matchesFilter = filter === 'all' || bucket(item.status) === filter;
    const haystack = `${item.title} ${item.owner} ${STATUS_LABEL[item.status] ?? item.status}`.toLowerCase();
    return matchesFilter && (!needle || haystack.includes(needle));
  });
  const counts = {
    screening: data.filter(item => bucket(item.status) === 'screening').length,
    investigator: data.filter(item => bucket(item.status) === 'investigator').length,
    escalation: data.filter(item => bucket(item.status) === 'escalation').length,
    final: data.filter(item => bucket(item.status) === 'final').length,
  };
  return <PageFrame>
    <div className="work-stats">
      <article className="work-stat"><b>{data.length}</b><span>Open cases</span></article>
      <article className="work-stat"><b>{counts.screening}</b><span>Screening</span></article>
      <article className="work-stat"><b>{counts.investigator}</b><span>Investigator</span></article>
      <article className="work-stat"><b>{counts.escalation}</b><span>Escalation</span></article>
    </div>
    <div className="work-toolbar">
      <div className="work-filters" role="tablist" aria-label="Filter cases">
        {FILTERS.map(item => <button key={item.id} type="button" role="tab" aria-selected={filter === item.id} className={filter === item.id ? 'active' : undefined} onClick={() => setFilter(item.id)}>{item.label}</button>)}
      </div>
      <input className="work-search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search cases" aria-label="Search cases"/>
    </div>
    {visible.length
      ? <div className="work-table">
        <div className="work-head"><span>Case</span><span>Status</span><span>Media</span><span>Findings</span><span>Owner</span><span>Opened</span></div>
        {visible.map(item => <CaseRow key={item.id} item={item}/>)}
      </div>
      : <section className="empty-panel work-empty"><h2>{data.length ? 'No matching cases' : 'No open cases'}</h2><p>{data.length ? 'Adjust the filter or search.' : role === 'supervisor' ? 'Cases appear here when an investigator submits them for review.' : EMPTY_QUEUE}</p>{!data.length && role !== 'supervisor' && <Link className="primary-link" href="/detector">Start a scan</Link>}</section>}
  </PageFrame>;
}

function CaseRow({item}: {item: AnalysisSummary}) {
  return <Link className="work-row" href={`/analyses/${item.id}`}>
    <span><strong>{item.title}</strong><small>{item.id}</small></span>
    <span className={`workflow-badge ${item.status}`}>{STATUS_LABEL[item.status] ?? item.status}</span>
    <span>{item.media_kind}</span>
    <span>{item.finding_count}</span>
    <span>{item.owner}</span>
    <span>{new Date(item.created_at).toLocaleDateString()}</span>
  </Link>;
}

export function AuditView() {
  const auth = useAuth();
  const {data, error, loading} = useLoad(getAudit, auth.token);
  if (loading) return <section className="empty-panel"><TraceLoadingMark/><h2>Loading audit history</h2></section>;
  if (error || !data) return <section className="empty-panel"><h2>Audit history unavailable</h2><p>{error}</p></section>;
  return <PageFrame>
    {!data.length
      ? <section className="empty-panel"><h2>No audit events</h2><p>Uploads, reviews, and report actions will appear here.</p></section>
      : <div className="audit-table"><div><span>When</span><span>Actor</span><span>Action</span><span>Record</span></div>{data.map(event => <div key={event.id}><span>{new Date(event.timestamp).toLocaleString()}</span><span>{event.actor_id}</span><span>{event.action}</span><span>{event.entity_type}</span></div>)}</div>}
  </PageFrame>;
}

export function SettingsView() {
  const auth = useAuth();
  const {data, error, loading} = useLoad(getModelInfo, auth.token);
  if (loading) return <section className="empty-panel"><TraceLoadingMark/><h2>Loading model information</h2></section>;
  if (error || !data) return <section className="empty-panel"><h2>Model information unavailable</h2><p>{error}</p></section>;
  return <PageFrame>
    <ModelInformation data={data}/>
  </PageFrame>;
}

export function UsersView() {
  const auth = useAuth();
  const [users, setUsers] = useState<{username: string; display_name: string; role: string; active: boolean}[]>([]);
  const [error, setError] = useState('');
  const [form, setForm] = useState({username: '', password: '', role: 'investigator', display_name: ''});
  useEffect(() => {
    if (!auth.token) return;
    listUsers(auth.token).then(setUsers).catch(reason => setError(reason instanceof Error ? reason.message : 'Could not load users.'));
  }, [auth.token]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!auth.token) return;
    try {
      const created = await createUser(form, auth.token);
      setUsers(current => [...current, created].sort((a, b) => a.username.localeCompare(b.username)));
      setForm({username: '', password: '', role: 'investigator', display_name: ''});
      setError('');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create user.');
    }
  }
  return <PageFrame>
    <div className="user-layout">
      <section className="profile-panel">
        <header className="pane-head"><h2>Directory</h2><span>{users.length}</span></header>
        <ul className="case-list">{users.map(user => <li key={user.username}><div><strong>{user.display_name || user.username}</strong><span>{user.role}</span><small>{user.username}{user.active ? '' : ' · inactive'}</small></div></li>)}{!users.length && <li className="workspace-empty">No directory users yet. Environment accounts can still sign in.</li>}</ul>
      </section>
      <section className="profile-panel">
        <h2>Add a user</h2>
        <form className="profile-form" onSubmit={event => void submit(event)}>
          <label>Username<input value={form.username} onChange={event => setForm({...form, username: event.target.value})} required autoComplete="off"/></label>
          <label>Display name<input value={form.display_name} onChange={event => setForm({...form, display_name: event.target.value})}/></label>
          <label>Password<input type="password" value={form.password} onChange={event => setForm({...form, password: event.target.value})} minLength={8} required autoComplete="new-password"/></label>
          <label>Role<select value={form.role} onChange={event => setForm({...form, role: event.target.value})}><option value="investigator">Investigator</option><option value="forensic_reviewer">Forensic reviewer</option><option value="supervisor">Supervisor</option><option value="administrator">Administrator</option></select></label>
          {error && <p role="alert">{error}</p>}
          <button className="primary-button">Create user</button>
        </form>
      </section>
    </div>
  </PageFrame>;
}
