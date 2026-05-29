'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  LayoutDashboard, 
  Library, 
  CalendarDays, 
  RefreshCw, 
  Settings, 
  Search, 
  Wifi, 
  CircleUser 
} from 'lucide-react';
import { cn } from '@/lib/utils';
import Image from 'next/image';

export function LayoutWrapper({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  const isLibraryActive = pathname === '/' || pathname.startsWith('/playlist');

  return (
    <div className="flex h-screen w-full overflow-hidden flex-col md:flex-row bg-background text-on-surface font-sans">
      {/* Sidebar */}
      <nav className="border-r border-outline-variant w-full md:w-64 flex-shrink-0 flex flex-col z-50 h-16 md:h-full overflow-y-auto hidden md:flex">
        <div className="p-6">
          <div className="flex items-center gap-2 mb-8">
            <div className="w-8 h-8 rounded bg-primary flex items-center justify-center font-bold text-white text-lg">
              P
            </div>
            <div>
              <h1 className="font-bold text-lg tracking-tight leading-none">Pro <span className="text-primary">Studio</span></h1>
            </div>
          </div>

          <ul className="space-y-1">
            <li>
              <Link 
                href="/dashboard"
                className={cn(
                  "flex items-center gap-3 p-3 rounded-r transition-colors group font-medium",
                  pathname === '/dashboard' 
                    ? "bg-surface-container-high text-primary border-l-2 border-primary -ml-[2px]" 
                    : "text-on-surface-variant hover:text-on-surface"
                )}
              >
                <LayoutDashboard size={20} />
                <span className="text-sm">Dashboard</span>
              </Link>
            </li>
            <li>
              <Link 
                href="/"
                className={cn(
                  "flex items-center gap-3 p-3 rounded-r transition-colors group font-medium",
                  isLibraryActive 
                    ? "bg-surface-container-high text-primary border-l-2 border-primary -ml-[2px]" 
                    : "text-on-surface-variant hover:text-on-surface"
                )}
              >
                <Library size={20} />
                <span className="text-sm">My Library</span>
              </Link>
            </li>
            <li>
              <Link 
                href="/events"
                className={cn(
                  "flex items-center gap-3 p-3 rounded-r transition-colors group font-medium",
                  pathname === '/events' 
                    ? "bg-surface-container-high text-primary border-l-2 border-primary -ml-[2px]" 
                    : "text-on-surface-variant hover:text-on-surface"
                )}
              >
                <CalendarDays size={20} />
                <span className="text-sm">Events</span>
              </Link>
            </li>
            <li>
              <Link 
                href="/downloads"
                className={cn(
                  "flex items-center gap-3 p-3 rounded-r transition-colors group font-medium",
                  pathname === '/downloads' || pathname === '/conflict'
                    ? "bg-surface-container-high text-primary border-l-2 border-primary -ml-[2px]" 
                    : "text-on-surface-variant hover:text-on-surface"
                )}
              >
                <RefreshCw size={20} />
                <span className="text-sm">Sync Hub</span>
              </Link>
            </li>
            <li>
              <Link 
                href="/settings"
                className={cn(
                  "flex items-center gap-3 p-3 rounded-r transition-colors group font-medium",
                  pathname === '/settings' 
                    ? "bg-surface-container-high text-primary border-l-2 border-primary -ml-[2px]" 
                    : "text-on-surface-variant hover:text-on-surface"
                )}
              >
                <Settings size={20} />
                <span className="text-sm">Settings</span>
              </Link>
            </li>
          </ul>
        </div>

        <div className="mt-auto p-6 border-t border-outline-variant">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-2 h-2 rounded-full bg-secondary shadow-[0_0_8px_var(--color-secondary)]"></div>
            <span className="text-xs text-on-surface-variant">Spotify Connected</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]"></div>
            <span className="text-xs text-on-surface-variant">Rekordbox Live</span>
          </div>
        </div>
      </nav>
      
      <div className="flex-1 flex flex-col h-full overflow-hidden bg-surface">
        {/* Topbar */}
        <header className="h-16 border-b border-outline-variant flex items-center justify-between px-8 bg-surface z-40 shrink-0">
          <div className="flex items-center gap-4">
            {/* The title from page can be handled there, but for global topbar we might just leave the search */}
          </div>
          
          <div className="flex items-center gap-4 ml-auto">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant" size={16} />
              <input 
                type="text" 
                placeholder="Search playlists..." 
                className="bg-surface-container-high border border-outline rounded px-4 py-1.5 pl-9 text-sm w-64 focus:outline-none focus:border-primary transition-colors text-on-surface"
              />
            </div>
            <button className="bg-primary text-white px-4 py-1.5 rounded text-sm font-semibold shadow-[0_4px_12px_rgba(0,112,255,0.3)] hover:scale-[1.02] transition-transform">
              Sync All
            </button>
          </div>
        </header>
        
        <main className="flex-1 overflow-hidden relative">
          {children}
        </main>
      </div>
    </div>
  );
}
