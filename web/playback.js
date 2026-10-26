// Plays raw PCM16 audio chunks back to back, with no gaps, through Web Audio.

export class Player {
  constructor() {
    this.ctx = new AudioContext();
    this.nextTime = 0; // when the next chunk must start, in AudioContext time
  }

  // call at the start of each agent reply
  reset() {
    this.nextTime = 0;
  }

  // schedule one chunk right after the previous one, returns its start time (performance.now())
  enqueue(arrayBuffer, sampleRate) {
    const int16 = new Int16Array(arrayBuffer);
    const buffer = this.ctx.createBuffer(1, int16.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 32768;

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);

    const startAt = Math.max(this.ctx.currentTime, this.nextTime);
    source.start(startAt);
    this.nextTime = startAt + buffer.duration;
    return performance.now() + (startAt - this.ctx.currentTime) * 1000;
  }
}
