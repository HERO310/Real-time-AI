const express = require('express');
const http = require('http');
const cors = require('cors');
const path = require('path');

const app = express();
const server = http.createServer(app);

// Initialize Socket.io — returns io instance
const setupSockets = require('./sockets');
const io = setupSockets(server);

// Make io accessible to routes
app.set('io', io);

// Allow all origins so the Android Capacitor app (file://) can connect.
// In production you can restrict to your specific IP/domain.
app.use(cors({ origin: '*', methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'] }));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Serve static files from live_video directory (for chunk playback)
app.use('/live_video', express.static(path.join(__dirname, 'live_video')));

// Routes
const cameraRoutes = require('./routes/cameras').router;
const threatRoutes = require('./routes/threats').router;
const sessionRoutes = require('./routes/sessions').router;

app.use('/api/cameras', cameraRoutes);
app.use('/api/threats', threatRoutes);
app.use('/api/sessions', sessionRoutes);

const PORT = process.env.PORT || 4400;

server.on('error', (err) => {
  if (err.code === 'EADDRINUSE') {
    console.error(`⚠️  Port ${PORT} in use. Killing occupying process and retrying...`);
    const { execSync } = require('child_process');
    try {
      execSync(`fuser -k ${PORT}/tcp`, { stdio: 'ignore' });
    } catch (_) {}
    setTimeout(() => {
      server.close();
      server.listen(PORT, () => {
        console.log(`Server running on port ${PORT} (restarted)`);
        console.log(`Live video storage: ${path.join(__dirname, 'live_video')}`);
      });
    }, 1500);
  } else {
    throw err;
  }
});

server.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
  console.log(`Live video storage: ${path.join(__dirname, 'live_video')}`);
});
