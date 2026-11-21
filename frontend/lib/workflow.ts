import {API_BASE, type DetectorCoverage, type ReviewCheck} from './api';

export const LIMITATION = 'DeepTrace provides automated screening assistance. Model outputs and attribution visualizations are advisory and require qualified human interpretation.';

export const ROLE_LABEL: Record<string, string> = {
  analyst: 'Analyst',
  investigator: 'Investigator',
  forensic_reviewer: 'Forensic reviewer',
  supervisor: 'Supervisor',
  administrator: 'Administrator',
};

export const STATUS_LABEL: Record<string, string> = {
  UPLOADED: 'Uploaded',
  PROCESSING: 'Processing',
  AI_SCREENING_COMPLETE: 'Screening complete',
  INVESTIGATOR_REVIEW: 'Investigator review',
  EXPERT_REVIEW_REQUESTED: 'Expert review requested',
  SUPERVISOR_REVIEW: 'Supervisor review',
  CHANGES_REQUESTED: 'Changes requested',
  FINALIZED: 'Finalized',
};

export type Disposition = 'agree'|'disagree'|'uncertain'|'needs_expert_review';

export interface AnalysisSummary {
  id: string;
  title: string;
  status: string;
  owner: string;
  media_kind: 'audio'|'video'|string;
  created_at: string;
  finding_count: number;
  legacy_report_id: string | null;
}

export interface Finding {
  id: string;
  modality: 'audio'|'video';
  start_time: number;
  end_time: number | null;
  model_name: string;
  model_version: string;
  preprocessing_version: string;
  raw_logits: number[] | null;
  raw_score: number;
  normalized_score: number | null;
  calibrated_probability: number | null;
  threshold: number;
  predicted_class: string;
  attribution_method: string | null;
  score_scope: string;
  human_disposition: string | null;
  attribution: {method: string; available: boolean; summary: string; metadata: Record<string, unknown>} | null;
  reviews: {id: string; actor_id: string; previous_value: string | null; new_value: string; comment: string; created_at: string}[];
}

export interface AnalysisDetail extends AnalysisSummary {
  media: {filename: string; media_kind: 'audio'|'video'; content_type: string; size_bytes: number; sha256: string; duration_seconds: number | null; container: string | null};
  model_runs: {id: string; modality: string; model_name: string; model_version: string; status: string; threshold: number; raw_score: number | null; calibrated_probability: number | null; calibration_version: string | null; preprocessing_version: string; notes: string[]; development_mock: boolean; coverage?:DetectorCoverage|null; coverage_limited?:boolean}[];
  findings: Finding[];
  comments: CaseComment[];
  limitation: string;
  development_mock: boolean;
  review_checks?:ReviewCheck[];
}

export interface CaseComment {
  id: string;
  author: string;
  author_role: string;
  body: string;
  finding_id: string | null;
  parent_id: string | null;
  timestamp_seconds: number | null;
  mentions: string[];
  resolved: boolean;
  created_at: string;
}

export interface ReportSection {text: string; origin: 'ai'|'human'}
export interface CaseReport {
  id: string;
  analysis_id: string;
  status: string;
  ai_original: Record<string, ReportSection>;
  current: Record<string, ReportSection>;
  revisions: {id: string; author: string; kind: string; created_at: string}[];
}

export interface DashboardData {
  awaiting_my_review: AnalysisSummary[];
  expert_review_requested: AnalysisSummary[];
  reports_awaiting_approval: AnalysisSummary[];
  recently_completed: AnalysisSummary[];
}

export const REPORT_SECTIONS: {key: string; label: string}[] = [
  ['analysis_information', 'Analysis Information'],
  ['media_information', 'Media Information'],
  ['models_used', 'Models Used'],
  ['automated_screening_results', 'Automated Screening Results'],
  ['audio_findings', 'Audio Findings'],
  ['video_findings', 'Video Findings'],
  ['investigator_assessment', 'Investigator Assessment'],
  ['items_requiring_additional_review', 'Items Requiring Additional Review'],
  ['limitations', 'Limitations'],
  ['reviewer_notes', 'Reviewer Notes'],
].map(([key, label]) => ({key, label}));

