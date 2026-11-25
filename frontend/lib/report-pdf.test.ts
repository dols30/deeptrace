import {expect,it} from 'vitest';
import type {Report} from './api';
import {createReportPdf} from './report-pdf';

const report: Report = {
  report_id:'test-report',generated_at:'2026-10-22T14:00:00Z',workflow_status:'draft',
  media:{filename:'Interview (été).mp4',media_kind:'video',size_bytes:2048,duration_seconds:31,sha256:'a'.repeat(64)},
  components:[{component:'video',task:'face_manipulation',status:'functional',model_name:'EfficientNet-B4',model_version:'pinned',raw_score:.936,synthetic_confidence:.936,threshold:.5,threshold_validated:false,num_samples:31,timestamps_seconds:[5],notes:[],samples:[{start_time:5,raw_score:.936,raw_logits:[-.123456789,.87654321]}]}],
  anomalies:[{component:'video',code:'ELEVATED_FRAME_SCORE',description:'Recorded detector observation.',severity:'medium'}],
  disclaimer:'Advisory outputs require qualified human review.',summary:'Original automated narrative.',recommended_action:'Recorded recommended action.',examination_scope:'Screening only.',review_status:'Pending qualified human review',overall_synthetic_confidence:.999,
  integrity:{provenance:'Not established'},methods:['Recorded method.'],limitations:['Recorded limitation.'],references:[{organization:'SWGDE',title:'Recorded reference',version:'1',application:'Documentation only.',url:'https://example.com/reference'}],
};
const contents = async (value:Report) => createReportPdf(value).text();

it('preserves the exact face PoC threshold in the export',async()=>{
  const pdf=await contents({...report,components:[{...report.components[0],threshold:0.9967585206031799}]});
  expect(pdf).toContain('(0.9967585206031799)');
  expect(pdf).toContain('Development rule');
});

it('uses current threshold wording in exports of saved reports', async () => {
  const pdf = await contents({
    ...report,
    methods: ["Each detector's recorded development/default decision rule is not a validated DPS operational threshold."],
    components: [{...report.components[0], notes: ['Small matched-domain benchmark only; not a validated DPS operational threshold.']}],
  });
  expect(pdf).toContain('The recorded decision rules are provisional.');
  expect(pdf).toContain('The benchmark covered a small set of similar recordings.');
  expect(pdf).not.toContain('validated DPS');
});

it('exports a readable overview and technical record without a fused probability',async()=>{
  const pdf=await contents(report);
  expect(pdf).toContain('(1. Screening summary)');
  expect(pdf).toContain('(Possible manipulation flagged)');
  expect(pdf).toContain('(Appendix A. Detector evidence)');
  expect(pdf).toContain('(Appendix B. Examination record)');
  expect(pdf).toContain('(0.936)');
  expect(pdf).not.toContain('93.6%');
  expect(pdf).not.toContain('99.9%');
  for(const value of ['Development rule','Recorded detector observation.','Original automated narrative.','Recorded limitation.','Recorded method.','https://example.com/reference','-0.123456789, 0.87654321']) expect(pdf).toContain(value);
  expect(pdf).toContain('Authenticity is undetermined.');
  expect(pdf).not.toContain('Advisory screening - qualified human review required');
  expect(pdf).toContain('Interview \\(\\351t\\351\\).mp4');
});

it('does not certify incomplete or placeholder screening as a clear result',async()=>{
  const unavailable={...report,components:[{...report.components[0],status:'unavailable' as const,raw_score:null,synthetic_confidence:null,timestamps_seconds:[],samples:[]}],anomalies:[]};
  expect(await contents(unavailable)).toContain('(Unable to assess authenticity)');
  expect(await contents({...unavailable,components:[{...unavailable.components[0],status:'stub'}]})).toContain('(Demonstration results)');
  const clear={...report,components:[{...report.components[0],raw_score:.2,synthetic_confidence:.2,timestamps_seconds:[],samples:[]}],anomalies:[]};
  expect(await contents(clear)).toContain('Authenticity remains unverified.');
});

