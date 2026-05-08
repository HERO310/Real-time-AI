import React, { createContext, useContext, useEffect, useState, useCallback, useRef, type ReactNode } from 'react';
import type { Camera, Threat, AnalysisResult, Session, PastSession } from '../types';
import { fetchCameras, fetchPastSessions, fetchPastSessionResults } from '../services/api';
import { socketService } from '../services/socket';
import { sanitizeDescriptor } from '../utils/sanitize';

interface AppContextProps {
  cameras: Camera[];
  activeCamera: Camera | null;
  setActiveCamera: (camera: Camera) => void;
  threats: Record<string, Threat[]>;
  isLoading: boolean;
  isConnected: boolean;
  frequentThreatWarning: boolean;
  latestEvent: string | null;

  // Session & Analysis
  activeSession: Session | null;
  setActiveSession: (session: Session | null) => void;
  analysisResults: AnalysisResult[];
  analysisStatus: 'idle' | 'analyzing' | 'complete';
  startSession: (cameraId: string) => Promise<void>;
  stopSession: () => void;

  // Screen share
  isScreenSharing: boolean;
  startScreenShare: (mode?: 'fast' | 'high_accuracy') => void;
  stopScreenShare: () => void;

  // Seek control — any active player registers its seek fn here
  videoSeekRef: React.MutableRefObject<((seconds: number) => void) | null>;
  seekTo: (seconds: number) => void;

  // Past sessions
  pastSessions: PastSession[];
  pastSessionsLoading: boolean;
  activePastSession: PastSession | null;
  pastSessionThreats: Threat[];
  pastSessionResults: AnalysisResult[];
  loadPastSession: (session: PastSession) => Promise<void>;
  clearPastSession: () => void;
}

const AppContext = createContext<AppContextProps | undefined>(undefined);