export function clock(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '—';
  const minutes = Math.floor(Math.max(value, 0) / 60);
  const seconds = Math.max(value, 0) % 60;
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`;
}

async function send<T>(path: string, token: string | null, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, {...init, headers});
  if (response.status === 401) throw new Error('SESSION_EXPIRED');
  const data = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? String(data.detail) : 'Request failed.';
    throw new Error(detail);
  }
  return data as T;
}

export const getDashboard = (token: string | null) => send<DashboardData>('/v1/dashboard', token);
export const getQueue = (token: string | null) => send<AnalysisSummary[]>('/v1/queue', token);
export const searchAnalyses = (query: string, token: string | null) => send<AnalysisSummary[]>(`/v1/search?q=${encodeURIComponent(query)}`, token);
export const getAnalysis = (id: string, token: string | null) => send<AnalysisDetail>(`/v1/analyses/${id}`, token);
export const getCaseReport = (id: string, token: string | null) => send<CaseReport>(`/v1/analyses/${id}/report`, token);
export const getAudit = (token: string | null) => send<{id: string; actor_id: string; action: string; entity_type: string; entity_id: string; timestamp: string; metadata: Record<string, unknown>}[]>('/v1/audit', token);
export const getModelInfo = (token: string | null) => send<{
  supplementary_methods?: {task:string;model:string;configured:boolean;kind:'detector'|'interval_spotter'}[];
  video_model: string; video_configured: boolean; audio_model: string; audio_configured: boolean;
  scene_model?: string; scene_configured?: boolean;
  decision_threshold: number; calibration_version: string | null; preprocessing: Record<string, string>; limitation: string; note: string;
  face_decision_rule?: string; face_decision_threshold?: number;
}>('/v1/settings/models', token);

export async function getAnalysisMedia(id: string, token: string | null) {
  const response = await fetch(`${API_BASE}/v1/analyses/${id}/media`, {headers: token ? {Authorization: `Bearer ${token}`} : {}});
  if (response.status === 401) throw new Error('SESSION_EXPIRED');
  if (!response.ok) throw new Error('Could not load media.');
  return response.blob();
}

export function reviewFinding(id: string, findingId: string, disposition: Disposition, comment: string, token: string | null) {
  return send<Finding>(`/v1/analyses/${id}/findings/${findingId}/reviews`, token, {method: 'POST', body: JSON.stringify({disposition, comment})});
}

export function addCaseComment(id: string, body: {body: string; finding_id?: string | null; parent_id?: string | null; timestamp_seconds?: number | null}, token: string | null) {
  return send<CaseComment>(`/v1/analyses/${id}/comments`, token, {method: 'POST', body: JSON.stringify(body)});
}

export function resolveCaseComment(id: string, commentId: string, token: string | null) {
  return send<CaseComment>(`/v1/analyses/${id}/comments/${commentId}/resolve`, token, {method: 'POST'});
}

export function saveCaseReport(id: string, sections: Record<string, ReportSection>, token: string | null) {
  return send<CaseReport>(`/v1/analyses/${id}/report`, token, {method: 'PUT', body: JSON.stringify({sections})});
}

export function reportDiff(id: string, token: string | null) {
  return send<{section: string; label: string; ai_text: string; current_text: string; changed: boolean; current_origin: 'ai'|'human'}[]>(`/v1/analyses/${id}/report/diff`, token);
}

export function restoreRevision(id: string, revisionId: string, token: string | null) {
  return send<CaseReport>(`/v1/analyses/${id}/report/restore`, token, {method: 'POST', body: JSON.stringify({revision_id: revisionId})});
}

export const submitCaseReport = (id: string, token: string | null) => send<AnalysisDetail>(`/v1/analyses/${id}/report/submit`, token, {method: 'POST'});
export function requestChanges(id: string, body: string, token: string | null) {
  return send<AnalysisDetail>(`/v1/analyses/${id}/report/request-changes`, token, {method: 'POST', body: JSON.stringify({body})});
}
export const finalizeCaseReport = (id: string, token: string | null) => send<AnalysisDetail>(`/v1/analyses/${id}/report/finalize`, token, {method: 'POST'});

export function askAssistant(id: string, question: string, token: string | null, history: {role: 'user'|'assistant'; text: string}[] = []) {
  return send<{answer: string; citations: {finding_id: string; start_time?: number}[]; advisory_only: boolean; provider: string}>(`/v1/analyses/${id}/assistant`, token, {method: 'POST', body: JSON.stringify({question, history})});
}

export const listUsers = (token: string | null) => send<{username: string; display_name: string; role: string; active: boolean}[]>('/v1/users', token);
export function createUser(user: {username: string; password: string; role: string; display_name: string}, token: string | null) {
  return send<{username: string; display_name: string; role: string; active: boolean}>('/v1/users', token, {method: 'POST', body: JSON.stringify(user)});
}
