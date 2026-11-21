import {act, cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {HomeEvidence} from './home-evidence';

let reducedMotion = false;
let updateVisibility: (visible: boolean) => void;

beforeEach(() => {
  vi.useFakeTimers();
  reducedMotion = false;
  vi.stubGlobal('matchMedia', () => ({matches: reducedMotion, addEventListener: vi.fn(), removeEventListener: vi.fn()}));
  vi.stubGlobal('IntersectionObserver', class {
    constructor(callback: (entries: {isIntersecting: boolean}[]) => void) {
      updateVisibility = visible => callback([{isIntersecting: visible}]);
    }
    observe() { updateVisibility(true); }
    disconnect() {}
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

it('keeps the selected frame in sync across the preview and both detector rows', () => {
  render(<HomeEvidence/>);
  expect(screen.getByText('Frame 1 of 10')).toBeTruthy();
  const face = screen.getByRole('region', {name: 'Face manipulation frame scores'});
  const imagery = screen.getByRole('region', {name: 'Generated imagery frame scores'});
  fireEvent.click(within(face).getByRole('button', {name: '00:02.0: no alignable face, not scored'}));
  expect(screen.getByText('Frame 3 of 10')).toBeTruthy();
  expect(screen.getByText('No alignable face. This frame was not scored.')).toBeTruthy();
  expect(within(imagery).getByRole('button', {name: '00:02.0: model score 0.24'}).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', {name: 'Next frame'}));
  expect(screen.getByText('Frame 4 of 10')).toBeTruthy();
  expect(screen.queryByText('No alignable face. This frame was not scored.')).toBeNull();
  fireEvent.change(screen.getByRole('slider', {name: 'Selected example frame'}), {target: {value: '9'}});
  expect(screen.getByText('Frame 10 of 10')).toBeTruthy();
  expect((screen.getByRole('button', {name: 'Next frame'}) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByText('Audio after 4.04 seconds is not analyzed by this model.')).toBeTruthy();
});

it('loops frames 1–10 and pauses for manual inspection until playback is resumed', () => {
  render(<HomeEvidence/>);
  for (let frame = 2; frame <= 10; frame++) {
    act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText(`Frame ${frame} of 10`)).toBeTruthy();
  }
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText('Frame 1 of 10')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Pause frames'}));
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByText('Frame 1 of 10')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Play frames'}));
  act(() => vi.advanceTimersByTime(1000));
  fireEvent.click(screen.getByRole('button', {name: 'Next frame'}));
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.getByText('Frame 3 of 10')).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Play frames'})).toBeTruthy();
});

it('suspends automatic playback while the example is outside the viewport', () => {
  render(<HomeEvidence/>);
  act(() => updateVisibility(false));
  act(() => vi.advanceTimersByTime(3000));
  expect(screen.getByText('Frame 1 of 10')).toBeTruthy();
  act(() => updateVisibility(true));
  act(() => vi.advanceTimersByTime(1000));
  expect(screen.getByText('Frame 2 of 10')).toBeTruthy();
});

it('leaves autoplay off when reduced motion is requested', () => {
  reducedMotion = true;
  render(<HomeEvidence/>);
  act(() => vi.advanceTimersByTime(10000));
  expect(screen.getByText('Frame 1 of 10')).toBeTruthy();
  expect(screen.getByRole('button', {name: 'Play frames'})).toBeTruthy();
});
