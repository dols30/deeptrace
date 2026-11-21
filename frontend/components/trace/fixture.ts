// Illustrative values shaped like real ComponentResult output. Not from a real file.
export const CLIP_SECONDS = 10;
export const FRAME_INTERVAL = 1;
export const DECISION_RULE = 0.5;
export const AASIST_WINDOW = 4.0375;

export type LaneId = 'synthetic' | 'face' | 'audio';

export type Lane = {
  id: LaneId;
  label: string;
  short: string;
  model: string;
  granularity: string;
  attribution: string;
};

export const LANES: Lane[] = [
  {
    id: 'synthetic',
    label: 'AI-generated video',
    short: 'AI',
    model: 'Community Forensics ViT-S/16',
    granularity: 'One score per sampled frame (centre 384 px crop), averaged across frames.',
    attribution: 'No attribution.',
  },
  {
    id: 'face',
    label: 'Face manipulation',
    short: 'FACE',
    model: 'DeepfakeBench EfficientNet-B4',
    granularity: 'One score per sampled frame on the largest aligned face. Frames without an alignable face abstain.',
    attribution: 'Grad-CAM per flagged frame shows model sensitivity, not a manipulation map.',
  },
  {
    id: 'audio',
    label: 'Audio spoof',
    short: 'AUDIO',
    model: 'AASIST',
    granularity: 'One file-level score from the first 4.04 s of speech. Later audio is not analysed.',
    attribution: 'Temporal occlusion in 500 ms windows, when explanations are enabled.',
  },
];

export const FRAMES = Array.from({length: CLIP_SECONDS / FRAME_INTERVAL}, (_, index) => index * FRAME_INTERVAL);

export const SYNTHETIC_SCORES = [0.21, 0.19, 0.24, 0.33, 0.29, 0.36, 0.31, 0.27, 0.22, 0.25];
export const FACE_SCORES: (number | null)[] = [0.12, 0.18, null, 0.22, 0.31, 0.58, 0.64, 0.41, null, 0.27];
export const AUDIO_SCORE = 0.62;

export function mean(values: (number | null)[]) {
  const scored = values.filter((value): value is number => value != null);
  return scored.length ? scored.reduce((sum, value) => sum + value, 0) / scored.length : null;
}

export const LANE_SCORE: Record<LaneId, number | null> = {
  synthetic: mean(SYNTHETIC_SCORES),
  face: mean(FACE_SCORES),
  audio: AUDIO_SCORE,
};

export type LaneEvent = {lane: LaneId; start: number; end: number; score: number};

export const EVENTS: LaneEvent[] = [
  ...FRAMES.flatMap((start, index) => {
    const score = FACE_SCORES[index];
    return score != null && score >= DECISION_RULE ? [{lane: 'face' as const, start, end: start + FRAME_INTERVAL, score}] : [];
  }),
  ...(AUDIO_SCORE >= DECISION_RULE ? [{lane: 'audio' as const, start: 0, end: AASIST_WINDOW, score: AUDIO_SCORE}] : []),
];

export const WAVEFORM = Array.from({length: 120}, (_, index) => {
  const t = index / 120;
  const speech = Math.abs(Math.sin(t * 37) * 0.55 + Math.sin(t * 91) * 0.3 + Math.sin(t * 13) * 0.15);
  const pause = t > 0.46 && t < 0.52 ? 0.15 : 1;
  return Math.max(0.06, Math.min(1, speech * pause));
});

export function score2(value: number | null) {
  return value == null ? '—' : value.toFixed(2);
}
