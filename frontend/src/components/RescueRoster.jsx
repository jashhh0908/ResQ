import React from 'react';
import HUDContainer from './HUDContainer';
import { Skull, Phone, AlertOctagon } from 'lucide-react';

const StatusBadge = ({ status }) => {
    if (status === 'pending') {
        return (
            <span className="bg-amber-500/20 text-amber-400 border border-amber-500/50 px-2 py-0.5 rounded text-[9px] tracking-widest uppercase font-bold shadow-[0_0_8px_rgba(234,179,8,0.3)]">
                PENDING
            </span>
        );
    }
    if (status === 'failed') {
        return (
            <span className="bg-rose-500/20 text-rose-400 border border-rose-500/50 px-2 py-0.5 rounded text-[9px] tracking-widest uppercase font-bold shadow-[0_0_8px_rgba(244,63,94,0.3)]">
                FAILED
            </span>
        );
    }
    return null;
};

const RescueRoster = ({ users = [] }) => {
    const list = users.filter(u => u.alert_status === 'pending' || u.alert_status === 'failed');

    return (
        <HUDContainer className="fixed top-[58%] -translate-y-1/2 left-4 z-50 w-80 h-[40vh] rounded-xl flex flex-col">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-700/40">
                <div className="flex items-center gap-2.5">
                    <div className="relative">
                        <Skull className="w-4 h-4 text-rose-500" />
                        <span className="absolute -top-1 -right-1 w-1.5 h-1.5 bg-rose-500 rounded-full animate-ping" />
                    </div>
                    <h2 className="text-[10px] font-black uppercase tracking-[0.2em] text-white">
                        Critical: Pending Rescues
                    </h2>
                </div>
                <span className="bg-rose-500/10 text-rose-500 border border-rose-500/30 px-2 py-0.5 rounded text-[9px] font-black font-mono tracking-widest shadow-[0_0_8px_rgba(244,63,94,0.3)]">
                    {list.length} OPS
                </span>
            </div>

            {/* List */}
            <div className="overflow-y-auto flex-1 p-3 space-y-2">
                {list.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-10 gap-3 opacity-30">
                        <AlertOctagon className="w-8 h-8 text-slate-500" />
                        <p className="text-[9px] font-mono font-bold uppercase tracking-[0.3em] text-slate-500">Sector Secured</p>
                    </div>
                ) : (
                    list.map(u => (
                        <div
                            key={u._id}
                            className="relative p-3 bg-slate-900/40 border-l-2 border-slate-700/40 hover:border-rose-500/60 hover:bg-slate-800/40 transition-all cursor-crosshair group"
                        >
                            <div className="flex items-start justify-between mb-2">
                                <div>
                                    <p className="text-xs font-bold text-slate-100 uppercase leading-tight group-hover:text-white transition-colors">
                                        {u.name}
                                    </p>
                                    <p className="text-[8px] font-mono text-slate-600 italic mt-0.5 tracking-tight">
                                        UID: {String(u._id).slice(-8).toUpperCase()}
                                    </p>
                                </div>
                                <StatusBadge status={u.alert_status} />
                            </div>
                            <div className="flex items-center gap-1.5">
                                <Phone className="w-3 h-3 text-slate-600" />
                                <span className="text-[10px] font-mono text-slate-500 tracking-tighter">{u.phone}</span>
                            </div>
                        </div>
                    ))
                )}
            </div>

            {/* Footer */}
            <div className="px-5 py-2.5 border-t border-slate-700/40 flex justify-between items-center">
                <span className="text-[8px] font-mono text-slate-600 tracking-widest italic animate-pulse">LIVE_SYNC_ACTIVE</span>
                <span className="text-[8px] font-mono text-slate-600 tracking-widest italic">~12ms LAT</span>
            </div>
        </HUDContainer>
    );
};

export default RescueRoster;