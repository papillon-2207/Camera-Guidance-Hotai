import { AudioController } from './audio.js';

const $ = id => document.getElementById(id);
const audio = new AudioController();
const state = {
  stream: null, socket: null, ready: false, mic: false, sharing: false,
  guiding: false, pending: false, busy: false, timer: null, deadline: null,
  lastSpeaker: '', audioSent: 0, framesSent: 0, audioReceived: 0, photoUrl: null,
};
const status = text => { $('status').textContent = text; };

function updateControls() {
  $('connect').disabled = !state.stream || state.ready || state.socket?.readyState === WebSocket.CONNECTING;
  $('stop').disabled = !state.stream;
  $('capture').disabled = !state.stream;
  $('guide').disabled = !state.ready || (state.busy && !state.guiding);
  $('guide').textContent = state.guiding ? 'Stop framing guidance' : 'Start framing guidance';
  $('subject').disabled = state.guiding;
  $('mic').disabled = !state.ready || state.guiding;
  $('camera').disabled = !state.ready || state.guiding;
  $('send').disabled = !state.ready || state.guiding || state.busy;
  $('mic').textContent = state.mic ? 'Pause microphone' : 'Start microphone';
  $('camera').textContent = state.sharing ? 'Stop camera sharing' : 'Share camera';
}

function updateCounts() {
  $('counts').textContent = `Audio chunks sent: ${state.audioSent} | Camera frames sent: ${state.framesSent} | Audio bytes received: ${state.audioReceived}`;
}

function log(speaker, text) {
  const box = $('transcript');
  box.textContent += (speaker === state.lastSpeaker ? '' : `\n${speaker}: `) + text;
  state.lastSpeaker = speaker;
  box.scrollTop = box.scrollHeight;
}

function send(data) {
  if (!state.ready || state.socket?.readyState !== WebSocket.OPEN) return false;
  state.socket.send(JSON.stringify(data));
  return true;
}

