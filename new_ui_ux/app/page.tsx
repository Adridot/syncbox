import Image from 'next/image';
import Link from 'next/link';
import { Plus, CheckCircle2, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';

const playlists = [
  {
    id: 'tech',
    title: 'Tech House Essentials',
    tracks: 150,
    updated: '2h ago',
    status: 'Synced',
    newCount: 5,
    progress: 100,
  },
  {
    id: 'summer',
    title: "Summer Vibes '24",
    tracks: 210,
    updated: '1d ago',
    status: 'Synced',
    newCount: 12,
    progress: 100,
  },
  {
    id: 'deep',
    title: 'Underground Deep',
    tracks: 85,
    updated: '3d ago',
    status: 'Out of Date',
    newCount: 0,
    progress: 66,
  },
  {
    id: 'grooves',
    title: 'Classic Grooves',
    tracks: 120,
    updated: '1w ago',
    status: 'Out of Date',
    newCount: 2,
    progress: 50,
  },
];

export default function LibraryPage() {
  return (
    <div className="h-full overflow-y-auto p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between mb-8 gap-4">
        <div>
          <h2 className="text-xl font-bold text-on-surface mb-1">
            Permanent Playlists Library
            <span className="text-on-surface-variant text-sm ml-2 font-normal">4 Playlists Active</span>
          </h2>
          <p className="text-sm text-on-surface-variant">Manage and sync your core collection.</p>
        </div>
        <button className="bg-surface-container-high border border-outline text-on-surface hover:border-primary px-4 py-2 rounded text-sm font-semibold flex items-center gap-1.5 transition-colors self-start md:self-auto">
          <Plus size={18} />
          Follow New Playlist
        </button>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 md:gap-6 pb-8">
        {playlists.map((playlist) => {
          const isSynced = playlist.status === 'Synced';
          return (
            <Link 
              href={`/playlist`} 
              key={playlist.id}
              className={cn(
                "bg-surface-container-high rounded-lg p-4 border flex flex-col transition-all group",
                isSynced 
                  ? "border-outline hover:border-primary" 
                  : "border-primary shadow-[0_0_15px_rgba(0,112,255,0.1)]"
              )}
            >
              {/* Artwork Grid */}
              <div className="relative aspect-square mb-4 rounded overflow-hidden bg-surface-container grid grid-cols-2 grid-rows-2 gap-[1px]">
                {/* Simulated images with picsum */}
                <div className="relative row-span-2 col-span-1 overflow-hidden">
                   <Image src={`https://picsum.photos/seed/${playlist.id}1/400/400`} alt="Cover" fill className="object-cover" referrerPolicy="no-referrer" />
                </div>
                <div className="relative overflow-hidden">
                   <Image src={`https://picsum.photos/seed/${playlist.id}2/400/400`} alt="Cover" fill className="object-cover" referrerPolicy="no-referrer" />
                </div>
                <div className="relative overflow-hidden">
                   <Image src={`https://picsum.photos/seed/${playlist.id}3/400/400`} alt="Cover" fill className="object-cover" referrerPolicy="no-referrer" />
                </div>

                {playlist.newCount > 0 && (
                  <div className="absolute top-2 right-2 bg-secondary text-black font-bold text-xs px-2 py-1 rounded-full z-10 shadow-sm">
                    +{playlist.newCount} NEW
                  </div>
                )}
              </div>

              {/* Info */}
              <div className="flex flex-col flex-grow">
                <h3 className="font-bold text-on-surface mb-1 truncate group-hover:text-primary transition-colors">
                  {playlist.title}
                </h3>
                <div className="text-xs text-on-surface-variant mb-4 opacity-80">
                  Last synced: {playlist.updated} • {playlist.tracks} tracks
                </div>

                {/* Status bar */}
                <div className="mt-auto pt-3 border-t border-outline-variant flex items-center justify-between">
                  <div className="text-xs text-on-surface-variant font-medium">
                    {!isSynced ? (
                      <span className="text-primary animate-pulse">Syncing...</span>
                    ) : (
                      "MATCH RATE"
                    )}
                  </div>
                  
                  <div className="w-24 h-1.5 bg-outline-variant rounded-full overflow-hidden">
                    <div 
                      className={cn("h-full rounded-full w-[95%]", isSynced ? "bg-secondary" : "bg-primary")} 
                    />
                  </div>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
