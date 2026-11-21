import type { Metadata } from 'next';
import { AuthProvider } from '../components/auth';
import { themeInitScript } from '../components/theme';
import './globals.css';
export const metadata: Metadata = {
  title: 'DeepTrace | Media screening',
  description: 'Advisory audio and video deepfake screening',
  icons: { icon: [{ url: '/icon.svg', type: 'image/svg+xml' }] },
};
export default function Layout({children}: {children: React.ReactNode}) {
  return (
    <html lang="en" data-scroll-behavior="smooth" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
      </head>
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
