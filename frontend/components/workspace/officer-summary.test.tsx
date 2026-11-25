import {afterEach, expect, it, vi} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import type {AnalysisDetail} from '../../lib/workflow';
import {OfficerSummary, TechnicalResults} from './officer-summary';

function analysis(): AnalysisDetail {
  return {
    id: 'case-1', title: 'clip.mp4', status: 'AI_SCREENING_COMPLETE', owner: 'officer',
    media_kind: 'video', created_at: '', finding_count: 0, legacy_report_id: null,
    media: {filename: 'clip.mp4', media_kind: 'video', content_type: 'video/mp4', size_bytes: 1, sha256: 'abc', duration_seconds: 60, container: 'mp4'},
    model_runs: [{id: 'run-1', modality: 'video', model_name: 'Community Forensics', model_version: 'test', status: 'functional', threshold: .5, raw_score: .27, calibrated_probability: null, calibration_version: null, preprocessing_version: 'test', notes: [], development_mock: false}],
    findings: [], comments: [], limitation: 'Advisory only.', development_mock: false,
  };
}

afterEach(cleanup);

it('never describes an unflagged result as proof of authenticity', () => {
  render(<OfficerSummary analysis={analysis()}/>);
  expect(screen.getByRole('heading', {name: 'No signs of manipulation flagged'})).toBeTruthy();
  expect(screen.getByText(/Manipulation may still be present/)).toBeTruthy();
  expect(screen.getByText(/Authenticity has not been established/)).toBeTruthy();
  expect(screen.queryByText('0.27')).toBeNull();
});

it('keeps a flagged frame visible when the detector average is below its rule', () => {
  const data = analysis();
  data.findings = [{model_name: 'Community Forensics', modality: 'video'} as AnalysisDetail['findings'][number]];
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'Signs of possible manipulation flagged'})).toBeTruthy();
  expect(screen.getByText('Flagged for review')).toBeTruthy();
});

it.each(['error', 'unavailable', 'stub'])('labels %s runs incomplete instead of clear', status => {
  const data = analysis();
  data.model_runs[0].status = status;
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'Screening incomplete'})).toBeTruthy();
  expect(screen.getByText('No usable result')).toBeTruthy();
});

it('treats missing records and missing scores as incomplete', () => {
  const data = analysis();
  data.model_runs[0].raw_score = null;
  const view = render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'Screening incomplete'})).toBeTruthy();
  view.rerender(<OfficerSummary analysis={{...data, model_runs: []}}/>);
  expect(screen.getByRole('heading', {name: 'Screening incomplete'})).toBeTruthy();
});

it('shows the speech coverage gap and any failures alongside flagged results', () => {
  const data = analysis();
  data.model_runs.push({...data.model_runs[0], id: 'audio', modality: 'audio', model_name: 'AASIST', raw_score: .62});
  data.model_runs[0].status = 'error';
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'Signs of possible manipulation flagged'})).toBeTruthy();
  expect(screen.getByText(/Only the opening 4.04 seconds/)).toBeTruthy();
  expect(screen.getByText(/Later audio was not checked/)).toBeTruthy();
  expect(screen.getByText(/Some checks did not return a usable result/)).toBeTruthy();
});

it('distinguishes development mocks from actual screening results', () => {
  const data = analysis();
  data.development_mock = true;
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'Demonstration results only'})).toBeTruthy();
  expect(screen.queryByText('Nothing flagged in checked material')).toBeNull();
});

it('does not treat an inapplicable check as a failed check', () => {
  const data = analysis();
  data.model_runs.push({...data.model_runs[0], id: 'audio', modality: 'audio', model_name: 'AASIST', status: 'not_applicable', raw_score: null});
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading', {name: 'No signs of manipulation flagged'})).toBeTruthy();
  expect(screen.getByText('Not applicable to this recording')).toBeTruthy();
});

