import mongoose from 'mongoose';

const userSchema = new mongoose.Schema({
    name: {
        type: String,
        required: true
    },
    phone: {
        type: String,
        required: true
    },
    alert_status: {
        type: String,
        enum: ['pending', 'queued', 'in-progress', 'completed', 'failed', 'busy'],
        default: 'pending'
    },
    location: {
        type: {
            type: String,
            enum: ['Point'],
            required: true
        },
        coordinates: {
            type: [Number],
            required: true
        }
    },
    last_updated: {
        type: Date,
        default: Date.now
    }
});

// Geospatial index for the location field
userSchema.index({ location: '2dsphere' });

export default mongoose.model('User', userSchema);
