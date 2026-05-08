import React, { useState, useRef, useCallback, useEffect } from 'react';
import { useAppContext } from '../context/AppContext';
import { uploadVideo, createSession } from '../services/api';
import { socketService } from '../services/socket';
import { Upload, FileVideo, CheckCircle, Loader2, X, Cpu } from 'lucide-react';

const VideoUpload: React.FC = () => {
  const { activeSession, setActiveSession, activeCamera, videoSeekRef } = useAppContext();
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [uploadStatus, setUploadStatus] = useState<'idle' | 'uploading' | 'analyzing' | 'error'>('idle');
  const [errorMsg, setErrorMsg] = useState('');
  const [videoObjectUrl, setVideoObjectUrl] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  // Register seek function so ThreatList clicks seek the uploaded video
  useEffect(() => {
    const seekFn = (seconds: number) => {
      const vid = videoRef.current;
      if (vid && isFinite(seconds)) {
        vid.currentTime = seconds;
        // Auto-play on seek so the user sees that moment
        vid.play().catch(() => {});
      }
    };
    videoSeekRef.current = seekFn;
    return () => { videoSeekRef.current = null; };
  }, [videoSeekRef]);

  // Create/revoke object URL for the selected file
  useEffect(() => {
    if (selectedFile) {
      const url = URL.createObjectURL(selectedFile);
      setVideoObjectUrl(url);
      return () => URL.revokeObjectURL(url);
    } else {
      setVideoObjectUrl(null);
    }
  }, [selectedFile]);

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith('video/')) {
      setErrorMsg('Please select a video file');
      return;
    }
    setSelectedFile(file);
    setErrorMsg('');
    setUploadStatus('idle');
    setUploadProgress(0);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => { setIsDragOver(false); }, []);

  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }, [handleFile]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile || !activeCamera) return;

    try {
      setUploadStatus('uploading');
      setErrorMsg('');

      // 1. Create session
      const { sessionId } = await createSession(activeCamera.id);

      // 2. Join the session room via socket
      const socket = socketService.getSocket() || socketService.connect();
      socket.emit('join_session', { sessionId });

      // 3. Upload the file (shows progress bar)
      await uploadVideo(sessionId, selectedFile, (percent) => {
        setUploadProgress(percent);
      });

      // 4. Mark as analyzing — video keeps playing, small badge appears
      setUploadStatus('analyzing');
      setActiveSession({
        id: sessionId,
        cameraId: activeCamera.id,
        status: 'analyzing',
        results: [],
      });

      // Start playing the video from beginning
      if (videoRef.current) {
        videoRef.current.currentTime = 0;
        videoRef.current.play().catch(() => {});
      }

    } catch (err: any) {
      setUploadStatus('error');
      setErrorMsg(err.message || 'Upload failed');
    }
  }, [selectedFile, activeCamera, setActiveSession]);

  const handleClearFile = useCallback(() => {
    setSelectedFile(null);
    setUploadStatus('idle');
    setUploadProgress(0);
    setErrorMsg('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  }, []);

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // ── Analyzing state: video plays full-size, small badge overlay ────────────
  const isAnalyzing = uploadStatus === 'analyzing'
    || (activeSession && activeSession.status === 'analyzing')
    || (activeSession && activeSession.status === 'recording');

  if (isAnalyzing && videoObjectUrl) {
    return (
      <div className="relative h-full w-full bg-black overflow-hidden group">
        {/* The uploaded video plays full-screen with controls */}
        <video
          ref={videoRef}
          src={videoObjectUrl}
          className="h-full w-full object-contain"
          controls
          playsInline
        />

        {/* Gradient top overlay for badges */}
        <div className="absolute top-0 left-0 right-0 h-14 bg-gradient-to-b from-black/70 to-transparent pointer-events-none" />

        {/* Analyzing badge — top left */}
        <div className="absolute top-3 left-3 flex items-center space-x-2 rounded-lg bg-black/60 border border-indigo-500/30 px-3 py-1.5 backdrop-blur-md">
          <Cpu size={12} className="text-indigo-400 animate-pulse" />
          <span className="text-xs font-bold text-indigo-300 tracking-wider">ANALYZING</span>
          <div className="flex space-x-0.5 ml-1">
            {[0, 1, 2].map(i => (
              <div
                key={i}
                className="w-1 rounded-full bg-indigo-400 animate-bounce"
                style={{ height: '10px', animationDelay: `${i * 150}ms` }}
              />
            ))}
          </div>
        </div>

        {/* File name badge — top right */}
        {selectedFile && (
          <div className="absolute top-3 right-3 flex items-center space-x-1.5 rounded-lg bg-black/60 border border-white/10 px-2.5 py-1.5 backdrop-blur-md max-w-[200px]">
            <FileVideo size={11} className="text-slate-400 flex-shrink-0" />
            <span className="text-[10px] text-slate-400 font-mono truncate">{selectedFile.name}</span>
          </div>
        )}
      </div>
    );
  }

  // ── No file selected — Drop zone ──────────────────────────────────────────
  if (!selectedFile) {
    return (
      <div className="relative h-full w-full bg-black flex flex-col items-center justify-center p-8">
        <div
          onDrop={handleDrop}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onClick={() => fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center w-full max-w-lg aspect-video rounded-2xl border-2 border-dashed transition-all cursor-pointer ${
            isDragOver
              ? 'border-indigo-400 bg-indigo-500/10 scale-[1.02]'
              : 'border-slate-700 bg-slate-900/50 hover:border-slate-500 hover:bg-slate-900/80'
          }`}
        >
          {/* Animated upload icon */}
          <div className={`relative flex h-20 w-20 items-center justify-center rounded-2xl mb-5 transition-colors ${
            isDragOver ? 'bg-indigo-500/20 text-indigo-400' : 'bg-slate-800 text-slate-400'
          }`}>
            {isDragOver && (
              <div className="absolute inset-0 rounded-2xl animate-ping bg-indigo-500/20" />
            )}
            <Upload size={30} className={isDragOver ? 'animate-bounce' : ''} />
          </div>
          <h3 className="text-base font-semibold text-slate-200 mb-1.5">
            {isDragOver ? 'Drop to Upload' : 'Upload Video for Analysis'}
          </h3>
          <p className="text-xs text-slate-500 text-center max-w-xs leading-relaxed">
            Drag and drop a video file here, or click to browse.
            <br />
            <span className="text-slate-600">MP4, WEBM, MKV, AVI · max 500 MB</span>
          </p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>
    );
  }

  // ── File selected — Preview + Upload button ────────────────────────────────
  return (
    <div className="relative h-full w-full bg-black flex flex-col overflow-hidden">
      {/* Video preview takes most of the space */}
      <div className="flex-1 min-h-0 relative">
        <video
          ref={videoRef}
          src={videoObjectUrl || undefined}
          className="h-full w-full object-contain"
          controls
          playsInline
        />

        {/* Clear file overlay button */}
        <button
          onClick={handleClearFile}
          className="absolute top-3 right-3 flex items-center justify-center w-7 h-7 rounded-full bg-black/60 border border-white/10 text-slate-400 hover:text-white hover:bg-black/80 transition-all backdrop-blur-md"
        >
          <X size={14} />
        </button>
      </div>

      {/* Bottom control bar */}
      <div className="flex-shrink-0 bg-slate-900/95 border-t border-slate-800 px-4 py-3">
        <div className="flex items-center space-x-3">
          {/* File info */}
          <div className="flex items-center space-x-2 flex-1 min-w-0">
            <FileVideo size={16} className="text-indigo-400 flex-shrink-0" />
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-200 truncate">{selectedFile.name}</p>
              <p className="text-xs text-slate-500">{formatFileSize(selectedFile.size)}</p>
            </div>
          </div>

          {/* Upload progress */}
          {uploadStatus === 'uploading' && (
            <div className="flex items-center space-x-2 flex-shrink-0">
              <div className="w-28 h-1.5 rounded-full bg-slate-700 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-300"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <span className="text-xs text-slate-400 font-mono w-8">{uploadProgress}%</span>
            </div>
          )}

          {/* Error */}
          {errorMsg && (
            <p className="text-xs text-red-400 flex-shrink-0">{errorMsg}</p>
          )}

          {/* Upload button */}
          <button
            onClick={handleUpload}
            disabled={uploadStatus === 'uploading'}
            className="flex items-center space-x-2 rounded-xl bg-indigo-500 px-5 py-2 text-sm font-semibold text-white shadow-lg shadow-indigo-500/25 hover:bg-indigo-600 transition-all hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100 flex-shrink-0"
          >
            {uploadStatus === 'uploading' ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                <span>Uploading...</span>
              </>
            ) : (
              <>
                <CheckCircle size={15} />
                <span>Analyze</span>
              </>
            )}
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={handleFileSelect}
      />
    </div>
  );
};

export default VideoUpload;
