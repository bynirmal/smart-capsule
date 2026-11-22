/** Smart Capsule popup: settings + one-click capture. */
"use strict";

const $ = (id) => document.getElementById(id);

function setStatus(message, kind = "") {
  const node = $("status");
  node.textContent = message;
  node.className = `status ${kind}`;
}

async function loadSettings() {
  const response = await chrome.runtime.sendMessage({ type: "SC_SETTINGS" });
  if (response && response.ok) {
    $("endpoint").value = response.settings.endpoint;
    $("token").value = response.settings.token;
  }
}

async function saveSettings() {
  await chrome.storage.local.set({
    endpoint: $("endpoint").value.trim() || "http://127.0.0.1:8765",
    token: $("token").value.trim(),
  });
  setStatus("Settings saved.", "ok");
}

async function capture(mode) {
  const buttons = [$("capture"), $("selection")];
  buttons.forEach((button) => (button.disabled = true));
  setStatus("Reading the page and saving locally…");
  try {
    const result = await chrome.runtime.sendMessage({ type: "SC_CAPTURE", mode });
    if (!result) {
      setStatus("No response from the extension worker.", "err");
      return;
    }
    if (!result.ok) {
      setStatus(result.error || "Capture failed.", "err");
      if (result.needsToken) $("token").focus();
      return;
    }
    const capsule = result.capsule || {};
    setStatus(`Saved “${capsule.title || "capsule"}” · ${capsule.messages || 0} messages`, "ok");
  } catch (error) {
    setStatus(String(error.message || error), "err");
  } finally {
    buttons.forEach((button) => (button.disabled = false));
  }
}

$("save").addEventListener("click", saveSettings);
$("capture").addEventListener("click", () => capture("conversation"));
$("selection").addEventListener("click", () => capture("selection"));
$("panel").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "SC_OPEN_PANEL" });
  window.close();
});

loadSettings().catch((error) => setStatus(String(error), "err"));
