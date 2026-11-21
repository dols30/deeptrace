const WAVE = [28, 46, 70, 52, 84, 40, 64, 34];

export function HeroSequence() {
  return (
    <div
      className="forensic-stage"
      role="img"
      aria-label="A recording enters the workspace. A scan crosses it, the face and voice checks run together, and the analysis finishes ready for review."
    >
      <div className="forensic-workspace" aria-hidden="true">
        <header className="forensic-bar">
          <span>Workspace</span>
          <span className="forensic-status">
            <span className="status-receive">Receiving media</span>
            <span className="status-screen">Screening</span>
            <span className="status-done">Analysis complete</span>
          </span>
        </header>
        <div className="forensic-body">
          <div className="media-well">
            <div className="media-artifact">
              <div className="media-still"/>
              <div className="face-region"><i/><i/><i/><i/></div>
              <div className="scan-pass"/>
            </div>
          </div>
          <div className="detector-stack">
            <article className="detector-card detector-video">
              <header><span>VIDEO</span><b>Face</b></header>
              <p>Region tracked</p>
              <div className="evidence" aria-hidden="true"><i/></div>
            </article>
            <article className="detector-card detector-audio">
              <header><span>AUDIO</span><b>Voice</b></header>
              <div className="wave">{WAVE.map((height, index) => <i key={index} style={{height: `${height}%`}}/>)}</div>
              <div className="evidence" aria-hidden="true"><i/></div>
            </article>
          </div>
        </div>
        <footer className="forensic-result">
          <span className="converge"/>
          <b>Ready for review</b>
        </footer>
      </div>
    </div>
  );
}
