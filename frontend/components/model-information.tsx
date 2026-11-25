import type {getModelInfo} from '../lib/workflow';
import {Terms} from './terms';

export type ModelInformationData = Awaited<ReturnType<typeof getModelInfo>>;
export type AnalysisMethod = {task: string; model: string; configured?: boolean};

// Methods that need video frames. Everything else (speech spoofing, vocoder artifacts) runs on audio,
// including the audio track extracted from a video.
const VIDEO_ONLY = new Set(['Face manipulation', 'Generated imagery', 'GAN artifacts', 'Micro-expression intervals']);

export function analysisMethods(data: ModelInformationData): AnalysisMethod[] {
  return [
    {task: 'Face manipulation', model: data.video_model, configured: data.video_configured},
    {task: 'Generated imagery', model: data.scene_model ?? 'community_forensics', configured: data.scene_configured},
    {task: 'Speech spoofing', model: data.audio_model, configured: data.audio_configured},
    ...(data.supplementary_methods ?? []),
  ];
}

/** Configured methods the backend will run for a file of this media kind. */
export function methodsForMedia(data: ModelInformationData, kind: 'audio' | 'video'): AnalysisMethod[] {
  return analysisMethods(data).filter(method => method.configured && (kind === 'video' || !VIDEO_ONLY.has(method.task)));
}

export function ModelInformation({data}: {data: ModelInformationData}) {
  const detectors = analysisMethods(data);

  return <div className="model-page">
    <section className="model-panel" aria-labelledby="model-detectors-title">
      <header className="model-panel-heading"><h2 id="model-detectors-title">Analysis methods</h2></header>
      <div className="model-detector-columns" aria-hidden="true"><span>Screening task</span><span>Model identifier</span><span>Configuration</span></div>
      <ul className="model-detector-list">
        {detectors.map(detector => <li key={detector.task}>
          <h3>{detector.task}</h3>
          <code>{detector.model}</code>
          <span className={`model-configuration${detector.configured ? ' configured' : ''}`}>
            {detector.configured == null ? 'Not reported' : detector.configured ? 'Configured' : 'Not configured'}
          </span>
        </li>)}
      </ul>
    </section>
    <div className="model-settings-grid">
      <section className="model-panel" aria-labelledby="model-rules-title">
        <header className="model-panel-heading"><h2 id="model-rules-title">Screening rules</h2></header>
        <dl className="model-facts">
          <div>
            <dt>Face decision threshold</dt>
            <dd><strong className="model-threshold">{(data.face_decision_threshold ?? data.decision_threshold).toString()}</strong><span>{data.face_decision_rule === 'ffpp_c23_kaggle_v1' ? 'Development-selected PoC rule' : 'Development rule'} · not DPS-validated</span></dd>
          </div>
          <div>
            <dt>Other workflow thresholds</dt>
            <dd><strong className="model-threshold">{data.decision_threshold.toFixed(2)}</strong><span>Development rule · not DPS-validated</span></dd>
          </div>
          <div>
            <dt>Calibration</dt>
            <dd><strong>{data.calibration_version ?? 'Not fitted'}</strong>{!data.calibration_version && <span>Estimated probability: Not available.</span>}</dd>
          </div>
        </dl>
      </section>
      <section className="model-panel" aria-labelledby="model-preprocessing-title">
        <header className="model-panel-heading"><h2 id="model-preprocessing-title">Media preprocessing</h2></header>
        <dl className="model-facts">
          <div><dt>Video</dt><dd>{data.preprocessing.video}</dd></div>
          <div><dt>Audio</dt><dd>{data.preprocessing.audio}</dd></div>
        </dl>
      </section>
    </div>
    <aside className="model-guidance" aria-label="Model limitations and terminology">
      <p>{data.note}</p>
      <Terms/>
    </aside>
  </div>;
}
