import React from 'react';
import type { Threat } from '../types';
import { Clock, ShieldCheck, ShieldAlert, AlertTriangle, Activity, Play } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { sanitizeDescriptor } from '../utils/sanitize';

interface ThreatListProps {
  threats: Threat[];
}

const levelIcon: Record<string, any> = {
  HIGH: ShieldAlert,
  MEDIUM: AlertTriangle,
  LOW: Activity,
  NORMAL: ShieldCheck,
};

const levelColors: Record<string, { text: string; bg: string; border: string; iconBg: string; glow: string }> = {
  HIGH:   { text: 'text-red-300',    bg: 'bg-red-500/10',    border: 'border-red-500/30',    iconBg: 'bg-red-500/20 text-red-400',    glow: 'hover:shadow-[0_0_12px_rgba(239,68,68,0.25)] hover:border-red-400/50' },
  MEDIUM: { text: 'text-orange-300', bg: 'bg-orange-500/10', border: 'border-orange-500/30', iconBg: 'bg-orange-500/20 text-orange-400', glow: 'hover:shadow-[0_0_12px_rgba(249,115,22,0.2)] hover:border-orange-400/50' },
  LOW:    { text: 'text-yellow-300', bg: 'bg-yellow-500/10', border: 'border-yellow-500/30', iconBg: 'bg-yellow-500/20 text-yellow-400', glow: 'hover:shadow-[0_0_12px_rgba(234,179,8,0.2)] hover:border-yellow-400/50' },
  NORMAL: { text: 'text-emerald-300',bg: 'bg-emerald-500/10',border: 'border-emerald-500/30',iconBg: 'bg-emerald-500/20 text-emerald-400', glow: '' },
};

const ThreatList: React.FC<ThreatListProps> = ({ threats }) => {
  const { seekTo } = useAppContext();

  if (threats.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center border border-dashed border-slate-800 rounded-xl bg-slate-950/50">
        <ShieldCheck size={32} className="text-emerald-500/50 mb-2" />
        <p className="text-sm font-medium text-slate-400">No threats detected</p>
      </div>
    );
  }

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  return (
    <div className="space-y-2 max-h-[calc(100vh-350px)] overflow-y-auto pr-1">
      {threats.map((threat) => {
        const level = threat.level || 'NORMAL';
        const colors = levelColors[level] || levelColors.NORMAL;
        const Icon = levelIcon[level] || Clock;
        const isClickable = level !== 'NORMAL';

        return (
          <button
            key={threat.id}
            onClick={() => seekTo(threat.timestamp)}
            title={`Jump to ${formatTime(threat.timestamp)}`}
            className={`flex w-full items-center justify-between rounded-lg border p-2.5 transition-all group text-left
              ${colors.border} ${colors.bg} ${colors.glow}
              ${isClickable ? 'cursor-pointer active:scale-[0.98]' : 'cursor-default'}
              hover:opacity-95`}
          >
            <div className="flex items-center space-x-2.5 min-w-0">
              <div className={`p-1.5 rounded-md flex-shrink-0 ${colors.iconBg}`}>
                <Icon size={14} />
              </div>
              <div className="min-w-0">
                <div className="flex items-center space-x-2">
                  <span className={`text-xs font-bold ${colors.text}`}>{level}</span>
                  {threat.status === 'ALERT-FAST' && (
                    <span className="text-[9px] font-bold text-red-400 bg-red-500/20 px-1 rounded">FAST</span>
                  )}
                </div>
                <p className="text-[11px] text-slate-400 mt-0.5 font-mono">
                  {formatTime(threat.timestamp)} mark
                </p>
                {threat.descriptor && sanitizeDescriptor(threat.descriptor) && (
                  <p className="text-[10px] text-slate-500 mt-0.5 truncate max-w-[180px]">
                    {sanitizeDescriptor(threat.descriptor)}
                  </p>
                )}
              </div>
            </div>

            <div className="flex items-center space-x-2 flex-shrink-0">
              {threat.severity !== undefined && (
                <div className="text-[10px] font-mono text-slate-600">
                  sev {threat.severity.toFixed(2)}
                </div>
              )}
              {/* Jump icon — visible on hover */}
              <div className={`opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded ${colors.iconBg}`}>
                <Play size={10} className={colors.text} fill="currentColor" />
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
};

export default ThreatList;
