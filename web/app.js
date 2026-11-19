import { startCapture } from "./capture.js";
import { Player } from "./playback.js";

const $ = (id) => document.getElementById(id);

let ws = null;
let player = null;
let speechEndAt = 0;   // when the user actually stopped speaking
let sampleRate = 0;    // of the audio chunks for the current reply
let firstChunk = true; // is the next chunk the first of this reply?
let turn = 0;
let turnDone = false;  // has the server finished sending this reply?
let doneTimer = null;  // fires playback_done when the last chunk has played

function armPlaybackDone() {
  clearTimeout(doneTimer);
  doneTimer = setTimeout(() => {
    ws.send(JSON.stringify({ type: "playback_done" }));
    $("status").textContent = "listening";
  }, player.remainingMs());
}

async function start() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    $("status").textContent = "listening";
    player = new Player();
    await startCapture((frame) => ws.send(frame)); // hands-free: every frame goes to the server
  };

  ws.onmessage = (e) => {
    if (e.data instanceof ArrayBuffer) {
      const playAt = player.enqueue(e.data, sampleRate);
      if (firstChunk) {
        $("v2v").textContent = Math.round(playAt - speechEndAt) + " ms";
        firstChunk = false;
      }
      return;
    }
    const msg = JSON.parse(e.data);
    if (msg.type === "speech_start") {
      $("status").textContent = "you are speaking...";
      $("live").textContent = "";
    } else if (msg.type === "speech_end") {
      // the server tells us how long after your last word it decided, so we can measure from the real end
      speechEndAt = performance.now() - msg.turn_detection_ms;
      $("status").textContent = "thinking...";
    } else if (msg.type === "audio_start") {
      sampleRate = msg.sample_rate;
      firstChunk = true;
      turnDone = false;
      player.reset();
      $("status").textContent = "speaking";
    } else if (msg.type === "pause_audio") {
      player.pause();
      clearTimeout(doneTimer);
      $("status").textContent = `paused, you spoke for ${msg.after_ms} ms`;
    } else if (msg.type === "resume_audio") {
      player.resume();
      if (turnDone) armPlaybackDone();
      $("status").textContent = "speaking";
    } else if (msg.type === "clear_audio") {
      const playedMs = player.clear();
      clearTimeout(doneTimer);
      ws.send(JSON.stringify({ type: "played", ms: playedMs }));
      $("status").textContent = `interrupted after ${Math.round(playedMs)} ms of reply`;
    } else if (msg.type === "transcript") {
      $("live").textContent = msg.text;
      $("live").className = msg.final ? "final" : "interim";
    } else if (msg.type === "turn_done") {
      addTurn(msg);
      turnDone = true;
      // tell the server once the last chunk has played. While paused the clock is frozen, resume will do it.
      if (!player.paused) armPlaybackDone();
    } else if (msg.type === "error") {
      $("status").textContent = msg.message;
      ws.send(JSON.stringify({ type: "playback_done" }));
    }
  };
}

function addTurn({ transcript, reply, timings: t }) {
  const v2v = $("v2v").textContent;
  const bar = (name, ms) => `<span class="${name}" style="width:${ms / 10}px"></span>`;
  $("turns").insertAdjacentHTML("afterbegin", `
    <tr>
      <td>${++turn}</td>
      <td>${transcript}</td>
      <td>${reply}</td>
      <td>${t.turn_detection}</td><td>${t.stt}</td><td>${t.llm_first_token}</td>
      <td>${t.llm_first_sentence}</td><td>${t.tts_first_byte}</td>
      <td>${t.first_audio}</td><td>${t.total}</td><td>${v2v}</td>
      <td><div class="bar">${bar("vad", t.turn_detection)}${bar("stt", t.stt)}${bar("ttft", t.llm_first_token)}${bar("llm", t.llm_first_sentence)}${bar("tts", t.tts_first_byte)}</div></td>
    </tr>`);
}

$("start").onclick = () => {
  $("start").disabled = true;
  start();
};
