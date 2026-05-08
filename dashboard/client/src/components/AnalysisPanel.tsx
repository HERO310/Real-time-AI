import React, { useRef, useEffect } from 'react';
import { useAppContext } from '../context/AppContext';
import type { AnalysisResult } from '../types';
import { ShieldAlert, ShieldCheck, Activity, AlertTriangle, Zap } from 'lucide-react';
import { sanitizeDescriptor } from '../utils/sanitize';

const levelConfig = {
  HIGH: {
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    badgeBg: 'bg-red-500',
    badgeText: 'text-white',
    icon: ShieldAlert,
    glow: 'shadow-[0_0_15px_rgba(239,68,68,0.2)]',
  },
  MEDIUM: {
    color: 'text-orange-400',
    bgColor: 'bg-orange-500/10',
    borderColor: 'border-orange-500/30',
    badgeBg: 'bg-orange-500',
    badgeText: 'text-white',
    icon: AlertTriangle,
    glow: 'shadow-[0_0_12px_rgba(249,115,22,0.15)]',
  },
  LOW: {
    color: 'text-yellow-400',
    bgColor: 'bg-yellow-500/10',
    borderColor: 'border-yellow-500/30',
    badgeBg: 'bg-yellow-500',
    badgeText: 'text-slate-900',
    icon: Activity,
    glow: '',
  },
  NORMAL: {
    color: 'text-emerald-400',
    bgColor: 'bg-emerald-500/10',
    borderColor: 'border-emerald-500/30',
    badgeBg: 'bg-emerald-500',
    badgeText: 'text-white',
    icon: ShieldCheck,
    glow: '',
  },
};

const AnalysisPanel: React.FC = () => {
  const { activeSession, analysisResults, analysisStatus } = useAppContext();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new results arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [analysisResults]);

  if (!activeSession) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-6">
        <div className="flex h-14 w-14 items-center justify-center rounded-2xl bg-slate-800 mb-3">
          <Activity size={24} className="text-slate-500" />
        </div>
        <p className="text-sm font-medium text-slate-400">No active session</p>
        <p className="text-xs text-slate-600 mt-1">Start a screen share or upload a video to begin analysis</p>
      </div>
    );
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  // Compute summary stats
  const threatResultsItems = analysisResults.filter(r => r.level !== 'NORMAL');
  const highCount = threatResultsItems.filter(r => r.level === 'HIGH').length;
  const mediumCount = threatResultsItems.filter(r => r.level === 'MEDIUM').length;
  const lowCount = threatResultsItems.filter(r => r.level === 'LOW').length;

  return (
    <div className="flex flex-col h-full">
      {/* Summary Bar */}
      <div className="flex-shrink-0 flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          <Zap size={14} className={analysisStatus === 'analyzing' ? 'text-indigo-400 animate-pulse' : 'text-slate-500'} />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
            {analysisStatus === 'analyzing' ? 'Live Analysis' : analysisStatus === 'complete' ? 'Analysis Complete' : 'Analysis'}
          </span>
        </div>
        <span className="text-xs text-slate-500 font-mono">
          {analysisResults.length} windows
        </span>
      </div>

      {/* Threat counts */}
      {analysisResults.length > 0 && (
        <div className="flex-shrink-0 flex items-center space-x-2 mb-4">
          {highCount > 0 && (
            <div className="flex items-center space-x-1 rounded-full bg-red-500/10 border border-red-500/20 px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500"></span>
              <span className="text-[10px] font-bold text-red-400">{highCount} HIGH</span>
            </div>
          )}
          {mediumCount > 0 && (
            <div className="flex items-center space-x-1 rounded-full bg-orange-500/10 border border-orange-500/20 px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500"></span>
              <span className="text-[10px] font-bold text-orange-400">{mediumCount} MED</span>
            </div>
          )}
          {lowCount > 0 && (
            <div className="flex items-center space-x-1 rounded-full bg-yellow-500/10 border border-yellow-500/20 px-2 py-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-500"></span>
              <span className="text-[10px] font-bold text-yellow-400">{lowCount} LOW</span>
            </div>
          )}
        </div>
      )}

      {/* Results list */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-2 pr-1 min-h-0">
        {analysisResults.length === 0 && analysisStatus === 'analyzing' && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mb-3"></div>
            <p className="text-sm text-slate-400">Waiting for results...</p>
            <p className="text-xs text-slate-600 mt-1">The VLM model is processing video windows</p>
          </div>
        )}

        {analysisResults.length > 0 && threatResultsItems.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center animate-in fade-in zoom-in duration-500">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/10 border border-emerald-500/20 mb-3 shadow-[0_0_15px_rgba(16,185,129,0.15)]">
               <ShieldCheck size={24} className="text-emerald-400" />
            </div>
            <p className="text-sm font-semibold tracking-wide text-emerald-400">All Systems Normal</p>
            <p className="text-xs text-slate-500 mt-1">Monitoring live feed for anomalies...</p>
            <div className="mt-4 flex items-center space-x-2 text-[10px] text-slate-600 bg-slate-900/50 px-3 py-1 rounded-full border border-slate-800">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span>{analysisResults.length} normal windows analyzed</span>
            </div>
          </div>
        )}

        {threatResultsItems.map((result, i) => {
          const config = levelConfig[result.level] || levelConfig.NORMAL;
          const Icon = config.icon;
          const isAlert = result.status === 'ALERT' || result.status === 'ALERT-FAST';

          return (
            <div
              key={result.id || i}
              className={`rounded-lg border p-3 transition-all animate-in fade-in slide-in-from-bottom-2 ${config.borderColor} ${config.bgColor} ${config.glow}`}
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <div className="flex items-start justify-between mb-1.5">
                <div className="flex items-center space-x-2">
                  <div className={`p-1 rounded ${config.bgColor}`}>
                    <Icon size={14} className={config.color} />
                  </div>
                  <span className={`text-xs font-bold ${config.badgeBg} ${config.badgeText} px-1.5 py-0.5 rounded`}>
                    {result.level}
                  </span>
                  {result.status === 'ALERT-FAST' && (
                    <span className="text-[9px] font-bold text-red-400 uppercase tracking-wider">FAST</span>
                  )}
                </div>
                <span className="text-[10px] font-mono text-slate-500">
                  {formatTime(result.startSec)} – {formatTime(result.endSec)}
                </span>
              </div>

              {result.descriptor && sanitizeDescriptor(result.descriptor) && (
                <p className="text-xs text-slate-300 leading-relaxed line-clamp-2 mb-1.5">
                  {sanitizeDescriptor(result.descriptor)}
                </p>
              )}

              <div className="flex items-center space-x-3 text-[10px] text-slate-500 font-mono">
                <span>w={result.windowScore?.toFixed(2)}</span>
                <span>s={result.smoothedScore?.toFixed(2)}</span>
                <span>sev={result.severity?.toFixed(2)}</span>
                {result.gates?.length > 0 && (
                  <span className="text-slate-600">gates={result.gates.join(',')}</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AnalysisPanel;
