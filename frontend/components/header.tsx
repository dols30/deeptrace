'use client';
import Link from 'next/link';
import {usePathname} from 'next/navigation';
import {useEffect, useState} from 'react';
import {AuthControls} from './auth';
import {useAuth} from './auth';
import {BrandLogo} from './brand';
import {ThemeToggle} from './theme';

export function SiteHeader() {
  const pathname = usePathname();
  const auth = useAuth();
  const [open, setOpen] = useState(false);

  useEffect(() => { setOpen(false); }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false); };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [open]);

  return (
    <header className="topbar">
      <div className="container topbar-inner">
        <BrandLogo />
        <nav id="site-nav" className={open ? 'top-nav open' : 'top-nav'} aria-label="Main">
          <Link className={pathname === '/' ? 'active' : undefined} href="/">Home</Link>
          <Link className={pathname.startsWith('/about') ? 'active' : undefined} href="/about">About</Link>
          {auth.token&&<Link className={pathname.startsWith('/detector') ? 'active' : undefined} href="/detector">Detector</Link>}
        </nav>
        <div className="topbar-actions">
          <ThemeToggle />
          <AuthControls />
          <button type="button" className="menu-toggle" aria-expanded={open} aria-controls="site-nav" onClick={() => setOpen(current => !current)}>
            {open ? 'Close' : 'Menu'}
          </button>
        </div>
      </div>
    </header>
  );
}
