export type TourId = 'detector' | 'case' | 'review' | 'supervisor';

export type TourStep = {
  anchor: string;
  action: string;
  meaning: string;
};

export const EMPTY_FINDINGS = 'This file was screened. No automated finding exceeded the decision threshold. That does not establish authenticity.';
export const EMPTY_QUEUE = 'Start a scan to open your first case. It stays here until it is finalized.';

export const TOURS: Record<TourId, TourStep[]> = {
  detector: [
    {
      anchor: 'drop',
      action: 'Drop a file to start.',
      meaning: 'Select or drag audio or video. A person still reviews the result.',
    },
    {
      anchor: 'checks',
      action: 'Three checks run, and none of them decide the case.',
      meaning: 'Face manipulation, generated-video patterns, and speech spoofing are separate scores.',
    },
    {
      anchor: 'open-case',
      action: 'When screening finishes, open the case.',
      meaning: 'Review the recording and findings in the workspace, then prepare your report.',
    },
  ],
  case: [
    {
      anchor: 'media',
      action: 'Play the recording and use the timeline.',
      meaning: 'Findings are marks on the recording, not a conclusion.',
    },
    {
      anchor: 'finding',
      action: 'Review each flagged portion and record your assessment.',
      meaning: 'A flag is a reason to review, not proof of manipulation. Scores and model explanations are in Technical details.',
    },
    {
      anchor: 'disposition',
      action: 'Agree or disagree with the flag, mark it uncertain, or request expert review.',
      meaning: 'Your disposition is the human judgment. It stays on the finding.',
    },
    {
      anchor: 'review-report',
      action: 'Open Review report when the write-up is next.',
      meaning: 'The AI draft stays read-only here. Your words go on the next page.',
    },
  ],
  review: [
    {
      anchor: 'review-evidence',
      action: 'The left side is the recording and findings.',
      meaning: 'Use it while you write. A quiet screen does not mean the file is authentic.',
    },
    {
      anchor: 'review-submit',
      action: 'The right side is your words. The AI draft stays.',
      meaning: 'Submit sends this draft to a supervisor.',
    },
  ],
  supervisor: [
    {
      anchor: 'review-evidence',
      action: 'Read the investigator’s sections against the findings.',
      meaning: 'The recording and the AI draft stay beside the human text.',
    },
    {
      anchor: 'supervisor-actions',
      action: 'Request changes or finalize.',
      meaning: 'Finalized text is no longer edited. A disagreement is a note.',
    },
  ],
};

const STORAGE = 'deeptrace.tour.seen';

export function tourSeenKey(userKey: string, tourId: TourId) {
  return `${STORAGE}.${userKey}.${tourId}`;
}

export function isTourSeen(userKey: string, tourId: TourId) {
  try {
    return localStorage.getItem(tourSeenKey(userKey, tourId)) === 'seen';
  } catch {
    return false;
  }
}

export function markTourSeen(userKey: string, tourId: TourId) {
  localStorage.setItem(tourSeenKey(userKey, tourId), 'seen');
}

export function clearTourSeen(userKey: string, tourId: TourId) {
  localStorage.removeItem(tourSeenKey(userKey, tourId));
}

export function userKeyFromToken(token: string | null) {
  if (!token) return 'local';
  try {
    const encoded = token.split('.')[1];
    if (!encoded) return 'local';
    const normalized = encoded.replace(/-/g, '+').replace(/_/g, '/');
    const payload = JSON.parse(atob(normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '='))) as {sub?: unknown; username?: unknown};
    const sub = payload.sub ?? payload.username;
    return typeof sub === 'string' && sub ? sub : 'local';
  } catch {
    return 'local';
  }
}

export function guideForSurface(role: string | null, surface: 'detector' | 'case' | 'review', status?: string) {
  if (surface === 'detector') return {tourId: 'detector' as const, autoStart: false};
  if (surface === 'case') return {tourId: 'case' as const, autoStart: false};
  if (role === 'supervisor') return {tourId: 'supervisor' as const, autoStart: false};
  return {tourId: 'review' as const, autoStart: false};
}
