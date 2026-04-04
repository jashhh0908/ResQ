import mongoose from 'mongoose';
import dotenv from 'dotenv';
import connectDB from './config/connectDB.js';
import User from './models/user.models.js';

dotenv.config();

const seedUsers = async () => {
    try {
        await connectDB();
        
        // 1. Clear existing users first to avoid duplicates
        await User.deleteMany({});
        console.log("Cleared existing database users.");

        const dummyUsers = [
            // --- USERS INSIDE THE POLYGON ---
            {
                name: "Alice (Inside Center)",
                phone: "+15550001111",
                location: {
                    type: "Point",
                    // This is safely inside our test triangle
                    coordinates: [-122.420000, 37.770000] 
                }
            },
            {
                name: "Bob (Inside Edge)",
                phone: "+15550002222",
                location: {
                    type: "Point",
                    // Closer to the border but still inside
                    coordinates: [-122.425000, 37.772000] 
                }
            },
            
            // --- USERS OUTSIDE THE POLYGON ---
            {
                name: "Charlie (Outside - Far North)",
                phone: "+15550003333",
                location: {
                    type: "Point",
                    // Way too far North
                    coordinates: [-122.420000, 37.800000] 
                }
            },
            {
                name: "Diana (Outside - East)",
                phone: "+15550004444",
                location: {
                    type: "Point",
                    // Way too far East
                    coordinates: [-122.390000, 37.770000] 
                }
            }
        ];

        // 2. Insert the dummy data
        await User.insertMany(dummyUsers);
        console.log(`Successfully seeded ${dummyUsers.length} test users!`);
        console.log("If you run your API test now, it should only catch Alice and Bob.");
        
        // 3. Close the connection gracefully
        mongoose.connection.close();
        process.exit(0);
    } catch (error) {
        console.error("Database seeding failed:", error);
        process.exit(1);
    }
};

seedUsers();
