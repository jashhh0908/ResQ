import React from 'react';
import HUDContainer from './HUDContainer';
import { AlertTriangle, Users, PhoneCall, Zap } from 'lucide-react';

const MetricCard = ({ icon: Icon, label, value, subValue, accent }) => {
    const accents = {
        rose:    { text: 'text-rose-500',    bg: 'bg-rose-500/10',    border: 'border-rose-500/30',    bar: 'bg-rose-500' },
        amber:   { text: 'text-amber-500',   bg: 'bg-amber-500/10',   border: 'border-amber-500/30',   bar: 'bg-amber-500' },
        emerald: { text: 'text-emerald-500', bg: 'bg-emerald-500/10', border: 'border-emerald-500/30', bar: 'bg-emerald-500' },
        sky:     { text: 'text-sky-500',     bg: 'bg-sky-500/10',     border: 'border-sky-500/30',     bar: 'bg-sky-500' },
    };
    const c = accents[accent] || accents.sky;

    return (
        <HUDContainer className="flex-1 min-w-[200px] rounded-xl p-5 flex flex-col gap-2">
            <div className="flex items-center justify-between">
                <span className="text-[10px] font-bold text-slate-400 tracking-widest uppercase">
                    {label}
                </span>
                <div className={`p-1.5 rounded ${c.bg} border ${c.border}`}>
                    <Icon className={`w-3.5 h-3.5 ${c.text}`} />
                </div>
            </div>
            <div className="flex items-baseline gap-2">
                <span className={`text-4xl font-black font-mono tracking-tight text-white`}>
                    {value}
                </span>
                {subValue && (
                    <span className="text-xs text-slate-500 font-mono font-normal">{subValue}</span>
                )}
            </div>
            {/* Status bar */}
            <div className="h-0.5 w-full bg-slate-800 rounded-full overflow-hidden mt-1">
                <div className={`h-full w-1/2 ${c.bar} opacity-40 rounded-full`} />
            </div>
        </HUDContainer>
    );
};

const MetricsHUD = ({ hazardBreakdown = {}, affected = {} }) => {
    const flood_current = hazardBreakdown.flood_current || 0;
    const flood_spread  = hazardBreakdown.flood_spread  || 0;
    const activeHazards = flood_current + flood_spread;

    const inFlood  = affected.in_flood_zone  || 0;
    const inSpread = affected.in_spread_zone || 0;
    const total    = inFlood + inSpread;

    const allUsers   = affected.flood_zone_users || [];
    const alerted    = allUsers.filter(u => u.alert_status !== 'pending').length;
    const alertRate  = allUsers.length > 0 ? Math.round((alerted / allUsers.length) * 100) : 0;

    return (
        <div className="fixed top-[88px] left-4 right-4 z-40 flex gap-3">
            <MetricCard
                icon={AlertTriangle}
                label="Active Hazards"
                value={activeHazards}
                subValue={`[${flood_current}H | ${flood_spread}P]`}
                accent="rose"
            />
            <MetricCard
                icon={Users}
                label="Civilians at Risk"
                value={total}
                subValue={`(~${total} est)`}
                accent="amber"
            />
            <MetricCard
                icon={PhoneCall}
                label="Evac Alerts Sent"
                value={`${alertRate}%`}
                subValue={`(${alerted}/${allUsers.length})`}
                accent="emerald"
            />
            
        </div>
    );
};

export default MetricsHUD;