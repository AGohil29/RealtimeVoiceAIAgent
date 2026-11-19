// Plays raw PCM16 audio chunks back to back, with no gaps, through Web Audio.

export class Player {
  constructor() {
    this.ctx = new AudioContext();
    this.nextTime = 0;   // when the next chunk must start, in AudioContext time
    this.startTime = 0;  // when the current reply started playing
    this.sources = [];   // everything scheduled for the current reply
    this.paused = false;
  }

  // call at the start of each agent reply
  reset() {
    this.nextTime = 0;
    this.startTime = 0;
    this.sources = [];
    this.resume(); // a new reply must never start frozen
  }

  // freezing the clock freezes playback, nothing already scheduled is lost
  pause() {
    this.paused = true;
    return this.ctx.suspend();
  }

  resume() {
    this.paused = false;
    return this.ctx.resume();
  }

  // stop everything and return how many ms of this reply were actually heard
  clear() {
    this.sources.forEach((s) => s.stop());
    const playedMs = this.sources.length ? (this.ctx.currentTime - this.startTime) * 1000 : 0; // nothing yet: 0
    this.reset();
    return Math.max(0, playedMs);
  }

  // how long until everything scheduled so far has finished playing
  remainingMs() {
    return Math.max(0, this.nextTime - this.ctx.currentTime) * 1000;
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
    if (this.sources.length === 0) this.startTime = startAt;
    this.sources.push(source);
    this.nextTime = startAt + buffer.duration;
    return performance.now() + (startAt - this.ctx.currentTime) * 1000;
  }
}