export const AppProvider = ({ children }: { children: ReactNode }) => {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [activeCameraState, setActiveCameraState] = useState<Camera | null>(null);
  const [threats, setThreats] = useState<Record<string, Threat[]>>({});
  const [isLoading, setIsLoading] = useState(true);
  const [isConnected, setIsConnected] = useState(false);
  const [frequentThreatWarning, setFrequentThreatWarning] = useState(false);
  const [latestEvent, setLatestEvent] = useState<string | null>(null);

  // Session state
  const [activeSession, setActiveSessionState] = useState<Session | null>(null);
  const [analysisResults, setAnalysisResults] = useState<AnalysisResult[]>([]);
  const [analysisStatus, setAnalysisStatus] = useState<'idle' | 'analyzing' | 'complete'>('idle');
  const [isScreenSharing, setIsScreenSharing] = useState(false);

  // Seek control — players register their seek function here
  const videoSeekRef = useRef<((seconds: number) => void) | null>(null);

  // Past sessions state
  const [pastSessions, setPastSessions] = useState<PastSession[]>([]);
  const [pastSessionsLoading, setPastSessionsLoading] = useState(false);
  const [activePastSession, setActivePastSession] = useState<PastSession | null>(null);
  const [pastSessionThreats, setPastSessionThreats] = useState<Threat[]>([]);
  const [pastSessionResults, setPastSessionResults] = useState<AnalysisResult[]>([]);

  // Refs to avoid stale closures in socket handlers
  const activeSessionRef = useRef<Session | null>(null);
  const activeCameraRef = useRef<Camera | null>(null);

  // Keep refs in sync
  useEffect(() => { activeSessionRef.current = activeSession; }, [activeSession]);
  useEffect(() => { activeCameraRef.current = activeCameraState; }, [activeCameraState]);

  const setActiveSession = useCallback((session: Session | null) => {
    setActiveSessionState(session);
    activeSessionRef.current = session;
    if (session) {
      setAnalysisStatus(session.status === 'complete' ? 'complete' : 'analyzing');
    } else {
      setAnalysisStatus('idle');
      setAnalysisResults([]);
    }
  }, []);

  // Seek to a specific time in the active player
  const seekTo = useCallback((seconds: number) => {
    if (videoSeekRef.current) {
      videoSeekRef.current(seconds);
    }
  }, []);

  // Load cameras and past sessions on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const cams = await fetchCameras();
        setCameras(cams);
        if (cams.length > 0) {
          setActiveCameraState(cams[0]);
          activeCameraRef.current = cams[0];
        }
      } catch (error) {
        console.error('Failed to load cameras', error);
      } finally {
        setIsLoading(false);
      }
    };
    loadData();

    const loadPastSessions = async () => {
      setPastSessionsLoading(true);
      try {
        const sessions = await fetchPastSessions();
        setPastSessions(sessions);
      } catch (error) {
        console.error('Failed to load past sessions', error);
      } finally {
        setPastSessionsLoading(false);
      }
    };
    loadPastSessions();
  }, []);

  // Set active camera (also clear past session view)
  const setActiveCamera = useCallback((camera: Camera) => {
    setActiveCameraState(camera);
    activeCameraRef.current = camera;
    setActivePastSession(null);
    setPastSessionThreats([]);
    setPastSessionResults([]);
    videoSeekRef.current = null;
  }, []);

  // Load a past session — fetch its results.json and populate threats
  const loadPastSession = useCallback(async (session: PastSession) => {
    setActivePastSession(session);
    setPastSessionThreats([]);
    setPastSessionResults([]);
    videoSeekRef.current = null;

    // Deactivate live cameras while viewing past session
    setActiveSessionState(null);
    activeSessionRef.current = null;
    setAnalysisStatus('idle');

    try {
      const data = await fetchPastSessionResults(session.sessionId);
      const results: AnalysisResult[] = data.results || [];
      setPastSessionResults(results);

      // Accumulate total time from chunks (each chunk is ~5s, but use batch
      // index from window ID to compute absolute timestamp)
      // Batch size is ~21 seconds (19 windows of 1s step at 3s window).
      // We approximate: batch N starts at N * batchDurationSec.
      // Each result.startSec is relative to its batch.
      const CHUNK_DURATION_SEC = 5; // ~5s per chunk file
      const BATCH_DURATION_SEC = 21; // approximate, used for display only

      const threats: Threat[] = results
        .filter(r => r.status === 'ALERT' || r.status === 'ALERT-FAST')
        .map((r, i) => {
          // Extract batch number from result id: session_XXX_batch_NNN_wM
          let batchNum = 0;
          const batchMatch = r.id?.match(/_batch_(\d+)_/);
          if (batchMatch) batchNum = parseInt(batchMatch[1], 10);

          const absoluteStart = batchNum * BATCH_DURATION_SEC + r.startSec;
          const absoluteEnd = batchNum * BATCH_DURATION_SEC + r.endSec;

          return {
            id: r.id || `past_${session.sessionId}_${i}`,
            cameraId: session.sessionId,
            timestamp: absoluteStart,
            endTimestamp: absoluteEnd,
            level: r.level,
            status: r.status,
            descriptor: r.descriptor,
            severity: r.severity,
            windowScore: r.windowScore,
            smoothedScore: r.smoothedScore,
            gates: r.gates || [],
            eventTags: r.eventTags || [],
            absoluteTimestamp: absoluteStart,
          };
        });

      setPastSessionThreats(threats);
    } catch (err) {
      console.error('Failed to load past session results:', err);
    }
  }, []);

  const clearPastSession = useCallback(() => {
    setActivePastSession(null);
    setPastSessionThreats([]);
    setPastSessionResults([]);
    videoSeekRef.current = null;
  }, []);

  // Start a new session
  const startSession = useCallback(async (cameraId: string) => {
    const socket = socketService.connect();
    socket.emit('start_session', { cameraId });
  }, []);

  // Stop current session
  const stopSession = useCallback(() => {
    const session = activeSessionRef.current;
    if (!session) return;
    const socket = socketService.getSocket();
    if (socket) {
      socket.emit('stop_session', { sessionId: session.id });
    }
    setActiveSessionState(null);
    activeSessionRef.current = null;
    setAnalysisStatus('idle');
    setIsScreenSharing(false);
  }, []);

  // Screen share controls
  const startScreenShare = useCallback((mode?: 'fast' | 'high_accuracy') => {
    const cam = activeCameraRef.current;
    if (!cam) return;
    const socket = socketService.connect();
    socket.emit('start_session', { cameraId: cam.id, analysisMode: mode || 'fast' });
    setIsScreenSharing(true);
    // Clear any past session view
    setActivePastSession(null);
    setPastSessionThreats([]);
    setPastSessionResults([]);
  }, []);

  const stopScreenShare = useCallback(() => {
    const session = activeSessionRef.current;
    if (session) {
      const socket = socketService.getSocket();
      if (socket) {
        socket.emit('stop_session', { sessionId: session.id });
      }
    }
    setIsScreenSharing(false);
    setActiveSessionState(null);
    activeSessionRef.current = null;
    setAnalysisStatus('idle');
    setAnalysisResults([]);
  }, []);

  // Socket connection and event listeners
  useEffect(() => {
    const socket = socketService.connect();

    socket.on('connect', () => setIsConnected(true));
    socket.on('disconnect', () => setIsConnected(false));

    // Session started confirmation
    socket.on('session_started', (data: { sessionId: string; cameraId: string; status: string }) => {
      console.log('[Context] Session started:', data);
      const session: Session = {
        id: data.sessionId,
        cameraId: data.cameraId,
        status: 'recording',
        results: [],
      };
      setActiveSessionState(session);
      activeSessionRef.current = session;
      setAnalysisResults([]);
      setAnalysisStatus('analyzing');

      // Join the session room
      socket.emit('join_session', { sessionId: data.sessionId });
    });

    // Chunk saved confirmation
    socket.on('chunk_saved', (data: { sessionId: string; chunkIndex: number; filename: string }) => {
      console.log('[Context] Chunk saved:', data);
    });

    // Analysis result (structured data from server)
    socket.on('analysis_result', (data: { sessionId: string; result: AnalysisResult; totalResults: number }) => {
      console.log('[Context] Analysis result:', data.result.status, data.result.level);

      setAnalysisResults(prev => {
        if (prev.find(r => r.id === data.result.id)) return prev;
        return [...prev, data.result];
      });

      // Convert to threat if it's an alert
      if (data.result.status === 'ALERT' || data.result.status === 'ALERT-FAST') {
        const session = activeSessionRef.current;
        const cam = activeCameraRef.current;
        const camId = session?.cameraId || cam?.id || 'cam1';

        const threat: Threat = {
          id: data.result.id || `t_${Date.now()}`,
          cameraId: camId,
          timestamp: data.result.startSec,
          endTimestamp: data.result.endSec,
          level: data.result.level,
          status: data.result.status,
          descriptor: data.result.descriptor,
          severity: data.result.severity,
          windowScore: data.result.windowScore,
          smoothedScore: data.result.smoothedScore,
          gates: data.result.gates,
          eventTags: data.result.eventTags,
        };

        setThreats(prev => {
          const camThreats = prev[camId] || [];
          if (camThreats.find(t => t.id === threat.id)) return prev;
          return {
            ...prev,
            [camId]: [...camThreats, threat].sort((a, b) => a.timestamp - b.timestamp),
          };
        });

        // Notification
        const m = Math.floor(data.result.startSec / 60);
        const s = Math.floor(data.result.startSec % 60);
        const formattedTime = `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        setLatestEvent(`${data.result.level} threat at ${formattedTime} — ${sanitizeDescriptor(data.result.descriptor) || 'Anomaly detected'}`);
      }
    });

    // Analysis preview
    socket.on('analysis_preview', (data: { sessionId: string; result: any }) => {
      console.log('[Context] Preview:', data.result?.status, data.result?.level);
    });

    // Analysis complete
    socket.on('analysis_complete', (data: { sessionId: string; totalResults: number; exitCode: number }) => {
      console.log('[Context] Analysis complete:', data);
      setAnalysisStatus('complete');
      setActiveSessionState(prev => {
        if (!prev || prev.id !== data.sessionId) return prev;
        const updated = { ...prev, status: 'complete' as const };
        activeSessionRef.current = updated;
        return updated;
      });
    });

    // Session stopped
    socket.on('session_stopped', (data: { sessionId: string; status: string }) => {
      console.log('[Context] Session stopped:', data);
    });

    // Error messages
    socket.on('error_msg', (data: { error: string }) => {
      console.error('[Context] Server error:', data.error);
    });

    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.off('session_started');
      socket.off('chunk_saved');
      socket.off('analysis_result');
      socket.off('analysis_preview');
      socket.off('analysis_complete');
      socket.off('session_stopped');
      socket.off('error_msg');
    };
  }, []);

  // Smart UI Intelligence Effect
  useEffect(() => {
    if (!activeCameraState || !threats[activeCameraState.id]) return;
    const currentThreats = threats[activeCameraState.id];
    setFrequentThreatWarning(currentThreats.length >= 5);
  }, [threats, activeCameraState]);

  // Clear latest event after some seconds
  useEffect(() => {
    if (latestEvent) {
      const timer = setTimeout(() => setLatestEvent(null), 7000);
      return () => clearTimeout(timer);
    }
  }, [latestEvent]);

  return (
    <AppContext.Provider
      value={{
        cameras,
        activeCamera: activeCameraState,
        setActiveCamera,
        threats,
        isLoading,
        isConnected,
        frequentThreatWarning,
        latestEvent,
        activeSession,
        setActiveSession,
        analysisResults,
        analysisStatus,
        startSession,
        stopSession,
        isScreenSharing,
        startScreenShare,
        stopScreenShare,
        videoSeekRef,
        seekTo,
        pastSessions,
        pastSessionsLoading,
        activePastSession,
        pastSessionThreats,
        pastSessionResults,
        loadPastSession,
        clearPastSession,
      }}
    >
      {children}
    </AppContext.Provider>
  );
};

export const useAppContext = () => {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useAppContext must be used within an AppProvider');
  }
  return context;
};
