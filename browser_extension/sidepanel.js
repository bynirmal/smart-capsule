/** Smart Capsule side panel: persistent capture surface. */
"use strict";

const $ = (id) => document.getElementById(id);

function log(message) {
  const entry = document.createElement("div");
  entry.textContent = `${new Date().toLocaleTimeString()} · ${message}`;
  $("log").prepend(entry);
}

function setStatus(message, kind = "") {
  $("status").textContent = message;
  $("status").className = `status ${kind}`;
}

async function loadSettings() {
  const response = await chrome.runtime.sendMessage({ type: "SC_SETTINGS" });
  if (response && response.ok) {
    $("token").value = response.settings.token;
  } else {
    setStatus("Could not read extension settings.", "err");
  }
}

async function capture(mode) {
  $("capture").disabled = true;
  $("selection").disabled = true;
  setStatus("Capturing…");
  try {
    const result = await chrome.runtime.sendMessage({ type: "SC_CAPTURE", mode });
    if (!result || !result.ok) {
      setStatus((result && result.error) || "Capture failed.", "err");
      log((result && result.error) || "Capture failed.");
      return;
    }
    const capsule = result.capsule || {};
    setStatus(`Saved “${capsule.title || "capsule"}”`, "ok");
    log(`Captured via ${result.adapter || "adapter"} · ${capsule.messages || 0} messages`);
    if (result.warning) log(`Adapter note: ${result.warning}`);
    chrome.tabs.create({ url: "http://127.0.0.1:8765/" });
  } catch (error) {
    setStatus(String(error.message || error), "err");
    log(String(error.message || error));
  } finally {
    $("capture").disabled = false;
    $("selection").disabled = false;
  }
}

$("capture").addEventListener("click", () => capture("conversation"));
$("selection").addEventListener("click", () => capture("selection"));
$("open-app").addEventListener("click", () => chrome.tabs.create({ url: "http://127.0.0.1:8765/" }));
$("save").addEventListener("click", async () => {
  await chrome.storage.local.set({ token: $("token").value.trim() });
  setStatus("Token saved.", "ok");
});

loadSettings().catch((error) => setStatus(String(error), "err"));
