import {clock} from '../../lib/workflow';
import type {FrameBookmark} from './frame-bookmarks';

export function BookmarkRail({
  bookmarks,
  onOpen,
  onRemove,
}: {
  bookmarks: FrameBookmark[];
  onOpen: (time: number) => void;
  onRemove: (id: string) => void;
}) {
  return <section className="bookmark-rail" aria-label="Bookmarked frames">
    <header>
      <h2>Bookmarked frames</h2>
      <span>{bookmarks.length}</span>
    </header>
    {bookmarks.length
      ? <ul>
        {bookmarks.map(item => <li key={item.id}>
          <button type="button" className="bookmark-card" onClick={() => onOpen(item.time)} aria-label={`Open bookmark at ${clock(item.time)}`}>
            {item.image
              ? <img src={item.image} alt=""/>
              : <span className="bookmark-fallback" aria-hidden="true">Frame</span>}
            <span className="bookmark-time">{clock(item.time)}</span>
          </button>
          <button type="button" className="bookmark-remove" onClick={() => onRemove(item.id)} aria-label={`Remove bookmark at ${clock(item.time)}`}>Remove</button>
        </li>)}
      </ul>
      : <p className="bookmark-empty">No frames bookmarked yet. Pause on a moment, then bookmark the frame.</p>}
  </section>;
}
