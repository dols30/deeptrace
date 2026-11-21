'use client';
import {useEffect, useId, useState} from 'react';
import {clearTourSeen, isTourSeen, markTourSeen, TOURS, type TourId} from './tour-copy';

type Box = {top: number; left: number; width: number; height: number};

function measure(anchor: string): Box | null {
  const node = document.querySelector(`[data-tour="${anchor}"]`);
  if (!(node instanceof HTMLElement) || node.hidden || node.getClientRects().length === 0) return null;
  const rect = node.getBoundingClientRect();
  if (rect.width === 0 && rect.height === 0) return null;
  return {top: rect.top, left: rect.left, width: rect.width, height: rect.height};
}

function placeCard(box: Box | null) {
  const width = 320;
  const height = 200;
  const gap = 12;
  if (!box || typeof window === 'undefined') return {top: 16, left: 16};
  const maxLeft = Math.max(gap, window.innerWidth - width - gap);
  const maxTop = Math.max(gap, window.innerHeight - height - gap);
  const candidates = [
    {top: box.top, left: box.left + box.width + gap},
    {top: box.top + box.height + gap, left: Math.min(Math.max(gap, box.left), maxLeft)},
    {top: box.top - height - gap, left: Math.min(Math.max(gap, box.left), maxLeft)},
  ];
  const fits = (point: {top: number; left: number}) => point.top >= gap && point.left >= gap && point.top <= maxTop && point.left <= maxLeft;
  return candidates.find(fits) ?? {top: maxTop, left: maxLeft};
}

export function GuideButton({tourId, userKey}: {tourId: TourId; userKey: string}) {
  return <button
    type="button"
    className="text-button guide-button"
    onClick={() => {
      clearTourSeen(userKey, tourId);
      window.dispatchEvent(new CustomEvent('deeptrace-tour-replay', {detail: tourId}));
    }}
  >Guide</button>;
}

export function GuidedTour({tourId, userKey, autoStart}: {tourId: TourId; userKey: string; autoStart: boolean}) {
  const steps = TOURS[tourId];
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);
  const [box, setBox] = useState<Box | null>(null);
  const step = steps[Math.min(stepIndex, steps.length - 1)];

  useEffect(() => {
    if (autoStart && !isTourSeen(userKey, tourId)) {
      setStepIndex(0);
      setOpen(true);
    }
  }, [autoStart, tourId, userKey]);

  useEffect(() => {
    function onReplay(event: Event) {
      if ((event as CustomEvent<TourId>).detail !== tourId) return;
      setStepIndex(0);
      setOpen(true);
    }
    window.addEventListener('deeptrace-tour-replay', onReplay);
    return () => window.removeEventListener('deeptrace-tour-replay', onReplay);
  }, [tourId]);

  useEffect(() => {
    if (!open) return;
    function dismiss(event: KeyboardEvent) {
      if (event.key !== 'Escape') return;
      markTourSeen(userKey, tourId);
      setOpen(false);
    }
    window.addEventListener('keydown', dismiss);
    return () => window.removeEventListener('keydown', dismiss);
  }, [open, tourId, userKey]);

  useEffect(() => {
    if (!open) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const node = document.querySelector(`[data-tour="${step.anchor}"]`);
        if (node instanceof HTMLElement) node.scrollIntoView?.({block: 'nearest', inline: 'nearest'});
        const next = measure(step.anchor);
        setBox(current => {
          if (!next && !current) return current;
          if (next && current && next.top === current.top && next.left === current.left && next.width === current.width && next.height === current.height) return current;
          return next;
        });
      });
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(document.body, {childList: true, subtree: true});
    window.addEventListener('resize', update);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      window.removeEventListener('resize', update);
    };
  }, [open, step.anchor]);

  if (!open) return null;
  const card = placeCard(box);
  const last = stepIndex >= steps.length - 1;

  function close() {
    markTourSeen(userKey, tourId);
    setOpen(false);
  }

  function advance() {
    if (last) close();
    else setStepIndex(index => index + 1);
  }

  return <>
    {box && <div className="tour-spot" style={{top: box.top, left: box.left, width: box.width, height: box.height}}/>}
    <div
      className="tour-card"
      role="dialog"
      aria-labelledby={titleId}
      style={{top: card.top, left: card.left}}
    >
      <p className="tour-progress">{stepIndex + 1} of {steps.length}</p>
      <h2 id={titleId}>{step.action}</h2>
      <p>{step.meaning}</p>
      <div className="tour-card-actions">
        <button type="button" className="text-button" onClick={close}>Skip</button>
        <button type="button" className="secondary-button" onClick={advance}>{last ? 'Done' : 'Next'}</button>
      </div>
    </div>
  </>;
}
