'use client';
import {useEffect, useRef, useState} from 'react';
import {askAssistant, clock} from '../lib/workflow';
import {useAuth} from './auth';

type Citation = {finding_id: string; start_time?: number};
type Turn = {role: 'user'|'assistant'; text: string; citations?: Citation[]};

const DISPOSITION_LABELS: Record<string, string> = {
  agree: 'Agreed', disagree: 'Disagreed', uncertain: 'Uncertain',
  needs_expert_review: 'Expert review requested', 'not reviewed': 'Not reviewed',
};

function parseFindingReply(text: string) {
  // The rules assistant emits stable finding records. Free-form answers are rendered as written.
  const pattern = /Finding ([\w-]+) \((audio|video), ([^)]+)\): possible manipulation signal, model score ([\d.]+), investigator disposition ([^.]+)\./g;
  const matches = Array.from(text.matchAll(pattern));
  if (!matches.length) return null;
  return {
    title: text.slice(0, matches[0].index).split('. ')[0].replace(/\.$/, ''),
    findings: matches.map(([, id, modality, span, score, disposition]) => ({id, modality, span, score, disposition})),
    note: text.slice((matches.at(-1)?.index ?? 0) + (matches.at(-1)?.[0].length ?? 0)).trim(),
  };
}

export function CaseChat({analysisId}: {analysisId: string}) {
  const auth = useAuth();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const log = useRef<HTMLDivElement>(null);
  const launcher = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight;
  }, [turns, pending, open]);

  function close() {
    setOpen(false);
    launcher.current?.focus();
  }

  async function send(question: string) {
    if (!auth.token || !question || pending) return;
    const history = turns.slice(-8).map(({role, text}) => ({role, text}));
    setTurns(current => [...current, {role: 'user', text: question}]);
    setDraft('');
    setPending(true);
    setError('');
    try {
      const result = await askAssistant(analysisId, question, auth.token, history);
      setTurns(current => [...current, {role: 'assistant', text: result.answer, citations: result.citations}]);
    } catch (reason) {
      if (reason instanceof Error && reason.message === 'SESSION_EXPIRED') auth.expire();
      else setError(reason instanceof Error ? reason.message : 'The assistant could not answer.');
    } finally {
      setPending(false);
    }
  }

  return <aside className="case-chat">
    {open && <section id="case-assistant" className="case-chat-panel" aria-label="Case assistant" onKeyDown={event => { if (event.key === 'Escape') close(); }}>
      <header>
        <div>
          <strong>Case assistant</strong>
          <p className="case-chat-scope">Advisory guidance for this case</p>
        </div>
        <button type="button" className="case-chat-close" aria-label="Close assistant" onClick={close}>×</button>
      </header>
      <div className="case-chat-log" role="log" aria-label="Conversation" ref={log}>
        {!turns.length && !pending && <div className="case-chat-prompt-block">
          <p className="case-chat-empty">Ask about the flagged moments or checks that ran.</p>
          <div className="case-chat-prompts">
            {['Which portions should I review?', 'Summarize the findings'].map(question =>
              <button type="button" key={question} onClick={() => void send(question)}>{question}</button>)}
          </div>
        </div>}
        {turns.map((turn, index) => {
          const text = turn.role === 'assistant'
            ? turn.text.replaceAll('DeepTrace cannot establish that this media is authentic or manipulated.', '').trim()
            : turn.text;
          const listing = turn.role === 'assistant' ? parseFindingReply(text) : null;

          function findingLink(citation: Citation, label: string) {
            const target = `finding-${citation.finding_id}`;
            return <a className="case-chat-source" href={`/analyses/${analysisId}/#${encodeURIComponent(target)}`} onClick={event => {
              const marker = document.getElementById(target);
              if (marker) {
                event.preventDefault();
                setOpen(false);
                marker.click();
              }
            }}>{label}</a>;
          }

          return <article key={index} className={`case-chat-turn ${turn.role}`}>
            <span>{turn.role === 'user' ? 'You' : 'Assistant'}</span>
            {listing ? <div className="case-chat-answer">
              <h3>{listing.title}</h3>
              <ol>{listing.findings.map(item => {
                const citation = turn.citations?.find(source => source.finding_id === item.id);
                const label = `${item.modality === 'video' ? 'Video' : 'Audio'} · ${item.span}`;
                return <li key={item.id}>
                  {citation ? findingLink(citation, label) : <strong>{label}</strong>}
                  <small>{DISPOSITION_LABELS[item.disposition] ?? item.disposition} · Model score {item.score}</small>
                </li>;
              })}</ol>
              {listing.note && <p>{listing.note}</p>}
            </div> : <>
              {text.split(/\n+/).filter(line => line.trim()).map((line, lineIndex) => <p key={lineIndex}>{line}</p>)}
              {!!turn.citations?.length && <div className="case-chat-prompts">
                {turn.citations.map((citation, citationIndex) => <div key={citationIndex}>
                  {findingLink(citation, citation.start_time == null ? 'Open finding' : `Finding at ${clock(citation.start_time)}`)}
                </div>)}
              </div>}
            </>}
          </article>;
        })}
        {pending && <article className="case-chat-turn assistant"><span>Assistant</span><p>Looking at the case…</p></article>}
      </div>
      {error && <p className="case-chat-error" role="alert">{error}</p>}
      <form className="case-chat-compose" onSubmit={event => { event.preventDefault(); void send(draft.trim()); }}>
        <textarea value={draft} onChange={event => setDraft(event.target.value)} maxLength={2000} rows={2} placeholder="Ask about this case" aria-label="Message the case assistant"/>
        <button className="case-chat-send" disabled={!draft.trim() || pending}>Send</button>
      </form>
    </section>}
    <button ref={launcher} type="button" className="case-chat-toggle" aria-controls={open ? 'case-assistant' : undefined} aria-expanded={open} aria-label={open ? 'Hide case assistant' : 'Open case assistant'} onClick={() => setOpen(current => !current)}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5 4v-4a2 2 0 0 1-1-2V7a2 2 0 0 1 2-2Zm2 4h10m-10 4h7"/></svg>
      <span>{open ? 'Hide assistant' : 'Case assistant'}</span>
    </button>
  </aside>;
}
