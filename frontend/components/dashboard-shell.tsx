'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {BrandLogo} from './brand';
import {CaseChat} from './case-chat';
import {ThemeToggle} from './theme';
import {useAuth} from './auth';
import type {Role} from '../lib/api';
import {ROLE_LABEL} from '../lib/workflow';

const groups: {label: string; links: {href: string; label: string; icon: string; roles: Array<Role | 'all'>}[]}[] = [
  {
    label: 'Work',
    links: [
      {href: '/detector', label: 'New analysis', icon: 'analysis', roles: ['all']},
      {href: '/queue', label: 'Workspace', icon: 'workspace', roles: ['all']},
      {href: '/reports', label: 'Reports', icon: 'reports', roles: ['all']},
    ],
  },
  {
    label: 'Oversight',
    links: [
      {href: '/audit', label: 'Audit', icon: 'audit', roles: ['supervisor', 'administrator']},
      {href: '/settings', label: 'Models', icon: 'models', roles: ['all']},
      {href: '/admin/users', label: 'Users', icon: 'users', roles: ['administrator']},
    ],
  },
  {
    label: 'Account',
    links: [
      {href: '/account', label: 'Profile', icon: 'profile', roles: ['all']},
    ],
  },
];

const ICONS: Record<string, string> = {
  analysis: 'M12 5v14M5 12h14',
  workspace: 'M4 5h7v7H4zM13 5h7v4h-7zM13 12h7v7h-7zM4 15h7v4H4z',
  reports: 'M7 3.5h7.5L19 8v12.5H7zM14.5 3.5V8H19',
  audit: 'M5 7h14M5 12h14M5 17h9',
  models: 'M12 3.5l7.5 4.25v8.5L12 20.5l-7.5-4.25v-8.5z',
  users: 'M9 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM16.5 11.5a2.4 2.4 0 1 0 0-4.8 2.4 2.4 0 0 0 0 4.8zM4 19c.7-2.5 2.6-3.8 5-3.8s4.3 1.3 5 3.8M14 15.5c.6-.3 1.4-.5 2.3-.5 1.7 0 3.1.8 3.7 2.5',
  profile: 'M12 12a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM5.5 19.5c.8-2.8 3-4.2 6.5-4.2s5.7 1.4 6.5 4.2',
};

function visible(role: Role | null, allowed: Array<Role | 'all'>) {
  if (allowed.includes('all')) return true;
  if (!role) return false;
  if ((role === 'analyst' || role === 'investigator') && allowed.includes('investigator')) return true;
  return allowed.includes(role);
}

function highlighted(path: string, href: string) {
  if (href === '/queue') return path === href || path.startsWith('/analyses');
  return path === href || path.startsWith(`${href}/`);
}

function sectionFor(path: string) {
  if (path.startsWith('/analyses/') && path.includes('/review')) return 'Report review';
  if (path.startsWith('/analyses/')) return 'Case review';
  if (path.startsWith('/reports')) return 'Reports';
  if (path.startsWith('/detector')) return 'New analysis';
  if (path.startsWith('/queue')) return 'Workspace';
  if (path.startsWith('/audit')) return 'Audit';
  if (path.startsWith('/settings')) return 'Models';
  if (path.startsWith('/admin')) return 'Users';
  if (path.startsWith('/account')) return 'Profile';
  return 'DeepTrace';
}

function initials(role: Role | null) {
  const label = ROLE_LABEL[role ?? ''] ?? 'User';
  const parts = label.split(/\s+/);
  if (parts.length > 1) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return label.slice(0, 2).toUpperCase();
}

export function DashboardShell({children}: {children: React.ReactNode}) {
  const path = usePathname();
  const auth = useAuth();
  const analysisId = path.match(/^\/analyses\/([^/]+)/)?.[1];
  const roleLabel = ROLE_LABEL[auth.role ?? ''] ?? 'Signed in';
  return <div className="dash-shell">
    <header className="dash-top">
      <div className="dash-top-brand"><BrandLogo/><span className="dash-section">{sectionFor(path)}</span></div>
      <div className="dash-top-actions"><ThemeToggle /><button className="dash-signout" onClick={auth.signOut}>Sign out</button></div>
    </header>
    <aside className="dash-side">
      <nav aria-label="Workspace">
        {groups.map(group => {
          const items = group.links.filter(item => visible(auth.role, item.roles));
          if (!items.length) return null;
          return <div key={group.label} className="nav-group">
            <span className="nav-label">{group.label}</span>
            {items.map(item => <Link key={item.href} href={item.href} className={highlighted(path, item.href) ? 'active' : undefined}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[item.icon]}/></svg><span>{item.label}</span></Link>)}
          </div>;
        })}
      </nav>
      <Link className="dash-user" href="/account">
        <span className="dash-avatar">{initials(auth.role)}</span>
        <div><strong>{roleLabel}</strong><small>Profile</small></div>
      </Link>
    </aside>
    <main className="dash-main"><div className="dash-content">{children}</div></main>
    {analysisId && <CaseChat analysisId={analysisId}/>}
  </div>;
}
