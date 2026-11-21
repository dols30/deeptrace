import {PageFrame} from '../../components/page-frame';

export default function ExperimentalModelsPage(){
  return <PageFrame>
    <div className="experimental-warning"><strong>EXPERIMENTAL — NOT USED FOR FINAL DEEPTRACE ASSESSMENT</strong><p>Production remains EfficientNet-B4, Community Forensics ViT-S/16, and AASIST.</p></div>
    <section className="report-section"><div className="section-heading"><h3>Face manipulation</h3><span>Benchmark track</span></div><div className="component-list">
      <article className="component"><span className="card-label">Production baseline</span><h3>DeepfakeBench EfficientNet-B4</h3><p>Frame-based aligned-face detector. Production aggregation remains unchanged.</p></article>
      <article className="component"><span className="card-label">Experimental challenger</span><h3>FakeSTormer</h3><p>Official spatiotemporal adapter available through an isolated CUDA environment. No benchmark result has been run in this repository.</p></article>
    </div></section>
    <section className="report-section"><div className="section-heading"><h3>AI-generated video</h3><span>Benchmark track</span></div><div className="component-list">
      <article className="component"><span className="card-label">Production baseline</span><h3>Community Forensics ViT-S/16</h3><p>Independent frame scores with production mean aggregation.</p></article>
      <article className="component"><span className="card-label">Experimental challenger</span><h3>DeMamba</h3><p><strong>BLOCKED:</strong> no reproducible official pretrained checkpoint and single-video inference contract are available.</p></article>
    </div></section>
  </PageFrame>;
}
