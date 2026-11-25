import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {cleanup,render,screen,fireEvent,waitFor,within} from '@testing-library/react';
import {Screening} from './screening';
import {ReportView} from './report';
import type {Report} from '../lib/api';
const {analyze,expire,listReports,getReport,submitReport,getReportMedia,listComments,getNotebook,addComment,saveNotebook,startReview,completeReview,authState}=vi.hoisted(()=>({
  analyze:vi.fn(),expire:vi.fn(),listReports:vi.fn(),getReport:vi.fn(),submitReport:vi.fn(),getReportMedia:vi.fn(),listComments:vi.fn(),getNotebook:vi.fn(),addComment:vi.fn(),saveNotebook:vi.fn(),startReview:vi.fn(),completeReview:vi.fn(),
  authState:{ready:true,config:{enabled:false},token:null as string|null,role:null as 'analyst'|'supervisor'|null,error:'',expire:vi.fn()},
}));
const {getModelInfo, askAssistant} = vi.hoisted(() => ({getModelInfo: vi.fn(), askAssistant: vi.fn()}));
vi.mock('../lib/api',async importOriginal=>({...await importOriginal<object>(),analyze,listReports,getReport,submitReport,getReportMedia,listComments,getNotebook,addComment,saveNotebook,startReview,completeReview}));
vi.mock('../lib/workflow', async importOriginal => ({...await importOriginal<object>(), getModelInfo, askAssistant}));
vi.mock('./auth',()=>({useAuth:()=>({...authState,expire})}));
const report:Report={report_id:'test',generated_at:'2026-09-06',disclaimer:'Advisory',summary:'No applicable detector produced a score.',recommended_action:'Review',examination_scope:'Screening',review_status:'Pending',overall_synthetic_confidence:null,media:{filename:'sample.wav',media_kind:'audio',size_bytes:4,sha256:'a'.repeat(64)},components:[{component:'audio',status:'unavailable',model_name:'AASIST',model_version:'unconfigured',synthetic_confidence:null,timestamps_seconds:[],notes:[]}],anomalies:[],integrity:{},methods:[],limitations:[],references:[]};
URL.createObjectURL=vi.fn(()=>'blob:preview');URL.revokeObjectURL=vi.fn();
Element.prototype.scrollIntoView=vi.fn();

it('shows the exact recorded PoC threshold in technical details',()=>{
  render(<ReportView report={{...report,components:[{...report.components[0],component:'video',task:'face_manipulation',status:'functional',raw_score:.8,threshold:.9967585206031799}]}} onReset={()=>{}}/>);
  fireEvent.click(screen.getByRole('radio',{name:'Technical details'}));
  expect(screen.getByText('0.9967585206031799')).toBeTruthy();
});
beforeEach(()=>{
  listComments.mockResolvedValue([]);
  getNotebook.mockResolvedValue({report_id:'test',author:'user',body:'',updated_at:'2026-09-06'});
  getReportMedia.mockResolvedValue(new Blob(['media']));
  getModelInfo.mockRejectedValue(new Error('offline'));
});
afterEach(()=>{cleanup();authState.token=null;authState.role=null;vi.clearAllMocks();});
it('starts clean instead of restoring a previous report',()=>{
  authState.token='token';
  render(<Screening/>);
    expect(screen.getByLabelText('Choose media file')).toBeTruthy();
    expect(screen.getByText('MP4, MOV, AVI, MP3, WAV, M4A')).toBeTruthy();
    expect(screen.queryByText(/Evidence intake|Start a media screening|What gets checked/)).toBeNull();
  expect(screen.queryByText('No applicable detector produced a score.')).toBeNull();
  expect(listReports).not.toHaveBeenCalled();
  expect(getReport).not.toHaveBeenCalled();
});
it('uploads the selected file and shows unavailable results honestly',async()=>{
  analyze.mockResolvedValue(report);render(<Screening/>);
  const file=new File(['audio'],'sample.wav',{type:'audio/wav'});
    fireEvent.change(screen.getByLabelText('Choose media file'),{target:{files:[file]}});
    fireEvent.click(screen.getByRole('button',{name:/Analyze file/}));
  await screen.findByRole('heading',{name:'Unable to assess authenticity'});
  expect(analyze).toHaveBeenCalledWith(file,null);
  expect(screen.getByText('Incomplete')).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'No manipulation detected'})).toBeNull();
});

