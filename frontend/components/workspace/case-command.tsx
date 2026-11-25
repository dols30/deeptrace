import Link from 'next/link';
import {GuideButton} from '../guide/guided-tour';
import {STATUS_LABEL} from '../../lib/workflow';
import type {TourId} from '../guide/tour-copy';

export function CaseCommand({
  caseId,
  filename,
  status,
  tourId,
  userKey,
}: {
  caseId: string;
  filename: string;
  status: string;
  tourId: TourId;
  userKey: string;
}) {
  return <header className="case-command">
    <div className="case-identity">
      <h1>{filename}</h1>
      <p className="case-meta">
        <span className={`workflow-badge ${status}`}>{status === 'AI_SCREENING_COMPLETE' && <span className="screening-checkmark" aria-hidden="true">✓</span>}{STATUS_LABEL[status] ?? status}</span>
      </p>
    </div>
    <div className="case-actions">
      <GuideButton tourId={tourId} userKey={userKey}/>
      <Link className="primary-button review-button" data-tour="review-report" href={`/analyses/${caseId}/review`}>Review report</Link>
    </div>
  </header>;
}
