/**
 * Content script: extracts the current conversation only when the extension
 * asks for it. Nothing is read, stored or transmitted in the background.
 */
(function () {
  "use strict";

  const registry = globalThis.SmartCapsuleAdapters;

  function buildTranscript(messages) {
    return messages
      .map((message) => `${message.role === "assistant" ? "Assistant" : message.role === "system" ? "System" : "User"}: ${message.text}`)
      .join("\n\n");
  }

  function extractConversation() {
    const adapter = registry ? registry.forLocation(location.href) : null;
    const active = adapter || (registry ? registry.generic : null);
    let messages = [];
    let warning = "";

    try {
      if (active && typeof active.collect === "function") messages = active.collect();
    } catch (error) {
      warning = `Adapter ${active ? active.id : "generic"} failed: ${error.message}`;
    }

    if (!messages.length) {
      const fallback = (document.body.innerText || "").trim();
      if (fallback) {
        messages = [{ role: "user", text: fallback.slice(0, 60000) }];
        warning = "No conversation structure was found; the visible page text was captured as one message.";
      }
    }

    return {
      platform: active ? active.platform : "Other",
      adapter: active ? `${active.id}@${active.version}` : "none",
      title: active && typeof active.title === "function" ? active.title() || document.title : document.title,
      messages,
      warning,
      url: location.href,
    };
  }

  chrome.runtime.onMessage.addListener((request, _sender, sendResponse) => {
    if (!request || request.type !== "SC_COLLECT") return undefined;

    if (request.mode === "selection") {
      const selection = (window.getSelection() || "").toString().trim();
      const adapter = registry ? registry.forLocation(location.href) : null;
      sendResponse({
        ok: true,
        selection,
        platform: adapter ? adapter.platform : "Other",
        title: document.title,
        url: location.href,
      });
      return undefined;
    }

    const payload = extractConversation();
    payload.ok = payload.messages.length > 0;
    payload.transcript = buildTranscript(payload.messages);
    delete payload.messages;
    sendResponse(payload);
    return undefined;
  });
})();
