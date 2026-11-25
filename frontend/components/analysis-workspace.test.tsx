import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {AnalysisWorkspace} from './analysis-workspace';

const {reviewFinding, getAnalysis, addCaseComment} = vi.hoisted(() => ({reviewFinding: vi.fn(), getAnalysis: vi.fn(), addCaseComment: vi.fn()}));
vi.mock('../lib/workflow', async importOriginal => {
  const actual = await importOriginal<typeof import('../lib/workflow')>();
  return {
    ...actual,
    getAnalysis,
    getCaseReport: vi.fn(async () => ({
      id: 'report-row', analysis_id: 'case-1', status: 'draft',
      ai_original: Object.fromEntries(actual.REPORT_SECTIONS.map(section => [section.key, {text: 'AI draft', origin: 'ai'}])),
      current: Object.fromEntries(actual.REPORT_SECTIONS.map(section => [section.key, {text: section.key === 'investigator_assessment' ? '' : 'AI draft', origin: section.key === 'investigator_assessment' ? 'human' : 'ai'}])),
      revisions: [],
    })),
    getAnalysisMedia: vi.fn(async () => new Blob(['audio'])),
    reviewFinding,
    addCaseComment,
  };
});
vi.mock('./auth', () => ({useAuth: () => ({token: 'token', role: 'analyst', expire: vi.fn()})}));

URL.createObjectURL = vi.fn(() => 'blob:audio');
URL.revokeObjectURL = vi.fn();
const CROP = '/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////2wBDAf//////////////////////////////////////////////////////////////////////////////////////wAARCAABAAEDASIAAhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAb/xAAUEAEAAAAAAAAAAAAAAAAAAAAA/8QAFQEBAQAAAAAAAAAAAAAAAAAAAAX/xAAUEQEAAAAAAAAAAAAAAAAAAAAA/9oADAMBAAIRAxEAPwCdABmX/9k=';

function audioAnalysis() {
  return {
    id: 'case-1', title: 'clip.wav', status: 'AI_SCREENING_COMPLETE', owner: 'dps.employee',
    media_kind: 'audio', created_at: '2026-09-30T00:00:00Z', finding_count: 1, legacy_report_id: 'report-1',
    limitation: 'DeepTrace provides automated screening assistance. Model outputs and attribution visualizations are advisory and require qualified human interpretation.',
    development_mock: false,
    media: {filename: 'clip.wav', media_kind: 'audio', content_type: 'audio/wav', size_bytes: 10, sha256: 'ab'.repeat(32), duration_seconds: 2, container: 'wav'},
    model_runs: [],
    findings: [{
      id: 'finding-1', modality: 'audio', start_time: 1.2, end_time: 2.4, model_name: 'AASIST', model_version: 'test',
      preprocessing_version: 'pcm-16k-mono', raw_logits: null, raw_score: 0.81, normalized_score: null,
      calibrated_probability: null, threshold: 0.5, predicted_class: 'possible_manipulation', attribution_method: 'AASIST relevance',
      score_scope: 'file', human_disposition: null, attribution: {method: 'AASIST relevance', available: false, summary: 'No map was produced.', metadata: {}}, reviews: [],
    }],
    comments: [],
  };
}

afterEach(() => { cleanup(); vi.clearAllMocks(); localStorage.clear(); });

