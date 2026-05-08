const express = require('express');
const router = express.Router();
const { sessions } = require('./sessions');

/**
 * GET /api/threats?cameraId=cam1&sessionId=xxx
 * Returns threats for a camera/session from live analysis results.
 */
router.get('/', (req, res) => {
  const { cameraId, sessionId } = req.query;

  if (sessionId && sessions[sessionId]) {
    const session = sessions[sessionId];
    const results = session.analyzerHandle ? session.analyzerHandle.results : [];
    // Filter to only threats (ALERT or ALERT-FAST, not FLAG)
    const threats = results
      .filter(r => r.status === 'ALERT' || r.status === 'ALERT-FAST')
      .map((r, i) => ({
        id: r.id || `t_${sessionId}_${i}`,
        cameraId: session.cameraId,
        timestamp: r.startSec,
        endTimestamp: r.endSec,
        level: r.level,
        status: r.status,
        descriptor: r.descriptor,
        severity: r.severity,
        windowScore: r.windowScore,
        smoothedScore: r.smoothedScore,
        gates: r.gates,
        eventTags: r.eventTags,
      }));
    return res.json(threats);
  }

  if (!cameraId) {
    return res.status(400).json({ error: 'cameraId or sessionId is required' });
  }

  // Return empty for cameras without active sessions
  res.json([]);
});

module.exports = { router };
