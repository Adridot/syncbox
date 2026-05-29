import { LayoutDashboard, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import Link from 'next/link';

export default function DashboardPage() {
  return (
    <div className="h-full overflow-y-auto p-6 md:p-8 max-w-7xl mx-auto w-full">
      <div className="mb-8">
        <h2 className="text-2xl md:text-3xl font-bold text-on-surface mb-2">Dashboard</h2>
        <p className="text-sm text-on-surface-variant">Overview of your Rekordbox sync status and library health.</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {/* Stat Cards */}
        <div className="bg-surface-container-high border border-outline-variant p-5 rounded-xl hover:border-primary transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
              <CheckCircle2 className="text-primary" size={20} />
            </div>
            <h3 className="font-semibold text-sm text-on-surface-variant uppercase tracking-wider">Synced Playlists</h3>
          </div>
          <div className="text-3xl font-bold text-on-surface">14</div>
        </div>
        
        <div className="bg-surface-container-high border border-outline-variant p-5 rounded-xl hover:border-primary transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-secondary/10 flex items-center justify-center">
              <RefreshCw className="text-secondary" size={20} />
            </div>
            <h3 className="font-semibold text-sm text-on-surface-variant uppercase tracking-wider">Pending Syncs</h3>
          </div>
          <div className="text-3xl font-bold text-on-surface">3</div>
        </div>

        <div className="bg-surface-container-high border border-outline-variant p-5 rounded-xl hover:border-primary transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-tertiary/10 flex items-center justify-center">
              <AlertTriangle className="text-tertiary" size={20} />
            </div>
            <h3 className="font-semibold text-sm text-on-surface-variant uppercase tracking-wider">Conflicts</h3>
          </div>
          <div className="text-3xl font-bold text-on-surface">1</div>
        </div>

        <div className="bg-surface-container-high border border-outline-variant p-5 rounded-xl hover:border-primary transition-colors">
          <div className="flex items-center gap-3 mb-3">
            <div className="w-10 h-10 rounded-full bg-surface-variant flex items-center justify-center">
              <LayoutDashboard className="text-on-surface-variant" size={20} />
            </div>
            <h3 className="font-semibold text-sm text-on-surface-variant uppercase tracking-wider">Total Tracks</h3>
          </div>
          <div className="text-3xl font-bold text-on-surface">4,521</div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface-container border border-outline-variant rounded-xl p-6">
          <h3 className="font-bold text-lg mb-4 text-on-surface">Recent Activity</h3>
          <div className="space-y-4">
            <div className="border-l-2 border-primary pl-4 py-1">
              <p className="text-sm font-semibold text-on-surface">Tech House Essentials synced</p>
              <p className="text-xs text-on-surface-variant mt-1">2 hours ago • Added 5 tracks</p>
            </div>
            <div className="border-l-2 border-outline-variant pl-4 py-1">
              <p className="text-sm font-semibold text-on-surface">Wedding Gig - Oct 26 created</p>
              <p className="text-xs text-on-surface-variant mt-1">4 hours ago</p>
            </div>
            <div className="border-l-2 border-secondary pl-4 py-1">
              <p className="text-sm font-semibold text-on-surface">Connected to Deemix successfully</p>
              <p className="text-xs text-on-surface-variant mt-1">Yesterday at 14:30</p>
            </div>
             <div className="border-l-2 border-tertiary pl-4 py-1">
              <p className="text-sm font-semibold text-on-surface">Metadata conflict on Pop Dance</p>
              <p className="text-xs text-on-surface-variant mt-1">Yesterday at 10:15</p>
            </div>
          </div>
        </div>

        <div className="bg-surface-container border border-outline-variant rounded-xl p-6 flex flex-col">
          <h3 className="font-bold text-lg mb-4 text-on-surface">System Status</h3>
          <div className="space-y-4 flex-1">
            <div className="flex justify-between items-center bg-surface-container-high p-3 rounded border border-outline-variant">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-secondary shadow-[0_0_8px_var(--color-secondary)]"></div>
                <span className="text-sm font-semibold text-on-surface">Spotify OAuth</span>
              </div>
              <span className="text-xs font-mono text-on-surface-variant bg-surface-variant px-2 py-1 rounded">CONNECTED</span>
            </div>
            
            <div className="flex justify-between items-center bg-surface-container-high p-3 rounded border border-outline-variant">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]"></div>
                <span className="text-sm font-semibold text-on-surface">Rekordbox Local DB</span>
              </div>
              <span className="text-xs font-mono text-on-surface-variant bg-surface-variant px-2 py-1 rounded">HEALTHY</span>
            </div>

            <div className="flex justify-between items-center bg-surface-container-high p-3 rounded border border-outline-variant">
              <div className="flex items-center gap-3">
                <div className="w-2 h-2 rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]"></div>
                <span className="text-sm font-semibold text-on-surface">Deemix Integration</span>
              </div>
              <span className="text-xs font-mono text-on-surface-variant bg-surface-variant px-2 py-1 rounded">V2024.1.0</span>
            </div>
          </div>
          
          <Link href="/downloads" className="mt-4 w-full bg-surface-container-high border border-outline hover:border-primary text-center py-2 rounded text-sm font-bold text-on-surface transition-colors">
            Check Download Queue
          </Link>
        </div>
      </div>
    </div>
  );
}
