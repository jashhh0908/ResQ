import express from 'express';
import { processHazardZone, getHazards, getState } from '../controllers/hazard.controllers.js';

const router = express.Router();

// POST — receive flood GeoJSON from Python detector + find affected users
router.post('/hazards', processHazardZone);

// GET  — retrieve stored hazard zones (optionally filter by ?type=flood_current)
router.get('/hazards', getHazards);

// GET  — dashboard hydration state
router.get('/state', getState);

export default router;
