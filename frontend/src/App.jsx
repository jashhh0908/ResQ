import React, { useState, useEffect } from 'react';
import { io } from 'socket.io-client';
import Dispatch from './pages/Dispatch';

const SOCKET_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:5000';

function App() {
    const [isConnected, setIsConnected] = useState(false);
    const [logs, setLogs] = useState([]);
    const [dashboardData, setDashboardData] = useState({
        hazard_breakdown: { flood_current: 0, flood_spread: 0 },
        affected: {
            in_flood_zone: 0,
            in_spread_zone: 0,
            flood_zone_users: [],
            spread_zone_users: []
        },
        active_polygons: []
    });

    useEffect(() => {
        const socket = io(SOCKET_URL);

        socket.on('connect', () => {
            setIsConnected(true);
            addLog("System Uplink Established. Satellite feed synced.");
        });

        socket.on('disconnect', () => {
            setIsConnected(false);
            addLog("⚠️ Uplink Interrupted. Attempting reconnection...");
        });

        socket.on('update_dashboard', (data) => {
            setDashboardData(data);
            
            // Logic for auto-logging based on new data
            if (data.hazard_breakdown.flood_current > 0) {
                addLog(`🚨 CRITICAL: ${data.affected.in_flood_zone} civilians detected in active flood zone. Dispatching alerts...`);
            }
            if (data.hazard_breakdown.flood_spread > 0) {
                addLog(`🟡 WARNING: ${data.affected.in_spread_zone} civilians in predicted path. Preparing evacuation warnings.`);
            }
        });

        // Mock state hydration if needed (can be fetched from GET /api/state)
        fetch(`${SOCKET_URL}/api/state`)
            .then(res => res.json())
            .then(data => {
                if (data && data.affected) setDashboardData(data);
            })
            .catch(err => console.log("State hydration skipped."));

        return () => {
            socket.disconnect();
        };
    }, []);

    const addLog = (message) => {
        setLogs(prev => [{
            timestamp: new Date().toISOString(),
            message
        }, ...prev].slice(0, 50)); // Keep last 50 logs
    };

    return (
        <Dispatch 
            data={dashboardData} 
            isConnected={isConnected}
            logs={logs}
        />
    );
}

export default App;
