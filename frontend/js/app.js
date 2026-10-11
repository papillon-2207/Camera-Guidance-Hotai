import { AudioController } from './audio.js';

const $ = id => document.getElementById(id);
const audio = new AudioController();
const state = { stream: null, socket: null, ready: false, mode: null, busy: false, starting: false, timer: null, deadline: null, photoUrl: null };
const words = {
  en: {
    title: 'Menstrual pad assistant', intro: 'Show your menstrual pads or packaging. Choose camera guidance or check the brand and features.',
    capture: 'Take photo', download: 'Download photo', captured: 'Photo captured. Use Download photo to save it.', guide: 'Start camera guidance', stop: 'Stop camera guidance', analyze: 'Look at the brand', stopBrand: 'Stop brand analysis',
    idle: 'Choose a button to start.', connecting: 'Starting camera and connecting to Gemini...', checking: 'Checking the latest camera frame...',
    complete: 'Brand analysis complete. Show another package and tap again.', stopped: 'Stopped. Camera released.',
    note: 'Allow camera access when asked. Replies are spoken and shown here. Brand details depend on readable packaging.',
    timeout: 'Response timed out. Tap a button to reconnect.', disconnected: 'Disconnected. Tap a button to reconnect.',
    error: 'Could not start. Check camera permissions and your connection.',
  },
  'zh-TW': {
    capture: '\u62cd\u7167', download: '\u4e0b\u8f09\u7167\u7247', captured: '\u5df2\u62cd\u7167\uff0c\u8acb\u9ede\u9078\u4e0b\u8f09\u7167\u7247\u5132\u5b58\u3002',
    title: '\u885b\u751f\u68c9\u5c0f\u5e6b\u624b', intro: '\u5c55\u793a\u885b\u751f\u68c9\u6216\u5305\u88dd\uff0c\u9078\u64c7\u93e1\u982d\u5f15\u5c0e\u6216\u67e5\u770b\u54c1\u724c\u7279\u8272\u3002',
    guide: '\u958b\u59cb\u93e1\u982d\u5f15\u5c0e', stop: '\u505c\u6b62\u93e1\u982d\u5f15\u5c0e', analyze: '\u67e5\u770b\u54c1\u724c', stopBrand: '\u505c\u6b62\u54c1\u724c\u5206\u6790',
    idle: '\u9078\u64c7\u6309\u9215\u958b\u59cb\u3002', connecting: '\u6b63\u5728\u958b\u555f\u76f8\u6a5f\u4e26\u9023\u7dda Gemini...', checking: '\u6b63\u5728\u67e5\u770b\u6700\u65b0\u756b\u9762...',
    complete: '\u5206\u6790\u5b8c\u6210\uff0c\u53ef\u5c55\u793a\u5176\u4ed6\u5305\u88dd\u518d\u6309\u4e00\u6b21\u3002', stopped: '\u5df2\u505c\u6b62\u4e26\u95dc\u9589\u76f8\u6a5f\u3002',
    note: '\u8acb\u5141\u8a31\u76f8\u6a5f\u5b58\u53d6\u3002\u56de\u8986\u6703\u64ad\u653e\u4e26\u986f\u793a\u5728\u9019\u88e1\uff1b\u54c1\u724c\u8cc7\u8a0a\u9700\u8981\u6e05\u695a\u53ef\u8b80\u7684\u5305\u88dd\u3002',
    timeout: '\u56de\u61c9\u903e\u6642\uff0c\u8acb\u6309\u9215\u91cd\u65b0\u9023\u7dda\u3002', disconnected: '\u9023\u7dda\u5df2\u4e2d\u65b7\uff0c\u8acb\u6309\u9215\u91cd\u65b0\u9023\u7dda\u3002',
    error: '\u7121\u6cd5\u958b\u59cb\uff0c\u8acb\u6aa2\u67e5\u76f8\u6a5f\u6b0a\u9650\u548c\u7db2\u8def\u9023\u7dda\u3002',
  },
};
const t = key => words[$('language').value][key];
const status = key => { $('status').textContent = t(key); };

function controls() {
  $('capture').disabled = !state.stream || state.starting;
  $('capture').textContent = t('capture');
  $('download').textContent = t('download');
  $('guide').textContent = t(state.mode === 'guide' ? 'stop' : 'guide');
  $('analyze').textContent = t(state.mode === 'analyze_pads' ? 'stopBrand' : 'analyze');
  $('guide').disabled = state.starting || (state.busy && state.mode !== 'guide');
  $('analyze').disabled = state.starting || (state.busy && state.mode !== 'analyze_pads');
  $('language').disabled = state.starting;
}

