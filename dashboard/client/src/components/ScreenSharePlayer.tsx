import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useAppContext } from '../context/AppContext';
import { socketService } from '../services/socket';
import { Monitor, Square, Circle, Wifi, Radio, Zap, Shield } from 'lucide-react';

const CHUNK_DURATION_MS = 5000; // 5 seconds per chunk

const ScreenSharePlayer: React.FC = () => {
  const { activeSession, isScreenSharing, startScreenShare, stopScreenShare, videoSeekRef } = useAppContext();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunkIndexRef = useRef(0);
  const recordingCycleRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const activeSessionRef = useRef(activeSession);
  const [elapsed, setElapsed] = useState(0);
  const [hasStream, setHasStream] = useState(false);
  const elapsedRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [analysisMode, setAnalysisMode] = useState<'fast' | 'high_accuracy'>('fast');

  // DVR state memory
  const [isDvrMode, setIsDvrMode] = useState(false);
  const [, setDvrUrl] = useState<string | null>(null);
  const dvrRecorderRef = useRef<MediaRecorder | null>(null);
  const dvrChunksRef = useRef<BlobPart[]>([]);

  // Keep ref in sync with state
  useEffect(() => {
    activeSessionRef.current = activeSession;
  }, [activeSession]);

  const sendChunk = useCallback((blob: Blob) => {
    const currentIndex = chunkIndexRef.current;
    chunkIndexRef.current++;

    const session = activeSessionRef.current;
    const socket = socketService.getSocket();

    if (!socket || !session) {
      console.warn('[ScreenShare] No socket or session, cannot send chunk');
      return;
    }

    blob.arrayBuffer().then((buffer) => {
      socket.emit('video_chunk', {
        sessionId: session.id,
        chunkIndex: currentIndex,
        data: buffer,
      });
      console.log(`[ScreenShare] Sent chunk ${currentIndex} (${blob.size} bytes) for session=${session.id}`);
    });
  }, []);

  const startRecordingCycle = useCallback(() => {
    const stream = streamRef.current;
    if (!stream || !stream.active) return;

    const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
      ? 'video/webm;codecs=vp9'
      : 'video/webm';

    let chunks: BlobPart[] = [];

    const recorder = new MediaRecorder(stream, {
      mimeType,
      videoBitsPerSecond: 2_000_000,
    });

    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        chunks.push(e.data);
      }
    };

    recorder.onstop = () => {
      if (chunks.length > 0) {
        const blob = new Blob(chunks, { type: mimeType });
        if (blob.size > 0) {
          sendChunk(blob);
        }
        chunks = [];
      }

      // Schedule next cycle if stream is still active
      if (stream.active && streamRef.current === stream) {
        recordingCycleRef.current = setTimeout(() => {
          startRecordingCycle();
        }, 100);
      }
    };

    try {
      recorder.start();
      console.log('[ScreenShare] Recording cycle started');
    } catch (err) {
      console.error('[ScreenShare] Failed to start recorder:', err);
      return;
    }

    // Stop after CHUNK_DURATION_MS
    recordingCycleRef.current = setTimeout(() => {
      if (recorder.state === 'recording') {
        recorder.stop();
      }
    }, CHUNK_DURATION_MS);
  }, [sendChunk]);

  const handleStartShare = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { width: 1280, height: 720, frameRate: 15 },
        audio: false,
      });

      streamRef.current = stream;
      setHasStream(true);

      // DVR recorder (continuous recording with small timeslice for seek ability)
      const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9') ? 'video/webm;codecs=vp9' : 'video/webm';
      dvrRecorderRef.current = new MediaRecorder(stream, { mimeType, videoBitsPerSecond: 2_000_000 });
      dvrRecorderRef.current.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) dvrChunksRef.current.push(e.data);
      };
      dvrRecorderRef.current.start(1000);

      // Start screen share session (this emits start_session socket event)
      startScreenShare(analysisMode);
      chunkIndexRef.current = 0;
      setElapsed(0);

      // Start elapsed timer
      elapsedRef.current = setInterval(() => {
        setElapsed(prev => prev + 1);
      }, 1000);

      // Handle stream ending (user clicks browser's "Stop sharing")
      stream.getVideoTracks()[0].addEventListener('ended', () => {
        handleStopShare();
      });
    } catch (err) {
      console.error('Screen share failed:', err);
    }
  }, [startScreenShare, analysisMode]);

  const handleStopShare = useCallback(() => {
    // Clear recording cycle
    if (recordingCycleRef.current) {
      clearTimeout(recordingCycleRef.current);
      recordingCycleRef.current = null;
    }

    // Stop all tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }

    // Clear video srcObject
    if (videoRef.current) {
      videoRef.current.srcObject = null;
      videoRef.current.src = '';
    }

    // Stop DVR
    if (dvrRecorderRef.current && dvrRecorderRef.current.state === 'recording') {
      dvrRecorderRef.current.stop();
    }
    dvrRecorderRef.current = null;
    dvrChunksRef.current = [];
    setDvrUrl(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
    setIsDvrMode(false);

    // Clear timer
    if (elapsedRef.current) {
      clearInterval(elapsedRef.current);
      elapsedRef.current = null;
    }

    setHasStream(false);
    setElapsed(0);
    stopScreenShare();
  }, [stopScreenShare]);

  // Attach stream to video tag when we are rendering LIVE mode
  useEffect(() => {
    if (hasStream && !isDvrMode && streamRef.current && videoRef.current) {
      if (videoRef.current.srcObject !== streamRef.current) {
        videoRef.current.src = '';
        videoRef.current.srcObject = streamRef.current;
        videoRef.current.play().catch(err => console.error("Video play failed:", err));
      }
    }
  }, [hasStream, isDvrMode]);

  // Start recording cycle when session becomes available AND we're screen sharing
  useEffect(() => {
    if (isScreenSharing && activeSession && streamRef.current && streamRef.current.active) {
      console.log('[ScreenShare] Session ready, starting recording cycle');
      // Small delay to ensure stream is stabilized
      const timer = setTimeout(() => {
        startRecordingCycle();
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [isScreenSharing, activeSession, startRecordingCycle]);

  // Register seek function into context videoSeekRef
  useEffect(() => {
    const seekFn = (seconds: number) => {
      const vid = videoRef.current;
      if (!vid || !isFinite(seconds)) return;

      const mimeType = dvrRecorderRef.current?.mimeType || 'video/webm';
      const blob = new Blob(dvrChunksRef.current, { type: mimeType });
      const url = URL.createObjectURL(blob);

      setDvrUrl(prevUrl => {
        if (prevUrl) URL.revokeObjectURL(prevUrl);
        return url;
      });
      setIsDvrMode(true);

      vid.srcObject = null;
      vid.src = url;

      vid.onloadedmetadata = () => {
        vid.currentTime = seconds;
        vid.play().catch(err => console.error("DVR play failed:", err));
        vid.onloadedmetadata = null;
      };
    };
    videoSeekRef.current = seekFn;
    return () => {
      videoSeekRef.current = null;
    };
  }, [videoSeekRef]);

  const returnToLive = useCallback(() => {
    setIsDvrMode(false);
    setDvrUrl(prev => {
      if (prev) URL.revokeObjectURL(prev);
      return null;
    });
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (recordingCycleRef.current) {
        clearTimeout(recordingCycleRef.current);
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop());
      }
      if (elapsedRef.current) {
        clearInterval(elapsedRef.current);
      }
    };
  }, []);

  const formatElapsed = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  // ── Idle state — show the start button ──────────────────────────────────────
  if (!hasStream && !isScreenSharing) {
    return (
      <div className="relative h-full w-full bg-black flex flex-col items-center justify-center">
        <div className="flex flex-col items-center space-y-6">
          {/* Animated ring */}
          <div className="relative flex items-center justify-center">
            <div className="absolute h-28 w-28 animate-ping rounded-full bg-indigo-500/10" />
            <div className="absolute h-24 w-24 animate-pulse rounded-full border border-indigo-500/20" />
            <div className="flex h-20 w-20 items-center justify-center rounded-2xl bg-indigo-500/10 border border-indigo-500/20">
              <Monitor size={36} className="text-indigo-400" />
            </div>
          </div>
          <div className="text-center space-y-2">
            <h3 className="text-lg font-semibold text-slate-200">
              Live Screen Share
            </h3>
            <p className="text-sm text-slate-500 max-w-xs">
              Share your screen to start real-time threat analysis. Video is split into 5-second chunks and analyzed by the VLM model.
            </p>
          </div>

          {/* Mode toggle switch */}
          <div className="flex items-center space-x-3 rounded-xl border border-slate-700/50 bg-slate-900/60 px-4 py-2.5 backdrop-blur-sm">
            <Zap size={14} className={`transition-colors ${analysisMode === 'fast' ? 'text-amber-400' : 'text-slate-600'}`} />
            <span className={`text-xs font-medium transition-colors ${analysisMode === 'fast' ? 'text-amber-300' : 'text-slate-600'}`}>Fast</span>
            <button
              onClick={() => setAnalysisMode(prev => prev === 'fast' ? 'high_accuracy' : 'fast')}
              className="relative h-6 w-11 rounded-full transition-colors duration-300 focus:outline-none"
              style={{ backgroundColor: analysisMode === 'high_accuracy' ? 'rgb(99 102 241)' : 'rgb(51 65 85)' }}
            >
              <span
                className="absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-300"
                style={{ transform: analysisMode === 'high_accuracy' ? 'translateX(20px)' : 'translateX(0)' }}
              />
            </button>
            <span className={`text-xs font-medium transition-colors ${analysisMode === 'high_accuracy' ? 'text-indigo-300' : 'text-slate-600'}`}>Accurate</span>
            <Shield size={14} className={`transition-colors ${analysisMode === 'high_accuracy' ? 'text-indigo-400' : 'text-slate-600'}`} />
          </div>

          <button
            onClick={handleStartShare}
            className="flex items-center space-x-2 rounded-xl bg-indigo-500 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 hover:bg-indigo-600 transition-all hover:shadow-indigo-500/40 hover:scale-105"
          >
            <Wifi size={18} />
            <span>Start Live Feed</span>
          </button>
        </div>
      </div>
    );
  }

  // ── Live feed — video fills the whole box ───────────────────────────────────
  return (
    <div className="relative h-full w-full bg-black overflow-hidden">
      {/* Full-size live video */}
      <video
        ref={videoRef}
        className="h-full w-full object-contain"
        autoPlay
        muted
        playsInline
      />

      {/* Gradient overlays for readability */}
      <div className="absolute top-0 left-0 right-0 h-16 bg-gradient-to-b from-black/60 to-transparent pointer-events-none" />
      <div className="absolute bottom-0 left-0 right-0 h-10 bg-gradient-to-t from-black/40 to-transparent pointer-events-none" />

      {/* REC / REPLAY badge — top left */}
      <div className="absolute top-3 left-3 flex items-center space-x-2 rounded-lg bg-black/60 px-3 py-1.5 backdrop-blur-md border border-white/10">
        {isDvrMode ? (
          <>
            <Radio size={12} className="text-orange-500" />
            <span className="text-xs font-bold text-orange-400 tracking-widest">DVR REPLAY</span>
          </>
        ) : (
          <>
            <Circle size={8} className="text-red-500 fill-red-500 animate-pulse" />
            <span className="text-xs font-bold text-white tracking-widest">LIVE</span>
            <span className="text-xs font-mono text-slate-300">{formatElapsed(elapsed)}</span>
          </>
        )}
        {activeSession && (
          <span className="text-[10px] text-slate-500 font-mono border-l border-white/10 pl-2">
            {chunkIndexRef.current} chunks
          </span>
        )}
      </div>

      {/* Return to Live button when in DVR Mode */}
      {isDvrMode && (
        <div className="absolute top-14 left-1/2 -translate-x-1/2 z-50">
          <button
            onClick={returnToLive}
            className="flex items-center space-x-2 rounded-full bg-indigo-500 hover:bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-[0_0_20px_rgba(99,102,241,0.5)] transition-all animate-bounce"
          >
            <Wifi size={16} className="animate-pulse" />
            <span>Return to Live Feed</span>
          </button>
        </div>
      )}

      {/* Analyzing badge — top right (when session active) */}
      {activeSession && (
        <div className="absolute top-3 right-14 flex items-center space-x-1.5 rounded-lg bg-indigo-500/20 border border-indigo-500/40 px-2.5 py-1.5 backdrop-blur-md">
          <div className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
          <span className="text-[10px] font-bold text-indigo-300 tracking-wider uppercase">Analyzing</span>
        </div>
      )}

      {/* Stop button — top right */}
      <div className="absolute top-3 right-3">
        <button
          onClick={handleStopShare}
          className="flex items-center space-x-1.5 rounded-lg bg-red-500/20 border border-red-500/40 px-2.5 py-1.5 text-red-400 hover:bg-red-500/30 transition-colors backdrop-blur-md"
        >
          <Square size={12} fill="currentColor" />
          <span className="text-[11px] font-semibold">Stop</span>
        </button>
      </div>

      {/* Scanning line animation */}
      <div className="absolute inset-x-0 h-px bg-gradient-to-r from-transparent via-indigo-500/60 to-transparent animate-[scan_3s_ease-in-out_infinite] pointer-events-none" />
    </div>
  );
};

export default ScreenSharePlayer;
