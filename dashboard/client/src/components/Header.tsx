import { useAppContext } from '../context/AppContext';
import { ShieldAlert, Zap, Server, Activity } from 'lucide-react';

const Header = () => {
  const { isConnected, frequentThreatWarning, analysisStatus, analysisResults } = useAppContext();

  const highAlerts = analysisResults.filter(r => r.level === 'HIGH').length;

  return (
    <header className="flex h-16 w-full items-center justify-between border-b border-slate-800 bg-slate-900 px-6">
      <div className="flex items-center space-x-3">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-500/20 text-indigo-400">
          <ShieldAlert size={24} />
        </div>
        <div>
          <h1 className="text-lg font-bold tracking-tight text-white">CCTV Threat Monitor</h1>
          <p className="text-xs font-medium text-slate-400">Real-time VLM Analysis Dashboard</p>
        </div>
      </div>

      <div className="flex items-center space-x-4">
        {/* Analysis status */}
        {analysisStatus === 'analyzing' && (
          <div className="flex items-center space-x-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-4 py-1.5 text-indigo-400">
            <Activity size={14} className="animate-pulse" />
            <span className="text-sm font-semibold">Analyzing...</span>
            <span className="text-xs text-indigo-400/60">{analysisResults.length} windows</span>
          </div>
        )}

        {/* High alert count */}
        {highAlerts > 0 && (
          <div className="flex items-center space-x-2 rounded-full border border-red-500/30 bg-red-500/10 px-4 py-1.5 text-red-400 shadow-[0_0_15px_rgba(239,68,68,0.1)]">
            <ShieldAlert size={14} className="animate-pulse" />
            <span className="text-sm font-semibold">{highAlerts} High Alerts</span>
          </div>
        )}

        {/* Frequent Threat Warning Banner */}
        {frequentThreatWarning && (
           <div className="flex items-center space-x-2 rounded-full border border-orange-500/30 bg-orange-500/10 px-4 py-1.5 text-orange-400 shadow-[0_0_15px_rgba(249,115,22,0.1)]">
              <Zap size={16} className="animate-pulse" />
              <span className="text-sm font-semibold">Frequent Threats</span>
           </div>
        )}

        {/* Connection Status */}
        <div className="flex items-center space-x-2 rounded-full border border-slate-800 bg-slate-950 px-4 py-1.5 shadow-inner">
          <Server size={14} className={isConnected ? "text-emerald-400" : "text-slate-500"} />
          <span className="text-sm font-medium text-slate-300">
            {isConnected ? 'Online' : 'Connecting...'}
          </span>
          <div className="relative ml-1 flex h-2.5 w-2.5">
            {isConnected && (
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
            )}
            <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${isConnected ? "bg-emerald-500" : "bg-slate-600"}`}></span>
          </div>
        </div>
      </div>
    </header>
  );
};

export default Header;
