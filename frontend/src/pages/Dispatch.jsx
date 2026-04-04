import React from 'react';
import TopNav from '../components/TopNav';
import MetricsHUD from '../components/MetricsHUD';
import MapViewer from '../components/MapViewer';
import RescueRoster from '../components/RescueRoster';
import EventTicker from '../components/EventTicker';

const Dispatch = ({ data, isConnected, logs }) => {
    return (
        <div className="h-screen w-screen overflow-hidden bg-slate-900 border-4 border-slate-800 relative">
            <MapViewer 
                activePolygons={data.active_polygons}
                floodZoneUsers={data.affected.flood_zone_users}
            />

            <TopNav isConnected={isConnected} />
            
            <MetricsHUD 
                hazardBreakdown={data.hazard_breakdown}
                affected={data.affected}
            />

            <RescueRoster users={data.affected.flood_zone_users} />

            <EventTicker logs={logs} />

            {/* Aesthetic Grain Overlay */}
            <div className="pointer-events-none absolute inset-0 z-[100] opacity-[0.03] bg-[url('https://grainy-gradients.vercel.app/noise.svg')]" />
        </div>
    );
};

export default Dispatch;