it('shows advisory findings and records an investigator disposition', async () => {
  getAnalysis.mockResolvedValue(audioAnalysis());
  reviewFinding.mockResolvedValue({
    id: 'finding-1', modality: 'audio', start_time: 1.2, end_time: 2.4, model_name: 'AASIST', model_version: 'test',
    preprocessing_version: 'pcm', raw_logits: null, raw_score: 0.81, normalized_score: null, calibrated_probability: null,
    threshold: 0.5, predicted_class: 'possible_manipulation', attribution_method: null, score_scope: 'file',
    human_disposition: 'uncertain', attribution: null, reviews: [],
  });
  render(<AnalysisWorkspace id="case-1"/>);
  expect(await screen.findByText('Possible audio manipulation signal')).toBeTruthy();
  const viewer = screen.getByRole('region', {name: 'Media viewer'});
  const timeline = screen.getByRole('region', {name: 'Evidence timeline'});
  const media = viewer.querySelector('video, audio');
  expect(viewer.contains(timeline)).toBe(true);
  expect(media).toBeTruthy();
  expect(media && (media.compareDocumentPosition(timeline) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
  expect(screen.queryByText('Model screening score')).toBeNull();
  expect(screen.queryByText('Decision threshold')).toBeNull();
  expect(screen.queryByText('Attribution off')).toBeNull();
  expect(screen.queryByRole('region', {name: 'AI-generated report'})).toBeNull();
  expect(screen.getByText(/Authenticity has not been established/)).toBeTruthy();
  expect(screen.queryByText(/deepfake confirmed/i)).toBeNull();
  expect(screen.getByRole('link', {name: 'Review report'}).getAttribute('href')).toBe('/analyses/case-1/review');
  fireEvent.click(screen.getByRole('button', {name: 'Review Synthetic speech at 00:01.2'}));
  expect((media as HTMLMediaElement).currentTime).toBeCloseTo(1.2);
  expect(screen.getByRole('tab', {name: 'Officer summary'}).getAttribute('aria-selected')).toBe('true');
  fireEvent.click(screen.getByRole('radio', {name: 'Uncertain'}));
  expect(reviewFinding).toHaveBeenCalledWith('case-1', 'finding-1', 'uncertain', '', 'token');
});

it('shows the face crop beside Grad-CAM and steps to the next explained frame', async () => {
  getAnalysis.mockResolvedValue({
    ...audioAnalysis(),
    title: 'clip.mp4',
    media_kind: 'video',
    media: {filename: 'clip.mp4', media_kind: 'video', content_type: 'video/mp4', size_bytes: 10, sha256: 'cd'.repeat(32), duration_seconds: 4, container: 'mp4'},
    model_runs: [{id: 'run-1', modality: 'video', model_name: 'DeepfakeBench EfficientNet-B4', model_version: 'efficientnetb4@test', status: 'functional', threshold: 0.5, raw_score: 0.77, calibrated_probability: null, calibration_version: null, preprocessing_version: 'jpeg', notes: [], development_mock: false}],
    findings: [0, 1].map(index => ({
      id: `finding-${index}`, modality: 'video' as const, start_time: index, end_time: index + 1,
      model_name: 'DeepfakeBench EfficientNet-B4', model_version: 'efficientnetb4@test',
      preprocessing_version: 'jpeg', raw_logits: [0.1, 1.2], raw_score: 0.81, normalized_score: null,
      calibrated_probability: null, threshold: 0.5, predicted_class: 'possible_manipulation', attribution_method: 'gradcam',
      score_scope: 'sample', human_disposition: null, reviews: [],
      attribution: {
        method: 'gradcam', available: true,
        summary: 'Highlighted areas had greater influence on this model output.',
        metadata: {heatmap: [[index === 0 ? 1 : 0, 0], [0, index === 1 ? 1 : 0]], crop_jpeg_base64: CROP},
      },
    })),
  });
  render(<AnalysisWorkspace id="case-1"/>);
  await screen.findByRole('tab', {name: 'Technical details'});
  fireEvent.click(screen.getByRole('tab', {name: 'Technical details'}));
  expect(screen.getByText('Highlighted areas had greater influence on this model output.')).toBeTruthy();
  expect(screen.getByRole('img', {name: 'Analyzed face crop'})).toBeTruthy();
  expect(screen.getByRole('img', {name: 'Face crop with model attribution'})).toBeTruthy();
  expect(screen.getByText('gradcam')).toBeTruthy();
  expect(screen.getAllByText('0.77').length).toBeGreaterThan(0);
  expect(screen.queryByText(/proves the video is fake/i)).toBeNull();
  fireEvent.click(screen.getByRole('button', {name: 'Next explained frame'}));
  expect(screen.getByRole('button', {name: /Finding 2/})).toHaveProperty('className', expect.stringContaining('selected'));
});

it('shows signed temporal occlusion and keeps the other audio views secondary', async () => {
  getAnalysis.mockResolvedValue({
    ...audioAnalysis(),
    model_runs: [{id: 'run-a', modality: 'audio', model_name: 'AASIST', model_version: 'aasist@test', status: 'functional', threshold: 0.5, raw_score: 0.81, calibrated_probability: null, calibration_version: null, preprocessing_version: 'pcm-16k-mono', notes: [], development_mock: false}],
    findings: [{
      ...audioAnalysis().findings[0],
      attribution_method: 'temporal_occlusion',
      attribution: {
        method: 'temporal_occlusion', available: true,
        summary: 'Masking a listed segment changed the model screening score by the stored score_delta.',
        metadata: {
          displayed_fill: 'local_mean', fill_rankings_agree: false, repeat_padded: true,
          windows: [
            {start: 0, end: 0.5, score_delta: 0.02, fill: 'local_mean'},
            {start: 0.5, end: 1, score_delta: 0.17, fill: 'local_mean'},
          ],
          integrated_gradients: {occlusion_comparison: [{top_sets_match: false}]},
          attention: {maps: [{name: 'GAT_layer_T', role: 'Encoder time nodes before GraphPool.'}], pools: [{name: 'pool_T'}]},
        },
      },
    }],
  });
  render(<AnalysisWorkspace id="case-1"/>);
  await screen.findByRole('tab', {name: 'Technical details'});
  fireEvent.click(screen.getByRole('tab', {name: 'Technical details'}));
  expect(screen.getByText(/changed the model screening score by 0.020/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: /0.170/}));
  expect(screen.getByText(/changed the model screening score by 0.170/)).toBeTruthy();
  expect(screen.getByText(/do not rank these windows the same way/)).toBeTruthy();
  expect(screen.getByText('Internal model attention')).toBeTruthy();
  expect(screen.getByText(/secondary experiment/)).toBeTruthy();
  expect(screen.queryByText(/proves the voice/i)).toBeNull();
});

it('bookmarks the current frame under the video', async () => {
  getAnalysis.mockResolvedValue({
    ...audioAnalysis(),
    title: 'clip.mp4',
    media_kind: 'video',
    media: {filename: 'clip.mp4', media_kind: 'video', content_type: 'video/mp4', size_bytes: 10, sha256: 'cd'.repeat(32), duration_seconds: 4, container: 'mp4'},
    findings: [{
      ...audioAnalysis().findings[0],
      id: 'finding-video',
      modality: 'video',
      start_time: 1.2,
      end_time: 1.5,
    }],
  });
  addCaseComment.mockResolvedValue({
    id: 'bookmark-1', author: 'Analyst', author_role: 'analyst', body: 'Bookmarked frame for review.',
    finding_id: 'finding-video', parent_id: null, timestamp_seconds: 0, mentions: [], resolved: false, created_at: '2026-09-30T00:00:00Z',
  });
  render(<AnalysisWorkspace id="case-1"/>);
  expect(await screen.findByRole('region', {name: 'Bookmarked frames'})).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Bookmark frame'}));
  expect(await screen.findByRole('button', {name: 'Open bookmark at 00:00.0'})).toBeTruthy();
  expect(addCaseComment).toHaveBeenCalledWith('case-1', expect.objectContaining({body: 'Bookmarked frame for review.', timestamp_seconds: 0}), 'token');
  const rail = screen.getByRole('region', {name: 'Bookmarked frames'});
  const viewer = screen.getByRole('region', {name: 'Media viewer'});
  const video = viewer.querySelector('video');
  expect(video).toBeTruthy();
  expect(video && (video.compareDocumentPosition(rail) & Node.DOCUMENT_POSITION_FOLLOWING)).toBeTruthy();
});

it('uses the selected video detector’s aggregate score in attribution details', async () => {
  const analysis = audioAnalysis();
  getAnalysis.mockResolvedValue({
    ...analysis,
    media_kind: 'video',
    media: {...analysis.media, media_kind: 'video'},
    model_runs: [
      {id: 'face', modality: 'video', model_name: 'DeepfakeBench EfficientNet-B4', raw_score: 0.77, threshold: .5, notes: []},
      {id: 'scene', modality: 'video', model_name: 'Community Forensics', raw_score: 0.42, threshold: .5, notes: []},
    ],
    findings: [{...analysis.findings[0], modality: 'video', model_name: 'Community Forensics', attribution: {available: true, method: 'test', summary: 'Selected detector attribution', metadata: {}}}],
  });
  render(<AnalysisWorkspace id="case-1"/>);
  await screen.findByRole('tab', {name: 'Technical details'});
  fireEvent.click(screen.getByRole('tab', {name: 'Technical details'}));
  const label = screen.getByText('Video screening score');
  expect(label.parentElement?.textContent).toContain('0.42');
  expect(label.parentElement?.textContent).not.toContain('0.77');
});

it('draws the audio waveform at device resolution and redraws after resize', async () => {
  const {waitFor} = await import('@testing-library/react');
  let width = 1200;
  let resize = () => {};
  const ctx = {setTransform: vi.fn(), clearRect: vi.fn(), fillRect: vi.fn(), fillStyle: ''};
  const rect = vi.spyOn(HTMLCanvasElement.prototype, 'getBoundingClientRect').mockImplementation(() => ({width, height: 72} as DOMRect));
  const drawing = vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(ctx as unknown as CanvasRenderingContext2D);
  vi.stubGlobal('devicePixelRatio', 2);
  vi.stubGlobal('ResizeObserver', class {
    constructor(callback: () => void) { resize = callback; }
    observe() {}
    disconnect() {}
  });
  vi.stubGlobal('AudioContext', class {
    decodeAudioData() { return Promise.resolve({getChannelData: () => new Float32Array([0, .5, -.75, 0])}); }
    close() { return Promise.resolve(); }
  });
  vi.stubGlobal('fetch', vi.fn(async () => ({arrayBuffer: async () => new ArrayBuffer(4)})));
  try {
    getAnalysis.mockResolvedValue(audioAnalysis());
    render(<AnalysisWorkspace id="case-1"/>);
    const canvas = await screen.findByLabelText('Waveform') as HTMLCanvasElement;
    await waitFor(() => expect(canvas.width).toBe(2400));
    expect(canvas.height).toBe(144);
    expect(ctx.setTransform).toHaveBeenCalledWith(2, 0, 0, 2, 0, 0);
    width = 1920;
    resize();
    expect(canvas.width).toBe(3840);
    expect(ctx.clearRect).toHaveBeenLastCalledWith(0, 0, 1920, 72);
  } finally {
    cleanup();
    rect.mockRestore();
    drawing.mockRestore();
    vi.unstubAllGlobals();
  }
});


it('supports keyboard tabs and keeps playback and draft assessments when switching views', async () => {
  getAnalysis.mockResolvedValue(audioAnalysis());
  render(<AnalysisWorkspace id="case-1"/>);
  const summary = await screen.findByRole('tab', {name: 'Officer summary'});
  const technical = screen.getByRole('tab', {name: 'Technical details'});
  const media = screen.getByRole('region', {name: 'Media viewer'}).querySelector('audio');
  fireEvent.change(screen.getByRole('textbox', {name: 'Investigator comment on this finding'}), {target: {value: 'Needs source comparison'}});
  fireEvent.keyDown(summary, {key: 'End'});
  expect(technical.getAttribute('aria-selected')).toBe('true');
  expect(document.activeElement).toBe(technical);
  expect(screen.getByRole('tabpanel', {name: 'Technical details'})).toBeTruthy();
  expect(screen.getAllByText('Decision threshold').length).toBeGreaterThan(0);
  expect(screen.getByRole('region', {name: 'AI-generated report'})).toBeTruthy();
  expect(screen.getByRole('region', {name: 'Media viewer'}).querySelector('audio')).toBe(media);
  fireEvent.keyDown(technical, {key: 'Home'});
  expect(summary.getAttribute('aria-selected')).toBe('true');
  expect(screen.queryByText('Decision threshold')).toBeNull();
  expect(screen.getByRole('textbox', {name: 'Investigator comment on this finding'})).toHaveProperty('value', 'Needs source comparison');
});
