'use client';
import {useEffect, useRef, useState} from 'react';
import {getProfile, updateProfile, type Profile} from '../lib/api';
import {ROLE_LABEL} from '../lib/workflow';
import {useAuth} from './auth';
import {PageFrame} from './page-frame';

export function ProfilePanel() {
  const auth = useAuth();
  const expire = useRef(auth.expire);
  expire.current = auth.expire;
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState('');
  const [title, setTitle] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle');

  useEffect(() => {
    if (!auth.token) return;
    let active = true;
    getProfile(auth.token).then(item => {
      if (!active) return;
      setProfile(item);
      setName(item.display_name);
      setTitle(item.title);
    }).catch(error => {
      if (!active) return;
      if (error instanceof Error && error.message === 'SESSION_EXPIRED') {
        expire.current();
      } else {
        setLoadFailed(true);
      }
    });
    return () => { active = false; };
  }, [auth.token, attempt]);

  const saving = saveState === 'saving';
  const dirty = profile && (name.trim() !== profile.display_name || title.trim() !== profile.title);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!auth.token || !dirty || saving) return;
    setSaveState('saving');
    try {
      const item = await updateProfile({display_name: name.trim(), title: title.trim()}, auth.token);
      setProfile(item);
      setName(item.display_name);
      setTitle(item.title);
      setSaveState('saved');
    } catch (error) {
      if (error instanceof Error && error.message === 'SESSION_EXPIRED') auth.expire();
      setSaveState('failed');
    }
  }

  return <PageFrame>
    <div className="account-profile">
      <header className="model-page-heading"><h1>Profile</h1></header>
      <div className="profile-panel">
        {profile ? <>
          <section aria-labelledby="profile-details-heading">
            <h2 id="profile-details-heading">Personal details</h2>
            <form className="profile-form" onSubmit={event => void save(event)} aria-busy={saving}>
              <label>Display name
                <input value={name} onChange={event => { setName(event.target.value); setSaveState('idle'); }}
                  required maxLength={80} autoComplete="name" disabled={saving}/>
              </label>
              <label>Job title
                <input value={title} onChange={event => { setTitle(event.target.value); setSaveState('idle'); }}
                  required maxLength={80} autoComplete="organization-title" disabled={saving}/>
              </label>
              <div className="profile-form-actions">
                <button className="primary-button" disabled={!dirty || !name.trim() || !title.trim() || saving}>
                  {saving ? 'Saving…' : 'Save changes'}
                </button>
                <span role="status">{saveState === 'saved' ? 'Changes saved' : ''}</span>
                {saveState === 'failed' && <span className="profile-save-error" role="alert">Couldn’t save changes. Try again.</span>}
              </div>
            </form>
          </section>
          <section className="profile-access" aria-labelledby="profile-access-heading">
            <h2 id="profile-access-heading">Account access</h2>
            <dl className="profile-facts">
              <div><dt>Username</dt><dd>{profile.username}</dd></div>
              <div><dt>Role</dt><dd>{ROLE_LABEL[profile.role] ?? profile.role}</dd></div>
            </dl>
          </section>
        </> : loadFailed ? <div className="profile-form-actions">
          <span role="alert">Couldn’t load your profile.</span>
          <button type="button" className="secondary-button" onClick={() => {
            setLoadFailed(false);
            setAttempt(previous => previous + 1);
          }}>Try again</button>
        </div> : <p className="profile-loading" role="status">Loading profile…</p>}
      </div>
    </div>
  </PageFrame>;
}
