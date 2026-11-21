# DeepTrace Next.js frontend

Next.js App Router + React + TypeScript. Styling is the custom CSS in
`app/globals.css` (indigo accent, navy workspace sidebar). See
[`docs/DESIGN_SYSTEM.md`](../docs/DESIGN_SYSTEM.md). FastAPI remains responsible for uploads, inference, reporting,
and token validation. No duplicate Next.js API routes are introduced.

## Development

Use Node.js 22.22.2+ (22 LTS), matching `.nvmrc` and the container image.
In this directory:

```bash
npm ci
cp .env.example .env.local
npm run dev
```

The development command uses Webpack because Next.js Turbopack requires native
SWC bindings that may be unavailable on some Apple Silicon installations.

Run the backend from its directory in another terminal:

```bash
cd ../backend
.venv/bin/uvicorn deeptrace.main:app --reload --port 8000
```

Workspace: http://localhost:3000. Login: http://localhost:3000/login/.
The local API default is http://localhost:8000. Use `localhost` consistently to
match the backend's allowed origin. Authentication-disabled mode is explicitly
labeled; real sign-in redirects to Cognito using Authorization Code + PKCE.

## Structure

- `app/`: page routes, root layout, shared stylesheet.
- `components/auth.tsx`: shared auth provider and session controls.
- `components/screening.tsx`: upload, local preview, and request state.
- `components/report.tsx`: typed report display and PDF export.
- `lib/report-pdf.ts`: private, browser-side PDF report generation.
- `lib/api.ts`: API origin, report types, and upload request.

## Checks and production build

```bash
npm test
npm run typecheck
npm run build
```

The lockfile pins installed dependencies. `.npmrc` keeps dependency resolution
consistent with the installer used to generate it. Vite is used only by Vitest;
Next.js is the application framework and development server.

## AWS container deployment

From this directory:

```bash
docker build --build-arg NEXT_PUBLIC_API_BASE_URL=https://your-api.example -t deeptrace-frontend .
```

The standalone Next.js image listens on port 3000. Deploy it separately from the
root backend Docker image. `NEXT_PUBLIC_API_BASE_URL` is public and baked into the
browser bundle at build time; rebuild when changing it. Do not put secrets in it.
Configure TLS, routing, and access restrictions to match the agency sandbox.

Backend settings:

```dotenv
DEEPTRACE_FRONTEND_ORIGINS=["https://your-frontend.example"]
DEEPTRACE_COGNITO_REDIRECT_URI=https://your-frontend.example/
```

Register that exact callback/sign-out URL in Cognito and enable the backend's
Cognito settings. Next.js serves the interface; FastAPI remains the authorization
boundary. Live Cognito and AWS deployment require environment-specific validation.
