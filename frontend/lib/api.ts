export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
export type Role = 'analyst'|'investigator'|'forensic_reviewer'|'supervisor'|'administrator';
export interface AuthConfig { enabled:boolean; mode?:'employee'|'cognito'; domain?:string; client_id?:string; redirect_uri?:string; local_auto_login?:boolean }
export interface AudioCoverage {mode:'first'|'full'; analyzed_seconds:number; duration_seconds:number; windows:number; complete:boolean}
export interface FaceCoverage {
  mode:'face_alignment_v1'; frames_sampled:number; frames_with_detected_face:number;
  frames_without_detected_face:number; frames_with_unalignable_face:number; frames_scored:number; complete:boolean;
}
export type DetectorCoverage = AudioCoverage|FaceCoverage;
export interface ReviewCheck {
  technique:string; title:string; modality:'audio'|'video'; status:'measured'|'unavailable'|'error'|'not_applicable';
  method:string; summary:string; measurements:Record<string,number|string>; intervals:Record<string,unknown>[];
  limitations:string[]; version:string; validated:boolean;
}
export interface ComponentResult {
  component:'audio'|'video'; status:'functional'|'stub'|'not_applicable'|'unavailable'|'error';
  model_name:string; model_version:string; checkpoint?:string|null; synthetic_confidence:number|null;
  anomalies?:{component:'audio'|'video';code:string;description:string;severity:string}[];
  detector_id?:string|null; detector_name?:string|null;
  task?:'face_manipulation'|'synthetic_video'|'audio_spoof'|null;
  raw_score?:number|null; display_score?:number|null; calibrated_probability?:number|null;
  threshold?:number|null; threshold_source?:string|null; threshold_validated?:boolean;
  detector_status?:'score_only'|'not_available'|'error'; aggregation_method?:string|null;
  thresholds?:{review:number|null;flag:number|null};
  threshold_validation?:{validated:boolean;dataset:string|null;target_fpr:number|null};
  operational_status?:string;
  num_samples?:number; limitations?:string[];
  coverage?:DetectorCoverage|null;
  samples?:{start_time:number;end_time?:number|null;raw_score:number;raw_logits?:number[]|null}[];
  timestamps_seconds:number[]; notes:string[];
}
export interface Report {
  report_id:string; generated_at:string; disclaimer:string; summary:string; recommended_action:string;
  examination_scope:string; review_status:string; overall_synthetic_confidence:number|null;
  evidence_summary?:Record<string,unknown>[];
  media:{filename:string;media_kind:string;size_bytes:number;duration_seconds?:number|null;container?:string|null;sha256:string};
  components:ComponentResult[]; anomalies:{code:string;description:string;severity:string;component:string}[];
  integrity:Record<string,string>; methods:string[]; limitations:string[];
  references:{organization:string;title:string;url:string;version:string;application:string}[];
  owner?:string|null; reviewer?:string|null; workflow_status?:'draft'|'submitted'|'in_review'|'reviewed';
  analysis_id?:string|null;
  review_checks?:ReviewCheck[];
  processing?:{status:string; elapsed_seconds:number; media_storage:string; workflow_storage:string; report_storage:string};
}
export interface ReportSummary {
  report_id:string;generated_at:string;filename:string;media_kind:string;
  overall_synthetic_confidence:number|null;owner:string;reviewer:string|null;
  workflow_status:'draft'|'submitted'|'in_review'|'reviewed';
}
export interface Profile {username:string;role:Role;display_name:string;title:string}
export interface ReviewComment {
  comment_id:number;report_id:string;author:string;author_role:Role;body:string;created_at:string;
}
export interface Notebook {report_id:string;author:string;body:string;updated_at:string}
export function formatBytes(bytes:number) {
  if (!bytes) return '0 B';
  const i=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),3);
  return `${(bytes/1024**i).toFixed(i?1:0)} ${['B','KB','MB','GB'][i]}`;
}
export function formatConfidence(value:number|null|undefined) {
  if(value==null)return '—';
  const percent=value*100;
  if(percent>0&&percent<0.1)return '<0.1%';
  return `${percent.toFixed(1)}%`;
}
export const formatModelScore=formatConfidence;
export async function analyze(file:File,token:string|null):Promise<Report> {
  const body=new FormData(); body.append('file',file);
  const response=await fetch(`${API_BASE}/v1/analyze`,{method:'POST',body,headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(response.status===401) throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'The file could not be analyzed.');
  return data;
}
async function authorizedJson<T>(path:string,token:string|null):Promise<T>{
  const response=await fetch(`${API_BASE}${path}`,{headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(response.status===401) throw new Error('SESSION_EXPIRED');
  if(!response.ok) throw new Error('Unable to load saved reports.');
  return response.json();
}
export const listReports=(token:string|null)=>authorizedJson<ReportSummary[]>('/v1/reports',token);
export async function deleteReport(id:string,token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}`,{method:'DELETE',headers:token?{Authorization:`Bearer ${token}`}:{}});
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  if(!response.ok){const data=await response.json().catch(()=>({}));throw new Error(typeof data.detail==='string'?data.detail:'Could not delete report.');}
}
export const getReport=(id:string,token:string|null)=>authorizedJson<Report>(`/v1/reports/${encodeURIComponent(id)}`,token);
export async function submitReport(id:string,token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}/submit`,{
    method:'POST',headers:token?{Authorization:`Bearer ${token}`}:{},
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not send report.');
  return data as {status:'submitted';reviewer:string};
}
async function reportAction(id:string,action:'start'|'complete',token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}/review/${action}`,{
    method:'POST',headers:token?{Authorization:`Bearer ${token}`}:{},
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not update review.');
  return data as {status:'in_review'|'reviewed'};
}
export const startReview=(id:string,token:string|null)=>reportAction(id,'start',token);
export const completeReview=(id:string,token:string|null)=>reportAction(id,'complete',token);
export const listComments=(id:string,token:string|null)=>authorizedJson<ReviewComment[]>(`/v1/reports/${encodeURIComponent(id)}/comments`,token);
export async function addComment(id:string,body:string,token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}/comments`,{
    method:'POST',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},
    body:JSON.stringify({body}),
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not add comment.');
  return data as ReviewComment;
}
export const getNotebook=(id:string,token:string|null)=>authorizedJson<Notebook>(`/v1/reports/${encodeURIComponent(id)}/notebook`,token);
export async function saveNotebook(id:string,body:string,token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}/notebook`,{
    method:'PUT',headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},
    body:JSON.stringify({body}),
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not save notebook.');
  return data as Notebook;
}
export async function getReportMedia(id:string,token:string|null){
  const response=await fetch(`${API_BASE}/v1/reports/${encodeURIComponent(id)}/media`,{
    headers:token?{Authorization:`Bearer ${token}`}:{},
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  if(!response.ok)throw new Error('Could not load media.');
  return response.blob();
}
export const getProfile=(token:string|null)=>authorizedJson<Profile>('/v1/profile',token);
export async function updateProfile(profile:Pick<Profile,'display_name'|'title'>,token:string|null){
  const response=await fetch(`${API_BASE}/v1/profile`,{
    method:'PATCH',
    headers:{'Content-Type':'application/json',...(token?{Authorization:`Bearer ${token}`}:{})},
    body:JSON.stringify(profile),
  });
  if(response.status===401)throw new Error('SESSION_EXPIRED');
  const data=await response.json();
  if(!response.ok)throw new Error(data.detail||'Could not save profile.');
  return data as Profile;
}
