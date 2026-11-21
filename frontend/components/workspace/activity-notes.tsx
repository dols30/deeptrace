import {clock, type CaseComment} from '../../lib/workflow';

export function ActivityNotes({
  comments,
  comment,
  replyTo,
  onComment,
  onReply,
  onSeek,
  onResolve,
  onSubmit,
}: {
  comments: CaseComment[];
  comment: string;
  replyTo: string | null;
  onComment: (value: string) => void;
  onReply: (id: string | null) => void;
  onSeek: (time: number) => void;
  onResolve: (id: string) => void;
  onSubmit: (event: React.FormEvent) => void;
}) {
  return <section className="notes-panel" aria-label="Investigator notes">
    <header className="pane-head">
      <h2>Investigator notes</h2>
      <span>{comments.length}</span>
    </header>
    <ul className="comment-list">{comments.length ? comments.map(item => <li key={item.id} className={item.parent_id ? 'reply' : ''}>
      <div>
        <strong>{item.author}</strong>
        <span>{item.author_role}{item.resolved ? ' · resolved' : ''}</span>
      </div>
      <p>{item.body}</p>
      <div className="note-actions">
        {item.body.startsWith('Bookmarked frame') && <span className="note-chip">Bookmark</span>}
        {item.timestamp_seconds != null && <button type="button" className="text-button" onClick={() => onSeek(item.timestamp_seconds ?? 0)}>{clock(item.timestamp_seconds)}</button>}
        <button type="button" className="text-button" onClick={() => onReply(item.id)}>Reply</button>
        <button type="button" className="text-button" onClick={() => onResolve(item.id)}>{item.resolved ? 'Reopen' : 'Resolve'}</button>
      </div>
    </li>) : <li className="workspace-empty">No notes yet. Comments stay on the case, separate from the screening draft.</li>}</ul>
    <form onSubmit={onSubmit}>
      <label className="stack">{replyTo ? 'Reply' : 'Comment'}<textarea value={comment} onChange={event => onComment(event.target.value)} maxLength={4000} aria-label="Analysis comment"/></label>
      <div className="note-form-actions">
        {replyTo && <button type="button" className="text-button" onClick={() => onReply(null)}>Cancel reply</button>}
        <button className="secondary-button" disabled={!comment.trim()}>Save comment</button>
      </div>
    </form>
  </section>;
}
