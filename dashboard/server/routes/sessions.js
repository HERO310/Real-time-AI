const express = require('express');
const router = express.Router();
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const { v4: uuidv4 } = require('uuid');
const { startAnalysis } = require('../services/analyzer');

const LIVE_VIDEO_DIR = path.join(__dirname, '..', 'live_video');

// Ensure live_video directory exists
if (!fs.existsSync(LIVE_VIDEO_DIR)) {
  fs.mkdirSync(LIVE_VIDEO_DIR, { recursive: true });
}

// In-memory session store
const sessions = {};

// Multer storage config for video uploads
const storage = multer.diskStorage({
  destination: (req, file, cb) => {
    const sessionId = req.body.sessionId || req.query.sessionId;
    if (!sessionId || !sessions[sessionId]) {
      return cb(new Error('Invalid or missing sessionId'));
    }
    const sessionDir = path.join(LIVE_VIDEO_DIR, sessionId);
    if (!fs.existsSync(sessionDir)) {
      fs.mkdirSync(sessionDir, { recursive: true });
    }
    cb(null, sessionDir);
  },
  filename: (req, file, cb) => {
    const ext = path.extname(file.originalname) || '.mp4';
    cb(null, `uploaded${ext}`);
  },
});

const upload = multer({
  storage,
  limits: { fileSize: 500 * 1024 * 1024 }, // 500MB max
  fileFilter: (req, file, cb) => {
    const allowedTypes = ['video/mp4', 'video/webm', 'video/x-matroska', 'video/avi', 'video/quicktime'];
    if (allowedTypes.includes(file.mimetype) || file.mimetype.startsWith('video/')) {
      cb(null, true);
    } else {
      cb(new Error('Only video files are allowed'));
    }
  },
});

/**
 * POST /api/sessions — Create a new session
 * Body: { cameraId: 'cam1' | 'cam2' }
 */
router.post('/', (req, res) => {
  const { cameraId } = req.body;
  if (!cameraId) {
    return res.status(400).json({ error: 'cameraId is required' });
  }

  const sessionId = `session_${Date.now()}_${uuidv4().slice(0, 8)}`;
  const sessionDir = path.join(LIVE_VIDEO_DIR, sessionId);
  fs.mkdirSync(sessionDir, { recursive: true });

  sessions[sessionId] = {
    id: sessionId,
    cameraId,
    createdAt: new Date().toISOString(),
    status: 'created', // created -> recording -> analyzing -> complete
    chunkCount: 0,
    results: [],
    analyzerHandle: null,
    sessionDir,
  };

  console.log(`[Sessions] Created session ${sessionId} for camera ${cameraId}`);
  res.json({ sessionId, cameraId, status: 'created' });
});

/**
 * POST /api/sessions/upload — Upload a video file for cam2 analysis
 * Multipart form: sessionId (field) + video (file)
 */
router.post('/upload', upload.single('video'), (req, res) => {
  const sessionId = req.body.sessionId || req.query.sessionId;
  const session = sessions[sessionId];

  if (!session) {
    return res.status(400).json({ error: 'Invalid session' });
  }

  if (!req.file) {
    return res.status(400).json({ error: 'No video file provided' });
  }

  const videoPath = req.file.path;
  session.status = 'analyzing';
  session.uploadedFile = videoPath;

  console.log(`[Sessions] Upload received for session ${sessionId}: ${videoPath}`);

  // Get io from the app
  const io = req.app.get('io');

  // Start analysis
  const handle = startAnalysis(videoPath, sessionId, session.sessionDir, io);
  session.analyzerHandle = handle;

  res.json({
    sessionId,
    status: 'analyzing',
    videoPath: path.basename(videoPath),
  });
});

/**
 * GET /api/sessions/:id/results — Get session results
 */
