import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, expect, it} from 'vitest';
import {DesignLab} from './design-lab';
import {EvidenceTimeline} from '../trace/evidence-timeline';
import {FrameStrip} from '../trace/frame-strip';

afterEach(cleanup);

it('opens on the combined direction and switches between all four', () => {
  const {container} = render(<DesignLab/>);
  expect(screen.getByRole('heading', {name: /Convergence \+ scanner/})).toBeTruthy();
  expect(screen.getByRole('heading', {name: 'Trace the evidence.'})).toBeTruthy();
  const root = container.querySelector('.trace')!;
  expect([root.getAttribute('data-theme'), root.getAttribute('data-type'), root.getAttribute('data-motion')]).toEqual(['light', 'grotesk', 'normal']);
  fireEvent.click(screen.getByRole('button', {name: 'Signal convergence'}));
  expect(screen.getByRole('heading', {name: /Signal convergence/})).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Forensic scanner'}));
  expect(screen.getByRole('heading', {name: /Forensic scanner/})).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name: 'Investigation timeline'}));
  expect(screen.getByRole('heading', {name: /Investigation timeline/})).toBeTruthy();
});

it('applies theme and motion choices to the lab root', () => {
  const {container} = render(<DesignLab/>);
  fireEvent.click(screen.getByRole('button', {name: 'Dark'}));
  fireEvent.click(screen.getByRole('button', {name: 'Reduced'}));
  const root = container.querySelector('.trace')!;
  expect(root.getAttribute('data-theme')).toBe('dark');
  expect(root.getAttribute('data-motion')).toBe('reduced');
});

it('never presents scores as probability, confidence, or authenticity', () => {
  const {container} = render(<DesignLab/>);
  const text = container.textContent!.toLowerCase();
  expect(text).not.toMatch(/fake probability|confidence|\bauthentic\b|verdict:/);
  expect(text).toContain('not probabilities');
});

it('shows abstained face frames as unscored rather than zero', () => {
  render(<FrameStrip lane="face"/>);
  expect(screen.getAllByRole('button', {name: /no alignable face, not scored/})).toHaveLength(2);
  expect(screen.getByText(/2 frames not scored/)).toBeTruthy();
});

it('reports audio outside the AASIST window as not analysed', () => {
  render(<EvidenceTimeline/>);
  fireEvent.change(screen.getByRole('slider'), {target: {value: '7'}});
  const timeline = screen.getByRole('region', {name: 'Evidence timeline'});
  expect(within(timeline).getByText('Not analysed by AASIST')).toBeTruthy();
});
