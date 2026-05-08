import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useAppContext } from '../context/AppContext';
import { Play, Pause, RotateCcw, ChevronLeft, Clock, ShieldAlert, AlertTriangle, Activity } from 'lucide-react';

// Each .webm chunk is ~5 seconds of video
const CHUNK_DURATION_SEC = 5;

const levelColors: Record<string, string> = {
  HIGH: 'bg-red-500',
  MEDIUM: 'bg-orange-500',
  LOW: 'bg-yellow-400',
  NORMAL: 'bg-emerald-500',
};

const levelIcon: Record<string, any> = {
  HIGH: ShieldAlert,
  MEDIUM: AlertTriangle,
  LOW: Activity,
};

const PastSessionPlayer: React.FC = () => {
  const { activePastSession, pastSessionThreats, videoSeekRef, clearPastSession } = useAppContext();
  const videoRef = useRef<HTMLVideoElement>(null);
  const timelineRef = useRef<HTMLDivElement>(null);

  const [currentChunkIndex, setCurrentChunkIndex] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [actualDuration, setActualDuration] = useState(0);
  const [absoluteTime, setAbsoluteTime] = useState(0);

  const chunkFiles = activePastSession?.chunks?.length ? activePastSession.chunks
    : activePastSession?.batches?.length ? activePastSession.batches
    : activePastSession?.uploads || [];

  const totalChunks = chunkFiles.length;
  
  const estimatedTotalDuration = (totalChunks === 1 && actualDuration > 0)
    ? actualDuration
    : totalChunks * CHUNK_DURATION_SEC;

  // Build absolute time from chunk index + video currentTime
  const getAbsoluteTime = useCallback((chunkIdx: number, videoTime: number) => {
    if (totalChunks === 1) return videoTime;
    return chunkIdx * CHUNK_DURATION_SEC + videoTime;
  }, [totalChunks]);

  // Seek to a specific absolute time in seconds
  const seekToAbsolute = useCallback((absoluteSec: number) => {
    if (!activePastSession) return;
    
    if (totalChunks === 1) {
       const vid = videoRef.current;
       if (vid) vid.currentTime = Math.max(0, absoluteSec);
       return;
    }

    const chunkIdx = Math.min(
      Math.floor(absoluteSec / CHUNK_DURATION_SEC),
      totalChunks - 1
    );
    const timeInChunk = absoluteSec - chunkIdx * CHUNK_DURATION_SEC;

    if (chunkIdx !== currentChunkIndex) {
      // Loading a new chunk
      setCurrentChunkIndex(chunkIdx);
      // After the video loads, we'll seek to timeInChunk
      // via the onLoadedMetadata handler
      const vid = videoRef.current;
      if (vid) {
        vid.dataset.pendingSeek = String(timeInChunk);
      }
    } else {
      // Same chunk, just seek
      const vid = videoRef.current;
      if (vid) {
        vid.currentTime = Math.max(0, timeInChunk);
      }
    }
  }, [activePastSession, currentChunkIndex, totalChunks]);

  // Register seek function in context
  useEffect(() => {
    videoSeekRef.current = seekToAbsolute;
    return () => {
      videoSeekRef.current = null;
    };
  }, [seekToAbsolute, videoSeekRef]);

  // Load the current chunk into the video element
  useEffect(() => {
    const vid = videoRef.current;
    if (!vid || !activePastSession || chunkFiles.length === 0) return;

    const chunkFile = chunkFiles[currentChunkIndex];
    const src = `/live_video/${activePastSession.sessionId}/${chunkFile}`;
    vid.src = src;
    vid.load();
    setIsPlaying(false);
  }, [currentChunkIndex, activePastSession, chunkFiles]);

  const handleLoadedMetadata = () => {
    const vid = videoRef.current;
    if (!vid) return;
    const dur = vid.duration || CHUNK_DURATION_SEC;
    setDuration(dur);

    if (totalChunks === 1) {
      setActualDuration(dur);
    }

    // Apply pending seek if any
    const pendingSeek = vid.dataset.pendingSeek;
    if (pendingSeek) {
      vid.currentTime = parseFloat(pendingSeek);
      delete vid.dataset.pendingSeek;
    }
  };

  const handleTimeUpdate = () => {
    const vid = videoRef.current;
    if (!vid) return;
    const abs = getAbsoluteTime(currentChunkIndex, vid.currentTime);
    setCurrentTime(vid.currentTime);
    setAbsoluteTime(abs);
  };

  const handleEnded = () => {
    // Auto-advance to next chunk
    if (currentChunkIndex < totalChunks - 1) {
      setCurrentChunkIndex(prev => prev + 1);
      // Auto-play next chunk
      setTimeout(() => {
        videoRef.current?.play().catch(() => {});
        setIsPlaying(true);
      }, 100);
    } else {
      setIsPlaying(false);
    }
  };

  const handlePlayPause = () => {
    const vid = videoRef.current;
    if (!vid) return;
    if (vid.paused) {
      vid.play().catch(() => {});
      setIsPlaying(true);
    } else {
      vid.pause();
      setIsPlaying(false);
    }
  };

  const handleRestart = () => {
    setCurrentChunkIndex(0);
    setCurrentTime(0);
    setAbsoluteTime(0);
    setIsPlaying(false);
    const vid = videoRef.current;
    if (vid) vid.dataset.pendingSeek = '0';
  };

  const handleTimelineClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!timelineRef.current) return;
    const rect = timelineRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, x / rect.width));
    seekToAbsolute(pct * estimatedTotalDuration);
  };

  const formatTime = (secs: number) => {
    if (!isFinite(secs)) return '00:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: 'short', day: 'numeric',
        hour: '2-digit', minute: '2-digit',
      });
    } catch { return iso; }
  };

  if (!activePastSession) return null;

  const playheadPct = estimatedTotalDuration > 0
    ? (absoluteTime / estimatedTotalDuration) * 100
    : 0;

  const onlyAlerts = pastSessionThreats.filter(t => t.level !== 'NORMAL');

  return (
    <div className="relative h-full w-full bg-black flex flex-col">
      {/* Video area */}
      <div className="relative flex-1 min-h-0 bg-black">
        <video
          ref={videoRef}
          className="h-full w-full object-contain"
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onEnded={handleEnded}
          playsInline
        />

        {/* Top bar */}
        <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-3 py-2 bg-gradient-to-b from-black/80 to-transparent">
          <button
            onClick={clearPastSession}
            className="flex items-center space-x-1.5 text-xs text-slate-300 hover:text-white transition-colors"
          >
            <ChevronLeft size={14} />
            <span>Live</span>
          </button>
          <div className="flex items-center space-x-2">
            <Clock size={12} className="text-slate-400" />
            <span className="text-xs text-slate-300 font-mono">
              {formatDate(activePastSession.completedAt)}
            </span>
          </div>
          <div className="flex items-center space-x-1 text-[10px] text-slate-500 font-mono">
            <span>chunk {currentChunkIndex + 1}/{totalChunks}</span>
          </div>
        </div>

        {/* Playhead time overlay */}
        <div className="absolute bottom-2 right-3 bg-black/70 rounded px-2 py-0.5 text-xs font-mono text-slate-300 backdrop-blur-sm">
          {formatTime(absoluteTime)} / {formatTime(estimatedTotalDuration)}
        </div>
      </div>

      {/* Timeline bar with threat markers */}
      <div className="flex-shrink-0 px-3 py-2 bg-slate-900 border-t border-slate-800">
        <div
          ref={timelineRef}
          onClick={handleTimelineClick}
          className="relative h-8 w-full rounded-lg bg-slate-800 overflow-hidden cursor-crosshair border border-slate-700 mb-2"
        >
          {/* Progress fill */}
          <div
            className="absolute inset-y-0 left-0 bg-indigo-500/20 pointer-events-none"
            style={{ width: `${playheadPct}%` }}
          />

          {/* Threat markers */}
          {onlyAlerts.map((threat) => {
            const pct = estimatedTotalDuration > 0
              ? (threat.timestamp / estimatedTotalDuration) * 100
              : 0;
            const color = levelColors[threat.level] || 'bg-slate-500';
            return (
              <div
                key={threat.id}
                className={`absolute top-0 bottom-0 w-1 -translate-x-1/2 ${color} opacity-80 hover:opacity-100 transition-opacity cursor-pointer group`}
                style={{ left: `${Math.min(pct, 99)}%` }}
                onClick={(e) => {
                  e.stopPropagation();
                  seekToAbsolute(threat.timestamp);
                }}
                title={`${threat.level}: ${formatTime(threat.timestamp)} — ${threat.descriptor}`}
              >
                <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1 opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                  <div className="bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-[9px] text-white whitespace-nowrap shadow-xl">
                    {threat.level} @ {formatTime(threat.timestamp)}
                  </div>
                </div>
              </div>
            );
          })}

          {/* Playhead */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-white shadow-[0_0_4px_rgba(255,255,255,0.8)] pointer-events-none transition-all duration-75"
            style={{ left: `${playheadPct}%` }}
          />
        </div>

        {/* Controls */}
        <div className="flex items-center space-x-2">
          <button
            onClick={handleRestart}
            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition-all"
          >
            <RotateCcw size={14} />
          </button>
          <button
            onClick={handlePlayPause}
            className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-white transition-all shadow-lg shadow-indigo-500/25"
          >
            {isPlaying
              ? <Pause size={16} fill="currentColor" />
              : <Play size={16} fill="currentColor" />
            }
          </button>

          <div className="flex-1" />

          {/* Threat count pills */}
          {onlyAlerts.length > 0 && (
            <div className="flex items-center space-x-1.5">
              {(['HIGH', 'MEDIUM', 'LOW'] as const).map(lvl => {
                const count = onlyAlerts.filter(t => t.level === lvl).length;
                if (count === 0) return null;
                const Icon = levelIcon[lvl];
                const color = lvl === 'HIGH' ? 'text-red-400 bg-red-500/10 border-red-500/20'
                  : lvl === 'MEDIUM' ? 'text-orange-400 bg-orange-500/10 border-orange-500/20'
                  : 'text-yellow-400 bg-yellow-500/10 border-yellow-500/20';
                return (
                  <div key={lvl} className={`flex items-center space-x-1 rounded-full border px-2 py-0.5 ${color}`}>
                    <Icon size={10} />
                    <span className="text-[10px] font-bold">{count}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default PastSessionPlayer;
