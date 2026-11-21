import type {ReviewCheck} from '../lib/api';

const display = (value: unknown) => typeof value === 'number' ? Number(value.toFixed(4)).toString() : String(value);

export function ReviewChecks({checks}: {checks?:ReviewCheck[]}) {
  if (!checks?.length) return null;
  return <section className="report-panel" aria-labelledby="review-measurements-title">
    <header className="report-panel-heading"><h2 id="review-measurements-title">Supplementary analysis</h2></header>
    <div className="report-panel-body">
      <p className="report-technical-note">Measured features support closer review. They do not identify a manipulation technique or change the detector result.</p>
      {checks.map(check => <details className="report-detail" key={check.technique}>
        <summary>{check.title} · {check.status.replaceAll('_', ' ')}</summary>
        <p>{check.summary}</p>
        <dl className="report-facts"><div><dt>Method</dt><dd>{check.method}</dd></div><div><dt>Method version</dt><dd>{check.version}</dd></div>
          {Object.entries(check.measurements).map(([key,value]) => <div key={key}><dt>{key.replaceAll('_',' ')}</dt><dd>{typeof value === 'number' ? Number(value.toFixed(4)).toString() : value}</dd></div>)}
        </dl>
        {!!check.intervals.length && <div className="report-table-scroll"><table className="report-sample-table"><thead><tr><th scope="col">Start (s)</th><th scope="col">End (s)</th><th scope="col">Measurement</th></tr></thead><tbody>{check.intervals.map((item,index) => <tr key={index}>
          <td>{display(item.start_time ?? '—')}</td><td>{display(item.end_time ?? '—')}</td><td>{Object.entries(item).filter(([key]) => !['start_time','end_time'].includes(key)).map(([key,value]) => `${key.replaceAll('_',' ')}: ${display(value)}`).join('; ')}</td>
        </tr>)}</tbody></table></div>}
        <ul className="report-text-list">{check.limitations.map((item,index) => <li key={index}>{item}</li>)}</ul>
      </details>)}
    </div>
  </section>;
}
