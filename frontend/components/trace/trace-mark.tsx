import {LANES} from './fixture';

export type MarkConcept = 'converge' | 'readings' | 'graph';

export const MARK_CONCEPTS: {id: MarkConcept; name: string; idea: string}[] = [
  {id: 'converge', name: 'Convergence', idea: 'Three streams meet in one point and leave as a single trace.'},
  {id: 'readings', name: 'Readings', idea: 'Three independent readings of different length reach one review line.'},
  {id: 'graph', name: 'Evidence graph', idea: 'Three analysis nodes connect to one open node: the undecided investigation.'},
];

export function TraceMark({concept, size = 32, title}: {concept: MarkConcept; size?: number; title?: string}) {
  return (
    <svg className={`trace-mark trace-mark-${concept}`} width={size} height={size} viewBox="0 0 32 32" role={title ? 'img' : undefined} aria-label={title} aria-hidden={title ? undefined : true}>
      {concept === 'converge' && <>
        <path d="M3 7h7l7 9M3 16h14M3 25h7l7-9" />
        <path d="M17 16h12" />
        <circle cx="17" cy="16" r="3.4" />
      </>}
      {concept === 'readings' && <>
        <path d="M4 8h20M10 16h14M7 24h17" />
        <path className="trace-mark-rule" d="M26.5 4v24" />
      </>}
      {concept === 'graph' && <>
        <path d="M7 7l12.5 7.2M7 16h12M7 25l12.5-7.2" />
        <circle className="trace-mark-node" cx="6" cy="7" r="2.6" />
        <circle className="trace-mark-node" cx="6" cy="16" r="2.6" />
        <circle className="trace-mark-node" cx="6" cy="25" r="2.6" />
        <circle className="trace-mark-open" cx="24" cy="16" r="5" />
      </>}
    </svg>
  );
}

export function TraceWordmark({concept, size = 28}: {concept: MarkConcept; size?: number}) {
  return (
    <span className="trace-wordmark">
      <TraceMark concept={concept} size={size} />
      <span>DeepTrace</span>
    </span>
  );
}

export function TraceLoadingMark({size = 30}: {size?: number}) {
  return <span className="trace-loading-mark" aria-hidden="true"><TraceMark concept="converge" size={size} /></span>;
}

export function TraceLoader({label = 'Analysis running'}: {label?: string}) {
  return (
    <div className="trace-loader" role="status" aria-label={label}>
      {LANES.map(lane => (
        <div key={lane.id} className={`trace-loader-lane trace-lane-${lane.id}`}>
          <span>{lane.short}</span>
          <i aria-hidden="true"><b /></i>
        </div>
      ))}
      <p>{label}. Duration depends on file length; no progress percentage is measured.</p>
    </div>
  );
}

export function TraceDivider() {
  return (
    <div className="trace-divider" aria-hidden="true">
      <svg viewBox="0 0 240 24" preserveAspectRatio="none">
        <path d="M0 4h80c20 0 28 8 40 8M0 12h120M0 20h80c20 0 28-8 40-8" />
        <path d="M120 12h120" />
        <circle cx="120" cy="12" r="2.6" />
      </svg>
    </div>
  );
}
