'use client';

import { useState } from 'react';
import { ListMusic, MoreHorizontal, Plus, AlertCircle, X, ChevronDown, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import Link from 'next/link';

const mockTracks = [
  { id: 1, title: 'Deep Tech Journey - Original Mix', isNew: true, artist: 'Artex Barmix', album: 'Deep Tech Journey - Ori...', key: 'A+', bpm: 180, quality: 'FLAC', date: '09/20/2023' },
  { id: 2, title: 'Sunrise Groove', isConflict: true, artist: 'Artex Ewove', album: 'Sunrise Groove', key: 'B+', bpm: 180, quality: 'FLAC', date: '09/20/2023' },
  { id: 3, title: 'Nocturnal Beats', isNew: true, artist: 'Artex Barmix', album: 'Nocturnal Beats EP', key: 'A-', bpm: 120, quality: '320 kbps', date: '09/21/2023' },
  { id: 4, title: 'Deep Tech Journey - Instrumental', artist: 'Artex Barmix', album: 'Deep Tech Journey', key: 'A+', bpm: 120, quality: '320 kbps', date: '09/21/2023' },
  { id: 5, title: 'Sunrise Groove - Extended', artist: 'Artex Ewove', album: 'Sunrise Groove', key: 'B+', bpm: 120, quality: 'FLAC', date: '09/22/2023' },
  { id: 6, title: 'The Zeint', artist: 'Steven Dameds', album: 'The Zeint EP', key: 'A+', bpm: 130, quality: '320 kbps', date: '09/25/2023' },
  { id: 7, title: 'Alcturnal Beats', artist: 'Booten Gaifiein', album: 'Nocturnal Beats EP', key: 'A+', bpm: 100, quality: '320 kbps', date: '09/25/2023' },
];

export default function PlaylistPage() {
  const [selectedTracks, setSelectedTracks] = useState<number[]>([1]); // First track selected mock

  return (
    <div className="flex h-full w-full overflow-hidden">
      {/* Main Table Area */}
      <div className="flex-1 flex flex-col min-w-0 border-r border-outline-variant bg-surface">
        
        {/* Context Header */}
        <div className="px-8 py-5 border-b border-outline-variant bg-surface flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <ListMusic className="text-primary" />
            <h2 className="text-xl font-bold text-on-surface">Playlist: &quot;Tech House Essentials&quot;</h2>
          </div>
          <div className="flex items-center gap-3">
            <button className="flex items-center gap-2 px-3 py-1.5 rounded border border-outline text-on-surface hover:border-primary transition-colors">
              <MoreHorizontal size={18} />
            </button>
            <button className="flex items-center gap-2 px-4 py-1.5 rounded bg-surface-container border border-outline hover:border-primary text-on-surface font-semibold transition-colors text-sm">
              <Plus size={18} />
              Add Tracks
            </button>
          </div>
        </div>

        {/* Data Table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-left border-collapse whitespace-nowrap">
            <thead className="sticky top-0 bg-surface-container-high z-10 border-b border-outline-variant font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
              <tr>
                <th className="py-3 px-6 w-12 text-center">
                  <input type="checkbox" className="rounded border-outline-variant bg-surface accent-primary" />
                </th>
                <th className="py-3 px-4 w-16 text-right">No.</th>
                <th className="py-3 px-4">Title</th>
                <th className="py-3 px-4">Artist</th>
                <th className="py-3 px-4">Album</th>
                <th className="py-3 px-4 w-20 text-center">Key</th>
                <th className="py-3 px-4 w-20 text-center">BPM</th>
                <th className="py-3 px-4 w-28">Quality</th>
              </tr>
            </thead>
            <tbody className="text-sm divide-y divide-outline-variant/50">
              {mockTracks.map((track) => {
                const isSelected = selectedTracks.includes(track.id);

                return (
                  <tr 
                    key={track.id} 
                    className={cn(
                      "transition-all cursor-pointer group border-l-2",
                      isSelected 
                        ? "bg-primary/5 hover:bg-primary/10 border-primary" 
                        : "bg-surface hover:bg-surface-container-high border-transparent",
                      track.isConflict && "hover:bg-error-container/10 border-l-error-container"
                    )}
                    onClick={() => {
                      if (isSelected) {
                        setSelectedTracks(selectedTracks.filter(id => id !== track.id));
                      } else {
                        setSelectedTracks([...selectedTracks, track.id]);
                      }
                    }}
                  >
                    <td className="py-3 px-6 text-center">
                      <input 
                        type="checkbox" 
                        checked={isSelected}
                        onChange={() => {}}
                        className="rounded border-outline-variant bg-surface accent-primary" 
                      />
                    </td>
                    <td className="py-3 px-4 text-right text-on-surface-variant font-mono text-xs">{track.id}</td>
                    <td className="py-3 px-4 font-bold text-on-surface">
                      <div className="flex items-center gap-2">
                        {track.title}
                        {track.isNew && <span className="px-1.5 py-0.5 rounded-sm bg-secondary text-black font-mono text-[10px] leading-none uppercase font-bold tracking-wider">NEW</span>}
                        {track.isConflict && <span title="Metadata Conflict"><AlertCircle size={16} className="text-tertiary" /></span>}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-on-surface-variant group-hover:text-on-surface">{track.artist}</td>
                    <td className="py-3 px-4 text-on-surface-variant truncate max-w-[200px]">{track.album}</td>
                    <td className="py-3 px-4 font-mono text-xs text-center"><span className={isSelected ? 'text-primary font-bold' : 'text-on-surface'}>{track.key}</span></td>
                    <td className="py-3 px-4 font-mono text-xs text-center text-on-surface-variant">{track.bpm}</td>
                    <td className="py-3 px-4 font-mono text-xs text-on-surface-variant">{track.quality}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Lateral Drawer: Tagging */}
      <aside className="w-[320px] lg:w-[380px] bg-surface-container border-l border-outline-variant h-full flex flex-col shadow-2xl z-20 shrink-0">
        <div className="p-6 flex-1 overflow-y-auto">
          <div className="flex items-center justify-between mb-6">
            <h2 className="font-bold text-lg text-on-surface">Tagging Panel</h2>
            <Link href="/" className="text-on-surface-variant hover:text-on-surface transition-colors p-1 rounded-full hover:bg-surface-variant">
              <X size={20} />
            </Link>
          </div>

          {/* Selection Summary */}
          <div className="bg-primary/5 border border-primary/20 rounded p-4 mb-8">
            <div className="text-[10px] text-primary font-bold uppercase mb-1">Selected for Import</div>
            <div className="text-xl font-bold text-on-surface">{selectedTracks.length} New Tracks</div>
            <p className="text-xs text-on-surface-variant mt-1">Source: Tech House Essentials</p>
          </div>

          <div className="space-y-4">
            <div className="border border-outline-variant rounded bg-surface-container-low overflow-hidden">
              <button className="w-full flex items-center justify-between px-4 py-3 hover:bg-surface-variant/50 transition-colors text-left text-on-surface font-semibold text-sm">
                <span>Rekordbox Tags</span>
                <ChevronDown size={16} />
              </button>
              <div className="p-4 space-y-5 border-t border-outline-variant">
                
                <div>
                  <h4 className="font-mono text-xs text-on-surface-variant mb-3 uppercase tracking-wider">Energy</h4>
                  <div className="space-y-3 ml-2">
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Peak Time</span>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Warm Up</span>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Cool Down</span>
                    </label>
                  </div>
                </div>

                <div>
                  <h4 className="font-mono text-xs text-on-surface-variant mb-3 uppercase tracking-wider">Vibe</h4>
                  <div className="space-y-3 ml-2">
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" defaultChecked className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Euphoric</span>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Hypnotic</span>
                    </label>
                    <label className="flex items-center gap-3 cursor-pointer group">
                      <input type="checkbox" defaultChecked className="rounded border-outline-variant bg-surface accent-primary w-4 h-4" />
                      <span className="text-sm text-on-surface group-hover:text-primary transition-colors">Groovy</span>
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <button className="w-full flex items-center justify-between px-4 py-3 border border-outline-variant rounded bg-surface-container-low hover:bg-surface-variant/50 transition-colors text-left text-on-surface font-semibold text-sm">
              <span>Genre Details</span>
              <ChevronRight size={16} />
            </button>
            
            <button className="w-full flex items-center justify-between px-4 py-3 border border-outline-variant rounded bg-surface-container-low hover:bg-surface-variant/50 transition-colors text-left text-on-surface font-semibold text-sm">
              <span>Key Compatibility</span>
              <ChevronRight size={16} />
            </button>
          </div>
        </div>

        <div className="p-6 border-t border-outline-variant shrink-0 flex flex-col gap-3">
          <button className="w-full bg-primary text-white py-3 rounded-lg font-bold text-sm shadow-[0_4px_12px_rgba(0,112,255,0.3)] hover:scale-[1.02] transition-transform flex items-center justify-center gap-2">
            Import to Rekordbox
          </button>
          <Link href="/" className="w-full text-center bg-transparent text-on-surface-variant py-2 text-xs font-semibold hover:text-on-surface transition-colors">
            Cancel Selection
          </Link>
        </div>
      </aside>
    </div>
  );
}
