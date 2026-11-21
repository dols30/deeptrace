'use client';
import {useState} from 'react';
import {askAssistant} from '../lib/workflow';
import {useAuth} from './auth';

type Turn = {role: 'user'|'assistant'; text: string};

export function CaseChat({analysisId}: {analysisId: string}) {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const question = draft.trim();
    if (!auth.token || !question || pending) return;
    const history = turns.slice(-8);
    setTurns(current => [...current, {role: 'user', text: question}]);
    setDraft('');
    setPending(true);
    setError('');
    try {
      const result = await askAssistant(analysisId, question, auth.token, history);
      setTurns(current => [...current, {role: 'assistant', text: result.answer}]);
    } catch (reason) {
      if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') auth.expire();
      else setError(reason instanceof Error ? reason.message : 'The assistant could not answer.');
    } finally {
      setPending(false);
    }
  }

  return <aside className="case-chat">
    {open && <section className="case-chat-panel" aria-label="Case assistant">
      <header>
        <div>
          <span className="case-chat-kicker">Advisory</span>
          <strong>Case assistant</strong>
        </div>
        <button type="button" className="case-chat-close" onClick={() => setOpen(false)}>Close</button>
      </header>
      <p className="case-chat-note">Answers use this case only. They are advisory screening help.</p>
      <div className="case-chat-log" aria-live="polite">
        {!turns.length && !pending && <p className="case-chat-empty">Ask about flagged intervals, model scores, or what to review next.</p>}
        {turns.map((turn, index) => <article key={index} className={`case-chat-turn ${turn.role}`}>
          <span>{turn.role === 'user' ? 'You' : 'Assistant'}</span>
          <p>{turn.text}</p>
        </article>)}
        {pending && <article className="case-chat-turn assistant"><span>Assistant</span><p>Looking at the case…</p></article>}
      </div>
      {error && <p className="case-chat-error" role="alert">{error}</p>}
      <form className="case-chat-compose" onSubmit={event => void send(event)}>
        <textarea value={draft} onChange={event => setDraft(event.target.value)} maxLength={2000} rows={2} placeholder="Ask about this case" aria-label="Message the case assistant"/>
        <button className="case-chat-send" disabled={!draft.trim() || pending}>Send</button>
      </form>
    </section>}
    <button type="button" className="case-chat-toggle" aria-expanded={open} aria-label={open ? 'Hide case assistant' : 'Open case assistant'} onClick={() => setOpen(current => !current)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 6.2A2.2 2.2 0 0 1 7.2 4h9.6A2.2 2.2 0 0 1 19 6.2v7.2a2.2 2.2 0 0 1-2.2 2.2H9.2L5.4 19a.7.7 0 0 1-1.1-.6V6.2Z"/></svg>
      <span>{open ? 'Hide assistant' : 'Assistant'}</span>
    </button>
  </aside>;
}
