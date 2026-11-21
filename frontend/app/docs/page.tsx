import type {Metadata} from 'next';
import {SiteFooter} from '../../components/footer';
import {SiteHeader} from '../../components/header';

export const metadata: Metadata = {
  title: 'API Documentation — DeepTrace',
  description: 'DeepTrace screening API endpoints',
};

export default function ApiDocsPage() {
  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <div className="app-shell">
        <SiteHeader />
        <main id="main" className="docs">

          <section className="docs-endpoint" id="analyze">
            <div className="docs-endpoint-head">
              <span className="method post">POST</span>
              <code>/v1/analyze</code>
            </div>
            <p>Upload one audio or video file. Returns an advisory report JSON.</p>
            <h2>Request</h2>
            <pre><code>{`curl -F "file=@sample.wav" \\
  -H "Authorization: Bearer <token>" \\
  http://localhost:8000/v1/analyze`}</code></pre>
            <ul>
              <li><code>multipart/form-data</code> field <code>file</code></li>
              <li>Bearer token required when authentication is enabled</li>
              <li>Common formats: MP4, MOV, AVI, MP3, WAV, M4A</li>
            </ul>
            <h2>Response</h2>
            <p><code>AdvisoryReport</code> with score, anomalies, component results, media SHA-256, methods, and limitations.</p>
          </section>

          <section className="docs-endpoint" id="auth-config">
            <div className="docs-endpoint-head">
              <span className="method get">GET</span>
              <code>/v1/auth/config</code>
            </div>
            <p>Public sign-in configuration for the frontend.</p>
            <pre><code>{`{
  "enabled": false,
  "domain": null,
  "client_id": null,
  "redirect_uri": null
}`}</code></pre>
          </section>

          <section className="docs-endpoint" id="health">
            <div className="docs-endpoint-head">
              <span className="method get">GET</span>
              <code>/health</code>
            </div>
            <p>Container health check.</p>
            <pre><code>{`curl http://localhost:8000/health`}</code></pre>
          </section>
        </main>
        <SiteFooter />
      </div>
    </>
  );
}
