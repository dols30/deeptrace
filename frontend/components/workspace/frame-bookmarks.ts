import type {CaseComment} from '../../lib/workflow';

export const BOOKMARK_BODY = 'Bookmarked frame for review.';

export type FrameBookmark = {
  id: string;
  time: number;
  image: string | null;
};

const storeKey = (id: string) => `deeptrace.frame-bookmarks.${id}`;
const hiddenKey = (id: string) => `deeptrace.frame-bookmarks.hidden.${id}`;

function readJson(key: string): unknown {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function readStored(analysisId: string): FrameBookmark[] {
  const parsed = readJson(storeKey(analysisId));
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap(item => {
    if (!item || typeof item !== 'object') return [];
    const record = item as {id?: unknown; time?: unknown; image?: unknown};
    if (typeof record.id !== 'string' || typeof record.time !== 'number') return [];
    return [{id: record.id, time: record.time, image: typeof record.image === 'string' ? record.image : null}];
  });
}

function readHidden(analysisId: string): string[] {
  const parsed = readJson(hiddenKey(analysisId));
  if (!Array.isArray(parsed)) return [];
  return parsed.filter((item): item is string => typeof item === 'string');
}

export function captureFrame(node: HTMLVideoElement | HTMLAudioElement | null): string | null {
  if (!(node instanceof HTMLVideoElement)) return null;
  const video = node;
  if (!video.videoWidth || !video.videoHeight) return null;
  const canvas = document.createElement('canvas');
  const width = Math.min(video.videoWidth, 640);
  const height = Math.max(1, Math.round(video.videoHeight * (width / video.videoWidth)));
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d');
  if (!context) return null;
  context.drawImage(video, 0, 0, width, height);
  try {
    return canvas.toDataURL('image/jpeg', 0.72);
  } catch {
    return null;
  }
}

export function rememberBookmark(analysisId: string, bookmark: FrameBookmark) {
  const next = readStored(analysisId).filter(item => item.id !== bookmark.id);
  next.push(bookmark);
  window.localStorage.setItem(storeKey(analysisId), JSON.stringify(next));
  const hidden = readHidden(analysisId).filter(item => item !== bookmark.id);
  window.localStorage.setItem(hiddenKey(analysisId), JSON.stringify(hidden));
}

export function forgetBookmark(analysisId: string, bookmarkId: string) {
  const next = readStored(analysisId).filter(item => item.id !== bookmarkId);
  window.localStorage.setItem(storeKey(analysisId), JSON.stringify(next));
  const hidden = readHidden(analysisId);
  if (!hidden.includes(bookmarkId)) hidden.push(bookmarkId);
  window.localStorage.setItem(hiddenKey(analysisId), JSON.stringify(hidden));
}

export function bookmarksFor(analysisId: string, comments: CaseComment[]): FrameBookmark[] {
  const stored = readStored(analysisId);
  const hidden = new Set(readHidden(analysisId));
  const images = new Map(stored.map(item => [item.id, item.image]));
  const fromComments = comments.flatMap(item => {
    if (hidden.has(item.id) || !item.body.startsWith('Bookmarked frame') || item.timestamp_seconds == null) return [];
    return [{id: item.id, time: item.timestamp_seconds, image: images.get(item.id) ?? null}];
  });
  const seen = new Set(fromComments.map(item => item.id));
  const extras = stored.filter(item => !seen.has(item.id) && !hidden.has(item.id));
  return [...fromComments, ...extras].sort((a, b) => a.time - b.time);
}
