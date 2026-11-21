# DeepTrace backend

FastAPI service for screening uploaded audio and video for possible synthetic or
manipulated media. It returns model scores, observations, integrity metadata,
and an advisory report. It is not a forensic determination.

## Development

Requires Python 3.11+. `ffmpeg` and `ffprobe` are recommended for media
extraction and metadata.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn deeptrace.main:app --reload --port 8000
```

Upload a public or synthetic sample:

```bash
curl -F "file=@sample.wav" http://localhost:8000/v1/analyze
```

Environment variables use the `DEEPTRACE_` prefix. Copy `.env.example` when
creating a local configuration. Local development uses employee authentication
and a SQLite workflow database (`DEEPTRACE_DATABASE_URL`). Docker Compose runs
PostgreSQL and applies the schema on startup. `alembic upgrade head` is the
migration command when an existing database needs the workflow tables.

The workflow API stores findings, dispositions, report revisions, and audit
events separately from the advisory report payload. Mock detectors stay off
unless `DEEPTRACE_USE_MOCK_DETECTORS=true`, and their output is labeled as not
a model prediction.

## Tests

```bash
pytest
```

## Structure

| Location | Purpose |
| --- | --- |
| `deeptrace/` | API, media processing, authentication, schemas, and reporting |
| `deeptrace/analyzers/` | Model command adapters and result validation |
| `scripts/inference/` | Model-specific inference entrypoints |
| `tests/` | API, adapter, reporting, and benchmark checks |
| `docs/` | Architecture, models, reporting, roadmap, and evaluation |
| `experiments/` | Dataset preparation and cluster evaluation workflows |
| `vendor/` | Ignored, locally downloaded upstream model source code |

See [model setup](docs/models.md), [architecture](docs/architecture.md), and
[reporting guidance](docs/reporting-guidance.md) for implementation details.

## Container

From this directory:

```bash
docker build -t deeptrace-backend .
```

The image contains FFmpeg, the CPU inference dependencies, upstream model
source, checkpoints, and face-landmark data. It exposes port 8080 and runs
`deeptrace.main:app`. From the repository root, `docker compose up --build`
starts both the frontend and backend.
