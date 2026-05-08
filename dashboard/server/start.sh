#!/bin/bash
# start.sh — clean start for the dashboard server
# Usage: ./start.sh
#        PORT=8080 ./start.sh

PORT=${PORT:-4400}
CLIENT_PORT=${CLIENT_PORT:-5173}

echo "🔄 Killing any existing processes on ports $PORT and $CLIENT_PORT..."
fuser -k ${PORT}/tcp 2>/dev/null
fuser -k ${CLIENT_PORT}/tcp 2>/dev/null
sleep 1

echo "🚀 Starting server on port $PORT..."
node server.js