function stop() {
  clearTimeout(state.timer);
  clearTimeout(state.deadline);
  if (state.socket) { state.socket.onclose = null; state.socket.close(); }
  state.socket = null;
  state.stream?.getTracks().forEach(track => track.stop());
  state.stream = null;
  $('preview').srcObject = null;
  state.ready = state.busy = false;
  state.mode = null;
  audio.clear();
  controls();
}

async function prepare() {
  audio.context ||= new AudioContext();
  await audio.context.resume();
  if (!state.stream) {
    state.stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } }, audio: false,
    });
    const video = $('preview');
    video.srcObject = state.stream;
    await video.play();
  }
  if (state.ready) return;
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const socket = new WebSocket(`${protocol}//${location.host}/live?language=${encodeURIComponent($('language').value)}`);
  state.socket = socket;
  await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Connection timed out')), 35000);
    const fail = () => { clearTimeout(timeout); reject(new Error('Connection failed')); };
    socket.onerror = fail;
    socket.onclose = fail;
    socket.onmessage = event => {
      const data = JSON.parse(event.data);
      if (data.type === 'ready') {
        clearTimeout(timeout);
        state.ready = true;
        socket.onmessage = receive;
        socket.onerror = () => { stop(); status('disconnected'); };
        socket.onclose = () => { stop(); status('disconnected'); };
        resolve();
      } else if (data.type === 'error') {
        clearTimeout(timeout);
        reject(new Error(data.text));
      }
    };
  });
}

function request() {
  if (!state.ready || !state.mode || state.busy) return;
  const video = $('preview');
  if (!video.videoWidth || video.readyState < 2) { state.timer = setTimeout(request, 300); return; }
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, 640 / video.videoWidth);
  canvas.width = Math.round(video.videoWidth * scale);
  canvas.height = Math.round(video.videoHeight * scale);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  state.socket.send(JSON.stringify({ type: state.mode, data: canvas.toDataURL('image/jpeg', 0.8).split(',')[1] }));
  state.busy = true;
  $('result').textContent = '';
  status('checking');
  state.deadline = setTimeout(() => { stop(); status('timeout'); }, 30000);
  controls();
}

function receive(event) {
  const data = JSON.parse(event.data);
  if (data.type === 'guidance' || data.type === 'pad_analysis') $('result').textContent = data.text;
  else if (data.type === 'audio') audio.play(data.data);
  else if (data.type === 'interrupted') audio.clear();
  else if (data.type === 'error') {
    stop();
    $('status').textContent = data.text;
  } else if (data.type === 'turn_complete') {
    clearTimeout(state.deadline);
    state.busy = false;
    if (state.mode === 'guide') state.timer = setTimeout(request, Math.max(3000, audio.remaining * 1000 + 500));
    else if (state.mode === 'analyze_pads') { state.mode = null; status('complete'); }
    controls();
  }
}

async function start(mode) {
  if (state.mode === mode) { stop(); status('stopped'); return; }
  if (state.starting || state.busy) return;
  clearTimeout(state.timer);
  state.starting = true;
  state.mode = mode;
  audio.clear();
  status('connecting');
  controls();
  try { await prepare(); request(); }
  catch { stop(); status('error'); }
  finally { state.starting = false; controls(); }
}

$('capture').onclick = () => {
  const video = $('preview');
  if (!state.stream || !video.videoWidth || video.readyState < 2) return;
  audio.context?.resume().catch(() => {});
  const canvas = document.createElement('canvas');
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  canvas.getContext('2d').drawImage(video, 0, 0);
  // Pause repeated guidance, retaining any in-flight turn until it finishes.
  clearTimeout(state.timer);
  state.mode = null;
  audio.clear();
  controls();
  canvas.toBlob(blob => {
    if (!blob) return;
    if (state.photoUrl) URL.revokeObjectURL(state.photoUrl);
    state.photoUrl = URL.createObjectURL(blob);
    $('photo').src = state.photoUrl;
    $('photo').hidden = false;
    $('download').href = state.photoUrl;
    $('download').download = `menstrual-pads-${Date.now()}.jpg`;
    $('download').hidden = false;
    status('captured');
    audio.captureBeep();
  }, 'image/jpeg', 0.95);
};
$('guide').onclick = () => start('guide');
$('analyze').onclick = () => start('analyze_pads');
$('language').onchange = () => {
  stop();
  document.documentElement.lang = $('language').value;
  for (const key of ['title', 'intro', 'note']) $(key).textContent = t(key);
  $('result').textContent = '';
  status('idle');
};
window.addEventListener('pagehide', stop);
controls();
