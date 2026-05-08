import { useAppContext } from '../context/AppContext';
import Header from '../components/Header';
import Sidebar from '../components/Sidebar';
import VideoPlayer from '../components/VideoPlayer';
import ThreatList from '../components/ThreatList';
import ThreatClip from '../components/ThreatClip';
import AnalysisPanel from '../components/AnalysisPanel';
import { AlertCircle } from 'lucide-react';

const Dashboard = () => {
  const {
    isLoading, activeCamera, threats, latestEvent, activeSession,
    activePastSession, pastSessionThreats,
  } = useAppContext();

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-slate-950 font-sans text-slate-100">
        <div className="flex flex-col items-center space-y-4">
          <div className="h-12 w-12 animate-spin rounded-full border-4 border-indigo-500 border-t-transparent"></div>
          <p className="text-xl font-medium tracking-wide text-indigo-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  // Use past session threats when viewing a past session, otherwise live threats
  const activeThreats = activePastSession
    ? pastSessionThreats
    : (activeCamera ? (threats[activeCamera.id] || []) : []);

  const sortedThreats = [...activeThreats].sort((a, b) => b.timestamp - a.timestamp); // descending

  const threatLabel = activePastSession
    ? `Past Session (${activePastSession.sessionId.slice(-8)})`
    : (activeCamera ? activeCamera.name : '');

  return (
    <div className="flex w-full flex-col overflow-hidden bg-slate-950 font-sans text-slate-200" style={{ height: '100dvh' }}>
      <Header />

      {/* Mobile: stack vertically. Desktop: side-by-side */}
      <div className="flex flex-col xl:flex-row flex-1 overflow-hidden min-h-0">

        {/* Sidebar — full width on mobile (compact), fixed w-72 on desktop */}
        <div className="xl:w-72 xl:flex-shrink-0 border-b xl:border-b-0 xl:border-r border-slate-800 bg-slate-900 overflow-y-auto">
          <Sidebar />
          <div className="p-4 border-t border-slate-800">
            <h3 className="mb-3 text-xs font-semibold uppercase tracking-wider text-slate-400">
              Threat Alerts {threatLabel ? `(${threatLabel})` : ''}
            </h3>
            {/* On mobile, show threats in a horizontal scroll row */}
            <div className="xl:block">
              <ThreatList threats={sortedThreats} />
            </div>
          </div>
        </div>

        {/* Main content area */}
        <div className="flex flex-1 flex-col overflow-y-auto xl:overflow-hidden bg-slate-950 p-3 xl:p-4 relative min-h-0">

          {/* Notification Bar */}
          {latestEvent && (
            <div className="sticky top-0 z-50 mb-3 flex w-full items-center space-x-3 rounded-lg border border-red-500/30 bg-red-500/10 p-3 font-medium text-red-400 shadow-xl backdrop-blur-md">
              <AlertCircle size={18} className="animate-pulse flex-shrink-0" />
              <span className="text-sm truncate">{latestEvent}</span>
            </div>
          )}

          {/* On mobile: single column. On xl: 8/4 split */}
          <div className="flex flex-col xl:grid xl:flex-1 xl:grid-cols-12 gap-4 xl:overflow-hidden">

            {/* Video Player */}
            <div className="xl:col-span-8 flex flex-col h-full min-h-0">
              <div className="flex-1 w-full h-full overflow-hidden rounded-xl border border-slate-800 bg-black shadow-2xl relative mobile-video-min-h flex flex-col" style={{ minHeight: '300px' }}>
                <VideoPlayer />
              </div>
            </div>

            {/* Right panel — Analysis / Threat clips */}
            <div className="xl:col-span-4 flex flex-col xl:overflow-hidden min-h-0 mt-4 xl:mt-0">
              {activeSession ? (
                <div className="flex-1 rounded-xl border border-slate-800 bg-slate-900/50 p-4 overflow-hidden flex flex-col min-h-0">
                  <AnalysisPanel />
                </div>
              ) : (
                <div className="flex-1 flex flex-col min-h-0">
                  <h3 className="mb-4 flex-shrink-0 text-sm font-semibold uppercase tracking-wider text-slate-400">
                    {activePastSession ? 'Past Session Threats' : 'Detected Threats'}
                  </h3>
                  <div className="flex-1 overflow-y-auto space-y-4 pr-2">
                    {sortedThreats.length > 0 ? (
                      sortedThreats.map((threat, index) => (
                        <ThreatClip
                          key={threat.id || index}
                          threat={threat}
                          label={index === 0 ? 'Latest Threat' : 'Previous Threat'}
                        />
                      ))
                    ) : (
                      <div className="flex flex-col items-center justify-center py-12 text-center">
                        <p className="text-sm text-slate-500">
                          {activePastSession
                            ? 'No alerts detected in this session'
                            : 'Select a camera and start a session to begin analysis'}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;