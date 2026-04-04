import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import connectDB from './config/connectDB.js';
import hazardRoutes from './routes/hazard.routes.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;
app.use(cors());
app.use(express.json());

// Routes
app.use('/api', hazardRoutes);
// Root route
app.get('/', (req, res) => {
  res.send('Welcome to ResQ API');
});

// Custom error middleware
app.listen(PORT, async () => {
    try {
        await connectDB();
        console.log(`Server is running on http://localhost:${PORT}`);
    } catch (error) {
        console.error("MongoDb connection failed: ", error);
        process.exit(1);
    }
});