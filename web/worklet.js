// Runs on the audio thread. Collects mic samples into 20ms frames
// and converts them from Float32 (-1..1) to Int16 (-32768..32767).

const FRAME_SAMPLES = 320; // 20ms at 16kHz

class PcmFrameProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Int16Array(FRAME_SAMPLES);
    this.offset = 0;
  }

  process(inputs) {
    const input = inputs[0][0]; // mono channel, 128 samples per call
    if (!input) return true;

    for (let i = 0; i < input.length; i++) {
      const s = Math.max(-1, Math.min(1, input[i]));
      this.buffer[this.offset++] = s < 0 ? s * 32768 : s * 32767;

      if (this.offset === FRAME_SAMPLES) {
        // send the frame to the main thread, transfer ownership (no copy)
        this.port.postMessage(this.buffer.buffer, [this.buffer.buffer]);
        this.buffer = new Int16Array(FRAME_SAMPLES);
        this.offset = 0;
      }
    }
    return true;
  }
}

registerProcessor("pcm-frame-processor", PcmFrameProcessor);
