'use client';
import {useEffect,useState} from 'react';
import {useParams,useRouter} from 'next/navigation';
import {DashboardShell} from '../../../components/dashboard-shell';
import {ReportView} from '../../../components/report';
import {useAuth} from '../../../components/auth';
import {getReport,type Report} from '../../../lib/api';
export default function SavedReportPage(){const {id}=useParams<{id:string}>();const router=useRouter();const auth=useAuth();const [report,setReport]=useState<Report|null>(null);const [error,setError]=useState('');useEffect(()=>{if(auth.token)getReport(id,auth.token).then(setReport).catch(()=>setError('Report not found.'));},[id,auth.token]);return <DashboardShell>{error?<p className="form-error">{error}</p>:report?<ReportView report={report} onReset={()=>router.push('/detector')}/>:<section className="empty-panel"><h2>Loading</h2></section>}</DashboardShell>}
