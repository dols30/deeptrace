import {REPORT_SECTIONS, type CaseReport} from '../../lib/workflow';

const AI_KEYS = ['models_used', 'automated_screening_results', 'audio_findings', 'video_findings', 'limitations'];

export function ScreeningDraft({report}: {report: CaseReport}) {
  const sections = REPORT_SECTIONS.filter(section => AI_KEYS.includes(section.key));
  return <section className="ai-report" aria-label="AI-generated report">
    <header className="pane-head">
      <h2>AI-generated report</h2>
      <span>Draft</span>
    </header>
    <p>Original screening text. Human edits happen on the review page and leave this draft in place.</p>
    {sections.map(section => <article key={section.key}><h3>{section.label}</h3><p>{report.ai_original[section.key]?.text || 'Empty'}</p></article>)}
  </section>;
}
