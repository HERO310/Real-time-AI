import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  // Unique app identifier — used as Android package name
  appId: 'com.videoanalytics.dashboard',
  appName: 'Video Analytics',

  // Points to the Vite production build of the frontend.
  // Path is relative to this file (android-app/ → ../client/dist)
  webDir: '../client/dist',

  server: {
    // ── DEVELOPMENT ONLY (live reload from dev server) ──────────────────────
    // Uncomment the lines below to use live-reload during development:
    //   url: 'http://YOUR_MACHINE_IP:5173',
    //   cleartext: true,
    // ────────────────────────────────────────────────────────────────────────

    // Allow HTTP (non-HTTPS) connections to the backend.
    // Required because the backend server likely doesn't have TLS configured.
    cleartext: true,

    // androidScheme: 'https' is the default — keep it so the app loads correctly
    androidScheme: 'https',
  },

  android: {
    // Allow mixed HTTP content inside the WebView (needed for HTTP backend API)
    allowMixedContent: true,
    // Capture unhandled WebView errors for debugging
    captureInput: false,
  },

  plugins: {
    // App splash screen (optional — customize if you add @capacitor/splash-screen)
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: '#0b0f19',
      showSpinner: false,
    },
  },
};

export default config;
