const { Server } = require('socket.io');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');
const { promisify } = require('util');
const { v4: uuidv4 } = require('uuid');
const { startAnalysis } = require('../services/analyzer');

const execFileAsync = promisify(execFile);

// Accumulate N chunks before running analysis
// 4 chunks × ~5s = ~20s of video → enough for high_accuracy (10s window)
const CHUNKS_PER_BATCH = 4;

let sessions, LIVE_VIDEO_DIR;

module.exports = (server) => {
  const sessionsModule = require('../routes/sessions');
  sessions = sessionsModule.sessions;
  LIVE_VIDEO_DIR = sessionsModule.LIVE_VIDEO_DIR;

  const io = new Server(server, {
    cors: { origin: '*', methods: ['GET', 'POST'] },
    maxHttpBufferSize: 50 * 1024 * 1024,
  });

  io.on('connection', (socket) => {
    console.log('[Socket] Client connected:', socket.id);

    // ── start_session ──────────────────────────────────────────────────────
    socket.on('start_session', (data) => {
      const { cameraId, analysisMode } = data;
      const sessionId = `session_${Date.now()}_${uuidv4().slice(0, 8)}`;
      const sessionDir = path.join(LIVE_VIDEO_DIR, sessionId);
      fs.mkdirSync(sessionDir, { recursive: true });

      sessions[sessionId] = {
        id: sessionId,
        cameraId,
        createdAt: new Date().toISOString(),
        status: 'recording',
        chunkCount: 0,
        pendingChunks: [],
        allChunks: [],
        batchIndex: 0,
        analysisRunning: false,
        analyzerHandle: null,
        analysisMode: analysisMode || 'fast',
        sessionDir,
      };

      socket.join(sessionId);
      console.log(`[Socket] Session started: ${sessionId} cameraId=${cameraId}`);
      socket.emit('session_started', { sessionId, cameraId, status: 'recording' });
    });

    // ── join_session ───────────────────────────────────────────────────────
    socket.on('join_session', (data) => {
      const { sessionId } = data;
      if (sessions[sessionId]) {
        socket.join(sessionId);
        console.log(`[Socket] ${socket.id} joined session ${sessionId}`);
      }
    });

    async function processQueue(session, sessionId) {
      if (session.analysisRunning) return;
      session.analysisRunning = true;

      try {
        while (session.pendingChunks && session.pendingChunks.length > 0) {
          // If not stopped, only run if we have a full batch.
          // If stopped, we can run a partial batch to finish remaining chunks.
          if (!session.isStopped && session.pendingChunks.length < CHUNKS_PER_BATCH) {
            break;
          }

          const takeCount = Math.min(CHUNKS_PER_BATCH, session.pendingChunks.length);
          const batch = session.pendingChunks.splice(0, takeCount);
          
          await triggerBatchAnalysis(session, sessionId, batch, io);
        }
      } catch (err) {
        console.error(`[Socket] processQueue error:`, err.message);
      } finally {
        session.analysisRunning = false;
        // Finalize only when stopped AND all chunks are completely analyzed
        if (session.isStopped && session.pendingChunks && session.pendingChunks.length === 0) {
          finalizeSession(session, sessionId, io);
        }
      }
    }

    // ── video_chunk ────────────────────────────────────────────────────────
    socket.on('video_chunk', (data) => {
      const { sessionId, chunkIndex } = data;
      const session = sessions[sessionId];
      if (!session) {
        socket.emit('error_msg', { error: 'Invalid session' });
        return;
      }

      // Ensure chunk-tracking fields exist
      if (!session.pendingChunks) session.pendingChunks = [];
      if (!session.allChunks) session.allChunks = [];
      if (session.batchIndex === undefined) session.batchIndex = 0;
      if (session.analysisRunning === undefined) session.analysisRunning = false;

      const filename = `chunk_${String(chunkIndex).padStart(4, '0')}.webm`;
      const chunkPath = path.join(session.sessionDir, filename);

      try {
        fs.writeFileSync(chunkPath, Buffer.from(data.data));
        session.chunkCount++;
        session.pendingChunks.push(chunkPath);
        session.allChunks.push(chunkPath);

        console.log(`[Socket] Chunk #${chunkIndex} saved (${data.data.byteLength} B) session=${sessionId}`);
        socket.emit('chunk_saved', { sessionId, chunkIndex, filename });

        // Trigger analysis if we have enough chunks
        if (session.pendingChunks.length >= CHUNKS_PER_BATCH && !session.analysisRunning) {
          processQueue(session, sessionId).catch(err => console.error(err));
        }
      } catch (err) {
        console.error('[Socket] Chunk save error:', err.message);
        socket.emit('error_msg', { error: 'Failed to save chunk' });
      }
    });

    // ── stop_session ───────────────────────────────────────────────────────
    socket.on('stop_session', (data) => {
      const { sessionId } = data;
      const session = sessions[sessionId];
      if (!session) return;

      console.log(`[Socket] Stopping session capture ${sessionId}, waiting for analysis to finish`);
      session.isStopped = true;

      // Kick the queue process to finish any remaining partial batches
      processQueue(session, sessionId).catch(err => console.error(err));
    });

    socket.on('disconnect', () => {
      console.log('[Socket] Client disconnected:', socket.id);
    });
  });

  return io;
};

