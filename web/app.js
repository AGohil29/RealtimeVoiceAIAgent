import { startCapture } from "./capture.js";
import { Player } from "./playback.js";

const $ = (id) => document.getElementById(id);

let ws = null;
let player = null;
let speechEndAt = 0;   // when the user actually stopped speaking
let sampleRate = 0;    // of the audio chunks for the current reply
let firstChunk = true; // is the next chunk the first of this reply?
let turn = 0;

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
      player.reset();
      $("status").textContent = "speaking";
    } else if (msg.type === "transcript") {
      $("live").textContent = msg.text;
      $("live").className = msg.final ? "final" : "interim";
    } else if (msg.type === "turn_done") {
      addTurn(msg);
      // tell the server once the last scheduled chunk has finished playing
      setTimeout(() => {
        ws.send(JSON.stringify({ type: "playback_done" }));
        $("status").textContent = "listening";
      }, player.remainingMs());
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
