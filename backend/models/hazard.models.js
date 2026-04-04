import mongoose from 'mongoose';

/**
 * Hazard Model
 * 
 * Stores flood hazard zones detected by the Python flood_detector.py pipeline.
 * Each document represents one hazard polygon (either currently flooded or
 * predicted-to-spread), persisted so the frontend can query and render them.
 */
const hazardSchema = new mongoose.Schema({
    // "flood_current" = area currently under water (Otsu detection)
    // "flood_spread"  = area where water may expand next (morphological prediction)
    hazard_type: {
        type: String,
        enum: ['flood_current', 'flood_spread'],
        required: true
    },

    // GeoJSON geometry — Polygon or MultiPolygon
    geometry: {
        type: {
            type: String,
            enum: ['Polygon', 'MultiPolygon'],
            required: true
        },
        coordinates: {
            type: mongoose.Schema.Types.Mixed,
            required: true
        }
    },

    // Which SEN1FLOODS11 chip / event produced this hazard
    source_event: {
        type: String,
        default: 'unknown'
    },

    // Number of affected users found when this hazard was ingested
    affected_user_count: {
        type: Number,
        default: 0
    },

    created_at: {
        type: Date,
        default: Date.now
    }
});

// 2dsphere index enables $geoWithin and $geoIntersects queries
hazardSchema.index({ geometry: '2dsphere' });

export default mongoose.model('Hazard', hazardSchema);
