import { AlertTriangle, Disc, Radio, Check, CloudDownload, Merge, Info } from 'lucide-react';
import Image from 'next/image';
import Link from 'next/link';

export default function ConflictPage() {
  return (
    <div className="flex-1 w-full h-full overflow-y-auto pt-8 px-6 pb-12">
      <div className="max-w-5xl mx-auto">
        
        {/* Header Section */}
        <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h2 className="text-2xl md:text-3xl font-bold text-on-surface flex items-center gap-3">
              <AlertTriangle className="text-tertiary" size={28} />
              Metadata Conflict Detected
            </h2>
            <p className="text-sm text-on-surface-variant mt-2">Review differences between local Rekordbox data and incoming Spotify metadata.</p>
          </div>
          <div className="px-3 py-1.5 bg-surface-container-high border border-outline-variant rounded flex items-center gap-2 self-start md:self-auto">
            <span className="font-mono text-xs text-on-surface-variant uppercase tracking-wider">Track ID:</span>
            <span className="font-mono text-xs font-bold text-on-surface">SP-882910A</span>
          </div>
        </div>

        {/* Comparison Canvas */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 relative">
          {/* Center VS Badge (Desktop) */}
          <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 hidden lg:flex items-center justify-center w-10 h-10 rounded-full bg-surface border border-outline-variant shadow-lg">
            <span className="font-mono text-[10px] font-bold text-on-surface-variant">VS</span>
          </div>

          {/* Rekordbox Card (Original) */}
          <div className="bg-surface-container border border-outline-variant rounded-xl p-5 md:p-6 flex flex-col relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-surface-variant"></div>
            
            <div className="flex items-center gap-3 mb-6">
              <Disc className="text-on-surface-variant" size={20} />
              <h3 className="text-lg font-bold text-on-surface">Rekordbox (Original)</h3>
              <span className="ml-auto px-2 py-0.5 rounded bg-surface-variant text-on-surface-variant font-mono text-[10px] font-bold tracking-wider">LOCAL</span>
            </div>

            <div className="flex gap-4 mb-6">
              <div className="w-24 h-24 rounded bg-surface-container-high flex-shrink-0 border border-outline-variant overflow-hidden relative">
                <Image src="https://picsum.photos/seed/rbx1/200/200" alt="Album Art" fill className="object-cover" referrerPolicy="no-referrer" />
              </div>
              <div className="flex flex-col justify-center gap-2">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider">BPM / KEY</div>
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1.5 bg-surface-container-high rounded border border-outline-variant font-mono text-xs font-bold text-on-surface">124.0</span>
                  <span className="px-3 py-1.5 bg-surface-container-high rounded border border-outline-variant font-mono text-xs font-bold text-on-surface">8A</span>
                </div>
              </div>
            </div>

            <div className="space-y-3 flex-1">
              <div className="p-3 rounded bg-surface-container-high border border-outline-variant">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider mb-1">ARTIST</div>
                <div className="text-base text-on-surface">Daft Punk</div>
              </div>
              
              {/* Conflict Field */}
              <div className="p-3 rounded bg-tertiary/10 border border-tertiary/40">
                <div className="font-mono text-[10px] text-tertiary font-bold tracking-wider mb-1">TITLE (CONFLICT)</div>
                <div className="text-base text-on-surface">One More Time (Club Mix)</div>
              </div>
              
              <div className="p-3 rounded bg-surface-container-high border border-outline-variant">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider mb-1">DURATION</div>
                <div className="text-base text-on-surface font-mono">05:20</div>
              </div>
            </div>
          </div>

          {/* Spotify Card (New) */}
          <div className="bg-surface-container border border-outline-variant rounded-xl p-5 md:p-6 flex flex-col relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-secondary"></div>
            
            <div className="flex items-center gap-3 mb-6">
              <Radio className="text-secondary" size={20} />
              <h3 className="text-lg font-bold text-on-surface">Spotify (New)</h3>
              <span className="ml-auto px-2 py-0.5 rounded bg-secondary/20 text-secondary font-mono text-[10px] font-bold tracking-wider">CLOUD</span>
            </div>

            <div className="flex gap-4 mb-6">
              <div className="w-24 h-24 rounded bg-surface-container-high flex-shrink-0 border-2 border-secondary/50 overflow-hidden relative shadow-[0_0_15px_rgba(29,185,84,0.1)]">
                <Image src="https://picsum.photos/seed/spot1/200/200" alt="Album Art" fill className="object-cover" referrerPolicy="no-referrer" />
              </div>
              <div className="flex flex-col justify-center gap-2">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider">BPM / KEY</div>
                <div className="flex items-center gap-2">
                  <span className="px-3 py-1.5 bg-surface-container-high rounded border border-outline-variant font-mono text-xs font-bold text-on-surface">124.0</span>
                  <span className="px-3 py-1.5 bg-surface-container-high rounded border border-outline-variant font-mono text-xs font-bold text-on-surface">8A</span>
                </div>
              </div>
            </div>

            <div className="space-y-3 flex-1">
              <div className="p-3 rounded bg-surface-container-high border border-outline-variant">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider mb-1">ARTIST</div>
                <div className="text-base text-on-surface">Daft Punk</div>
              </div>
              
              {/* Resolution Field */}
              <div className="p-3 rounded bg-secondary/10 border border-secondary/40 relative">
                <div className="font-mono text-[10px] text-secondary font-bold tracking-wider mb-1">TITLE (NEW)</div>
                <div className="text-base text-on-surface">One More Time - Extended Mix</div>
                <Check className="absolute top-3 right-3 text-secondary" size={16} />
              </div>
              
              <div className="p-3 rounded bg-surface-container-high border border-outline-variant">
                <div className="font-mono text-[10px] text-on-surface-variant font-bold tracking-wider mb-1">DURATION</div>
                <div className="text-base text-on-surface font-mono">05:20</div>
              </div>
            </div>
          </div>
        </div>

        {/* Resolution Action Bar */}
        <div className="mt-8 p-4 md:p-5 bg-surface-container-high border border-outline-variant rounded-xl flex flex-col md:flex-row items-center justify-between gap-4 shadow-xl">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-surface-variant flex items-center justify-center shrink-0">
              <Info className="text-on-surface-variant" size={16} />
            </div>
            <span className="text-sm text-on-surface-variant">Select which metadata version to retain in your master library.</span>
          </div>
          
          <div className="flex flex-col sm:flex-row items-center gap-3 w-full md:w-auto">
            <Link href="/downloads" className="w-full sm:w-auto px-5 py-2.5 rounded border border-outline bg-transparent hover:bg-surface-variant text-on-surface font-semibold text-sm transition-colors text-center">
              Keep Original
            </Link>
            <Link href="/downloads" className="w-full sm:w-auto px-5 py-2.5 rounded border border-outline bg-transparent hover:bg-surface-variant text-on-surface font-semibold text-sm transition-colors flex items-center justify-center gap-2">
              <Merge size={16} />
              Merge Data
            </Link>
            <Link href="/downloads" className="w-full sm:w-auto px-6 py-2.5 rounded bg-primary text-white font-bold text-sm hover:scale-[1.02] shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform flex items-center justify-center gap-2">
              <CloudDownload size={18} />
              Update from Spotify
            </Link>
          </div>
        </div>

      </div>
    </div>
  );
}
