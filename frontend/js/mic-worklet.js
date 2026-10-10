class MicProcessor extends AudioWorkletProcessor {
  constructor() { super(); this.samples = []; this.phase = 0; this.total = 0; this.count = 0; }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (input) for (const value of input) {
      this.total += value; this.count++; this.phase += 16000;
      if (this.phase >= sampleRate) {
        this.phase -= sampleRate;
        this.samples.push(Math.max(-1, Math.min(1, this.total / this.count)));
        this.total = 0; this.count = 0;
      }
      if (this.samples.length === 2048) {
        const buffer = new ArrayBuffer(4096), view = new DataView(buffer);
        this.samples.forEach((v, i) => view.setInt16(i * 2, Math.round(v * (v < 0 ? 32768 : 32767)), true));
        const rms = Math.sqrt(this.samples.reduce((sum, v) => sum + v*v, 0) / this.samples.length);
        this.port.postMessage({buffer, rms}, [buffer]); this.samples = [];
      }
    }
    return true;
  }
}
registerProcessor('mic-processor', MicProcessor);
