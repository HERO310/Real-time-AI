import React, { useRef } from 'react';
import type { Threat } from '../types';
import { useAppContext } from '../context/AppContext';

interface TimelineProps {
  threats: Threat[];
  duration: number; // dynamically passed video duration
}

const Timeline: React.FC<TimelineProps> = ({ threats, duration }) => {
  const videoCurrentTime = 0;
  const setVideoSeekTime = (t: number) => console.log('seek', t);
  const timelineRef = useRef<HTMLDivElement>(null);

  const formatTime = (seconds: number) => {
    if (!isFinite(seconds) || isNaN(seconds)) return "00:00";
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const calculateLeft = (timestamp: number) => {
    const validDuration = isFinite(duration) && duration > 0 ? duration : 60;
    return `${(timestamp / validDuration) * 100}%`;
  };

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = Math.max(0, Math.min(1, x / rect.width));
    const validDuration = isFinite(duration) && duration > 0 ? duration : 60;
    const seekTime = percentage * validDuration;
    setVideoSeekTime(seekTime);
  };

  return (
    <div className="w-full flex flex-col select-none">
      <div className="mb-2 flex items-center justify-between text-xs font-medium text-slate-500">
        <span>00:00</span>
        <span className="uppercase tracking-widest text-[#6366f1] font-bold">Threat Timeline Activity</span>
        <span>{formatTime(duration)}</span>
      </div>

      <div 
        className="relative h-12 w-full rounded-xl bg-green-500 overflow-hidden cursor-crosshair border border-green-700"
        ref={timelineRef}
        onClick={handleTimelineClick}
      >
        {/* Placeholder text for thumbnails */}
        <div className="absolute inset-0 flex items-center justify-center text-sm font-semibold text-green-900 pointer-events-none z-0">
          time feed with thumbnails
        </div>

        {threats.map((threat) => {
          return (
            <div
              key={threat.id}
              className="absolute top-0 bottom-0 w-[8%] -translate-x-1/2 group transition-colors hover:bg-red-500 bg-red-600/90 z-10 flex items-center justify-center"
              style={{ left: calculateLeft(threat.timestamp) }}
              onClick={(e) => {
                e.stopPropagation();
                setVideoSeekTime(threat.timestamp);
              }}
            >
              <div className="opacity-0 group-hover:opacity-100 text-white text-xs font-bold transition-opacity">
                 {formatTime(threat.timestamp)}
              </div>
            </div>
          );
        })}

        {/* Playhead */}
        <div 
          className="absolute top-0 bottom-0 w-[2px] bg-black z-20 pointer-events-none transition-all duration-75"
          style={{ left: calculateLeft(videoCurrentTime) }}
        />
      </div>
    </div>
  );
};

export default Timeline;
