import {describe, expect, it} from 'vitest';
import cases from '../../backend/tests/fixtures/tool_assessment_cases.json';
import type {Report} from './api';
import {assessment} from './report-presentation';

describe('file-level benchmark uses the actual report overview', () => {
  for (const entry of cases) {
    it(entry.name, () => {
      const actual = assessment(entry.report as unknown as Report);
      expect(actual.tone).toBe(entry.expected.tone);
      expect(actual.missing).toBe(entry.expected.missing_checks);
      const decision = actual.title === 'Demonstration results' ? 'demo'
        : actual.tone === 'review' ? 'flagged'
        : actual.tone === 'incomplete' ? 'incomplete' : 'not_flagged';
      expect(decision).toBe(entry.expected.decision);
    });
  }
});