function cameraCanvas(fullSize = false) {
  const video = $('preview');
  if (!video.videoWidth || video.readyState < 2) return null;
  const canvas = document.createElement('canvas');
  const scale = fullSize ? 1 : Math.min(1, 640 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  return canvas;
}

function stopGuidance(message = 'Guidance paused.') {
  state.guiding = false;
  clearTimeout(state.timer);
  // Retain in-flight request state until its response finishes.
  $('guidance').textContent = message;
  updateControls();
}

function requestGuidance() {
  if (!state.guiding || !state.ready || state.pending || state.busy) return;
  const canvas = cameraCanvas();
  if (!canvas) {
    state.timer = setTimeout(requestGuidance, 500);
    return;
  }
  const sent = send({ type: 'guide', subject: $('subject').value.trim(), data: canvas.toDataURL('image/jpeg', 0.7).split(',')[1] });
  if (!sent) return;
  state.pending = state.busy = true;
  state.framesSent++;
  updateCounts();
  $('guidance').textContent = 'Checking the latest frame...';
  state.deadline = setTimeout(() => {
    stopGuidance('No completed guidance response within 30 seconds. Reconnect to retry.');
    state.socket?.close();
  }, 30000);
  updateControls();
}

function resetConnection() {
  state.ready = state.mic = state.sharing = state.pending = state.busy = false;
  clearTimeout(state.deadline);
  stopGuidance('Guidance is off.');
  audio.clear();
  updateControls();
}

async function cleanup() {
  const socket = state.socket;
  state.socket = null;
  if (socket) { socket.onclose = null; socket.close(); }
  resetConnection();
  state.stream?.getTracks().forEach(track => track.stop());
  state.stream = null;
  await audio.close();
  $('preview').srcObject = null;
  $('level').value = 0;
  $('devices').disabled = false;
  updateControls();
  status('Stopped. Camera and microphone released.');
}

async function enableDevices() {
  try {
    $('devices').disabled = true;
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    $('preview').srcObject = state.stream;
    await audio.start(state.stream, data => {
      $('level').value = Math.min(1, data.rms * 5);
      if (state.mic && state.ready && state.socket?.readyState === WebSocket.OPEN && state.socket.bufferedAmount < 65536) {
        state.socket.send(data.buffer);
        state.audioSent++;
        updateCounts();
      }
    });
    updateControls();
    status('Camera preview and microphone meter ready. Connect to Gemini.');
  } catch (error) {
    await cleanup();
    status(`Device error: ${error.message}. Check browser permissions.`);
  }
}

function receiveMessage(event) {
  const data = JSON.parse(event.data);
  if (data.type === 'ready') {
    state.ready = true;
    status(data.text);
    updateControls();
  } else if (data.type === 'transcript') {
    log(data.speaker === 'you' ? 'You' : 'Gemini', data.text);
  } else if (data.type === 'guidance') {
    if (state.guiding) $('guidance').textContent = data.text;
  } else if (data.type === 'audio') {
    state.audioReceived += audio.play(data.data);
    updateCounts();
  } else if (data.type === 'interrupted') {
    audio.clear();
  } else if (data.type === 'turn_complete') {
    state.pending = state.busy = false;
    state.lastSpeaker = '';
    clearTimeout(state.deadline);
    updateControls();
    if (state.guiding) state.timer = setTimeout(requestGuidance, Math.max(3000, audio.remaining * 1000 + 500));
  } else if (data.type === 'error') {
    stopGuidance(data.text);
    log('Error', data.text);
    status(data.text);
  }
}

async function connect() {
  try {
    await audio.context.resume();
    status('Connecting to Gemini Live...');
    state.socket = new WebSocket(`ws://${location.host}/live`);
    state.socket.onmessage = receiveMessage;
    state.socket.onerror = () => status('WebSocket failed. Check the Python server.');
    state.socket.onclose = () => {
      state.socket = null;
      resetConnection();
      status('Gemini disconnected. Reconnect or Stop all.');
    };
    updateControls();
  } catch (error) { resetConnection(); status(error.message); }
}

function toggleGuidance() {
  if (state.guiding) { stopGuidance(); return; }
  if (!$('subject').value.trim()) { $('guidance').textContent = 'Enter the photo subject first.'; return; }
  if (state.mic) send({ type: 'audio_end' });
  state.mic = state.sharing = false;
  clearTimeout(state.timer);
  state.guiding = true;
  audio.clear();
  updateControls();
  requestGuidance();
}

function shareFrame() {
  if (!state.sharing || !state.ready) return;
  const canvas = cameraCanvas();
  if (canvas && state.socket.bufferedAmount < 65536) {
    send({ type: 'video', data: canvas.toDataURL('image/jpeg', 0.6).split(',')[1] });
    state.framesSent++;
    updateCounts();
  }
  state.timer = setTimeout(shareFrame, 1000);
}

function takePhoto() {
  const canvas = cameraCanvas(true);
  if (!canvas) { status('Wait for the camera preview before taking a photo.'); return; }
  stopGuidance('Photo captured. Start guidance again for another photo.');
  audio.clear();
  canvas.toBlob(blob => {
    if (!blob) return;
    if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
    state.photoUrl = URL.createObjectURL(blob);
    $('photo').src = state.photoUrl;
    $('photo').hidden = false;
    $('download').href = state.photoUrl;
    $('download').download = `photo-${Date.now()}.jpg`;
    $('download').hidden = false;
    status('Photo captured locally. Select Download photo to save it.');
  }, 'image/jpeg', 0.95);
}

$('devices').onclick = enableDevices;
$('connect').onclick = connect;
$('guide').onclick = toggleGuidance;
$('capture').onclick = takePhoto;
$('stop').onclick = cleanup;
$('mic').onclick = () => {
  state.mic = !state.mic;
  if (!state.mic) send({ type: 'audio_end' });
  updateControls();
  status(state.mic ? 'Microphone streaming. Speak, then pause for Gemini.' : 'Microphone paused.');
};
$('camera').onclick = () => {
  state.sharing = !state.sharing;
  clearTimeout(state.timer);
  if (state.sharing) shareFrame();
  updateControls();
  status(state.sharing ? 'Sharing camera. Ask Gemini what it sees.' : 'Camera sharing stopped.');
};
$('form').onsubmit = event => {
  event.preventDefault();
  const text = $('message').value.trim();
  if (text && state.ready && !state.guiding && !state.busy && send({ type: 'text', text })) {
    state.busy = true;
    log('You', text);
    $('message').value = '';
    updateControls();
  }
};
window.addEventListener('beforeunload', () => {
  state.socket?.close();
  state.stream?.getTracks().forEach(track => track.stop());
  if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
});
updateControls();
