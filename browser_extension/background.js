/**
 * Smart Capsule Capture — background service worker.
 *
 * Responsibilities:
 *  - open the side panel from the toolbar button
 *  - ask the content script for the current conversation (user-initiated only)
 *  - forward it to the local Smart Capsule server using the per-install token
 *
 * No credentials, cookies or page storage are ever read.
 */

const DEFAULT_ENDPOINT = "http://127.0.0.1:8765";

async function getSettings() {
  const stored = await chrome.storage.local.get({ endpoint: DEFAULT_ENDPOINT, token: "", destination: "ChatGPT" });
  return {
    endpoint: (stored.endpoint || DEFAULT_ENDPOINT).replace(/\/+$/, ""),
    token: stored.token || "",
    destination: stored.destination || "ChatGPT",
  };
}

chrome.runtime.onInstalled.addListener(async () => {
  try {
    await chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: false });
  } catch (error) {
    console.warn("sidePanel behaviour unavailable", error);
  }
});

chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
  if (!request || !request.type) return undefined;

  if (request.type === "SC_SETTINGS") {
    getSettings().then((settings) => sendResponse({ ok: true, settings }));
    return true;
  }

  if (request.type === "SC_CAPTURE") {
    captureActiveTab(request.mode || "conversation")
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: String(error && error.message ? error.message : error) }));
    return true; // async response
  }

  if (request.type === "SC_OPEN_PANEL") {
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      if (tab && chrome.sidePanel && chrome.sidePanel.open) {
        chrome.sidePanel.open({ windowId: tab.windowId }).catch((error) => console.warn(error));
      }
    });
    sendResponse({ ok: true });
    return undefined;
  }

  return undefined;
});

async function captureActiveTab(mode) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) throw new Error("No active tab.");
  if (!/^https?:/.test(tab.url || "")) throw new Error("Open a supported AI chat page first.");

  let collected;
  try {
    collected = await chrome.tabs.sendMessage(tab.id, { type: "SC_COLLECT", mode });
  } catch (error) {
    throw new Error("The page is not reachable yet. Reload the AI chat tab and try again.");
  }
  if (!collected || collected.ok === false) {
    throw new Error((collected && collected.warning) || "Could not read the conversation from this page.");
  }

  const settings = await getSettings();
  if (!settings.token) {
    return { ok: false, needsToken: true, error: "Add your bridge token in the extension settings first." };
  }

  const text =
    mode === "selection"
      ? `User: ${collected.selection}`
      : collected.transcript || "";
  if (!text.trim()) throw new Error("Nothing to capture on this page.");

  const response = await fetch(`${settings.endpoint}/api/bridge/capture`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-SmartCapsule-Token": settings.token },
    body: JSON.stringify({ text, platform: collected.platform, mode: "balanced" }),
  });

  if (response.status === 401) {
    return { ok: false, needsToken: true, error: "The desktop app rejected the token. Copy the current token again." };
  }
  if (!response.ok) {
    let message = `Desktop app returned ${response.status}.`;
    try {
      const payload = await response.json();
      if (payload && payload.error) message = payload.error;
    } catch (error) {
      /* keep the status message */
    }
    throw new Error(message);
  }

  const payload = await response.json();
  return { ok: true, capsule: payload, adapter: collected.adapter, warning: collected.warning || "" };
}

