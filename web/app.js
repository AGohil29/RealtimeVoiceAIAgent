import { startCapture } from "./capture.js";
import { Player } from "./playback.js";

const $ = (id) => document.getElementById(id);

let ws = null;
let player = null;
let talking = false;
let speechEndAt = 0;   // when the user released the button
let sampleRate = 0;    // of the next audio message from the server
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
      const playStart = player.play(e.data, sampleRate);
      $("v2v").textContent = Math.round(playStart - speechEndAt) + " ms";
      return;
    }
    const msg = JSON.parse(e.data);
    if (msg.type === "audio_start") sampleRate = msg.sample_rate;
    else if (msg.type === "turn_done") addTurn(msg);
    else if (msg.type === "error") $("status").textContent = msg.message;
  };
}

function addTurn({ transcript, reply, timings }) {
  const v2v = $("v2v").textContent;
  const bar = (name) => `<span class="${name}" style="width:${timings[name] / 10}px"></span>`;
  $("turns").insertAdjacentHTML("afterbegin", `
    <tr>
      <td>${++turn}</td>
      <td>${transcript}</td>
      <td>${reply}</td>
      <td>${timings.stt}</td><td>${timings.llm}</td><td>${timings.tts}</td>
      <td>${timings.total}</td><td>${v2v}</td>
      <td><div class="bar">${bar("stt")}${bar("llm")}${bar("tts")}</div></td>
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
  $("status").textContent = "listening...";
  ws.send(JSON.stringify({ type: "start" }));
};
talk.onpointerup = () => {
  talking = false;
  speechEndAt = performance.now();
  $("status").textContent = "thinking...";
  ws.send(JSON.stringify({ type: "end_of_speech" }));
};
