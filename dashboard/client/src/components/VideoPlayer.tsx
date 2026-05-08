import { useAppContext } from '../context/AppContext';
import ScreenSharePlayer from './ScreenSharePlayer';
import LiveCameraPlayer from './LiveCameraPlayer';
import VideoUpload from './VideoUpload';
import PastSessionPlayer from './PastSessionPlayer';

const VideoPlayer = () => {
  const { activeCamera, activePastSession } = useAppContext();

  // Past session playback takes priority
  if (activePastSession) {
    return <PastSessionPlayer />;
  }

  if (!activeCamera) {
    return <div className="flex h-full items-center justify-center text-slate-500">No camera selected</div>;
  }

  // Render based on camera type
  if (activeCamera.type === 'screenshare') {
    return <div className="h-full w-full flex-1"><ScreenSharePlayer /></div>;
  }

  if (activeCamera.type === 'webcam') {
    return <div className="h-full w-full flex-1"><LiveCameraPlayer /></div>;
  }

  if (activeCamera.type === 'upload') {
    return <div className="h-full w-full flex-1"><VideoUpload /></div>;
  }

  return <div className="flex h-full w-full flex-1 items-center justify-center text-slate-500">Unknown camera type</div>;
};

export default VideoPlayer;
