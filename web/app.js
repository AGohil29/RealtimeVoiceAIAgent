import { startCapture } from "./capture.js";
import { Player } from "./playback.js";

const $ = (id) => document.getElementById(id);

let ws = null;
let player = null;
let talking = false;
let speechEndAt = 0;   // when the user released the button
let sampleRate = 0;    // of the audio chunks for the current reply
let firstChunk = true; // is the next chunk the first of this reply?
let turn = 0;

async function start() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    $("status").textContent = "connected";
    player = new Player();
    await startCapture((frame) => {
      if (talking) ws.send(frame); // only send audio while the button is held
    });
    $("talk").disabled = false;
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
    if (msg.type === "audio_start") {
      sampleRate = msg.sample_rate;
      firstChunk = true;
      player.reset();
    } else if (msg.type === "transcript") {
      $("live").textContent = msg.text;
      $("live").className = msg.final ? "final" : "interim";
    } else if (msg.type === "turn_done") addTurn(msg);
    else if (msg.type === "error") $("status").textContent = msg.message;
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
      <td>${t.stt}</td><td>${t.llm_first_token}</td><td>${t.llm_first_sentence}</td><td>${t.tts_first_byte}</td>
      <td>${t.first_audio}</td><td>${t.total}</td><td>${v2v}</td>
      <td><div class="bar">${bar("stt", t.stt)}${bar("ttft", t.llm_first_token)}${bar("llm", t.llm_first_sentence)}${bar("tts", t.tts_first_byte)}</div></td>
    </tr>`);
  $("status").textContent = "connected";
}

$("start").onclick = () => {
  $("start").disabled = true;
  start();
};

const talk = $("talk");
talk.onpointerdown = () => {
  talking = true;
  $("live").textContent = "";
  $("status").textContent = "listening...";
  ws.send(JSON.stringify({ type: "start" }));
};
talk.onpointerup = () => {
  talking = false;
  speechEndAt = performance.now();
  $("status").textContent = "thinking...";
  ws.send(JSON.stringify({ type: "end_of_speech" }));
};
