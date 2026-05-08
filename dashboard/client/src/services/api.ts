import type { Camera, PastSession, AnalysisResult } from '../types';

// In production/mobile builds, VITE_API_BASE_URL must point to the real backend server.
// Example: VITE_API_BASE_URL=http://192.168.1.100:5000/api
// Falls back to '/api' for browser dev (handled by Vite proxy in dev mode).
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? '/api';

export const fetchCameras = async (): Promise<Camera[]> => {
  const response = await fetch(`${API_BASE_URL}/cameras`);
  if (!response.ok) throw new Error('Failed to fetch cameras');
  return response.json();
};

export const createSession = async (cameraId: string): Promise<{ sessionId: string; cameraId: string; status: string }> => {
  const response = await fetch(`${API_BASE_URL}/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cameraId }),
  });
  if (!response.ok) throw new Error('Failed to create session');
  return response.json();
};

export const uploadVideo = async (
  sessionId: string,
  file: File,
  onProgress?: (percent: number) => void
): Promise<{ sessionId: string; status: string; videoPath: string }> => {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('sessionId', sessionId);
    formData.append('video', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/sessions/upload`);

    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`Upload failed: ${xhr.statusText}`));
      }
    };

    xhr.onerror = () => reject(new Error('Upload failed'));
    xhr.send(formData);
  });
};

export const getSessionResults = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/results`);
  if (!response.ok) throw new Error('Failed to fetch results');
  return response.json();
};

export const stopSession = async (sessionId: string) => {
  const response = await fetch(`${API_BASE_URL}/sessions/${sessionId}/stop`, {
    method: 'POST',
  });
  if (!response.ok) throw new Error('Failed to stop session');
  return response.json();
};

// ── Past Sessions ──────────────────────────────────────────────────────────────

export const fetchPastSessions = async (): Promise<PastSession[]> => {
  const response = await fetch(`${API_BASE_URL}/sessions/past`);
  if (!response.ok) throw new Error('Failed to fetch past sessions');
  return response.json();
};

export const fetchPastSessionResults = async (
  sessionId: string
): Promise<{ sessionId: string; results: AnalysisResult[] }> => {
  const response = await fetch(`${API_BASE_URL}/sessions/past/${sessionId}/results`);
  if (!response.ok) throw new Error('Failed to fetch past session results');
  return response.json();
};

