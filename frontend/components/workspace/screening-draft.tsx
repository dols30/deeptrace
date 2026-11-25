import type {CaseReport} from '../../lib/workflow';
import {detectorTask} from './findings-inspector';

const REPORT_CONTENT = [
  {key: 'automated_screening_results', title: 'Screening summary'},
  {key: 'video_findings', title: 'Video findings'},
  {key: 'audio_findings', title: 'Audio findings'},
  {key: 'limitations', title: 'Limitations'},
  {key: 'models_used', title: 'Models and methods'},
] as const;

export function ScreeningDraft({report}: {report: CaseReport}) {
  return <section className="ai-report screening-draft" aria-label="AI-generated report">
    <header>
      <h2>AI-generated report</h2>
      <p>Original screening draft. Investigator edits are recorded separately in Review report.</p>
    </header>
    {REPORT_CONTENT.map(({key, title}) => <section key={key}>
      <h3>{title}</h3>
      <ReportSectionText text={report.ai_original[key]?.text}/>
    </section>)}
  </section>;
}

export function ReportSectionText({text}: {text?: string}) {
  const lines = text?.split(/\r?\n/).map(line => line.trim()).filter(Boolean) ?? [];
  const isIdentifier = (line: string) => /^(?:SHA-256[: ]+|(?:Analysis|Report|Case) ID[: ]+)\S{8,}/i.test(line);
  const identifiers = lines.filter(isIdentifier);
  const narrative = lines.filter(line => !isIdentifier(line));
  return <div className="report-readable">
    {!lines.length && <p>No text recorded.</p>}
    {narrative.map((line, index) => {
      const finding = line.match(/^(Findings? [^:]+?), (\d+:\d{2}(?:\.\d+)?[–-]\d+:\d{2}(?:\.\d+)?): (.+)$/);
      if (finding) {
        const outcome = finding[3].match(/^(.+?) scored (\d+) windows? at or above the ([\d.]+) decision threshold \(peak model screening score ([\d.]+)\)\. Possible manipulation signal for human review\.$/);
        return <div className="report-finding-line" key={index}>
          <strong>{finding[2]} <span>· {finding[1]}</span></strong>
          {outcome ? <>
            <p>{detectorTask(outcome[1])} flagged {outcome[2]} {outcome[2] === '1' ? 'window' : 'windows'} for review.</p>
            <details className="technical-finding-output"><summary>Model details</summary>
              <p>{outcome[1]} · Peak screening score {outcome[4]} · Decision threshold {outcome[3]}</p>
            </details>
          </> : <p>{finding[3]}</p>}
        </div>;
      }
      return <p key={index}>{line}</p>;
    })}
    {!!identifiers.length && <details className="technical-finding-output">
      <summary>File identifiers</summary>
      {identifiers.map(line => <p key={line}>{line}</p>)}
    </details>}
  </div>;
}
