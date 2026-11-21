'use client';
import {createContext, useContext, useEffect, useRef, useState} from 'react';
import {usePathname, useRouter} from 'next/navigation';
import Link from 'next/link';
import {API_BASE, type AuthConfig, type Role} from '../lib/api';

const TOKEN = 'deeptrace_access_token';
const ROLE = 'deeptrace_role';
const LOCAL_SESSION = 'deeptrace_local_session';
const LOCAL_PAUSED = 'deeptrace_local_login_paused';
const SIGN_IN = '/signin';
const PROTECTED_PATHS=['/detector','/reports','/account','/docs','/dashboard','/analyses','/queue','/audit','/settings','/admin'];
const ROLES: Role[]=['analyst','investigator','forensic_reviewer','supervisor','administrator'];

function roleFromToken(token:string|null):Role|null {
  if(!token)return null;
  try{
    const encoded=token.split('.')[1];
    const normalized=encoded.replace(/-/g,'+').replace(/_/g,'/');
    const payload=JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length/4)*4,'=')));
    return ROLES.includes(payload.role)?payload.role:null;
  }catch{return null;}
}

function localLoginEnabled(config: AuthConfig) {
  return config.enabled && config.local_auto_login === true
    && ['localhost','127.0.0.1','[::1]','::1'].includes(window.location.hostname);
}

function unexpired(token: string|null) {
  if (!token) return false;
  try {
    const part = token.split('.')[1].replace(/-/g,'+').replace(/_/g,'/');
    const payload = JSON.parse(atob(part.padEnd(Math.ceil(part.length/4)*4,'=')));
    return typeof payload.exp === 'number' && payload.exp > Date.now()/1000;
  } catch { return false; }
}

async function localSession() {
  const response = await fetch(`${API_BASE}/v1/auth/local-login`, {method:'POST'});
  const data = await response.json();
  if (!response.ok || typeof data.access_token !== 'string' || !data.access_token || !ROLES.includes(data.role)) {
    throw new Error('Automatic local sign-in failed. Sign in manually or retry.');
  }
  sessionStorage.setItem(TOKEN,data.access_token);
  sessionStorage.setItem(ROLE,data.role);
  sessionStorage.setItem(LOCAL_SESSION,'true');
  return {token:data.access_token as string,role:data.role as Role};
}

async function initialize() {
  const res = await fetch(`${API_BASE}/v1/auth/config`);
  if (!res.ok) throw new Error('Unable to verify sign-in configuration. Please reload.');
  const config: AuthConfig = await res.json();
  let token = sessionStorage.getItem(TOKEN);
  if (localLoginEnabled(config) && !sessionStorage.getItem(LOCAL_PAUSED) && !unexpired(token)) {
    return {config,...await localSession()};
  }
  const savedRole = sessionStorage.getItem(ROLE);
  const role: Role | null = roleFromToken(token) ??
    (ROLES.includes(savedRole as Role)?savedRole as Role:null);
  if(role)sessionStorage.setItem(ROLE,role);
  return {config, token, role};
}

interface AuthState {
  config: AuthConfig;
  token: string | null;
  role: Role | null;
  ready: boolean;
  error: string;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
  expire: () => void;
}

const Context = createContext<AuthState | null>(null);

function isSignInPath(pathname: string) {
  const path = pathname.replace(/\/$/, '');
  return path === '/signin' || path === '/login';
}

export function AuthProvider({children}: {children: React.ReactNode}) {
  const [config, setConfig] = useState<AuthConfig>({enabled: true});
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<Role | null>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<ReturnType<typeof initialize> | null>(null);
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    let active = true;
    pending.current ??= initialize();
    pending.current
      .then((data) => {
        if (active) {
          setConfig(data.config);
          setToken(data.token);
          setRole(data.role);
          setReady(true);
        }
      })
      .catch((e) => {
        if (active) {
          const message = e instanceof TypeError
            ? 'DeepTrace is temporarily unavailable. Try again in a moment.'
            : e.message;
          setError(message);
          setReady(true);
          // Fail closed: an unavailable API must never expose the detector.
          setConfig({enabled: true});
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    const onSignIn = isSignInPath(pathname);
    if (!token && PROTECTED_PATHS.some(path=>pathname===path||pathname.startsWith(`${path}/`))) router.replace(`${SIGN_IN}/`);
    if (config.enabled && token && onSignIn) router.replace(role==='supervisor'?'/reports':'/detector');
  }, [ready, token, role, pathname, router]);

  const expire = () => {
    const renew = localLoginEnabled(config) && sessionStorage.getItem(LOCAL_SESSION) === 'true' && !sessionStorage.getItem(LOCAL_PAUSED);
    sessionStorage.removeItem(TOKEN);
    sessionStorage.removeItem(ROLE);
    setToken(null);
    setRole(null);
    if (renew) {
      setReady(false);
      void localSession().then(data => {setToken(data.token);setRole(data.role);setError('');})
        .catch(() => {setError('Automatic local sign-in failed. Sign in manually or retry.');router.replace(`${SIGN_IN}/`);})
        .finally(() => setReady(true));
    } else router.replace(`${SIGN_IN}/`);
  };

  async function signIn(username: string, password: string) {
    try {
      setError('');
      const response = await fetch(`${API_BASE}/v1/auth/login`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username, password})});
      const data = await response.json();
      if (!response.ok || !data.access_token) throw new Error(data.detail || 'Sign-in failed.');
      sessionStorage.removeItem(LOCAL_SESSION);
      sessionStorage.setItem(LOCAL_PAUSED,'true');
      sessionStorage.setItem(TOKEN, data.access_token);
      sessionStorage.setItem(ROLE, data.role);
      setToken(data.access_token);
      setRole(data.role);
      router.replace(data.role==='supervisor'?'/reports':'/detector');
    } catch (e) {
      setError(e instanceof TypeError
        ? 'DeepTrace is temporarily unavailable. Try again in a moment.'
        : e instanceof Error ? e.message : 'Sign-in failed.');
    }
  }

  const signOut = () => {
    sessionStorage.setItem(LOCAL_PAUSED,'true');
    sessionStorage.removeItem(LOCAL_SESSION);
    sessionStorage.removeItem(TOKEN);
    sessionStorage.removeItem(ROLE);
    setToken(null);
    setRole(null);
    router.replace(`${SIGN_IN}/`);
  };

  return (
    <Context.Provider value={{config, token, role, ready, error, signIn, signOut, expire}}>
      {children}
    </Context.Provider>
  );
}

export function useAuth() {
  const value = useContext(Context);
  if (!value) throw new Error('Missing AuthProvider');
  return value;
}

export function AuthControls() {
  const auth = useAuth();
  const pathname = usePathname();
  if (isSignInPath(pathname)) return null;

  return (
    <div className="auth-controls">
      {auth.token
        ? <button className="text-button" type="button" onClick={auth.signOut}>Sign out</button>
        : <Link className="sign-in-button" href={`${SIGN_IN}/`}>Sign In</Link>}
    </div>
  );
}
