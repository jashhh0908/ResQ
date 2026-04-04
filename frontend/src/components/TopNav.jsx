import React, { useState, useEffect } from 'react';
import HUDContainer from './HUDContainer';
import { Radio, Shield, Activity } from 'lucide-react';

const TopNav = ({ isConnected }) => {
    const [time, setTime] = useState(new Date());

    useEffect(() => {
        const t = setInterval(() => setTime(new Date()), 1000);
        return () => clearInterval(t);
    }, []);

    return (
        <HUDContainer className="fixed top-4 left-4 right-4 z-50 rounded-xl flex items-center justify-between px-6 py-3">
            {/* Left: Brand */}
            <div className="flex items-center gap-4">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-rose-500/10 border border-rose-500/30">
                    <Radio className="w-5 h-5 text-rose-500 animate-pulse" />
                </div>
                <div>
                    <h1 className="text-sm font-black tracking-[0.25em] text-white uppercase italic leading-none">
                        AEGIS-CORE // <span className="text-rose-500">DISPATCH</span>
                    </h1>
                    <p className="text-[9px] font-mono text-slate-500 tracking-widest uppercase mt-0.5">
                        DEPLOYMENT: TR-502 // NORTH-ASSAM // STACK_V4
                    </p>
                </div>
            </div>

            {/* Center: System Tags */}
            <div className="hidden lg:flex items-center gap-3">
                <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-900/50 rounded border border-slate-700/30">
                    <Activity className="w-3 h-3 text-sky-500" />
                    <span className="text-[9px] font-mono font-bold text-sky-500 uppercase tracking-widest">SAR_FEED: LIVE</span>
                </div>
                <div className="flex items-center gap-1.5 px-3 py-1 bg-slate-900/50 rounded border border-slate-700/30">
                    <Shield className="w-3 h-3 text-emerald-500" />
                    <span className="text-[9px] font-mono font-bold text-emerald-500 uppercase tracking-widest">GRID_SCAN: ACTIVE</span>
                </div>
            </div>

            {/* Right: Status */}
            <div className="flex items-center gap-5">
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.7)]' : 'bg-rose-500 shadow-[0_0_10px_rgba(239,68,68,0.7)]'} animate-pulse`} />
                    <span className="text-[9px] font-mono font-black tracking-widest uppercase text-slate-300">
                        {isConnected ? 'UPLINK_STABLE' : 'SIGNAL_LOST'}
                    </span>
                </div>
                <div className="w-px h-5 bg-slate-700/60" />
                <span className="text-sm font-mono font-black text-white tabular-nums tracking-tight">
                    {time.toLocaleTimeString()}
                </span>
            </div>
        </HUDContainer>
    );
};

export default TopNav;