it('shows each flagged window without scores and opens the selected finding', () => {
  const data = analysis();
  data.findings = [0, 1].map(index => ({id: `finding-${index}`, model_name: 'Community Forensics', modality: 'video', start_time: index, end_time: index + 1}) as AnalysisDetail['findings'][number]);
  const onReview = vi.fn();
  render(<OfficerSummary analysis={data} onReviewFinding={onReview}/>);
  expect(screen.getByText(/The whole-image check flagged sampled images/)).toBeTruthy();
  const button = screen.getByRole('button', {name: 'Finding 2, AI-generated video at 00:01.0'});
  fireEvent.click(button);
  expect(onReview).toHaveBeenCalledWith(data.findings[1]);
  expect(screen.queryByText('0.27')).toBeNull();
});

it('does not invent a timestamp when only a file-level detector score is available', () => {
  const data = analysis();
  data.model_runs[0].raw_score = .7;
  render(<OfficerSummary analysis={data} onReviewFinding={vi.fn()}/>);
  expect(screen.getByText(/without returning a specific timestamp/)).toBeTruthy();
  expect(screen.queryByRole('button', {name: /^Review/})).toBeNull();
});

it('keeps file provenance and model output in the technical view', () => {
  render(<TechnicalResults analysis={analysis()}/>);
  expect(screen.getByRole('heading', {name: 'Media metadata'})).toBeTruthy();
  expect(screen.getByText('clip.mp4')).toBeTruthy();
  expect(screen.getByText('video/mp4')).toBeTruthy();
  expect(screen.getByText('SHA-256')).toBeTruthy();
  expect(screen.getByText('0.27')).toBeTruthy();
  expect(screen.getByText('Thresholds shown here are development rules.')).toBeTruthy();
});

it('uses recorded full-window coverage instead of the legacy four-second notice',()=>{
  const data=analysis();
  data.model_runs.push({...data.model_runs[0],id:'audio',modality:'audio',model_name:'AASIST',coverage:{mode:'full',analyzed_seconds:60,duration_seconds:60,windows:15,complete:true}});
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByText(/60.00 of 60.00 seconds screened/)).toBeTruthy();
  expect(screen.queryByText(/Later audio was not checked/)).toBeNull();
});

// These same persisted-result fixtures exercise the notebook's Python mirror.
import bannerCases from '../../../backend/tests/fixtures/tool_workspace_v2_cases.json';
for (const entry of bannerCases) {
  it(`Kaggle banner parity: ${entry.name}`, () => {
    render(<OfficerSummary analysis={entry.analysis as unknown as AnalysisDetail}/>);
    expect(screen.getByRole('heading', {name: entry.expected.title})).toBeTruthy();
  });
}


it('shows measured face coverage and keeps an unflagged partial check incomplete',()=>{
  const data=analysis();
  data.model_runs[0].model_name='DeepfakeBench EfficientNet-B4';
  data.model_runs[0].coverage={mode:'face_alignment_v1',frames_sampled:8,frames_with_detected_face:3,frames_without_detected_face:5,frames_with_unalignable_face:1,frames_scored:2,complete:false};
  const view=render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading',{name:'Screening incomplete'})).toBeTruthy();
  expect(screen.getByText('Limited coverage')).toBeTruthy();
  expect(screen.getByText(/2 of 8 sampled frames scored; 5 with no detected face; 1 with a detected face/)).toBeTruthy();
  data.model_runs[0].raw_score=.9;
  view.rerender(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading',{name:'Signs of possible manipulation flagged'})).toBeTruthy();
  expect(screen.getByText(/Some checks did not return a usable result or have limited coverage/)).toBeTruthy();
});

it('retains zero-face coverage on unavailable results without declaring them inapplicable',()=>{
  const data=analysis();
  data.model_runs[0].status='unavailable';
  data.model_runs[0].raw_score=null;
  data.model_runs[0].coverage={mode:'face_alignment_v1',frames_sampled:8,frames_with_detected_face:0,frames_without_detected_face:8,frames_with_unalignable_face:0,frames_scored:0,complete:false};
  render(<OfficerSummary analysis={data}/>);
  expect(screen.getByRole('heading',{name:'Screening incomplete'})).toBeTruthy();
  expect(screen.getByText(/0 of 8 sampled frames scored/)).toBeTruthy();
  expect(screen.queryByText('Not applicable to this recording')).toBeNull();
});
