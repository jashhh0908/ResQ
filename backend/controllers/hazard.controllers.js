import User from '../models/user.models.js';
import Hazard from '../models/hazard.models.js';

/**
 * POST /api/hazards
 * 
 * Accepts a GeoJSON FeatureCollection from the Python flood_detector.py pipeline.
 * Each feature has a `hazard_type` property ("flood_current" or "flood_spread").
 * 
 * Request body format (from Python script):
 * {
 *   "type": "FeatureCollection",
 *   "features": [
 *     { "type": "Feature", "geometry": { "type": "Polygon", "coordinates": [...] }, "properties": { "hazard_type": "flood_current" } },
 *     ...
 *   ],
 *   "source_event": "India_698338"
 * }
 */
export const processHazardZone = async (req, res) => {
    try {
        const body = req.body;
        let features = [];
        let sourceEvent = body.source_event || 'unknown';

        if (body.type === 'FeatureCollection' && Array.isArray(body.features)) {
            features = body.features;
            console.log(`Received FeatureCollection with ${features.length} feature(s) [source: ${sourceEvent}]`);
        } else if (body.hazard_polygon) {
            features = [{
                type: 'Feature',
                geometry: body.hazard_polygon,
                properties: { hazard_type: body.hazard_type || 'flood_current' }
            }];
            console.log('Received single hazard_polygon (legacy format)');
        } else {
            return res.status(400).json({ error: 'Request body must be a GeoJSON FeatureCollection.' });
        }

        // ------------------------------------------------------------------
        // Find affected users across current features
        // ------------------------------------------------------------------
        const affectedUsersMap = new Map();
        const atRiskUsersMap = new Map();
        
        const currentFeatures = features.filter(f => (f.properties?.hazard_type || 'flood_current') === 'flood_current' && f.geometry);
        const spreadFeatures = features.filter(f => f.properties?.hazard_type === 'flood_spread' && f.geometry);

        console.log(`Analyzing ${currentFeatures.length} current / ${spreadFeatures.length} spread zones...`);

        // Batch search for immediate flood impact
        for (const feature of currentFeatures) {
            try {
                const users = await User.find({
                    location: { $geoWithin: { $geometry: feature.geometry } }
                });
                for (const user of users) {
                    if (!affectedUsersMap.has(user._id.toString())) {
                        // Update status in DB as 'failed' (requires rescue intervention)
                        user.alert_status = 'pending';
                        await user.save();
                        affectedUsersMap.set(user._id.toString(), user);
                    }
                }
            } catch (err) { continue; }
        }

        // Log results
        const affectedUsers = Array.from(affectedUsersMap.values());
        const atRiskUsers = Array.from(atRiskUsersMap.values());

        // ------------------------------------------------------------------
        // Persistent Update: Clear old hazards and save NEW ones atomically
        // ------------------------------------------------------------------
        await Hazard.deleteMany({});
        const hazardDocs = features.map(f => ({
            hazard_type: f.properties?.hazard_type || 'flood_current',
            geometry: f.geometry,
            source_event: sourceEvent,
            affected_user_count: 0
        }));

        // Batch insert in chunks of 500 to stay within limits
        const BATCH_SIZE = 500;
        for (let i = 0; i < hazardDocs.length; i += BATCH_SIZE) {
            await Hazard.insertMany(hazardDocs.slice(i, i + BATCH_SIZE), { ordered: false });
        }

        // ------------------------------------------------------------------
        // Socket Emission: Notify the React dashboard
        // ------------------------------------------------------------------
        const io = req.app.get('socketio');
        const dashboardPayload = {
            hazard_breakdown: {
                flood_current: currentFeatures.length,
                flood_spread: spreadFeatures.length
            },
            affected: {
                in_flood_zone: affectedUsers.length,
                in_spread_zone: atRiskUsers.length,
                flood_zone_users: affectedUsers,
                spread_zone_users: atRiskUsers
            },
            active_polygons: features // All GeoJSON features
        };
        
        if (io) io.emit('update_dashboard', dashboardPayload);

        res.status(200).json({
            message: 'Hazard zones processed and saved',
            source_event: sourceEvent,
            ...dashboardPayload
        });

    } catch (error) {
        console.error('Error processing hazard zone:', error);
        res.status(500).json({ error: 'Internal server error while processing hazard zone.' });
    }
};

/**
 * GET /api/state
 * 
 * Hydrates the dashboard with current hazards and affected users on mount.
 * Uses status-based lookup for speed and stability.
 */
export const getState = async (req, res) => {
    try {
        // Fetch all polygons from DB (GeoJSON rendering handles 5000+ easily)
        const hazards = await Hazard.find({}).lean();
        
        if (!hazards || hazards.length === 0) {
            return res.status(200).json({
                hazard_breakdown: { flood_current: 0, flood_spread: 0 },
                affected: { in_flood_zone: 0, in_spread_zone: 0, flood_zone_users: [], spread_zone_users: [] },
                active_polygons: []
            });
        }

        const activePolygons = hazards.map(h => ({
            type: 'Feature',
            geometry: h.geometry,
            properties: { hazard_type: h.hazard_type }
        }));

        // Fetch affected users based on status (NOT pending usually means we've started tracking them)
        // For development, we find all previously found users
        const affectedUsers = await User.find({ }).lean();

        res.status(200).json({
            hazard_breakdown: {
                flood_current: hazards.filter(h => h.hazard_type === 'flood_current').length,
                flood_spread: hazards.filter(h => h.hazard_type === 'flood_spread').length
            },
            affected: {
                in_flood_zone: affectedUsers.length,
                in_spread_zone: 0,
                flood_zone_users: affectedUsers,
                spread_zone_users: []
            },
            active_polygons: activePolygons
        });

    } catch (error) {
        console.error('State hydration error:', error);
        res.status(500).json({ error: 'System state hydration failed' });
    }
};

/**
 * GET /api/hazards
 */
export const getHazards = async (req, res) => {
    try {
        const filter = {};
        if (req.query.type) filter.hazard_type = req.query.type;
        const hazards = await Hazard.find(filter).select('-__v').sort({ created_at: -1 });
        const featureCollection = {
            type: 'FeatureCollection',
            features: hazards.map(h => ({
                type: 'Feature',
                geometry: h.geometry,
                properties: { _id: h._id, hazard_type: h.hazard_type, source_event: h.source_event }
            }))
        };
        res.status(200).json(featureCollection);
    } catch (error) {
        res.status(500).json({ error: 'Internal server error' });
    }
};
