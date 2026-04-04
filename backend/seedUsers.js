import mongoose from 'mongoose';
import dotenv from 'dotenv';
import connectDB from './config/connectDB.js';
import User from './models/user.models.js';

dotenv.config();

/**
 * Seed the Users collection with test users located in/around the
 * SEN1FLOODS11 India_698338 chip area (Assam, NE India).
 * 
 * Chip bounding box:  ~93.689°E – 93.735°E,  ~26.952°N – 26.998°N
 * 
 * We place some users INSIDE the flood zone and some OUTSIDE
 * so we can verify the $geoWithin queries work correctly.
 */
const seedUsers = async () => {
    try {
        await connectDB();
        
        // 1. Clear existing users first to avoid duplicates
        await User.deleteMany({});
        console.log("Cleared existing database users.");

        const dummyUsers = [
            // --- USERS INSIDE THE FLOOD ZONE (within the SAR chip) ---
            {
                name: "Arjun (Inside - River Bank)",
                phone: "+919876543210",
                location: {
                    type: "Point",
                    // Right in the centre of the chip — likely flooded
                    coordinates: [93.712, 26.975]
                }
            },
            {
                name: "Priya (Inside - Low Ground)",
                phone: "+919876543211",
                location: {
                    type: "Point",
                    // Near the western edge of the chip — low-lying area
                    coordinates: [93.695, 26.965]
                }
            },
            {
                name: "Ravi (Inside - Village Centre)",
                phone: "+919876543212",
                location: {
                    type: "Point",
                    // North-central part of chip
                    coordinates: [93.710, 26.990]
                }
            },
            {
                name: "Meera (Inside - Paddy Fields)",
                phone: "+919876543213",
                location: {
                    type: "Point",
                    // Eastern side of chip
                    coordinates: [93.725, 26.970]
                }
            },

            // --- USERS OUTSIDE THE FLOOD ZONE ---
            {
                name: "Karan (Outside - Hilltop, North)",
                phone: "+919876543214",
                location: {
                    type: "Point",
                    // North of the chip, higher elevation
                    coordinates: [93.712, 27.050]
                }
            },
            {
                name: "Deepa (Outside - City, West)",
                phone: "+919876543215",
                location: {
                    type: "Point",
                    // Well west of the chip
                    coordinates: [93.600, 26.970]
                }
            }
        ];

        // 2. Insert the dummy data
        await User.insertMany(dummyUsers);
        console.log(`Successfully seeded ${dummyUsers.length} test users!`);
        console.log("\nUsers INSIDE chip area (should be found by flood queries):");
        dummyUsers.slice(0, 4).forEach(u => 
            console.log(`  📍 ${u.name}  →  [${u.location.coordinates}]`)
        );
        console.log("\nUsers OUTSIDE chip area (should NOT be found):");
        dummyUsers.slice(4).forEach(u => 
            console.log(`  📍 ${u.name}  →  [${u.location.coordinates}]`)
        );
        
        // 3. Close the connection gracefully
        mongoose.connection.close();
        process.exit(0);
    } catch (error) {
        console.error("Database seeding failed:", error);
        process.exit(1);
    }
};

seedUsers();
