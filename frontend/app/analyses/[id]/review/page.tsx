'use client';
import Link from 'next/link';
import {useParams} from 'next/navigation';
import {DashboardShell} from '../../../../components/dashboard-shell';
import {PageFrame} from '../../../../components/page-frame';
import {ReportReview} from '../../../../components/report-review';
import {useAuth} from '../../../../components/auth';

export default function ReportReviewPage() {
  const auth = useAuth();
  const params = useParams<{id: string}>();
  if (!auth.ready) return <main className="route-gate">Loading…</main>;
  if (!auth.token) return <main className="route-gate"><h1>Sign in</h1><Link className="primary-link" href="/signin/">Continue →</Link></main>;
  return <DashboardShell><PageFrame><ReportReview id={params.id}/></PageFrame></DashboardShell>;
}
