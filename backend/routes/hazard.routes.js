import express from 'express';
import { processHazardZone } from '../controllers/hazard.controllers.js';

const router = express.Router();

router.post('/hazards', processHazardZone);

export default router;
