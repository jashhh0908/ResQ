import React from 'react';

const HUDContainer = ({ children, className = "", style = {} }) => (
    <div className={`overflow-hidden bg-slate-950/60 backdrop-blur-md border border-slate-700/50 shadow-[0_0_15px_rgba(0,0,0,0.5)] ${className}`} style={style}>
        {/* Targeting reticle corners */}
        <span className="absolute top-0 left-0 w-2.5 h-2.5 border-t-2 border-l-2 border-slate-500/60 z-10" />
        <span className="absolute top-0 right-0 w-2.5 h-2.5 border-t-2 border-r-2 border-slate-500/60 z-10" />
        <span className="absolute bottom-0 left-0 w-2.5 h-2.5 border-b-2 border-l-2 border-slate-500/60 z-10" />
        <span className="absolute bottom-0 right-0 w-2.5 h-2.5 border-b-2 border-r-2 border-slate-500/60 z-10" />
        {/* Top shimmer */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-slate-500/30 to-transparent z-10" />
        {children}
    </div>
);

export default HUDContainer;