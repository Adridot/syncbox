import { HardDrive, Settings2, FolderOpen, Link2, Music, Database, Key, Save } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function SettingsPage() {
  return (
    <div className="flex-1 h-full overflow-y-auto p-6 md:p-8 w-full max-w-5xl mx-auto">
      
      <div className="flex items-center justify-between mb-8">
        <div>
          <h2 className="text-2xl md:text-3xl font-bold text-on-surface mb-1">Configuration & Settings</h2>
          <p className="text-sm text-on-surface-variant">Manage connections, paths, and metadata rules.</p>
        </div>
        <button className="bg-primary text-white px-5 py-2 rounded text-sm font-bold shadow-[0_4px_12px_rgba(0,112,255,0.3)] hover:scale-[1.02] transition-transform flex items-center gap-2">
          <Save size={18} />
          Save Changes
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Main Settings Column */}
        <div className="lg:col-span-8 flex flex-col gap-8">
          
          {/* Integrations Section */}
          <section className="bg-surface-container-high border border-outline-variant rounded-xl p-6">
            <h3 className="font-bold text-lg text-on-surface flex items-center gap-2 mb-6">
              <Link2 className="text-primary" size={20} />
              Platform Integrations
            </h3>
            
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-bold text-on-surface mb-2">Spotify Client ID</label>
                <div className="flex gap-3">
                  <input 
                    type="password" 
                    defaultValue="a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p"
                    className="w-full bg-surface-container border border-outline rounded py-2 px-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm font-mono"
                  />
                  <button className="px-4 py-2 border border-outline bg-surface rounded hover:border-primary transition-colors text-on-surface text-sm font-semibold whitespace-nowrap">
                    Re-Auth
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-on-surface mb-2">Spotify Client Secret</label>
                <div className="flex gap-3">
                  <input 
                    type="password" 
                    defaultValue="********************************"
                    className="w-full bg-surface-container border border-outline rounded py-2 px-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm font-mono"
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-outline-variant">
                <label className="block text-sm font-bold text-on-surface mb-2">Deemix ARL (Token)</label>
                <div className="flex gap-3">
                  <input 
                    type="password" 
                    defaultValue="1a2b3c4d5e6f7g8h9i0j1k2l3m4n5o6p7q8r9s0t1u2v3w4x5y6z"
                    className="w-full bg-surface-container border border-outline rounded py-2 px-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm font-mono"
                  />
                </div>
                <p className="text-xs text-on-surface-variant mt-2">Required for lossless audio downloading.</p>
              </div>
            </div>
          </section>

          {/* Paths Section */}
          <section className="bg-surface-container-high border border-outline-variant rounded-xl p-6">
            <h3 className="font-bold text-lg text-on-surface flex items-center gap-2 mb-6">
              <FolderOpen className="text-secondary" size={20} />
              Local Directories & Paths
            </h3>
            
            <div className="space-y-6">
              <div>
                <label className="block text-sm font-bold text-on-surface mb-2">Rekordbox XML Database Path</label>
                <div className="flex gap-3">
                  <input 
                    type="text" 
                    defaultValue="/Users/adrien/Documents/Rekordbox/rekordbox.xml"
                    className="w-full bg-surface-container border border-outline rounded py-2 px-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm font-mono"
                  />
                  <button className="px-3 py-2 border border-outline bg-surface rounded hover:border-primary transition-colors text-on-surface">
                    <FolderOpen size={18} />
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-sm font-bold text-on-surface mb-2">Master Library Directory (Root)</label>
                <div className="flex gap-3">
                  <input 
                    type="text" 
                    defaultValue="/Volumes/DJ_MASTER/Library/"
                    className="w-full bg-surface-container border border-outline rounded py-2 px-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm font-mono"
                  />
                  <button className="px-3 py-2 border border-outline bg-surface rounded hover:border-primary transition-colors text-on-surface">
                    <FolderOpen size={18} />
                  </button>
                </div>
                <p className="text-xs text-on-surface-variant mt-2">Where all new downloads will be sorted and grouped by genre.</p>
              </div>
            </div>
          </section>

          {/* Tag Mapping Section */}
          <section className="bg-surface-container-high border border-outline-variant rounded-xl p-0 overflow-hidden">
            <div className="p-6 border-b border-outline-variant flex items-center justify-between">
              <h3 className="font-bold text-lg text-on-surface flex items-center gap-2">
                <Database className="text-tertiary" size={20} />
                Playlist Rules (Auto-Tagging)
              </h3>
              <button className="px-3 py-1.5 border border-outline bg-surface rounded hover:border-primary transition-colors text-on-surface text-sm font-semibold">
                + New Rule
              </button>
            </div>
            
            <div className="divide-y divide-outline-variant bg-surface-container">
              
              {/* Mapping 1 */}
              <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded bg-primary/10 flex items-center justify-center shrink-0">
                    <Music className="text-primary" size={18} />
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-on-surface">Tech House Essentials</h4>
                    <span className="text-xs text-on-surface-variant font-mono">Spotify Playlist</span>
                  </div>
                </div>
                
                <div className="flex items-center gap-2 flex-wrap md:justify-end">
                  <span className="text-xs font-mono text-on-surface-variant mr-2">APPLY TAGS:</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Tech House</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Peak Time</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Club</span>
                </div>
              </div>

              {/* Mapping 2 */}
              <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded bg-secondary/10 flex items-center justify-center shrink-0">
                    <Music className="text-secondary" size={18} />
                  </div>
                  <div>
                    <h4 className="font-bold text-sm text-on-surface">Underground Deep</h4>
                    <span className="text-xs text-on-surface-variant font-mono">Spotify Playlist</span>
                  </div>
                </div>
                
                <div className="flex items-center gap-2 flex-wrap md:justify-end">
                  <span className="text-xs font-mono text-on-surface-variant mr-2">APPLY TAGS:</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Deep House</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Warmup</span>
                  <span className="px-2 py-1 bg-surface-variant border border-outline text-on-surface text-xs font-bold rounded">Hypnotic</span>
                </div>
              </div>

            </div>
          </section>

        </div>

        {/* Right Sidebar */}
        <div className="lg:col-span-4 flex flex-col gap-6">
          
          <div className="bg-surface-container-high border border-outline-variant rounded-xl p-6">
            <h3 className="font-bold text-lg text-on-surface flex items-center gap-2 mb-4">
              <Settings2 className="text-on-surface-variant" size={20} />
              Sync Preferences
            </h3>
            
            <div className="space-y-4">
              
              <label className="flex items-start gap-3 cursor-pointer group">
                <input type="checkbox" defaultChecked className="mt-1 rounded border-outline-variant bg-surface accent-primary w-4 h-4 shrink-0" />
                <div>
                  <span className="block text-sm font-bold text-on-surface group-hover:text-primary transition-colors">Auto-Sync on App Launch</span>
                  <span className="block text-xs text-on-surface-variant mt-0.5">Check for playlist updates immediately.</span>
                </div>
              </label>

              <label className="flex items-start gap-3 cursor-pointer group">
                <input type="checkbox" defaultChecked className="mt-1 rounded border-outline-variant bg-surface accent-primary w-4 h-4 shrink-0" />
                <div>
                  <span className="block text-sm font-bold text-on-surface group-hover:text-primary transition-colors">Overwrite Local Metadata</span>
                  <span className="block text-xs text-on-surface-variant mt-0.5">Prioritize Spotify metadata over your local ID3 tags automatically.</span>
                </div>
              </label>

              <label className="flex items-start gap-3 cursor-pointer group">
                <input type="checkbox" className="mt-1 rounded border-outline-variant bg-surface accent-primary w-4 h-4 shrink-0" />
                <div>
                  <span className="block text-sm font-bold text-on-surface group-hover:text-primary transition-colors">Embed Artwork</span>
                  <span className="block text-xs text-on-surface-variant mt-0.5">Download Hi-Res 1000x1000 artwork via Deemix and embed it into FLAC.</span>
                </div>
              </label>

            </div>
          </div>

          <div className="bg-surface-container border border-outline-variant rounded-xl p-6 relative overflow-hidden">
             <div className="absolute top-0 left-0 w-1 h-full bg-error"></div>
             <h3 className="font-bold text-base text-on-surface mb-2">Danger Zone</h3>
             <p className="text-xs text-on-surface-variant mb-4">Resetting settings will log you out of all integrations and remove path configurations.</p>
             <button className="px-4 py-2 bg-error/10 text-error border border-error/30 hover:bg-error/20 rounded font-bold text-xs transition-colors w-full">
               Reset All Configurations
             </button>
          </div>

        </div>

      </div>
    </div>
  );
}
