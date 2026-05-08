const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');

const CONDA_ENV = 'VADTree';
const REALTIME_SCRIPT = '/data/video_analytics/real-time/run_realtime.py';
const REALTIME_DIR = '/data/video_analytics/real-time';
const RESULTS_ROOT = path.join(REALTIME_DIR, 'results');

/**
 * Parse a single JSONL record into a normalized result object.
 */
function parseJsonlLine(line) {
  try {
    const record = JSON.parse(line.trim());
    return {
      startSec: record.start_s,
      endSec: record.end_s,
      status: record.status,         // ALERT-FAST | ALERT | FLAG
      level: record.level,           // HIGH | MEDIUM | LOW | NORMAL
      windowScore: record.window_score,
      smoothedScore: record.smoothed_score,
      severity: record.severity,
      gates: record.gates || [],
      descriptor: record.descriptor || '',
      eventTags: record.event_tags || [],
      sourceType: record.source_type || 'file',
      mode: record.mode,
    };
  } catch (err) {
    return null;
  }
}

/**
 * Start analysis on a video file using run_realtime.py.
 *
 * Strategy to ensure unique JSONL output per session:
 * - Create a symlink in the real-time dir: <sessionId>.mp4 → actual video
 * - Run run_realtime.py against the symlink so results go to results/<sessionId>_<mode>/
 * - Clean up the symlink after analysis completes
 *
 * @param {string} videoPath - absolute path to the video file
 * @param {string} sessionId - session identifier (used as JSONL stem)
 * @param {string} sessionDir - absolute path to the session folder
 * @param {object} io - Socket.IO server instance
 * @param {object} [options]
 * @param {boolean} [options.isChunk]         - if true, use fast mode (3s window fits 5s chunk)
 * @param {string}  [options.mode]             - override mode
 * @param {string}  [options.sessionIdOverride] - emit socket events to this room instead of sessionId
 * @returns {{ process, kill: Function, results: Array }}
 */