it('paginates long text and sample tables without dropping data or writing below the body',async()=>{
  const samples=Array.from({length:120},(_,i)=>({start_time:i,raw_score:.1,raw_logits:[i,.123456789]}));
  const pdf=await contents({...report,media:{...report.media,filename:'W'.repeat(4000)},components:[{...report.components[0],samples}],limitations:[('Long limitation text. ').repeat(800),'FINAL_LIMITATION_SENTINEL']});
  expect(pdf).toContain('FINAL_LIMITATION_SENTINEL');
  expect(pdf).toContain('(119, 0.123456789)');
  const headers=pdf.match(/\(Reported time\)/g) ?? [];
  expect(headers.length).toBeGreaterThan(2);
  for(const match of pdf.matchAll(/1 0 0 1 (-?[\d.]+) (-?[\d.]+) Tm \((.*?)\) Tj/g)) {
    const x=Number(match[1]),baseline=Number(match[2]);
    expect(x).toBeGreaterThanOrEqual(54);
    const footer=match[3] === 'DeepTrace' || /^\d+ \/ \d+$/.test(match[3]);
    expect(baseline).toBeGreaterThanOrEqual(footer ? 23.5 : 64);
    expect(baseline).toBeLessThan(HEIGHT);
  }
});
const HEIGHT=792;

it('includes independent artifact detectors and neural expression intervals in the export',async()=>{
  const artifact={...report.components[0],detector_id:'cnn_gan_artifacts',model_name:'CNNDetection',task:'synthetic_video' as const};
  const vocoder={...report.components[0],component:'audio' as const,detector_id:'lfcc_lcnn_artifacts',model_name:'LFCC-LCNN',task:'audio_spoof' as const};
  const pdf=await contents({...report,components:[artifact,vocoder],review_checks:[{
    technique:'micro_expression',title:'Micro-expression intervals',modality:'video',status:'measured',method:'SOFTNet',
    version:'pinned',validated:false,summary:'Candidate brief movement',measurements:{checkpoint:'released.hdf5#sha256=123'},
    intervals:[{start_time:1,end_time:1.4,regression_score:1.2}],limitations:['Not an authenticity classifier.']}]});
  for(const value of ['GAN artifacts','Vocoder artifacts','Micro-expression intervals','released.hdf5#sha256=123','Not an authenticity classifier.']) expect(pdf).toContain(value);
});

it('writes valid object offsets, stream lengths, and page counts',async()=>{
  const pdf=await contents(report);
  const xref=Number(pdf.match(/startxref\n(\d+)/)?.[1]);
  expect(pdf.slice(xref,xref+4)).toBe('xref');
  const entries=pdf.slice(xref).split('\n');
  const count=Number(entries[1].split(' ')[1]);
  for(let i=1;i<count;i++) {
    const offset=Number(entries[i+2].slice(0,10));
    expect(pdf.slice(offset,offset+String(i).length+6)).toBe(i+' 0 obj');
  }
  for(const match of pdf.matchAll(/\/Length (\d+) >>\nstream\n([\s\S]*?)\nendstream/g)) expect(match[2].length).toBe(Number(match[1]));
  expect(pdf.match(/\/Type \/Page /g)?.length).toBe(Number(pdf.match(/\/Count (\d+)/)?.[1]));
});

it('exports measured audio coverage, supplementary intervals, and storage failures',async()=>{
  const pdf=await contents({...report,
    components:[{...report.components[0],component:'audio',task:'audio_spoof',model_name:'AASIST',coverage:{mode:'full',analyzed_seconds:31,duration_seconds:31,windows:8,complete:true}}],
    review_checks:[{technique:'background_noise',title:'Background-noise consistency',modality:'audio',status:'measured',method:'Low-energy level comparison',summary:'A level change needs listening review.',measurements:{level_changes:1},intervals:[{start_time:8,end_time:9,change_db:14}],limitations:['Recording gain can cause the same change.'],version:'review-signals-v1',validated:false}],
    processing:{status:'incomplete',elapsed_seconds:3,media_storage:'unavailable',workflow_storage:'unavailable',report_storage:'unavailable'},
  });
  for(const value of ['31.00 of 31.00 seconds screened','Appendix C. Supplementary analysis','A level change needs listening review.','Change db: 14','Recording gain can cause the same change.','Media storage','unavailable']) expect(pdf).toContain(value);
});
