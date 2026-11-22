/**
 * Site adapters for Smart Capsule Capture.
 *
 * Websites change their markup, so every adapter is versioned and every lookup
 * is defensive. When no messages can be found the generic fallback is used and
 * the result is flagged so the user knows capture was best-effort.
 */
(function () {
  "use strict";

  const ADAPTERS = [
    {
      id: "chatgpt",
      version: "1.1.0",
      match: (host) => host === "chatgpt.com" || host === "chat.openai.com",
      platform: "ChatGPT",
      title: () => {
        const heading = document.querySelector("h1");
        return (heading && heading.textContent.trim()) || document.title.replace(/\s*[-|]\s*ChatGPT.*$/i, "").trim();
      },
      collect: () => {
        const nodes = document.querySelectorAll("[data-message-author-role]");
        const messages = [];
        nodes.forEach((node) => {
          const role = node.getAttribute("data-message-author-role");
          const text = (node.innerText || "").trim();
          if (text) messages.push({ role: role === "assistant" ? "assistant" : role === "system" ? "system" : "user", text });
        });
        return messages;
      },
    },
    {
      id: "claude",
      version: "1.0.0",
      match: (host) => host === "claude.ai",
      platform: "Claude",
      title: () => {
        const heading = document.querySelector('[data-testid="conversation-title"], h1');
        return (heading && heading.textContent.trim()) || document.title.trim();
      },
      collect: () => {
        const messages = [];
        const turns = document.querySelectorAll('[data-testid="user-message"], .font-claude-message, .font-claude-response');
        turns.forEach((node) => {
          const isUser = node.matches('[data-testid="user-message"]') || node.className.includes("user");
          const text = (node.innerText || "").trim();
          if (text) messages.push({ role: isUser ? "user" : "assistant", text });
        });
        return messages;
      },
    },
    {
      id: "gemini",
      version: "1.0.0",
      match: (host) => host === "gemini.google.com",
      platform: "Gemini",
      title: () => {
        const heading = document.querySelector(".conversation-title, h1");
        return (heading && heading.textContent.trim()) || document.title.trim();
      },
      collect: () => {
        const messages = [];
        document.querySelectorAll("user-query, model-response").forEach((node) => {
          const text = (node.innerText || "").trim();
          if (!text) return;
          const isUser = node.tagName.toLowerCase() === "user-query";
          messages.push({ role: isUser ? "user" : "assistant", text });
        });
        return messages;
      },
    },
  ];

  const generic = {
    id: "generic",
    version: "1.0.0",
    platform: "Other",
    title: () => document.title.trim(),
    collect: () => {
      const messages = [];
      document.querySelectorAll("[data-message-author-role]").forEach((node) => {
        const role = node.getAttribute("data-message-author-role");
        const text = (node.innerText || "").trim();
        if (text) messages.push({ role: role === "assistant" ? "assistant" : "user", text });
      });
      return messages;
    },
  };

  function forLocation(href) {
    let host = "";
    try {
      host = new URL(href).hostname;
    } catch (error) {
      return null;
    }
    return ADAPTERS.find((adapter) => adapter.match(host)) || null;
  }

  globalThis.SmartCapsuleAdapters = { ADAPTERS, generic, forLocation };
})();
