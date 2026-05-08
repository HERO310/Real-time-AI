export interface Camera {
  id: string;
  name: string;
  type: 'screenshare' | 'upload' | 'webcam';
  status: 'online' | 'offline';
}

export interface AnalysisResult {
  id: string;
  startSec: number;
  endSec: number;
  status: 'ALERT-FAST' | 'ALERT' | 'FLAG';
  level: 'HIGH' | 'MEDIUM' | 'LOW' | 'NORMAL';
  windowScore: number;
  smoothedScore: number;
  severity: number;
  gates: string[];
  descriptor: string;
  eventTags: string[];
  sourceType: string;
  mode: string;
  preview?: boolean;
}

export interface Threat {
  id: string;
  cameraId: string;
  timestamp: number;
  endTimestamp?: number;
  level: 'HIGH' | 'MEDIUM' | 'LOW' | 'NORMAL';
  status: string;
  descriptor: string;
  severity: number;
  windowScore?: number;
  smoothedScore?: number;
  gates: string[];
  eventTags?: string[];
  // For past session playback: absolute time in the full session
  absoluteTimestamp?: number;
}

export interface Session {
  id: string;
  cameraId: string;
  status: 'created' | 'recording' | 'analyzing' | 'complete';
  results: AnalysisResult[];
}

export interface PastSession {
  sessionId: string;
  completedAt: string;
  totalWindows: number;
  threatCount: number;
  hasVideo: boolean;
  chunks: string[];        // chunk_XXXX.webm files
  batches: string[];       // batch_XXX.mp4 files (fallback)
  uploads?: string[];      // uploaded files
}

