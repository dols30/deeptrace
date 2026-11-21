'use client';
import Link from 'next/link';
import {Screening} from '../../components/screening';
import {useAuth} from '../../components/auth';
import {DashboardShell} from '../../components/dashboard-shell';
import {PageFrame} from '../../components/page-frame';
export default function DetectorPage(){const auth=useAuth();if(!auth.ready)return <main className="route-gate">Loading…</main>;if(!auth.token)return <main className="route-gate"><h1>Sign in</h1><Link className="primary-link" href="/signin/">Continue →</Link></main>;return <DashboardShell><PageFrame><Screening/></PageFrame></DashboardShell>}
