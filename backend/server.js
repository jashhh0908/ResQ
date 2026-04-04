import express from 'express';
import cors from 'cors';
import { createServer } from 'http';
import { Server } from 'socket.io';
import dotenv from 'dotenv';
import connectDB from './config/connectDB.js';
import hazardRoutes from './routes/hazard.routes.js';

dotenv.config();

const app = express();
const PORT = process.env.PORT || 5000;
app.use(cors());
app.use(express.json({ limit: '50mb' }));

const httpServer = createServer(app);
const io = new Server(httpServer, {
    cors: {
        origin: "*", // allow all for dev
        methods: ["GET", "POST"]
    }
});

// Attach io to app so routes can access it
app.set('socketio', io);

io.on('connection', (socket) => {
    console.log('Client connected to command center:', socket.id);
});

// Routes
app.use('/api', hazardRoutes);
// Root route
app.get('/', (req, res) => {
  res.send('Welcome to ResQ API');
});

// Custom error middleware
httpServer.listen(PORT, async () => {
    try {
        await connectDB();
        console.log(`Server and Sockets running on http://localhost:${PORT}`);
    } catch (error) {
        console.error("MongoDb connection failed: ", error);
        process.exit(1);
    }
});