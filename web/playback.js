// Plays raw PCM16 audio received from the server through Web Audio.

export class Player {
  constructor() {
    this.ctx = new AudioContext();
  }

  // returns the time (performance.now()) at which playback started
  play(arrayBuffer, sampleRate) {
    const int16 = new Int16Array(arrayBuffer);
    const buffer = this.ctx.createBuffer(1, int16.length, sampleRate);
    const channel = buffer.getChannelData(0);
    for (let i = 0; i < int16.length; i++) channel[i] = int16[i] / 32768;

    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(this.ctx.destination);
    source.start();
    return performance.now();
  }
}
