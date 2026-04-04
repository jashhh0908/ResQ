import React from 'react';
import { MapContainer, TileLayer, Polygon, CircleMarker, Tooltip, ZoomControl } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';

const MapViewer = ({ activePolygons = [], floodZoneUsers = [] }) => {
    
    const flipPolygonCoordinates = (geojsonCoords) => {
        if (!geojsonCoords || !Array.isArray(geojsonCoords)) return [];
        return geojsonCoords.map(ring => 
            ring.map(coordPair => [coordPair[1], coordPair[0]])
        );
    };

    const flipPointCoordinates = (pointCoords) => {
        if (!pointCoords || pointCoords.length < 2) return [0, 0];
        return [pointCoords[1], pointCoords[0]];
    };

    const getHazardStyle = (feature) => {
        const type = feature.properties?.hazard_type || 'flood_current';

        if (type === 'flood_spread') {
            // Projected Spread: Orange, highly transparent, dashed border
            return { color: '#f59e0b', weight: 2, dashArray: '5, 5', fillColor: '#f59e0b', fillOpacity: 0.15 };
        } else {
            // Active Hazard: Red, semi-transparent, solid border
            return { color: '#ef4444', weight: 1.5, fillColor: '#ef4444', fillOpacity: 0.35 };
        }
    };

    return (
        <div className="absolute inset-0 z-0 h-screen w-screen bg-slate-950 overflow-hidden cursor-crosshair">
            {/* Global HUD Scanline Overlay */}
            <div className="pointer-events-none absolute inset-0 z-10 w-full h-full">
                <div className="w-full h-1 bg-white/5 blur-md animate-scanline opacity-20" />
            </div>

            {/* Tactical Grid Overlay */}
            <div className="pointer-events-none absolute inset-0 z-10 opacity-[0.08] bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]" />

            <MapContainer
                center={[26.975, 93.712]}
                zoom={14}
                zoomControl={false}
                style={{ height: '100%', width: '100%', zIndex: 0, backgroundColor: '#020617' }}
            >
                <TileLayer
                    url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                    attribution='&copy; CARTO'
                />

                <ZoomControl position="bottomright" />

                {/* Polygons (Fixed Styling) */}
                {activePolygons.map((feature, idx) => (
                    <Polygon
                        key={`hazard-${idx}`}
                        positions={flipPolygonCoordinates(feature.geometry.coordinates)}
                        pathOptions={getHazardStyle(feature)}
                    >
                        <Tooltip sticky opacity={0.8} offset={[10, 10]}>
                            <div className="font-mono p-1 leading-none">
                                <p className="text-[10px] font-black uppercase text-slate-800 tracking-widest">
                                    [THREAT_ID: AX-{idx}]
                                </p>
                                <p className={`text-[8px] mt-1 uppercase font-bold ${
                                    feature.properties?.hazard_type === 'flood_spread'
                                        ? 'text-amber-500'
                                        : 'text-rose-500'
                                }`}>
                                    CLASS: {feature.properties?.hazard_type === 'flood_spread' ? 'PROJECTED SPREAD' : 'ACTIVE HAZARD'}
                                </p>
                            </div>
                        </Tooltip>
                    </Polygon>
                ))}

                {/* Tactical Radar Blips (Users - Fixed Styling) */}
                {floodZoneUsers.map((user) => (
                    <CircleMarker
                        key={user._id}
                        center={flipPointCoordinates(user.location.coordinates)}
                        radius={5}
                        weight={1}
                        color={'#000'}
                        fillOpacity={1}
                        fillColor={
                            user.alert_status === 'completed' ? '#22c55e' : 
                            user.alert_status === 'pending' ? '#facc15' : '#ef4444'
                        }
                        className={user.alert_status === 'failed' ? 'radar-pulse-red' : 'radar-pulse-yellow'}
                    >
                        <Tooltip direction="top" offset={[0, -10]} opacity={1}>
                            <div className="font-mono p-2 bg-slate-950 text-white rounded shadow-2xl border border-white/20 min-w-[140px]">
                                <div className="flex justify-between items-center mb-1 border-b border-white/10 pb-1">
                                    <span className="text-[8px] font-black text-rose-500 uppercase tracking-widest italic">Active_Target</span>
                                    <span className="text-[7px] text-slate-500 tracking-tighter italic">V_0.4</span>
                                </div>
                                <p className="font-black text-xs uppercase tracking-tight text-white mb-0.5">{user.name}</p>
                                <div className="flex items-center justify-between text-[9px] font-bold text-slate-400">
                                    <span>COORD: {user.location.coordinates[1].toFixed(4)}, {user.location.coordinates[0].toFixed(4)}</span>
                                </div>
                            </div>
                        </Tooltip>
                    </CircleMarker>
                ))}
            </MapContainer>

            {/* Static HUD Decoration */}
            <div className="pointer-events-none absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-10 w-24 h-24 border border-white/5 rounded-full flex items-center justify-center">
                <div className="w-1 h-8 bg-white/5 rounded-full" />
                <div className="h-1 w-8 bg-white/5 rounded-full absolute" />
            </div>
        </div>
    );
};

export default MapViewer;