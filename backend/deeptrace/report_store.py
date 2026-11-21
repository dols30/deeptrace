import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from deeptrace.schemas import AdvisoryReport, CommentResponse, NotebookResponse, ProfileResponse


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS reports (
        report_id TEXT PRIMARY KEY,
        owner TEXT NOT NULL,
        generated_at TEXT NOT NULL,
        filename TEXT NOT NULL,
        media_kind TEXT NOT NULL,
        score REAL,
        payload TEXT NOT NULL,
        workflow_status TEXT NOT NULL DEFAULT 'draft',
        reviewer TEXT,
        submitted_at TEXT,
        media_path TEXT
    )""")
    columns = {row[1] for row in connection.execute("PRAGMA table_info(reports)")}
    for name, definition in {
        "workflow_status": "TEXT NOT NULL DEFAULT 'draft'",
        "reviewer": "TEXT",
        "submitted_at": "TEXT",
        "media_path": "TEXT",
    }.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE reports ADD COLUMN {name} {definition}")
    connection.execute("""CREATE TABLE IF NOT EXISTS profiles (
        username TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        title TEXT NOT NULL
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS report_comments (
        comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
        report_id TEXT NOT NULL,
        author TEXT NOT NULL,
        author_role TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at TEXT NOT NULL,
        FOREIGN KEY(report_id) REFERENCES reports(report_id)
    )""")
    connection.execute("""CREATE TABLE IF NOT EXISTS report_notebooks (
        report_id TEXT NOT NULL,
        author TEXT NOT NULL,
        body TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(report_id, author),
        FOREIGN KEY(report_id) REFERENCES reports(report_id)
    )""")
    return connection


def persist_media(directory: Path, report_id: str, source: Path, filename: str) -> Path:
    target = directory / report_id / Path(filename).name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return target


def save_report(path: Path, owner: str, report: AdvisoryReport, media_path: Path) -> None:
    report.owner = owner
    payload = report.model_dump(mode="json")
    with _connect(path) as connection:
        connection.execute(
            """INSERT OR REPLACE INTO reports
               (report_id, owner, generated_at, filename, media_kind, score, payload, media_path)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (report.report_id, owner, payload["generated_at"], report.media.filename,
             report.media.media_kind, report.overall_synthetic_confidence, json.dumps(payload), str(media_path)),
        )


