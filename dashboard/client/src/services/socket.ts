import { io, Socket } from 'socket.io-client';

// In production/mobile builds, set VITE_SOCKET_URL=http://SERVER_IP:4400
// Falls back to '' (empty) for browser dev — socket.io auto-connects to origin via Vite proxy.
const SOCKET_URL: string = import.meta.env.VITE_SOCKET_URL ?? '';

class SocketService {
  private socket: Socket | null = null;

  connect() {
    if (!this.socket) {
      this.socket = io(SOCKET_URL, {
        // Prefer WebSocket transport for reliability on mobile networks.
        // Polling fallback is kept as a safety net.
        transports: ['websocket', 'polling'],
        // Reconnect automatically if the connection drops
        reconnection: true,
        reconnectionAttempts: 10,
        reconnectionDelay: 1500,
      });
    }
    return this.socket;
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect();
      this.socket = null;
    }
  }

  getSocket() {
    return this.socket;
  }
}

export const socketService = new SocketService();
