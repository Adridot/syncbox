import type { Metadata } from 'next';
import { Hanken_Grotesk, JetBrains_Mono } from 'next/font/google';
import './globals.css';
import { LayoutWrapper } from '@/components/layout-wrapper';

const hanken = Hanken_Grotesk({
  subsets: ['latin'],
  variable: '--font-hanken',
});

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains',
});

export const metadata: Metadata = {
  title: 'Pro Studio',
  description: 'Rekordbox Sync Studio',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${hanken.variable} ${jetbrains.variable} dark`}>
      <body className="font-sans antialiased overflow-hidden selection:bg-primary-container selection:text-white">
        <LayoutWrapper>{children}</LayoutWrapper>
      </body>
    </html>
  );
}