router.get('/:id/results', (req, res) => {
  const session = sessions[req.params.id];
  if (!session) {
    return res.status(404).json({ error: 'Session not found' });
  }

  // Try to read results from analyzer handle first
  const results = session.analyzerHandle ? session.analyzerHandle.results : [];

  // Also check for saved results.json
  const resultsPath = path.join(session.sessionDir, 'results.json');
  if (fs.existsSync(resultsPath)) {
    try {
      const saved = JSON.parse(fs.readFileSync(resultsPath, 'utf-8'));
      return res.json(saved);
    } catch (err) {
      // Fall through to live results
    }
  }

  res.json({
    sessionId: session.id,
    status: session.status,
    totalResults: results.length,
    results,
  });
});

/**
 * POST /api/sessions/:id/stop — Stop a session
 */
router.post('/:id/stop', (req, res) => {
  const session = sessions[req.params.id];
  if (!session) {
    return res.status(404).json({ error: 'Session not found' });
  }

  if (session.analyzerHandle) {
    session.analyzerHandle.kill();
    session.analyzerHandle = null;
  }
  session.status = 'complete';

  console.log(`[Sessions] Stopped session ${req.params.id}`);
  res.json({ sessionId: session.id, status: 'complete' });
});

/**
 * GET /api/sessions/past — List all completed past sessions from live_video/ dir
 * Returns metadata for each session folder that has a results.json
 */
router.get('/past', (req, res) => {
  try {
    const entries = fs.readdirSync(LIVE_VIDEO_DIR, { withFileTypes: true });
    const pastSessions = [];

    for (const entry of entries) {
      if (!entry.isDirectory() || !entry.name.startsWith('session_')) continue;

      const sessionDir = path.join(LIVE_VIDEO_DIR, entry.name);
      const resultsPath = path.join(sessionDir, 'results.json');
      if (!fs.existsSync(resultsPath)) continue;

      try {
        const data = JSON.parse(fs.readFileSync(resultsPath, 'utf-8'));
        const results = data.results || [];
        const threatCount = results.filter(r =>
          r.status === 'ALERT' || r.status === 'ALERT-FAST'
        ).length;

        // Collect chunk files for playback
        const allFiles = fs.readdirSync(sessionDir);
        const chunks = allFiles
          .filter(f => f.match(/^chunk_\d+\.webm$/))
          .sort();

        // Batch mp4s as fallback
        const batches = allFiles
          .filter(f => f.match(/^batch_\d+\.mp4$/))
          .sort();

        // Uploaded files as fallback
        const uploads = allFiles
          .filter(f => f.startsWith('uploaded.'))
          .sort();

        const stat = fs.statSync(resultsPath);
        pastSessions.push({
          sessionId: entry.name,
          completedAt: data.completedAt || stat.mtime.toISOString(),
          totalWindows: data.totalWindows || results.length,
          threatCount,
          hasVideo: chunks.length > 0 || batches.length > 0 || uploads.length > 0,
          chunks,
          batches,
          uploads,
        });
      } catch (_) {
        // skip malformed sessions
      }
    }

    // Sort newest first
    pastSessions.sort((a, b) => new Date(b.completedAt) - new Date(a.completedAt));
    res.json(pastSessions);
  } catch (err) {
    console.error('[Sessions] Error listing past sessions:', err);
    res.status(500).json({ error: 'Failed to list past sessions' });
  }
});

/**
 * GET /api/sessions/past/:id/results — Get results.json for a past session
 */
router.get('/past/:id/results', (req, res) => {
  const sessionId = req.params.id;
  // Security: ensure no path traversal
  if (!sessionId.match(/^session_[\w]+$/)) {
    return res.status(400).json({ error: 'Invalid session id' });
  }

  const resultsPath = path.join(LIVE_VIDEO_DIR, sessionId, 'results.json');
  if (!fs.existsSync(resultsPath)) {
    return res.status(404).json({ error: 'No results found for this session' });
  }

  try {
    const data = JSON.parse(fs.readFileSync(resultsPath, 'utf-8'));
    res.json(data);
  } catch (err) {
    res.status(500).json({ error: 'Failed to read results' });
  }
});

// Export sessions store so sockets can access it
module.exports = { router, sessions, LIVE_VIDEO_DIR };
