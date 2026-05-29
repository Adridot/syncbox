import Image from 'next/image';
import { Link2, Cpu, Trash2, AreaChart } from 'lucide-react';
import { cn } from '@/lib/utils';
import Link from 'next/link';

const temporaryPlaylists = [
  {
    id: 'wedding',
    title: 'Wedding Gig - Oct 26',
    tracks: 84,
    created: '2h ago',
    status: 'Ready to Sync',
  },
  {
    id: 'bash',
    title: 'Birthday Bash Mix',
    tracks: 120,
    created: 'Yesterday',
    status: 'Downloading...',
    newCount: 5,
  },
  {
    id: 'corporate',
    title: 'Corporate Event Q3',
    tracks: 36,
    created: 'Oct 12',
    status: 'Action Needed',
  },
];

export default function EventsPage() {
  return (
    <div className="h-full overflow-y-auto p-6 md:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h2 className="text-2xl md:text-3xl font-bold text-on-surface mb-1">Event Imports</h2>
        <p className="text-sm text-on-surface-variant">Manage temporary playlists for upcoming gigs.</p>
      </div>

      {/* Import Area */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-10">
        <div className="lg:col-span-2 bg-surface-container-high rounded-xl p-6 border border-outline-variant flex flex-col justify-between">
          <div>
            <h3 className="font-bold text-lg text-on-surface flex items-center mb-2">
              <Link2 className="mr-2 text-primary" size={20} />
              New Event Import
            </h3>
            <p className="text-sm text-on-surface-variant mb-6">Paste a Spotify or Apple Music URL to generate a temporary event playlist for analysis and syncing.</p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 items-center">
            <div className="relative flex-grow w-full">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Link2 className="text-on-surface-variant" size={16} />
              </div>
              <input 
                type="text" 
                placeholder="https://open.spotify.com/playlist/..." 
                className="w-full bg-surface-container border border-outline rounded py-2 pl-9 pr-4 text-on-surface focus:outline-none focus:border-primary transition-colors text-sm"
              />
            </div>
            <button className="bg-primary text-white font-bold text-sm px-6 py-2 rounded shadow-[0_4px_12px_rgba(0,112,255,0.3)] hover:scale-[1.02] transition-transform flex items-center whitespace-nowrap w-full sm:w-auto justify-center">
              <AreaChart className="mr-2" size={18} />
              Analyze Import
            </button>
          </div>
        </div>

        <div className="bg-surface-container-high rounded-xl p-6 border border-outline-variant flex flex-col justify-center items-center text-center">
          <div className="w-16 h-16 rounded-full bg-surface-container border border-outline flex items-center justify-center mb-4">
            <Cpu className="text-primary" size={32} />
          </div>
          <h4 className="font-bold text-lg text-on-surface">3 Active Events</h4>
          <p className="font-mono text-xs text-on-surface-variant mt-2 tracking-wider">240 TRACKS PENDING SYNC</p>
        </div>
      </div>

      {/* Playlists List */}
      <div>
        <h3 className="font-bold text-lg text-on-surface mb-4">Temporary Playlists</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {temporaryPlaylists.map((playlist) => (
            <div key={playlist.id} className="bg-surface-container-high rounded-lg p-4 border border-outline-variant flex flex-col group relative">
              <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button className="text-on-surface-variant hover:text-error transition-colors p-1 rounded-full hover:bg-error-container/20">
                  <Trash2 size={16} />
                </button>
              </div>
              
              <div className="flex items-start mb-4">
                <div className="w-16 h-16 bg-surface-container rounded border border-outline mr-4 flex-shrink-0 grid grid-cols-2 grid-rows-2 gap-[1px] p-[1px] relative">
                   {playlist.newCount && (
                     <div className="absolute -top-2 -right-2 bg-secondary text-black font-bold text-[10px] w-5 h-5 flex items-center justify-center rounded-full z-10 shadow-sm">
                       +{playlist.newCount}
                     </div>
                   )}
                   <div className="relative overflow-hidden"><Image src={`https://picsum.photos/seed/${playlist.id}1/100/100`} fill alt="art" className="object-cover" referrerPolicy="no-referrer" /></div>
                   <div className="relative overflow-hidden"><Image src={`https://picsum.photos/seed/${playlist.id}2/100/100`} fill alt="art" className="object-cover" referrerPolicy="no-referrer" /></div>
                   <div className="relative overflow-hidden"><Image src={`https://picsum.photos/seed/${playlist.id}3/100/100`} fill alt="art" className="object-cover" referrerPolicy="no-referrer" /></div>
                   <div className="relative overflow-hidden"><Image src={`https://picsum.photos/seed/${playlist.id}4/100/100`} fill alt="art" className="object-cover" referrerPolicy="no-referrer" /></div>
                </div>
                <div>
                  <h4 className="font-bold text-base text-on-surface leading-tight mb-1">{playlist.title}</h4>
                  <p className="font-mono text-xs text-on-surface-variant">Created {playlist.created}</p>
                </div>
              </div>
              
              <div className="flex justify-between items-center mt-auto border-t border-outline-variant pt-3">
                <span className="font-mono text-xs text-on-surface-variant">{playlist.tracks} Tracks</span>
                <span className={cn(
                  "font-mono text-[10px] uppercase font-bold tracking-wider px-2 py-1 rounded",
                  playlist.status === 'Ready to Sync' && "bg-primary/10 text-primary border border-primary/20",
                  playlist.status === 'Downloading...' && "bg-secondary/10 text-secondary border border-secondary/20",
                  playlist.status === 'Action Needed' && "bg-tertiary/10 text-tertiary border border-tertiary/20",
                )}>
                  {playlist.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
