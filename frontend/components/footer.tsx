'use client';
import Link from 'next/link';
import {API_BASE} from '../lib/api';
import {BrandLogo} from './brand';

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <BrandLogo size={32} onDark />
          <p>Audio and video screening for investigative review.</p>
        </div>
        <div>
          <h3>Product</h3>
          <ul>
            <li><Link href="/detector">Detector</Link></li>
          </ul>
        </div>
        <div>
          <h3>Project</h3>
          <ul>
            <li><a href={`${API_BASE}/docs`} target="_blank" rel="noopener noreferrer">OpenAPI</a></li>
            <li><a href="https://github.com/tarbipyakurel21/deep_trace" target="_blank" rel="noopener noreferrer">GitHub</a></li>
            <li><Link href="/docs">Docs</Link></li>
            <li><Link href="/about">About</Link></li>
          </ul>
        </div>
      </div>
      <div className="site-footer-bottom">
        <span>AI Innovation Hub proof of concept.</span>
        <span>© 2026 Silicon Peaks, University of Southern Mississippi</span>
      </div>
    </footer>
  );
}