it('shows the model count during screening and opens the assistant for the completed case', async () => {
  authState.token = 'token';
  getModelInfo.mockResolvedValue({
    video_configured: true,
    audio_configured: true,
    scene_configured: true,
    video_model: 'efficientnetb4',
    audio_model: 'aasist',
    supplementary_methods: [
      {task: 'GAN artifacts', model: 'CNNDetection', configured: true},
      {task: 'Vocoder artifacts', model: 'LFCC-LCNN', configured: true},
      {task: 'Micro-expression intervals', model: 'SOFTNet', configured: true},
    ],
  });
  askAssistant.mockResolvedValue({answer: 'Review the results in context.', citations: []});
  let finish!: (result: Report) => void;
  analyze.mockReturnValue(new Promise<Report>(resolve => { finish = resolve; }));
  render(<Screening />);
  const file = new File(['audio'], 'sample.wav', {type: 'audio/wav'});
  fireEvent.change(screen.getByLabelText('Choose media file'), {target: {files: [file]}});
  fireEvent.click(screen.getByRole('button', {name: 'Analyze file'}));

  const models = within(await screen.findByRole('list', {name: 'Configured models'}));
  for (const name of ['EfficientNet-B4', 'Community Forensics', 'AASIST', 'CNNDetection', 'LFCC-LCNN', 'SOFTNet']) {
    expect(models.getByText(name)).toBeTruthy();
  }
  expect(models.getAllByText('Video only')).toHaveLength(4);
  expect(screen.queryByRole('button', {name: 'Open case assistant'})).toBeNull();

  finish({...report, analysis_id: 'case-123'});
  fireEvent.click(await screen.findByRole('button', {name: 'Open case assistant'}));
  fireEvent.click(screen.getByRole('button', {name: 'Summarize the findings'}));
  expect(await screen.findByText('Review the results in context.')).toBeTruthy();
  expect(askAssistant).toHaveBeenCalledWith('case-123', 'Summarize the findings', 'token', []);
  expect(screen.queryByRole('list', {name: 'Configured models'})).toBeNull();

  fireEvent.click(screen.getByRole('button', {name: 'New screening'}));
  expect(screen.queryByRole('button', {name: /case assistant/i})).toBeNull();
});
it('rejects oversized uploads before calling the API',()=>{
  render(<Screening/>);const file=new File(['a'],'large.wav',{type:'audio/wav'});Object.defineProperty(file,'size',{value:101*1024*1024});
    fireEvent.change(screen.getByLabelText('Choose media file'),{target:{files:[file]}});
    fireEvent.click(screen.getByRole('button',{name:/Analyze file/}));
  expect(screen.getByRole('alert').textContent).toContain('100 MB');expect(analyze).not.toHaveBeenCalled();
});
it('expires the session on unauthorized analysis',async()=>{
  analyze.mockRejectedValue(new Error('SESSION_EXPIRED'));render(<Screening/>);
    fireEvent.change(screen.getByLabelText('Choose media file'),{target:{files:[new File(['a'],'x.wav',{type:'audio/wav'})]}});
    fireEvent.click(screen.getByRole('button',{name:/Analyze file/}));await waitFor(()=>expect(expire).toHaveBeenCalled());
});
it('renders model output as text rather than HTML',()=>{
  render(<ReportView report={{...report,summary:'<img src=x onerror=alert(1)>'}} onReset={()=>{}}/>);
  fireEvent.click(screen.getByRole('radio',{name:'Technical details'}));
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeTruthy();expect(document.querySelector('.report img')).toBeNull();
});
it('shows detector model scores without a composite confidence',()=>{
  render(<ReportView report={{...report,overall_synthetic_confidence:.1734,components:[{...report.components[0],status:'functional',synthetic_confidence:.346697}]}} onReset={()=>{}}/>);
  expect(screen.queryByText('17.3%')).toBeNull();
  fireEvent.click(screen.getByRole('radio',{name:'Technical details'}));
  expect(screen.getByText('0.347')).toBeTruthy();
  expect(screen.getByText(/No cross-detector average/)).toBeTruthy();
});
it('defaults to a plain-language overview and lets technical users switch detail levels',()=>{
  const signal={component:'audio' as const,code:'ELEVATED_SPOOF_SCORE',description:'Technical description',severity:'medium'};
  render(<ReportView report={{...report,components:[{...report.components[0],status:'functional',raw_score:.62,anomalies:[signal]}],anomalies:[signal]}} onReset={()=>{}}/>);
  expect((screen.getByRole('radio',{name:'Overview'}) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByText('Advisory screening · requires qualified review')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Possible manipulation flagged'})).toBeTruthy();
  expect(screen.getByText('Flagged for review')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'Findings'})).toBeTruthy();
  expect(screen.queryByText('Technical description')).toBeNull();
  fireEvent.click(screen.getByRole('radio',{name:'Technical details'}));
  expect((screen.getByRole('radio',{name:'Technical details'}) as HTMLInputElement).checked).toBe(true);
  expect(screen.getByText('Technical description')).toBeTruthy();
});

