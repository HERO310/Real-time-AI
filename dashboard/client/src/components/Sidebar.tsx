import { useState } from 'react';
import { useAppContext } from '../context/AppContext';
import { Monitor, Upload, Video, Camera, StopCircle, ChevronDown, ChevronRight, Clock, ShieldAlert, Loader2, Film } from 'lucide-react';
import type { PastSession } from '../types';

const formatDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  } catch { return iso; }
};

const Sidebar = () => {
  const {
    cameras, activeCamera, setActiveCamera, threats, activeSession,
    analysisStatus, analysisResults, stopSession,
    pastSessions, pastSessionsLoading, activePastSession, loadPastSession,
  } = useAppContext();

  const [pastExpanded, setPastExpanded] = useState(true);

  const handleCameraClick = (camera: typeof cameras[0]) => {
    setActiveCamera(camera);
  };

  return (
    <div className="flex flex-col p-4 w-full space-y-5">

      {/* ── Live Cameras ── */}
      <div>
        <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">Live Cameras</h3>
        <div className="space-y-2">
          {cameras.map((camera) => {
            const isActive = activeCamera?.id === camera.id && !activePastSession;
            const threatCount = threats[camera.id]?.length || 0;
            const isSessionActive = activeSession?.cameraId === camera.id;

            return (
              <button
                key={camera.id}
                onClick={() => handleCameraClick(camera)}
                className={`flex w-full items-center justify-between rounded-xl border p-3 text-left transition-all ${
                  isActive
                    ? 'border-indigo-500/50 bg-indigo-500/10 shadow-[0_0_20px_rgba(99,102,241,0.1)]'
                    : 'border-slate-800 bg-slate-950/50 hover:border-slate-700 hover:bg-slate-800'
                }`}
              >
                <div className="flex items-center space-x-3">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-lg ${isActive ? 'bg-indigo-500 text-white' : 'bg-slate-800 text-slate-400'}`}>
                    {camera.type === 'screenshare' ? <Monitor size={18} /> : camera.type === 'webcam' ? <Camera size={18} /> : <Upload size={18} />}
                  </div>
                  <div>
                    <p className={`text-sm font-medium ${isActive ? 'text-white' : 'text-slate-300'}`}>
                      {camera.name}
                    </p>
                    <div className="flex items-center mt-1">
                      {isSessionActive ? (
                        <>
                          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 animate-pulse ${
                            analysisStatus === 'analyzing' ? 'bg-indigo-500' : analysisStatus === 'complete' ? 'bg-emerald-500' : 'bg-yellow-500'
                          }`} />
                          <span className="text-[10px] uppercase text-slate-500 tracking-wider">
                            {analysisStatus === 'analyzing' ? 'analyzing' : analysisStatus === 'complete' ? 'complete' : 'active'}
                          </span>
                        </>
                      ) : (
                        <>
                          <span className={`inline-block w-1.5 h-1.5 rounded-full mr-1.5 ${camera.status === 'online' ? 'bg-emerald-500' : 'bg-red-500'}`} />
                          <span className="text-[10px] uppercase text-slate-500 tracking-wider">
                            {camera.type === 'screenshare' ? 'screen share' : camera.type === 'webcam' ? 'live camera' : 'upload'}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  {threatCount > 0 && (
                    <div className={`flex h-6 min-w-[24px] items-center justify-center rounded-full px-1.5 text-xs font-bold ${
                      isActive ? 'bg-indigo-400 text-slate-950' : 'bg-slate-700 text-slate-300'
                    }`}>
                      {threatCount}
                    </div>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* ── Session control ── */}
      {activeSession && (
        <div className="pt-3 border-t border-slate-800">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Session</span>
            <span className="text-[10px] font-mono text-slate-600">{activeSession.id.slice(0, 20)}...</span>
          </div>
          <div className="flex items-center space-x-2 mb-3">
            <div className={`w-2 h-2 rounded-full ${
              analysisStatus === 'analyzing' ? 'bg-indigo-500 animate-pulse' : 'bg-emerald-500'
            }`} />
            <span className="text-xs text-slate-300 capitalize">{analysisStatus}</span>
            <span className="text-xs text-slate-600">• {analysisResults.length} windows</span>
          </div>
          <button
            onClick={stopSession}
            className="flex w-full items-center justify-center space-x-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm font-medium text-red-400 hover:bg-red-500/20 transition-colors"
          >
            <StopCircle size={16} />
            <span>Stop Session</span>
          </button>
        </div>
      )}

      {/* ── Past Sessions ── */}
      <div className="border-t border-slate-800 pt-3">
        <button
          onClick={() => setPastExpanded(v => !v)}
          className="flex w-full items-center justify-between mb-3 group"
        >
          <div className="flex items-center space-x-2">
            <Film size={13} className="text-slate-500" />
            <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 group-hover:text-slate-300 transition-colors">
              Past Sessions
            </h3>
            {pastSessions.length > 0 && (
              <span className="text-[10px] text-slate-600 font-mono">({pastSessions.length})</span>
            )}
          </div>
          {pastExpanded
            ? <ChevronDown size={13} className="text-slate-600" />
            : <ChevronRight size={13} className="text-slate-600" />
          }
        </button>

        {pastExpanded && (
          <div className="space-y-1.5">
            {pastSessionsLoading ? (
              <div className="flex items-center justify-center py-4 space-x-2">
                <Loader2 size={14} className="text-indigo-400 animate-spin" />
                <span className="text-xs text-slate-500">Loading sessions...</span>
              </div>
            ) : pastSessions.length === 0 ? (
              <div className="flex flex-col items-center py-5 text-center border border-dashed border-slate-800 rounded-xl">
                <Video size={20} className="text-slate-600 mb-1.5" />
                <p className="text-xs text-slate-500">No past sessions found</p>
              </div>
            ) : (
              pastSessions.map((session) => {
                const isActive = activePastSession?.sessionId === session.sessionId;
                return (
                  <PastSessionCard
                    key={session.sessionId}
                    session={session}
                    isActive={isActive}
                    onLoad={() => loadPastSession(session)}
                  />
                );
              })
            )}
          </div>
        )}
      </div>
    </div>
  );
};

// ── Past Session Card ──────────────────────────────────────────────────────────
const PastSessionCard = ({
  session, isActive, onLoad,
}: {
  session: PastSession;
  isActive: boolean;
  onLoad: () => void;
}) => {
  const hasThreat = session.threatCount > 0;

  return (
    <button
      onClick={onLoad}
      className={`w-full text-left rounded-lg border p-2.5 transition-all group ${
        isActive
          ? 'border-violet-500/50 bg-violet-500/10 shadow-[0_0_12px_rgba(139,92,246,0.15)]'
          : 'border-slate-800 bg-slate-950/50 hover:border-slate-700 hover:bg-slate-800/50'
      }`}
    >
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center space-x-1.5 min-w-0">
          <Film size={11} className={isActive ? 'text-violet-400 flex-shrink-0' : 'text-slate-600 flex-shrink-0'} />
          <span className={`text-[10px] font-mono truncate ${isActive ? 'text-slate-200' : 'text-slate-400'}`}>
            {session.sessionId.slice(-14)}
          </span>
        </div>
        {hasThreat && (
          <div className="flex items-center space-x-1 flex-shrink-0 ml-1">
            <ShieldAlert size={10} className="text-red-400" />
            <span className="text-[10px] font-bold text-red-400">{session.threatCount}</span>
          </div>
        )}
      </div>
      <div className="flex items-center space-x-1 mt-0.5">
        <Clock size={9} className="text-slate-600 flex-shrink-0" />
        <span className="text-[10px] text-slate-500">{formatDate(session.completedAt)}</span>
      </div>
      {!session.hasVideo && (
        <span className="text-[9px] text-slate-600 mt-0.5 block">no video chunks</span>
      )}
    </button>
  );
};

export default Sidebar;
