import {afterEach, expect, it} from 'vitest';
import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {GuideButton, GuidedTour} from './guided-tour';
import {EMPTY_FINDINGS, EMPTY_QUEUE, guideForSurface, isTourSeen} from './tour-copy';

afterEach(() => {
  cleanup();
  localStorage.clear();
});

function anchors() {
  return <>
    <div data-tour="drop">Drop</div>
    <div data-tour="checks">Checks</div>
    <a data-tour="open-case" href="/analyses/1">Open workspace</a>
    <div data-tour="review-evidence">Evidence</div>
    <div data-tour="review-submit">Submit</div>
    <div data-tour="supervisor-actions">Decide</div>
  </>;
}

it('does not show a tour twice for the same user', () => {
  const {unmount} = render(<>{anchors()}<GuidedTour tourId="detector" userKey="ada" autoStart/></>);
  expect(screen.getByRole('dialog').textContent).toContain('Drop a file to start.');
  fireEvent.click(screen.getByRole('button', {name: 'Skip'}));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(isTourSeen('ada', 'detector')).toBe(true);
  unmount();
  render(<>{anchors()}<GuidedTour tourId="detector" userKey="ada" autoStart/></>);
  expect(screen.queryByRole('dialog')).toBeNull();
});

it('closes the tour with Escape', () => {
  render(<GuidedTour tourId="detector" userKey="ada" autoStart/>);
  fireEvent.keyDown(window, {key: 'Escape'});
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(isTourSeen('ada', 'detector')).toBe(true);
});

it('replays a dismissed tour from Guide', () => {
  render(<>
    {anchors()}
    <GuidedTour tourId="detector" userKey="ada" autoStart/>
    <GuideButton tourId="detector" userKey="ada"/>
  </>);
  fireEvent.click(screen.getByRole('button', {name: 'Skip'}));
  fireEvent.click(screen.getByRole('button', {name: 'Guide'}));
  expect(screen.getByRole('dialog').textContent).toContain('Drop a file to start.');
  expect(isTourSeen('ada', 'detector')).toBe(false);
});

it('does not show the investigator submit step to a supervisor', () => {
  const ready = guideForSurface('supervisor', 'review', 'SUPERVISOR_REVIEW');
  const waiting = guideForSurface('supervisor', 'review', 'INVESTIGATOR_REVIEW');
  expect(ready.tourId).toBe('supervisor');
  expect(waiting.autoStart).toBe(false);
  expect(guideForSurface('supervisor', 'case').autoStart).toBe(false);
  render(<GuidedTour tourId={waiting.tourId} userKey="sam" autoStart={waiting.autoStart}/>);
  expect(screen.queryByRole('dialog')).toBeNull();
  cleanup();
  render(<>{anchors()}<GuidedTour tourId={ready.tourId} userKey="sam" autoStart/></>);
  expect(screen.getByRole('dialog').textContent).not.toContain('Submit sends this draft to a supervisor.');
  fireEvent.click(screen.getByRole('button', {name: 'Next'}));
  expect(screen.getByRole('dialog').textContent).toContain('Request changes or finalize.');
  expect(screen.getByRole('dialog').textContent).not.toContain('Submit sends this draft to a supervisor.');
});

it('shows the investigator submit step on the review tour', () => {
  const guide = guideForSurface('investigator', 'review', 'INVESTIGATOR_REVIEW');
  expect(guide.tourId).toBe('review');
  render(<>{anchors()}<GuidedTour tourId={guide.tourId} userKey="ida" autoStart/></>);
  fireEvent.click(screen.getByRole('button', {name: 'Next'}));
  expect(screen.getByRole('dialog').textContent).toContain('Submit sends this draft to a supervisor.');
  expect(screen.queryByText('Request changes or finalize.')).toBeNull();
});

it('keeps empty-state teaching on the same next action', () => {
  expect(EMPTY_FINDINGS).toMatch(/was screened/);
  expect(EMPTY_FINDINGS).toMatch(/does not establish authenticity/);
  expect(EMPTY_QUEUE).toMatch(/Start a scan/);
});

it('keeps help available without opening unsolicited popups', () => {
  for (const role of ['investigator', 'supervisor', 'forensic_reviewer']) {
    for (const surface of ['detector', 'case', 'review'] as const) {
      expect(guideForSurface(role, surface, 'SUPERVISOR_REVIEW').autoStart).toBe(false);
    }
  }
});
