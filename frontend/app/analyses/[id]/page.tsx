'use client';
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {AnalysisWorkspace} from '../../../components/analysis-workspace';
import {DashboardShell} from '../../../components/dashboard-shell';
import {useAuth} from '../../../components/auth';

export default function AnalysisPage() {
  const auth = useAuth();
  const params = useParams<{id: string}>();
  if (!auth.ready) return <main className="route-gate">Loading…</main>;
  if (!auth.token) return <main className="route-gate"><h1>Sign in</h1><Link className="primary-link" href="/signin/">Continue →</Link></main>;
  return <DashboardShell><AnalysisWorkspace id={params.id}/></DashboardShell>;
}
