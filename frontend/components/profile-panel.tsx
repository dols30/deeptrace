'use client';
import {useEffect, useState} from 'react';
import {getProfile, updateProfile, type Profile, type Role} from '../lib/api';
import {ROLE_LABEL} from '../lib/workflow';
import {useAuth} from './auth';
import {PageFrame} from './page-frame';

const ACCESS: Record<Role, string> = {
  analyst: 'Records dispositions and can send a report for approval.',
  investigator: 'Records dispositions and can send a report for approval.',
  forensic_reviewer: 'Reviews escalated findings and adds expert comments.',
  supervisor: 'Approves submitted reports and can request changes.',
  administrator: 'Manages directory users and oversight settings.',
};

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return 'DT';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[parts.length - 1][0]}`.toUpperCase();
}

export function ProfilePanel() {
  const auth = useAuth();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!auth.token) return;
    getProfile(auth.token).then(item => {
      setProfile(item);
      setName(item.display_name);
      setTitle(item.title);
    }).catch(() => setMessage('Could not load profile.'));
  }, [auth.token]);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (!auth.token) return;
    setSaving(true);
    setMessage('Saving…');
    try {
      const item = await updateProfile({display_name: name, title}, auth.token);
      setProfile(item);
      setMessage('Profile saved.');
    } catch {
      setMessage('Could not save profile.');
    } finally {
      setSaving(false);
    }
  }

  const role = profile?.role ?? auth.role;
  const roleLabel = role ? ROLE_LABEL[role] ?? role : 'Loading…';

  return <PageFrame>
    <div className="profile-layout">
      <section className="profile-identity">
        <span className="profile-avatar" aria-hidden="true">{initials(name || profile?.username || 'DeepTrace')}</span>
        <div>
          <h2>{name || 'Profile'}</h2>
          <p>{title || 'Add a title'}</p>
        </div>
        <span className="role-chip">{roleLabel}</span>
        <dl className="profile-facts profile-facts-stack">
          <div><dt>Username</dt><dd>{profile?.username || 'Loading…'}</dd></div>
          <div><dt>Session</dt><dd>This browser</dd></div>
        </dl>
        <button type="button" className="secondary-button" onClick={auth.signOut}>Sign out</button>
      </section>
      <div className="profile-panels">
        <section className="profile-panel">
          <h2>Identity</h2>
          <form className="profile-form" onSubmit={event => void save(event)}>
            <label>Display name<input value={name} onChange={event => setName(event.target.value)} required maxLength={80} autoComplete="name"/></label>
            <label>Title<input value={title} onChange={event => setTitle(event.target.value)} required maxLength={80} autoComplete="organization-title"/></label>
            <div className="profile-form-actions">
              <button className="primary-button" disabled={saving}>{saving ? 'Saving…' : 'Save profile'}</button>
              <p aria-live="polite">{message}</p>
            </div>
          </form>
        </section>
        <section className="profile-panel">
          <h2>Access</h2>
          <dl className="profile-facts">
            <div><dt>Role</dt><dd>{roleLabel}</dd></div>
            <div><dt>Authority</dt><dd>{role ? ACCESS[role] : 'Loading…'}</dd></div>
            <div><dt>Workspace</dt><dd>Open cases, media review, and reports</dd></div>
            <div><dt>Record</dt><dd>Actions are written to the audit log</dd></div>
          </dl>
        </section>
      </div>
    </div>
  </PageFrame>;
}
