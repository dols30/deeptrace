import Link from 'next/link';
import {GuideButton} from '../guide/guided-tour';
import {clock, STATUS_LABEL} from '../../lib/workflow';
import type {TourId} from '../guide/tour-copy';

const STEPS: {id: string; label: string; statuses: string[]}[] = [
  {id: 'intake', label: 'Intake', statuses: ['UPLOADED', 'PROCESSING']},
  {id: 'screen', label: 'Screening', statuses: ['AI_SCREENING_COMPLETE']},
  {id: 'review', label: 'Investigator', statuses: ['INVESTIGATOR_REVIEW', 'CHANGES_REQUESTED']},
  {id: 'escalate', label: 'Escalation', statuses: ['EXPERT_REVIEW_REQUESTED', 'SUPERVISOR_REVIEW']},
  {id: 'final', label: 'Final', statuses: ['FINALIZED']},
];

export function CaseCommand({
  caseId,
  filename,
  status,
  mediaKind,
  duration,
  tourId,
  userKey,
}: {
  caseId: string;
  filename: string;
  status: string;
  mediaKind: string;
  duration: number;
  tourId: TourId;
  userKey: string;
}) {
  const active = Math.max(0, STEPS.findIndex(step => step.statuses.includes(status)));
  return <header className="case-command">
    <div>
      <span className="micro-label">Case review</span>
      <h1>{filename}</h1>
      <p className="case-meta">
        <span className={`workflow-badge ${status}`}>{STATUS_LABEL[status] ?? status}</span>
        <span>{mediaKind}</span>
        <span>{clock(duration)}</span>
      </p>
    </div>
    <div className="case-actions">
      <GuideButton tourId={tourId} userKey={userKey}/>
      <Link className="primary-button review-button" data-tour="review-report" href={`/analyses/${caseId}/review`}>Review report</Link>
    </div>
    <ol className="case-pipeline" aria-label="Review progress">
      {STEPS.map((step, index) => <li key={step.id} className={index < active ? 'done' : index === active ? 'current' : undefined}>{step.label}</li>)}
    </ol>
  </header>;
}
