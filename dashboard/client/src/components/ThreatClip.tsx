import React from 'react';
import type { Threat } from '../types';
import { ShieldAlert, AlertTriangle, Activity, ShieldCheck, Play } from 'lucide-react';
import { useAppContext } from '../context/AppContext';
import { sanitizeDescriptor } from '../utils/sanitize';

interface ThreatClipProps {
  threat: Threat | null;
  label: string;
}

const levelConfig: Record<string, {
  color: string; bgColor: string; borderColor: string; icon: any;
  hoverBorder: string; glow: string; playBg: string;
}> = {
  HIGH:   { color: 'text-red-400',    bgColor: 'bg-red-500/10',    borderColor: 'border-red-500/30',    hoverBorder: 'hover:border-red-400/60',    glow: 'hover:shadow-[0_0_16px_rgba(239,68,68,0.2)]',    icon: ShieldAlert,  playBg: 'bg-red-500/20 text-red-400'    },
  MEDIUM: { color: 'text-orange-400', bgColor: 'bg-orange-500/10', borderColor: 'border-orange-500/30', hoverBorder: 'hover:border-orange-400/60', glow: 'hover:shadow-[0_0_16px_rgba(249,115,22,0.15)]', icon: AlertTriangle, playBg: 'bg-orange-500/20 text-orange-400' },
  LOW:    { color: 'text-yellow-400', bgColor: 'bg-yellow-500/10', borderColor: 'border-yellow-500/30', hoverBorder: 'hover:border-yellow-400/60', glow: 'hover:shadow-[0_0_16px_rgba(234,179,8,0.15)]',  icon: Activity,     playBg: 'bg-yellow-500/20 text-yellow-400' },
  NORMAL: { color: 'text-emerald-400',bgColor: 'bg-emerald-500/10',borderColor: 'border-emerald-500/30',hoverBorder: '',                           glow: '',                                              icon: ShieldCheck,  playBg: 'bg-emerald-500/20 text-emerald-400' },
};

const ThreatClip: React.FC<ThreatClipProps> = ({ threat, label }) => {
  const { seekTo } = useAppContext();

  if (!threat) {
    return (
      <div className="flex h-28 flex-col items-center justify-center rounded-xl border border-dashed border-slate-800 bg-slate-900/50 p-4 relative overflow-hidden">
        <p className="text-sm font-medium text-slate-500">No {label.toLowerCase()} available</p>
      </div>
    );
  }

  const level = threat.level || 'NORMAL';
  const config = levelConfig[level] || levelConfig.NORMAL;
  const Icon = config.icon;
  const isClickable = level !== 'NORMAL';

  const formatTime = (secs: number) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
  };

  const handleClick = () => {
    if (isClickable) {
      seekTo(threat.timestamp);
    }
  };

  return (
    <button
      onClick={handleClick}
      disabled={!isClickable}
      title={isClickable ? `Jump to ${formatTime(threat.timestamp)}` : undefined}
      className={`w-full text-left rounded-xl border p-4 transition-all group
        ${config.borderColor} ${config.bgColor}
        ${isClickable ? `${config.hoverBorder} ${config.glow} cursor-pointer active:scale-[0.98]` : 'cursor-default'}
      `}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center space-x-2">
          <div className={`p-1.5 rounded-lg ${config.bgColor} transition-transform ${isClickable ? 'group-hover:scale-110' : ''}`}>
            <Icon size={16} className={config.color} />
          </div>
          <div>
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</span>
            <div className="flex items-center space-x-1.5 mt-0.5">
              <span className={`text-xs font-bold ${config.color}`}>{level}</span>
              {threat.status === 'ALERT-FAST' && (
                <span className="text-[9px] font-bold text-red-400 bg-red-500/20 px-1 rounded">FAST</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <span className="text-[10px] font-mono text-slate-500 bg-black/30 px-2 py-0.5 rounded">
            {formatTime(threat.timestamp)}{threat.endTimestamp ? ` – ${formatTime(threat.endTimestamp)}` : ''}
          </span>
          {/* Jump-to icon — visible on hover */}
          {isClickable && (
            <div className={`opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center w-6 h-6 rounded-md ${config.playBg}`}>
              <Play size={10} fill="currentColor" />
            </div>
          )}
        </div>
      </div>

      {threat.descriptor && sanitizeDescriptor(threat.descriptor) && (
        <p className="text-xs text-slate-300 leading-relaxed mb-2">
          {sanitizeDescriptor(threat.descriptor)}
        </p>
      )}

      <div className="flex items-center space-x-3 text-[10px] text-slate-500 font-mono">
        {threat.windowScore !== undefined && <span>w={threat.windowScore.toFixed(2)}</span>}
        {threat.severity !== undefined && <span>sev={threat.severity.toFixed(2)}</span>}
        {threat.gates && threat.gates.length > 0 && (
          <span>gates={threat.gates.join(',')}</span>
        )}
      </div>

      {/* Click hint text — visible on hover */}
      {isClickable && (
        <p className="text-[9px] text-slate-600 mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
          Click to jump to this moment
        </p>
      )}
    </button>
  );
};

export default ThreatClip;
