import React, { useEffect, useRef } from 'react';
import HUDContainer from './HUDContainer';
import { Activity, Terminal } from 'lucide-react';

const EventTicker = ({ logs = [] }) => {
    const scrollRef = useRef(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = 0;
        }
    }, [logs]);

    return (
        <HUDContainer className="fixed top-[58%] -translate-y-1/2 right-4 z-50 w-80 h-[40vh] rounded-xl flex flex-col overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/40 bg-slate-900/30">
                <div className="flex items-center gap-2.5">
                    <Activity className="w-4 h-4 text-emerald-500" />
                    <h2 className="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-500">
                        Live Dispatch Log
                    </h2>
                </div>
                <div className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_6px_rgba(16,185,129,0.7)]" />
                    <span className="text-[8px] font-mono font-bold text-emerald-500/70 uppercase tracking-widest">REC</span>
                </div>
            </div>

            {/* Log Feed */}
            <div className="flex-1 overflow-y-auto p-3 space-y-2 font-mono" ref={scrollRef}>
                {logs.length === 0 ? (
                    <div className="flex flex-col items-start gap-2 mt-4 opacity-40">
                        <Terminal className="w-5 h-5 text-slate-500" />
                        <p className="text-[10px] text-slate-500 italic animate-pulse">&gt; Awaiting uplink data...</p>
                    </div>
                ) : (
                    logs.map((log, i) => (
                        <div
                            key={i}
                            className={`p-3 rounded border text-[10px] transition-all ${
                                i === 0
                                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.12)]'
                                    : 'bg-slate-900/20 border-slate-700/20 text-slate-400'
                            }`}
                        >
                            <div className="flex justify-between items-center mb-1 opacity-50">
                                <span className="text-[8px] font-black tracking-widest uppercase">
                                    NODE_{String(i).padStart(3, '0')}
                                </span>
                                <span className="text-[8px]">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                            </div>
                            <p className="leading-relaxed tracking-tight">{log.message}</p>
                        </div>
                    ))
                )}
            </div>

            {/* Footer */}
            <div className="px-5 py-2.5 border-t border-slate-700/40 bg-slate-900/30 flex justify-between items-center">
                <div className="flex items-center gap-1.5">
                    <span className="w-1 h-1 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-[8px] font-mono text-slate-600 uppercase tracking-widest">Terminal Active</span>
                </div>
                <span className="text-[8px] font-mono text-slate-600 italic">{logs.length} events</span>
            </div>
        </HUDContainer>
    );
};

export default EventTicker;
