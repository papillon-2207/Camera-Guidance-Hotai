export class AudioController {
  constructor() { this.playing = new Set(); this.next = 0; }

  async start(stream, onChunk) {
    this.context = new AudioContext({ sampleRate: 16000 });
    await this.context.resume();
    await this.context.audioWorklet.addModule('/js/mic-worklet.js');
    this.source = this.context.createMediaStreamSource(stream);
    this.node = new AudioWorkletNode(this.context, 'mic-processor');
    this.node.port.onmessage = ({ data }) => onChunk(data);
    const silence = this.context.createGain();
    silence.gain.value = 0;
    this.source.connect(this.node);
    this.node.connect(silence).connect(this.context.destination);
  }

  play(encoded) {
    const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
    const view = new DataView(bytes.buffer);
    const buffer = this.context.createBuffer(1, Math.floor(bytes.length / 2), 24000);
    const samples = buffer.getChannelData(0);
    for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
    const output = this.context.createBufferSource();
    output.buffer = buffer;
    output.connect(this.context.destination);
    this.playing.add(output);
    output.onended = () => this.playing.delete(output);
    this.next = Math.max(this.next, this.context.currentTime + 0.03);
    output.start(this.next);
    this.next += buffer.duration;
    return bytes.length;
  }

  clear() {
    for (const output of this.playing) { try { output.stop(); } catch {} }
    this.playing.clear();
    this.next = 0;
  }

  get remaining() { return Math.max(0, this.next - (this.context?.currentTime || 0)); }

  async close() {
    this.clear();
    this.node?.disconnect();
    this.source?.disconnect();
    if (this.context && this.context.state !== 'closed') await this.context.close();
  }
}
