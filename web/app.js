import { startCapture } from "./capture.js";

const $ = (id) => document.getElementById(id);

let ws = null;
let capture = null;
let sent = 0;
let pingTimer = null;

async function start() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";

  ws.onopen = async () => {
    $("status").textContent = "connected";
    capture = await startCapture((frame) => {
      ws.send(frame); // binary: 640 bytes of PCM16
      $("sent").textContent = ++sent;
    });
    // measure round-trip time once a second
    pingTimer = setInterval(() => {
      ws.send(JSON.stringify({ type: "ping", t: performance.now() }));
    }, 1000);
  };

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.type === "pong") {
      $("rtt").textContent = (performance.now() - msg.t).toFixed(1) + " ms";
    } else if (msg.type === "stats") {
      $("fps").textContent = msg.frames_per_sec;
      $("bps").textContent = msg.bytes_per_sec;
    }
  };

  ws.onclose = () => ($("status").textContent = "disconnected");
}

function stop() {
  clearInterval(pingTimer);
  capture?.stop();
  ws?.close();
  $("status").textContent = "idle";
}

$("toggle").onclick = () => {
  const running = $("toggle").textContent === "Stop";
  running ? stop() : start();
  $("toggle").textContent = running ? "Start" : "Stop";
};
