import Image from 'next/image';
import { Play, Pause, X, CheckCircle2, Clock, Music, Settings2, HardDrive } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils';

export default function DownloadsPage() {
  return (
    <div className="flex-1 h-full overflow-y-auto p-6 md:p-8 flex flex-col lg:flex-row gap-8 max-w-[1600px] mx-auto w-full">
      
      {/* Left Column: Download Queue */}
      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-6 gap-4">
          <div>
            <h2 className="text-2xl md:text-3xl font-bold text-on-surface mb-1">Download Queue</h2>
            <p className="text-sm text-on-surface-variant">Deemix Integration - 3 Active</p>
          </div>
          <div className="flex gap-3">
            <button className="px-4 py-2 bg-surface-container border border-outline rounded text-sm text-on-surface hover:border-primary transition-colors font-bold shadow-sm">
              PAUSE ALL
            </button>
            <button className="px-4 py-2 bg-primary text-white rounded text-sm font-bold shadow-[0_4px_12px_rgba(0,112,255,0.3)] hover:scale-[1.02] transition-transform">
              ADD URL
            </button>
          </div>
        </div>

        {/* Queue List */}
        <div className="flex flex-col gap-3">
          
          {/* Active Downloading */}
          <Link href="/conflict" className="bg-surface-container-high border border-primary/30 rounded-lg p-4 flex flex-col md:flex-row items-center gap-4 hover:border-primary transition-colors group relative overflow-hidden shadow-[0_0_15px_rgba(0,112,255,0.05)]">
            <div className="absolute left-0 top-0 h-full w-[45%] bg-primary/5 z-0 transition-all duration-500"></div>
            
            <div className="relative z-10 flex-shrink-0 w-16 h-16 rounded overflow-hidden border border-outline-variant shadow-lg bg-surface">
              <Image src="https://picsum.photos/seed/dld1/200/200" alt="Art" fill className="object-cover" referrerPolicy="no-referrer" />
            </div>
            
            <div className="relative z-10 flex-1 flex flex-col w-full min-w-0">
              <div className="flex justify-between items-start mb-2">
                <div className="min-w-0 pr-4">
                  <h3 className="text-base font-bold text-on-surface truncate">Midnight City (Eric Prydz Private Remix)</h3>
                  <p className="text-sm text-on-surface-variant truncate border-b border-dashed border-tertiary cursor-pointer inline-block mt-1">M83 (Conflict Detected)</p>
                </div>
                <span className="font-mono text-xs text-primary font-bold bg-primary/10 px-2 py-1 rounded shrink-0">45%</span>
              </div>
              
              <div className="w-full h-1.5 bg-surface-container rounded-full mt-1 overflow-hidden">
                <div className="h-full bg-primary rounded-full relative w-[45%]">
                  <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-r from-transparent via-white/20 to-transparent -translate-x-full animate-[shimmer_2s_infinite]"></div>
                </div>
              </div>
              
              <div className="flex justify-between items-center mt-3">
                <p className="font-mono text-[11px] text-on-surface-variant">2.5 MB/s • 14s remaining</p>
                <div className="flex bg-surface-container rounded p-[2px] border border-outline-variant">
                  <button className="px-2 py-0.5 rounded bg-surface-variant text-on-surface font-mono text-[10px] font-bold shadow-sm">FLAC</button>
                  <button className="px-2 py-0.5 rounded text-on-surface-variant hover:text-on-surface font-mono text-[10px] font-bold">MP3</button>
                </div>
              </div>
            </div>
            
            <div className="relative z-10 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button className="p-2 rounded-full hover:bg-surface-variant text-on-surface-variant hover:text-on-surface transition-colors">
                <Pause size={18} />
              </button>
              <button className="p-2 rounded-full hover:bg-error-container/20 text-on-surface-variant hover:text-error transition-colors">
                <X size={18} />
              </button>
            </div>
          </Link>

          {/* Queued */}
          <div className="bg-surface-container-high border border-outline-variant rounded-lg p-4 flex flex-col md:flex-row items-center gap-4 hover:border-outline transition-colors group">
            <div className="flex-shrink-0 w-16 h-16 rounded overflow-hidden border border-outline-variant shadow-lg bg-surface relative">
              <Image src="https://picsum.photos/seed/dld2/200/200" alt="Art" fill className="object-cover opacity-50 grayscale" referrerPolicy="no-referrer" />
              <div className="absolute inset-0 flex items-center justify-center bg-surface/50">
                <Clock className="text-on-surface-variant" size={20} />
              </div>
            </div>

            <div className="flex-1 flex flex-col w-full min-w-0">
              <div className="flex justify-between items-start mb-2">
                <div className="min-w-0 pr-4">
                  <h3 className="text-base font-bold text-on-surface-variant truncate">Opus</h3>
                  <p className="text-sm text-on-surface-variant truncate">Eric Prydz</p>
                </div>
                <span className="font-mono text-[10px] text-on-surface-variant font-bold bg-surface-variant px-2 py-1 rounded shrink-0">QUEUED</span>
              </div>
              <div className="flex justify-between items-center mt-3">
                <p className="font-mono text-[11px] text-on-surface-variant">Waiting...</p>
                <div className="flex bg-surface-container rounded p-[2px] border border-outline-variant">
                  <button className="px-2 py-0.5 rounded bg-surface-variant text-on-surface font-mono text-[10px] font-bold shadow-sm">FLAC</button>
                  <button className="px-2 py-0.5 rounded text-on-surface-variant hover:text-on-surface font-mono text-[10px] font-bold">MP3</button>
                </div>
              </div>
            </div>

            <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button className="p-2 rounded-full hover:bg-surface-variant text-on-surface-variant hover:text-on-surface transition-colors">
                <Play size={18} />
              </button>
              <button className="p-2 rounded-full hover:bg-error-container/20 text-on-surface-variant hover:text-error transition-colors">
                <X size={18} />
              </button>
            </div>
          </div>

          {/* Completed */}
          <div className="bg-surface-container-high border border-outline-variant rounded-lg p-4 flex flex-col md:flex-row items-center gap-4 hover:border-outline transition-colors relative overflow-hidden">
            <div className="absolute left-0 top-0 h-full w-1 bg-secondary z-0"></div>
            
            <div className="relative z-10 flex-shrink-0 w-16 h-16 rounded overflow-hidden border border-outline-variant shadow-lg bg-surface">
              <Image src="https://picsum.photos/seed/dld3/200/200" alt="Art" fill className="object-cover" referrerPolicy="no-referrer" />
            </div>
            
            <div className="relative z-10 flex-1 flex flex-col w-full min-w-0">
              <div className="flex justify-between items-start mb-2">
                <div className="min-w-0 pr-4">
                  <h3 className="text-base font-bold text-on-surface truncate">Strobe (Club Edit)</h3>
                  <p className="text-sm text-on-surface-variant truncate">deadmau5</p>
                </div>
                <span className="font-mono text-[10px] text-secondary font-bold bg-secondary/10 px-2 py-1 rounded shrink-0">DONE</span>
              </div>
              
              <div className="w-full h-1.5 bg-surface-container rounded-full mt-1 overflow-hidden">
                <div className="h-full bg-secondary rounded-full relative w-full"></div>
              </div>
              
              <div className="flex justify-between items-center mt-3">
                <p className="font-mono text-[11px] text-on-surface-variant">FLAC • 42.1 MB</p>
                <CheckCircle2 size={16} className="text-secondary" />
              </div>
            </div>
          </div>

        </div>
      </div>

      {/* Right Column: Global Settings */}
      <div className="w-full lg:w-80 flex-shrink-0 flex flex-col">
        <div className="bg-surface-container-high border border-outline-variant rounded-xl p-6 sticky top-6">
          <div className="flex items-center gap-3 mb-6 border-b border-outline-variant pb-4">
            <Settings2 className="text-on-surface-variant" size={20} />
            <h3 className="font-bold text-lg text-on-surface">Global Settings</h3>
          </div>
          
          <div className="space-y-6">
            {/* Concurrent Downloads */}
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm text-on-surface-variant">Max Concurrent</label>
                <span className="font-mono text-xs font-bold text-primary">3</span>
              </div>
              <input type="range" min="1" max="10" defaultValue="3" className="w-full h-1 bg-surface-container rounded-lg appearance-none cursor-pointer accent-primary" />
              <div className="flex justify-between mt-2">
                <span className="font-mono text-[10px] text-on-surface-variant">1</span>
                <span className="font-mono text-[10px] text-on-surface-variant">10</span>
              </div>
            </div>

            {/* Speed Limit */}
            <div>
              <div className="flex justify-between items-center mb-3">
                <label className="text-sm text-on-surface-variant">Speed Limit</label>
                <span className="font-mono text-xs text-on-surface-variant">Unlimited</span>
              </div>
              <input type="range" min="0" max="100" defaultValue="100" className="w-full h-1 bg-surface-container rounded-lg appearance-none cursor-pointer accent-outline" />
            </div>

            {/* Default Format Preference */}
            <div className="pt-2">
              <label className="text-sm text-on-surface-variant mb-3 block">Default Format</label>
              <div className="grid grid-cols-3 gap-2">
                <button className="bg-surface-container border border-outline-variant text-on-surface-variant hover:border-outline font-mono text-[11px] font-bold py-2 rounded transition-colors">
                  MP3 128
                </button>
                <button className="bg-primary/10 border border-primary text-primary font-mono text-[11px] font-bold py-2 rounded">
                  MP3 320
                </button>
                <button className="bg-surface-container border border-outline-variant text-on-surface-variant hover:border-outline font-mono text-[11px] font-bold py-2 rounded transition-colors">
                  FLAC
                </button>
              </div>
            </div>

            {/* Storage Info */}
            <div className="pt-6 border-t border-outline-variant">
              <div className="flex justify-between items-center mb-3">
                <span className="text-sm text-on-surface-variant flex items-center gap-2">
                  <HardDrive size={16} /> Storage
                </span>
                <span className="font-mono text-xs text-on-surface font-bold">124 GB free</span>
              </div>
              <div className="w-full h-1.5 bg-surface-container rounded-full overflow-hidden">
                <div className="h-full bg-outline-variant rounded-full w-[75%]"></div>
              </div>
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
