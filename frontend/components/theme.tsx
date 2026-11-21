'use client';
import {useEffect, useState} from 'react';

export type Theme = 'light' | 'dark';

const THEME_KEY = 'deeptrace-theme';

export const themeInitScript = `(function(){try{var t=localStorage.getItem('${THEME_KEY}');if(t!=='light'&&t!=='dark'){t=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light';}document.documentElement.dataset.theme=t;}catch(e){document.documentElement.dataset.theme='light';}})();`;

function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>('light');
  useEffect(() => {
    setTheme(currentTheme());
    const observer = new MutationObserver(() => setTheme(currentTheme()));
    observer.observe(document.documentElement, {attributes: true, attributeFilter: ['data-theme']});
    return () => observer.disconnect();
  }, []);
  const choose = (next: Theme) => {
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch {}
  };
  return {theme, setTheme: choose, toggle: () => choose(currentTheme() === 'dark' ? 'light' : 'dark')};
}

export function ThemeToggle() {
  const {theme, toggle} = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button type="button" className="theme-toggle" onClick={toggle} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        {theme === 'dark'
          ? <><circle cx="12" cy="12" r="4.2" /><path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.6 1.6M17.1 17.1l1.6 1.6M5.3 18.7l1.6-1.6M17.1 6.9l1.6-1.6" /></>
          : <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z" />}
      </svg>
    </button>
  );
}