it('excludes inapplicable checks from completeness without certifying authenticity',()=>{
  render(<ReportView report={{...report,components:[{...report.components[0],status:'functional',raw_score:.2,threshold:.5},{...report.components[0],component:'video',task:'face_manipulation',status:'not_applicable'}]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'No manipulation detected'})).toBeTruthy();
  expect(screen.getByText(/Authenticity remains unverified/)).toBeTruthy();
  expect(screen.getByText('Not applicable')).toBeTruthy();
});

it('does not present a partial or missing-score screening as an unflagged result',()=>{
  const view=render(<ReportView report={{...report,components:[{...report.components[0],status:'functional',raw_score:.2},{...report.components[0],status:'error'}]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Unable to assess authenticity'})).toBeTruthy();
  view.rerender(<ReportView report={{...report,components:[{...report.components[0],status:'functional'}]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Unable to assess authenticity'})).toBeTruthy();
});

it('preserves flagged frames below the detector average and distinguishes coverage warnings',()=>{
  const signal={component:'video' as const,code:'ELEVATED_FRAME_SCORE',description:'A sampled frame met the rule.',severity:'medium'};
  const view=render(<ReportView report={{...report,components:[{...report.components[0],component:'video',task:'face_manipulation',status:'functional',raw_score:.2,threshold:.5,anomalies:[signal]}],anomalies:[signal]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Possible manipulation flagged'})).toBeTruthy();
  const coverage={...signal,code:'LIMITED_FACE_COVERAGE',description:'Only a few usable faces.'};
  view.rerender(<ReportView report={{...report,components:[{...report.components[0],component:'video',task:'face_manipulation',status:'functional',raw_score:.2,threshold:.5,anomalies:[coverage]}],anomalies:[coverage]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Limited screening coverage'})).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'Possible manipulation flagged'})).toBeNull();
});

it('keeps metadata warnings out of the manipulation assessment and retains technical evidence',()=>{
  const warning={component:'media',code:'METADATA_WARNING',description:'Metadata read warning',severity:'low'};
  render(<ReportView report={{...report,components:[{...report.components[0],status:'functional',raw_score:.2,threshold:.5,limitations:['Limited to the analyzed speech window.'],samples:[{start_time:0,end_time:4.0375,raw_score:.2,raw_logits:[-.2,.7]}]}],anomalies:[warning]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'No manipulation detected'})).toBeTruthy();
  expect(screen.queryByText('Metadata read warning')).toBeNull();
  fireEvent.click(screen.getByRole('radio',{name:'Technical details'}));
  expect(screen.getByText('Metadata read warning')).toBeTruthy();
  expect(screen.getByText('Limited to the analyzed speech window.')).toBeTruthy();
  expect(screen.getByRole('columnheader',{name:'Raw logits',hidden:true})).toBeTruthy();
  expect(screen.getByText('-0.2, 0.7')).toBeTruthy();
  expect(screen.getByText('Development rule')).toBeTruthy();
});

it('does not infer an unflagged assessment from a score without a decision threshold',()=>{
  render(<ReportView report={{...report,components:[{...report.components[0],status:'functional',raw_score:.2,threshold:null}]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Unable to assess authenticity'})).toBeTruthy();
  expect(screen.getByText('Score only')).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'No manipulation detected'})).toBeNull();
});

it('labels placeholder detector results as demonstrations',()=>{
  render(<ReportView report={{...report,components:[{...report.components[0],status:'stub',synthetic_confidence:.1}]}} onReset={()=>{}}/>);
  expect(screen.getByRole('heading',{name:'Demonstration results'})).toBeTruthy();
  expect(screen.queryByRole('heading',{name:'No manipulation detected'})).toBeNull();
});
it('lets an analyst send a report for review',async()=>{
  authState.token='token';authState.role='analyst';submitReport.mockResolvedValue({status:'submitted',reviewer:'dps.supervisor'});
  render(<ReportView report={report} onReset={()=>{}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Send for review'}));
  await screen.findByText('Sent for review.');
  expect(submitReport).toHaveBeenCalledWith('test','token');
});
it('lets the assigned supervisor start a review',async()=>{
  authState.token='token';authState.role='supervisor';startReview.mockResolvedValue({status:'in_review'});
  render(<ReportView report={{...report,workflow_status:'submitted'}} onReset={()=>{}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Start review'}));
  await screen.findByText('Review started.');
  expect(screen.getByRole('button',{name:'Complete review'})).toBeTruthy();
  expect(startReview).toHaveBeenCalledWith('test','token');
});
it('downloads the report as a PDF',async()=>{
  const click=vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  render(<ReportView report={report} onReset={()=>{}}/>);
  fireEvent.click(screen.getByRole('button',{name:'Download PDF'}));
  expect(URL.createObjectURL).toHaveBeenCalledOnce();
  const blob=vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
  expect(blob.type).toBe('application/pdf');
  expect(await blob.text()).toMatch(/^%PDF-1\.4/);
  expect(click).toHaveBeenCalledOnce();
});
