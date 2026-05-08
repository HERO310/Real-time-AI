const express = require('express');
const router = express.Router();

const cameras = [
  {
    id: 'cam1',
    name: 'Screen Share',
    type: 'screenshare',
    status: 'online',
  },
  {
    id: 'cam2',
    name: 'Video Upload',
    type: 'upload',
    status: 'online',
  },
  {
    id: 'cam3',
    name: 'Live Camera',
    type: 'webcam',
    status: 'online',
  },
];

router.get('/', (req, res) => {
  res.json(cameras);
});

module.exports = { router, cameras };
