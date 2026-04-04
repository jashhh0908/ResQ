import User from '../models/user.models.js';
import Hazard from '../models/hazard.models.js';

/**
 * POST /api/hazards
 * 
 * Accepts a GeoJSON FeatureCollection from the Python flood_detector.py pipeline.
 * Each feature has a `hazard_type` property ("flood_current" or "flood_spread").
 * 
 * For every polygon:
 *   1. Save it to the Hazard collection
 *   2. Query Users whose location falls within the polygon ($geoWithin)
 *   3. Collect all affected users (deduplicated)
 * 
 * Request body format (from Python script):
 * {
 *   "type": "FeatureCollection",
 *   "features": [
 *     {
 *       "type": "Feature",
 *       "geometry": { "type": "Polygon", "coordinates": [...] },
 *       "properties": { "hazard_type": "flood_current" }
 *     },
 *     ...
 *   ],
 *   "source_event": "India_698338"          // optional metadata
 * }
 */
export const processHazardZone = async (req, res) => {
    try {
        const body = req.body;

        // ------------------------------------------------------------------
        // Detect payload format:
        //   A) GeoJSON FeatureCollection  (from flood_detector.py)
        //   B) Legacy single polygon      { hazard_polygon: {...} }
        // ------------------------------------------------------------------
        let features = [];
        let sourceEvent = body.source_event || 'unknown';

        if (body.type === 'FeatureCollection' && Array.isArray(body.features)) {
            // Format A — FeatureCollection from the Python pipeline
            features = body.features;
            console.log(`Received FeatureCollection with ${features.length} feature(s)  [source: ${sourceEvent}]`);
        } else if (body.hazard_polygon) {
            // Format B — legacy single polygon (backwards-compatible)
            features = [{
                type: 'Feature',
                geometry: body.hazard_polygon,
                properties: { hazard_type: body.hazard_type || 'flood_current' }
            }];
            console.log('Received single hazard_polygon (legacy format)');
        } else {
            return res.status(400).json({
                error: 'Request body must be a GeoJSON FeatureCollection or contain a hazard_polygon field.'
            });
        }

        // ------------------------------------------------------------------
        // Clear previous hazard data for a fresh analysis run
        // (In production you'd version these; for the hackathon we overwrite)
        // ------------------------------------------------------------------
        await Hazard.deleteMany({});
        console.log('Cleared previous hazard data.');

        // ------------------------------------------------------------------
        // Process each feature: save to DB + find affected users
        // ------------------------------------------------------------------
        const affectedUsersMap = new Map();   // Deduplicate by user _id
        let savedCount = 0;
        let currentCount = 0;
        let spreadCount = 0;

        // Process in batches to avoid overwhelming MongoDB
        const BATCH_SIZE = 100;
        const hazardDocs = [];

        for (const feature of features) {
            if (!feature.geometry) continue;

            const hazardType = feature.properties?.hazard_type || 'flood_current';

            // Prepare hazard document for batch insert
            hazardDocs.push({
                hazard_type: hazardType,
                geometry: feature.geometry,
                source_event: sourceEvent,
                affected_user_count: 0
            });

            if (hazardType === 'flood_current') currentCount++;
            else spreadCount++;
        }

        // Batch insert all hazard documents
        if (hazardDocs.length > 0) {
            // Insert in chunks to avoid exceeding MongoDB limits
            for (let i = 0; i < hazardDocs.length; i += BATCH_SIZE) {
                const batch = hazardDocs.slice(i, i + BATCH_SIZE);
                await Hazard.insertMany(batch, { ordered: false });
                savedCount += batch.length;
            }
        }

        console.log(`Saved ${savedCount} hazard zones (${currentCount} current, ${spreadCount} spread)`);

        // ------------------------------------------------------------------
        // Query affected users using only flood_current polygons
        // (These are the areas actively flooded right now)
        // ------------------------------------------------------------------
        const currentFeatures = features.filter(
            f => (f.properties?.hazard_type || 'flood_current') === 'flood_current' && f.geometry
        );

        console.log(`Querying affected users across ${currentFeatures.length} flood_current polygon(s)...`);

        for (const feature of currentFeatures) {
            try {
                const users = await User.find({
                    location: {
                        $geoWithin: {
                            $geometry: feature.geometry
                        }
                    }
                });

                for (const user of users) {
                    if (!affectedUsersMap.has(user._id.toString())) {
                        affectedUsersMap.set(user._id.toString(), user);
                    }
                }
            } catch (queryErr) {
                // Some polygons may be too small or degenerate — skip them
                continue;
            }
        }

        // Also check flood_spread polygons for users at risk
        const spreadFeatures = features.filter(
            f => f.properties?.hazard_type === 'flood_spread' && f.geometry
        );

        const atRiskUsersMap = new Map();
        for (const feature of spreadFeatures) {
            try {
                const users = await User.find({
                    location: {
                        $geoWithin: {
                            $geometry: feature.geometry
                        }
                    }
                });

                for (const user of users) {
                    const id = user._id.toString();
                    // Only count as "at risk" if not already in the flooded zone
                    if (!affectedUsersMap.has(id) && !atRiskUsersMap.has(id)) {
                        atRiskUsersMap.set(id, user);
                    }
                }
            } catch (queryErr) {
                continue;
            }
        }

        const affectedUsers = Array.from(affectedUsersMap.values());
        const atRiskUsers = Array.from(atRiskUsersMap.values());

        console.log(`\n--- RESULTS ---`);
        console.log(`Hazard zones saved: ${savedCount}`);
        console.log(`Users in ACTIVE flood zone: ${affectedUsers.length}`);
        affectedUsers.forEach(u => {
            console.log(`  🔴 ${u.name} (${u.phone})`);
        });
        console.log(`Users in PREDICTED spread zone: ${atRiskUsers.length}`);
        atRiskUsers.forEach(u => {
            console.log(`  🟡 ${u.name} (${u.phone})`);
        });

        // ------------------------------------------------------------------
        // Response
        // ------------------------------------------------------------------
        res.status(200).json({
            message: 'Hazard zones processed and saved',
            source_event: sourceEvent,
            hazards_saved: savedCount,
            hazard_breakdown: {
                flood_current: currentCount,
                flood_spread: spreadCount
            },
            affected: {
                in_flood_zone: affectedUsers.length,
                in_spread_zone: atRiskUsers.length,
                flood_zone_users: affectedUsers,
                spread_zone_users: atRiskUsers
            }
        });

    } catch (error) {
        console.error('Error processing hazard zone:', error);
        res.status(500).json({ error: 'Internal server error while processing hazard zone.' });
    }
};


/**
 * GET /api/hazards
 * 
 * Returns all stored hazard zones, optionally filtered by hazard_type.
 * Query params:
 *   ?type=flood_current   — only current flood polygons
 *   ?type=flood_spread    — only predicted spread polygons
 */
export const getHazards = async (req, res) => {
    try {
        const filter = {};
        if (req.query.type) {
            filter.hazard_type = req.query.type;
        }

        const hazards = await Hazard.find(filter)
            .select('-__v')
            .sort({ created_at: -1 });

        // Build a GeoJSON FeatureCollection for easy frontend consumption
        const featureCollection = {
            type: 'FeatureCollection',
            features: hazards.map(h => ({
                type: 'Feature',
                geometry: h.geometry,
                properties: {
                    _id: h._id,
                    hazard_type: h.hazard_type,
                    source_event: h.source_event,
                    created_at: h.created_at
                }
            }))
        };

        res.status(200).json(featureCollection);

    } catch (error) {
        console.error('Error fetching hazards:', error);
        res.status(500).json({ error: 'Internal server error while fetching hazards.' });
    }
};
