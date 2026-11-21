'use client';
import {useState} from 'react';
import Link from 'next/link';
import {useAuth} from '../../components/auth';
import {BrandLogo} from '../../components/brand';

export default function SignInPage() {
  const auth = useAuth();
  const [username,setUsername]=useState('');
  const [password,setPassword]=useState('');
  const [busy,setBusy]=useState(false);

  async function submit(e:React.FormEvent){e.preventDefault();setBusy(true);await auth.signIn(username,password);setBusy(false);}

  return (
    <div className="signin-page">
      <section className="signin-aside">
        <BrandLogo size={34} onDark />
        <div className="signin-aside-copy">
          <h1>Secure media screening.</h1>
          <p>Employee access.</p>
        </div>
        <p className="signin-aside-meta">DeepTrace secure workspace</p>
      </section>

      <main className="signin-main">
        <div className="signin-card">
          <h2>Sign in</h2>
          <p className="signin-lead">
            {!auth.ready
              ? 'Checking availability…'
              : auth.config.enabled
                ? 'Enter your employee credentials.'
                : 'Authentication is not enabled on the API. Enable it before using the detector.'}
          </p>

          {auth.ready && auth.config.enabled && <form className="employee-login" onSubmit={submit}>
            <label>Employee username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required /></label>
            <label>Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required /></label>
            <button className="primary-button" disabled={busy}>{busy?'Signing in…':'Sign in to DeepTrace'}</button>
          </form>}

          {!auth.ready && (
            <button className="primary-button" type="button" disabled>
              Loading…
            </button>
          )}

          {auth.error && <p className="form-error" role="alert">{auth.error}</p>}

          <Link className="signin-back" href="/">← Home</Link>
        </div>
      </main>
    </div>
  );
}
