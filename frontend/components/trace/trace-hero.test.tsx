import {act, cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {TraceHero} from './trace-hero';

afterEach(cleanup);

it('renders the completed convergence immediately when motion is reduced', () => {
  render(<TraceHero reduced actions={<a href="/detector">Scan media</a>} />);
  expect(screen.getByRole('heading', {level: 1}).textContent).toContain('Three signals.');
  expect(screen.getByRole('link', {name: 'Scan media'})).toBeTruthy();
  expect(screen.queryByRole('button', {name: 'Replay analysis'})).toBeNull();
  expect(screen.queryByRole('group', {name: 'Scanner overlays'})).toBeNull();
  expect(screen.getByRole('button', {name: 'Sampled frame 6 at 00:05.0'}).getAttribute('aria-pressed')).toBe('true');
});

const current = () => screen.getAllByRole('button', {name: /^Sampled frame/}).find(button => button.getAttribute('aria-pressed') === 'true')!.getAttribute('aria-label');

it('plays one pass when the scanner appears, then waits for hover', () => {
  vi.useFakeTimers();
  try {
    const {container} = render(<TraceHero reduced={false} />);
    expect(current()).toBe('Sampled frame 1 at 00:00.0');
    act(() => { vi.advanceTimersByTime(1200 * 12); });
    expect(current()).toBe('Sampled frame 10 at 00:09.0');
    act(() => { vi.advanceTimersByTime(1200 * 3); });
    expect(current()).toBe('Sampled frame 10 at 00:09.0');

    const grid = container.querySelector('.trace-combined-grid')!;
    fireEvent.pointerEnter(grid);
    act(() => { vi.advanceTimersByTime(1200 * 2); });
    expect(current()).toBe('Sampled frame 2 at 00:01.0');
    fireEvent.pointerLeave(grid);
    act(() => { vi.advanceTimersByTime(1200 * 3); });
    expect(current()).toBe('Sampled frame 2 at 00:01.0');
  } finally {
    vi.useRealTimers();
  }
});

it('stays still with reduced motion, even on hover', () => {
  vi.useFakeTimers();
  try {
    const {container} = render(<TraceHero reduced />);
    fireEvent.pointerEnter(container.querySelector('.trace-combined-grid')!);
    act(() => { vi.advanceTimersByTime(1200 * 3); });
    expect(current()).toBe('Sampled frame 6 at 00:05.0');
  } finally {
    vi.useRealTimers();
  }
});

it('keeps model output language advisory', () => {
  const {container} = render(<TraceHero reduced />);
  const text = container.textContent!.toLowerCase();
  expect(text).not.toMatch(/fake probability|confidence|\bauthentic\b|verdict:|is real|is fake/);
  expect(text).toContain('not probabilities');
  expect(text).toContain('never combin');
});