function startAnalysis(videoPath, sessionId, sessionDir, io, options = {}) {
  const mode = options.mode || (options.isChunk ? 'fast' : 'high_accuracy');
  // The room to emit socket events to (may differ from sessionId for batch chunks)
  const emitRoom = options.sessionIdOverride || sessionId;

  // ── 1. Build a unique stem so the model writes to a session-specific JSONL ──
  //    The model derives the output folder from Path(video_path).stem, so
  //    symlinking the video as <sessionId>.mp4 gives us results/<sessionId>_<mode>/
  const ext = path.extname(videoPath) || '.mp4';
  const symlinkName = `${sessionId}${ext}`;
  const symlinkPath = path.join(REALTIME_DIR, symlinkName);
  let inputPath = videoPath; // fallback if symlink fails

  try {
    if (fs.existsSync(symlinkPath)) fs.unlinkSync(symlinkPath);
    fs.symlinkSync(videoPath, symlinkPath);
    inputPath = symlinkPath;
    console.log(`[Analyzer] Symlink: ${symlinkPath} → ${videoPath}`);
  } catch (err) {
    console.warn(`[Analyzer] Symlink failed (${err.message}), using original path`);
  }

  // ── 2. Predict where the JSONL will be written ──
  // Always use sessionId as the stem — it matches exactly what the model will use
  // (since inputPath is the symlink named after sessionId, or we fall back gracefully)
  const stem = (inputPath === symlinkPath) ? sessionId : path.basename(videoPath, ext);
  const jsonlPath = path.join(RESULTS_ROOT, `${stem}_${mode}`, 'window_flags.jsonl');
  console.log(`[Analyzer] Expecting JSONL at: ${jsonlPath}`);

  // ── 3. Spawn run_realtime.py ──
  const args = [
    'run', '-n', CONDA_ENV,
    'python', REALTIME_SCRIPT,
    '--mode', mode,
    '--video_path', inputPath,
  ];

  // For screen share batches (fast mode), limit sample_frames to save VRAM
  if (mode === 'fast') {
    args.push('--sample_frames', '6');
  }

  console.log(`[Analyzer] Starting: session=${sessionId} mode=${mode}`);
  console.log(`[Analyzer] Command: conda ${args.join(' ')}`);

  const child = spawn('conda', args, {
    cwd: REALTIME_DIR,
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  const results = [];
  let jsonlLinesRead = 0;

  // ── 4. Emit known stdout lines for quick previews ──
  let stdoutBuf = '';
  child.stdout.on('data', (chunk) => {
    stdoutBuf += chunk.toString();
    // Split on newlines; keep incomplete tail
    const lines = stdoutBuf.split('\n');
    stdoutBuf = lines.pop();
    for (const raw of lines) {
      const line = raw.replace(/\x1b\[[0-9;]*m/g, '').replace(/\r/g, '').trim();
      if (line) console.log(`[Analyzer][${sessionId}] ${line}`);
    }
  });

  child.stderr.on('data', (chunk) => {
    const text = chunk.toString().trim();
    if (!text) return;
    // Suppress noisy TF/CUDA noise
    if (/tensorflow|TF-TRT|OneDNN|cudnn|cublas|Warning|DeprecationWarning/i.test(text)) return;
    console.log(`[Analyzer][${sessionId}] stderr: ${text}`);
  });

  // ── 5. Poll the JSONL file for new records (primary data source) ──
  const poll = setInterval(() => readNewLines(), 1500);

  function readNewLines() {
    if (!fs.existsSync(jsonlPath)) return;
    try {
      const content = fs.readFileSync(jsonlPath, 'utf-8');
      const lines = content.trim().split('\n').filter(l => l.trim());
      for (let i = jsonlLinesRead; i < lines.length; i++) {
        const parsed = parseJsonlLine(lines[i]);
        if (!parsed) continue;

        const timeOffset = options.timeOffset || 0;
        parsed.startSec += timeOffset;
        parsed.endSec += timeOffset;

        parsed.id = `${sessionId}_w${i}`;
        results.push(parsed);

        io.to(emitRoom).emit('analysis_result', {
          sessionId: emitRoom,
          result: parsed,
          totalResults: results.length,
        });

        console.log(
          `[Analyzer][${sessionId}] ✓ #${results.length} ${parsed.status} ${parsed.level} [${parsed.startSec}s-${parsed.endSec}s]`
        );
      }
      jsonlLinesRead = lines.length;
    } catch (_) { /* file mid-write, retry */ }
  }

  // ── 6. On process exit: final read, save results, notify frontend, cleanup ──
  child.on('close', (code) => {
    console.log(`[Analyzer][${sessionId}] Process exited code=${code}`);

    clearInterval(poll);
    readNewLines(); // catch final records

    // Clean up symlink
    if (fs.existsSync(symlinkPath)) {
      try { fs.unlinkSync(symlinkPath); } catch (_) {}
    }

    // Save results.json in the session folder
    // Merge with any existing results (for screen share with multiple batches)
    const resultsPath = path.join(sessionDir, 'results.json');
    let existingResults = [];
    try {
      if (fs.existsSync(resultsPath)) {
        const existing = JSON.parse(fs.readFileSync(resultsPath, 'utf-8'));
        existingResults = existing.results || [];
      }
    } catch (_) {}

    const allResults = [...existingResults, ...results];
    const out = {
      sessionId: emitRoom,
      videoPath,
      mode,
      completedAt: new Date().toISOString(),
      totalWindows: allResults.length,
      results: allResults,
    };
    try {
      fs.writeFileSync(resultsPath, JSON.stringify(out, null, 2));
      console.log(`[Analyzer][${sessionId}] Saved results.json (${allResults.length} total windows, +${results.length} this batch)`);
    } catch (e) {
      console.error(`[Analyzer][${sessionId}] Failed to save results.json:`, e.message);
    }

    // ── Move model output from real-time/results/ into live_video session folder ──
    const modelOutDir = path.join(RESULTS_ROOT, `${stem}_${mode}`);
    if (fs.existsSync(modelOutDir)) {
      try {
        // Copy window_flags.jsonl directly into sessionDir for easy access
        const srcJsonl = path.join(modelOutDir, 'window_flags.jsonl');
        if (fs.existsSync(srcJsonl)) {
          const destJsonl = path.join(sessionDir, `${stem}_window_flags.jsonl`);
          fs.copyFileSync(srcJsonl, destJsonl);
        }

        // Move entire model output subfolder into live_video/<sessionId>/
        const destDir = path.join(sessionDir, `analysis_${stem}_${mode}`);
        if (!fs.existsSync(destDir)) {
          fs.mkdirSync(destDir, { recursive: true });
        }
        // Move all files from modelOutDir into destDir
        for (const f of fs.readdirSync(modelOutDir)) {
          fs.renameSync(path.join(modelOutDir, f), path.join(destDir, f));
        }
        // Remove now-empty model output dir
        fs.rmdirSync(modelOutDir);
        console.log(`[Analyzer][${sessionId}] Results moved to: ${destDir}`);
      } catch (moveErr) {
        console.warn(`[Analyzer][${sessionId}] Could not move results dir: ${moveErr.message}`);
      }
    }

    io.to(emitRoom).emit('analysis_complete', {
      sessionId: emitRoom,
      totalResults: results.length,
      exitCode: code,
    });
  });

  child.on('error', (err) => {
    console.error(`[Analyzer][${sessionId}] Spawn error:`, err.message);
    clearInterval(poll);
    if (fs.existsSync(symlinkPath)) {
      try { fs.unlinkSync(symlinkPath); } catch (_) {}
    }
    io.to(emitRoom).emit('analysis_complete', {
      sessionId: emitRoom,
      totalResults: results.length,
      exitCode: -1,
      error: err.message,
    });
  });

  return {
    process: child,
    results,
    kill: () => {
      clearInterval(poll);
      if (!child.killed) child.kill('SIGTERM');
      if (fs.existsSync(symlinkPath)) {
        try { fs.unlinkSync(symlinkPath); } catch (_) {}
      }
    },
  };
}

module.exports = { startAnalysis, parseJsonlLine };