def list_reports(path: Path, username: str, role: str) -> list[dict]:
    with _connect(path) as connection:
        if role == "supervisor":
            rows = connection.execute(
                """SELECT report_id, generated_at, filename, media_kind, score, owner,
                          workflow_status, reviewer
                   FROM reports
                   WHERE owner=? OR (workflow_status IN ('submitted','in_review','reviewed') AND reviewer=?)
                   ORDER BY generated_at DESC""", (username, username),
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT report_id, generated_at, filename, media_kind, score, owner,
                          workflow_status, reviewer
                   FROM reports WHERE owner=? ORDER BY generated_at DESC""", (username,),
            ).fetchall()
    return [{"report_id": row[0], "generated_at": row[1], "filename": row[2],
             "media_kind": row[3], "overall_synthetic_confidence": row[4], "owner": row[5],
             "workflow_status": row[6], "reviewer": row[7]} for row in rows]


def get_report(path: Path, username: str, role: str, report_id: str) -> AdvisoryReport | None:
    with _connect(path) as connection:
        row = connection.execute(
            """SELECT payload, owner, workflow_status, reviewer FROM reports
               WHERE report_id=? AND
                     (owner=? OR (?='supervisor' AND workflow_status IN ('submitted','in_review','reviewed') AND reviewer=?))""",
            (report_id, username, role, username),
        ).fetchone()
    if not row:
        return None
    report = AdvisoryReport.model_validate_json(row[0])
    report.owner = row[1]
    report.workflow_status = row[2]
    report.reviewer = row[3]
    return report


def submit_report(path: Path, owner: str, report_id: str, reviewer: str) -> bool:
    with _connect(path) as connection:
        result = connection.execute(
            """UPDATE reports SET workflow_status='submitted', reviewer=?, submitted_at=?
               WHERE report_id=? AND owner=? AND workflow_status='draft'""",
            (reviewer, datetime.now(timezone.utc).isoformat(), report_id, owner),
        )
    return result.rowcount == 1


def transition_review(path: Path, reviewer: str, report_id: str, current: str, next_status: str) -> bool:
    with _connect(path) as connection:
        result = connection.execute(
            """UPDATE reports SET workflow_status=?
               WHERE report_id=? AND reviewer=? AND workflow_status=?""",
            (next_status, report_id, reviewer, current),
        )
    return result.rowcount == 1


def delete_report(path: Path, report_id: str) -> str | None:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT owner, media_path FROM reports WHERE report_id=?", (report_id,),
        ).fetchone()
        if not row:
            return None
        connection.execute("DELETE FROM report_comments WHERE report_id=?", (report_id,))
        connection.execute("DELETE FROM report_notebooks WHERE report_id=?", (report_id,))
        connection.execute("DELETE FROM reports WHERE report_id=?", (report_id,))
    return row[1] or ""


def report_owner(path: Path, report_id: str) -> str | None:
    with _connect(path) as connection:
        row = connection.execute("SELECT owner FROM reports WHERE report_id=?", (report_id,)).fetchone()
    return row[0] if row else None


def can_access_report(path: Path, username: str, role: str, report_id: str) -> bool:
    with _connect(path) as connection:
        row = connection.execute(
            """SELECT 1 FROM reports WHERE report_id=? AND
               (owner=? OR (?='supervisor' AND reviewer=? AND
                workflow_status IN ('submitted','in_review','reviewed')))""",
            (report_id, username, role, username),
        ).fetchone()
    return row is not None


def add_comment(path: Path, report_id: str, author: str, role: str, body: str) -> CommentResponse:
    created_at = datetime.now(timezone.utc)
    with _connect(path) as connection:
        cursor = connection.execute(
            """INSERT INTO report_comments (report_id, author, author_role, body, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (report_id, author, role, body, created_at.isoformat()),
        )
    return CommentResponse(
        comment_id=int(cursor.lastrowid), report_id=report_id, author=author,
        author_role=role, body=body, created_at=created_at,
    )


def list_comments(path: Path, report_id: str) -> list[CommentResponse]:
    with _connect(path) as connection:
        rows = connection.execute(
            """SELECT comment_id, author, author_role, body, created_at
               FROM report_comments WHERE report_id=? ORDER BY comment_id""",
            (report_id,),
        ).fetchall()
    return [
        CommentResponse(
            comment_id=row[0], report_id=report_id, author=row[1],
            author_role=row[2], body=row[3], created_at=row[4],
        ) for row in rows
    ]


def get_notebook(path: Path, report_id: str, author: str) -> NotebookResponse:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT body, updated_at FROM report_notebooks WHERE report_id=? AND author=?",
            (report_id, author),
        ).fetchone()
    if row:
        return NotebookResponse(report_id=report_id, author=author, body=row[0], updated_at=row[1])
    return NotebookResponse(
        report_id=report_id, author=author, body="", updated_at=datetime.now(timezone.utc),
    )


def save_notebook(path: Path, report_id: str, author: str, body: str) -> NotebookResponse:
    updated_at = datetime.now(timezone.utc)
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO report_notebooks (report_id, author, body, updated_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(report_id, author) DO UPDATE
               SET body=excluded.body, updated_at=excluded.updated_at""",
            (report_id, author, body, updated_at.isoformat()),
        )
    return NotebookResponse(
        report_id=report_id, author=author, body=body, updated_at=updated_at,
    )


def get_media_path(path: Path, username: str, role: str, report_id: str) -> Path | None:
    with _connect(path) as connection:
        row = connection.execute(
            """SELECT media_path FROM reports
               WHERE report_id=? AND
                     (owner=? OR (?='supervisor' AND workflow_status IN ('submitted','in_review','reviewed') AND reviewer=?))""",
            (report_id, username, role, username),
        ).fetchone()
    return Path(row[0]) if row and row[0] else None


def get_profile(path: Path, username: str, role: str) -> ProfileResponse:
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT display_name, title FROM profiles WHERE username=?", (username,)
        ).fetchone()
    if row:
        return ProfileResponse(username=username, role=role, display_name=row[0], title=row[1])
    display_name = "Review Supervisor" if role == "supervisor" else "Media Analyst"
    title = "Senior Reviewer" if role == "supervisor" else "Analyst"
    return ProfileResponse(username=username, role=role, display_name=display_name, title=title)


def update_profile(path: Path, username: str, role: str, display_name: str, title: str) -> ProfileResponse:
    with _connect(path) as connection:
        connection.execute(
            """INSERT INTO profiles (username, display_name, title) VALUES (?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET display_name=excluded.display_name, title=excluded.title""",
            (username, display_name, title),
        )
    return ProfileResponse(
        username=username, role=role, display_name=display_name, title=title,
    )
