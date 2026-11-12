// Audio thread: hands the raw input (first channel, no effects) to the page in blocks,
// each with the index of its first sample on the audio clock. Loaded by views/stream.js.
class StreamCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(2048);
    this.fill = 0;
    this.index = 0;                 // samples sent so far
  }

  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    let i = 0;
    while (i < ch.length) {
      const n = Math.min(ch.length - i, this.block.length - this.fill);
      this.block.set(ch.subarray(i, i + n), this.fill);
      this.fill += n;
      i += n;
      if (this.fill === this.block.length) {
        this.port.postMessage({ start: this.index, samples: this.block }, [this.block.buffer]);
        this.index += this.fill;
        this.block = new Float32Array(2048);
        this.fill = 0;
      }
    }
    return true;
  }
}

registerProcessor("stream-capture", StreamCapture);