// ─────────────────────────────────────────────────────────────────────────────
// triggerBatchAnalysis — async, non-blocking (uses execFileAsync not execSync)
// ─────────────────────────────────────────────────────────────────────────────
async function triggerBatchAnalysis(session, sessionId, chunkPaths, io) {
  if (!chunkPaths || chunkPaths.length === 0) return;

  const batchIdx = session.batchIndex++;
  const batchBase = `batch_${String(batchIdx).padStart(3, '0')}`;
  const batchDir = session.sessionDir;
  const concatPath = path.join(batchDir, `${batchBase}.mp4`);
  const tmpMp4s = [];

  try {
    console.log(`[Batch] Converting ${chunkPaths.length} webm chunks → batch ${batchBase}`);

    // Step 1: Convert each VP9 webm → fixed-fps x264 mp4 (ASYNC — non-blocking)
    for (const chunkPath of chunkPaths) {
      const stem = path.basename(chunkPath, '.webm');
      const mp4Path = path.join(batchDir, `${stem}_tmp.mp4`);
      tmpMp4s.push(mp4Path);

      await execFileAsync('ffmpeg', [
        '-y', '-i', chunkPath,
        '-r', '5',                  // 5fps instead of 10 — halves frame count
        '-vf', 'scale=320:-2',      // 320px wide instead of 640 — 4x fewer pixels
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-crf', '28',
        mp4Path,
      ], { timeout: 20000 });
    }

    // Step 2: Build concat list and concatenate (ASYNC — non-blocking)
    const concatList = path.join(batchDir, `${batchBase}_list.txt`);
    fs.writeFileSync(concatList, tmpMp4s.map(p => `file '${p}'`).join('\n'));

    await execFileAsync('ffmpeg', [
      '-y', '-f', 'concat', '-safe', '0',
      '-i', concatList,
      '-c', 'copy',
      concatPath,
    ], { timeout: 15000 });

    // Cleanup temp files
    try { fs.unlinkSync(concatList); } catch (_) {}
    for (const t of tmpMp4s) { try { fs.unlinkSync(t); } catch (_) {} }

    // Verify duration
    const { stdout: durOut } = await execFileAsync('ffprobe', [
      '-v', 'error',
      '-show_entries', 'format=duration',
      '-of', 'default=noprint_wrappers=1',
      concatPath,
    ], { timeout: 5000 });
    const duration = parseFloat(durOut.trim().replace('duration=', ''));
    console.log(`[Batch] ${batchBase} ready: ${duration.toFixed(1)}s`);

    if (duration < 3) {
      console.warn(`[Batch] Too short (${duration}s), skipping`);
      return;
    }

    if (session.analyzedDuration === undefined) {
      session.analyzedDuration = 0;
    }
    const timeOffset = Math.floor(session.analyzedDuration);
    session.analyzedDuration += duration;

    // Step 3: Run analysis — use the mode chosen by the user
    const analysisMode = session.analysisMode || 'fast';
    const batchStem = `${sessionId}_${batchBase}`;
    const handle = startAnalysis(
      concatPath,
      batchStem,
      session.sessionDir,
      io,
      { mode: analysisMode, sessionIdOverride: sessionId, timeOffset }
    );
    session.analyzerHandle = handle;

    // Wait for analysis to finish before allowing next batch
    await new Promise((resolve) => {
      handle.process.on('close', resolve);
      handle.process.on('error', resolve);
    });

  } catch (err) {
    console.error(`[Batch] Error in ${batchBase}:`, err.message);
    // Cleanup any leftover tmp files on error
    for (const t of tmpMp4s) { try { if (fs.existsSync(t)) fs.unlinkSync(t); } catch (_) {} }
  }
}

function finalizeSession(session, sessionId, io) {
  session.status = 'complete';
  io.to(sessionId).emit('session_stopped', {
    sessionId,
    totalChunks: session.chunkCount,
    status: 'complete',
  });
}
