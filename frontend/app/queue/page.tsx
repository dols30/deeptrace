'use client';
import Link from 'next/link';
import {DashboardShell} from '../../components/dashboard-shell';
import {QueueView} from '../../components/workflow-home';
import {useAuth} from '../../components/auth';

export default function QueuePage() {
  const auth = useAuth();
  if (!auth.ready) return <main className="route-gate">Loading…</main>;
  if (!auth.token) return <main className="route-gate"><h1>Sign in</h1><Link className="primary-link" href="/signin/">Continue →</Link></main>;
  return <DashboardShell><QueueView/></DashboardShell>;
}
