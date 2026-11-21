import {useEffect, useRef, type RefObject} from 'react';
import {clock, type Finding} from '../../lib/workflow';
import {BookmarkRail} from './bookmark-rail';
import type {FrameBookmark} from './frame-bookmarks';

export function MediaCanvas({
  technical = false,
  mediaKind,
  mediaUrl,
  mediaRef,
  currentTime,
  duration,
  findings,
  selectedId,
  onTime,
  onSeek,
  onSelectFinding,
  bookmarks,
  onBookmark,
  onOpenBookmark,
  onRemoveBookmark,
  bookmarkMessage,
  bookmarking,
  overlay,
  onOverlay,
  opacity,
  onOpacity,
  attributionReady,
  explainedIndex,
  explainedCount,
  onStepExplained,
  children,
}: {
  technical?: boolean;
  mediaKind: string;
  mediaUrl: string;
  mediaRef: RefObject<(HTMLVideoElement & HTMLAudioElement) | null>;
  currentTime: number;
  duration: number;
  findings: Finding[];
  selectedId: string | null;
  onTime: (time: number) => void;
  onSeek: (time: number) => void;
  onSelectFinding: (finding: Finding) => void;
  bookmarks: FrameBookmark[];
  onBookmark: () => void;
  onOpenBookmark: (time: number) => void;
  onRemoveBookmark: (id: string) => void;
  bookmarkMessage: string;
  bookmarking: boolean;
  overlay: boolean;
  onOverlay: (value: boolean) => void;
  opacity: number;
  onOpacity: (value: number) => void;
  attributionReady: boolean;
  explainedIndex: number;
  explainedCount: number;
  onStepExplained: (index: number) => void;
  children?: React.ReactNode;
}) {
  const detectors = [...new Set(findings.map(finding => finding.model_name))];
  return <section className="media-stage" aria-label="Media viewer" data-tour="media">
    {mediaKind === 'video'
      ? <video ref={mediaRef} src={mediaUrl} controls onTimeUpdate={event => onTime(event.currentTarget.currentTime)}/>
      : <audio ref={mediaRef} src={mediaUrl} controls onTimeUpdate={event => onTime(event.currentTarget.currentTime)}/>}
    {mediaKind === 'audio' && <Waveform url={mediaUrl}/>}
    <BookmarkRail bookmarks={bookmarks} onOpen={onOpenBookmark} onRemove={onRemoveBookmark}/>
    <section className="timeline-panel" aria-label="Evidence timeline">
      <div className="timeline-scale"><span>0:00</span><strong>{clock(currentTime)}</strong><span>{clock(duration)}</span></div>
      <div className="timeline-track">
        <i className="playhead" style={{left: `${Math.min(100, (currentTime / Math.max(duration, 0.001)) * 100)}%`}}/>
        {findings.map(finding => {
          const span = Math.max(0, (finding.end_time ?? finding.start_time) - finding.start_time);
          const style = {
            left: `${Math.min(100, (finding.start_time / duration) * 100)}%`,
            width: `${Math.min(100, (span / duration) * 100)}%`,
            '--row': detectors.indexOf(finding.model_name),
            '--rows': detectors.length,
          } as React.CSSProperties;
          return <button key={finding.id} type="button" className={`marker ${finding.modality} ${finding.id === selectedId ? 'selected' : ''}`} style={style} onClick={() => onSelectFinding(finding)} aria-label={`${finding.modality} finding at ${clock(finding.start_time)}${technical ? `, model score ${finding.raw_score.toFixed(2)}` : ''}`}/>;
        })}
      </div>
    </section>
    <div className="media-tools">
      {mediaKind === 'video' && <div className="media-frame-actions" role="group" aria-label="Frame navigation">
        <button type="button" className="secondary-button" onClick={() => onSeek(currentTime - 1 / 30)}>Previous frame</button>
        <button type="button" className="secondary-button" onClick={() => onSeek(currentTime + 1 / 30)}>Next frame</button>
      </div>}
      <label>Seek<input type="number" min={0} step={0.1} value={Number(currentTime.toFixed(1))} onChange={event => onSeek(Number(event.target.value))} aria-label="Seek to seconds"/></label>
      <button type="button" className="secondary-button" onClick={onBookmark} disabled={bookmarking}>{bookmarking ? 'Saving frame…' : 'Bookmark frame'}</button>
    </div>
    {bookmarkMessage && <p className="bookmark-status" aria-live="polite">{bookmarkMessage}</p>}
    {technical && <div className="compare-row">
      <div className="attribution-toggle" role="group" aria-label="Attribution overlay">
        <button type="button" className={!overlay ? 'active' : ''} aria-pressed={!overlay} onClick={() => onOverlay(false)}>Attribution off</button>
        <button type="button" className={overlay ? 'active' : ''} aria-pressed={overlay} onClick={() => onOverlay(true)} disabled={!attributionReady}>Attribution on</button>
      </div>
      <label>Opacity<input type="range" min={0.15} max={0.9} step={0.05} value={opacity} onChange={event => onOpacity(Number(event.target.value))} disabled={!overlay} aria-valuetext={`${Math.round(opacity * 100)} percent`}/></label>
      {explainedCount > 1 && <div className="explained-frame-actions" role="group" aria-label="Explained frame navigation">
        <button type="button" className="secondary-button" disabled={explainedIndex <= 0} onClick={() => onStepExplained(explainedIndex - 1)}>Previous explained frame</button>
        <button type="button" className="secondary-button" disabled={explainedIndex < 0 || explainedIndex >= explainedCount - 1} onClick={() => onStepExplained(explainedIndex + 1)}>Next explained frame</button>
      </div>}
    </div>}
    {children}
  </section>;
}

function Waveform({url}: {url: string}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    let cancelled = false;
    const Ctx = window.AudioContext;
    if (!Ctx || !canvas.current) return;
    const context = new Ctx();
    let channel: Float32Array | null = null;
    function draw() {
      const node = canvas.current;
      if (cancelled || !node || !channel) return;
      const rect = node.getBoundingClientRect();
      const width = Math.max(1, Math.round(rect.width || 640));
      const height = Math.max(1, Math.round(rect.height || 72));
      const ratio = window.devicePixelRatio || 1;
      node.width = Math.round(width * ratio);
      node.height = Math.round(height * ratio);
      const ctx = node.getContext('2d');
      if (!ctx) return;
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent-deep').trim() || '#24327a';
      const step = Math.ceil(channel.length / width);
      for (let x = 0; x < width; x += 1) {
        let peak = 0;
        for (let i = 0; i < step; i += 1) peak = Math.max(peak, Math.abs(channel[x * step + i] || 0));
        const barHeight = peak * height;
        ctx.fillRect(x, (height - barHeight) / 2, 1, barHeight);
      }
    }
    const resize = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(draw);
    resize?.observe(canvas.current);
    const theme = new MutationObserver(draw);
    theme.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
    window.addEventListener('resize', draw);
    fetch(url).then(response => response.arrayBuffer()).then(buffer => context.decodeAudioData(buffer)).then(audio => {
      if (cancelled || !canvas.current) return;
      channel = audio.getChannelData(0);
      draw();
    }).catch(() => undefined);
    return () => { cancelled = true; resize?.disconnect(); theme.disconnect(); window.removeEventListener('resize', draw); void context.close(); };
  }, [url]);
  return <canvas ref={canvas} className="waveform" width={640} height={72} aria-label="Waveform"/>;
}
