/* Smart Capsule web client — no framework, no build step. */
"use strict";

const state = {
  view: "capture",
  capsules: [],
  current: null,
  status: null,
  destinations: ["ChatGPT", "Claude", "Gemini", "Cursor", "Other"],
};

const $ = (selector) => document.querySelector(selector);

function h(tag, attrs, ...children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const [key, value] of Object.entries(attrs)) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key === "html") node.innerHTML = value;
      else if (key.startsWith("on") && typeof value === "function") {
        node.addEventListener(key.slice(2).toLowerCase(), value);
      } else node.setAttribute(key, value);
    }
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

/* ------------------------------------------------------------------ */
/* API + chrome                                                        */
/* ------------------------------------------------------------------ */
async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: options.body ? { "Content-Type": "application/json" } : {},
    ...options,
  });
  const contentType = response.headers.get("Content-Type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) throw new Error((payload && payload.error) || `Request failed (${response.status})`);
  return payload;
}

function setChildren(node, ...children) {
  // replaceChildren() stringifies null into the text "null", so filter first.
  node.replaceChildren(...children.filter((child) => child !== null && child !== undefined && child !== false));
}

let toastTimer = null;
function toast(message, kind = "info") {
  const node = $("#toast");
  node.textContent = message;
  node.className = `toast show ${kind}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (node.className = "toast"), 4200);
}

function setBusy(button, busy, label) {
  if (!button) return;
  if (busy) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    button.innerHTML = `<span class="spinner"></span> ${label || "Working…"}`;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.label || button.textContent;
  }
}

function formatDate(value) {
  if (!value) return "unknown date";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

const VIEW_META = {
  capture: ["Capture Conversation", "Paste a transcript, review the parse, generate a portable capsule."],
  library: ["Capsule Library", "Search, open, export or delete every capsule on this machine."],
  import: ["Import Capsule", "Load a .scapsule package and restore its working context."],
  detail: ["Capsule", "Structured context, continuation prompt and export."],
  about: ["About", "Runtime, API surface and the desktop/extension bridge."],
};

function showView(name) {
  state.view = name;
  document.querySelectorAll(".view").forEach((section) => section.classList.add("hidden"));
  const section = document.getElementById(`view-${name}`);
  if (section) section.classList.remove("hidden");
  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.view === name);
  });
  const [title, subtitle] = VIEW_META[name] || ["Smart Capsule", ""];
  $("#view-title").textContent = title;
  $("#view-sub").textContent = subtitle;
  if (name === "library") loadLibrary();
  if (name === "about") loadStatus();
}

/* ------------------------------------------------------------------ */
/* Status                                                              */
/* ------------------------------------------------------------------ */
async function loadStatus() {
  try {
    const status = await api("/api/status");
    state.status = status;
    state.destinations = status.destinations || state.destinations;
    $("#hw-text").textContent = status.hardware.device;
    $("#hw-dot").className = `dot ${status.hardware.has_gpu ? "ok" : "warn"}`;
    $("#capsule-count").textContent = `${status.capsules} capsule${status.capsules === 1 ? "" : "s"}`;
    $("#version-line").textContent = `${status.app} v${status.version}`;
    populateDestinations();
    renderAbout(status);
  } catch (error) {
    toast(`Status unavailable: ${error.message}`, "error");
  }
}

function populateDestinations() {
  const select = $("#result-destination");
  if (!select) return;
  select.replaceChildren(
    ...state.destinations.map((name) => h("option", { value: name }, name)),
  );
}

function renderAbout(status) {
  const target = $("#about-status");
  if (!target) return;
  target.replaceChildren(
    h("dt", null, "Version"), h("dd", null, `v${status.version} · ${status.stage}`),
    h("dt", null, "Capsule format"), h("dd", null, `v${status.format_version}`),
    h("dt", null, "Compute"), h("dd", null, status.hardware.device),
    h("dt", null, "Neural engine"), h("dd", null, status.hardware.neural ? "PyTorch available" : "Rule-based (CPU)"),
    h("dt", null, "Capsules"), h("dd", null, String(status.capsules)),
    h("dt", null, "Data folder"), h("dd", null, status.data_dir),
  );
  const bridge = $("#bridge-path");
  if (bridge) bridge.textContent = `${status.data_dir}${status.data_dir.includes("\\") ? "\\" : "/"}bridge_token.txt`;
}

/* ------------------------------------------------------------------ */
/* Capture                                                             */
/* ------------------------------------------------------------------ */
function renderPreview(preview) {
  const node = $("#preview");
  node.classList.remove("hidden");
  setChildren(
    h("div", { class: "preview-title" }, preview.title),
    h("div", { class: "capsule-meta" },
      h("span", { class: "badge" }, preview.platform),
      h("span", { class: `badge ${preview.confidence === "high" ? "success" : preview.confidence === "medium" ? "warn" : ""}` },
        `${preview.confidence} confidence`),
      h("span", { class: "badge violet" }, `${preview.messages} messages`),
      h("span", { class: "badge" }, `${preview.code_blocks} code blocks`),
    ),
    h("dl", { class: "kv" },
      h("dt", null, "Volume"), h("dd", null, `${preview.characters.toLocaleString()} characters · ~${preview.tokens.toLocaleString()} tokens`),
      h("dt", null, "Token method"), h("dd", null, preview.token_method),
      h("dt", null, "Roles"), h("dd", null, Object.entries(preview.roles).map(([role, count]) => `${role}: ${count}`).join(", ")),
      h("dt", null, "Platform reason"), h("dd", null, preview.reason),
    ),
    preview.warnings && preview.warnings.length
      ? h("div", { class: "warnings" }, ...preview.warnings.map((warning) => h("div", null, `⚠ ${warning}`)))
      : null,
  );
}

async function previewCapture() {
  const button = $("#btn-preview");
  const text = $("#source").value.trim();
  if (!text) return toast("Paste a conversation first", "error");
  setBusy(button, true, "Parsing…");
  try {
    const preview = await api("/api/preview", {
      method: "POST",
      body: JSON.stringify({ text, platform: $("#platform").value || null }),
    });
    renderPreview(preview);
    toast(`Parsed ${preview.messages} message(s)`, "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

function renderResult(payload) {
  const card = $("#result-card");
  card.classList.remove("hidden");
  const { capsule, document, preview } = payload;
  const compression = document.compression || {};

  $("#result-title").textContent = document.project.name;
  $("#result-badge").textContent = `${compression.mode} · saved`;

  $("#result-body").replaceChildren(
    h("div", { class: "stats-row" },
      h("div", { class: "stat" }, h("b", null, String(preview.messages)), h("span", null, "messages")),
      h("div", { class: "stat" }, h("b", null, String(preview.code_blocks)), h("span", null, "code blocks")),
      h("div", { class: "stat" }, h("b", null, `~${(compression.capsule_tokens || 0).toLocaleString()}`), h("span", null, "capsule tokens")),
    ),
    h("dl", { class: "kv" },
      h("dt", null, "Platform"), h("dd", null, `${preview.platform} (${preview.confidence})`),
      h("dt", null, "Objective"), h("dd", null, document.project.objective || "not stated"),
      h("dt", null, "Stage"), h("dd", null, `${document.project.stage} (inferred)`),
      h("dt", null, "Next action"), h("dd", null, document.progress.next_action || "not recorded"),
    ),
    h("div", { class: "export-row" }, ...exportButtons(capsule.id)),
  );

  $("#result-prompt").value = payload.prompt || "";
  card.dataset.id = capsule.id;
  populateDestinations();
  loadStatus();
  toast("Capsule created", "success");
}

async function createCapsule() {
  const button = $("#btn-create");
  const text = $("#source").value.trim();
  if (!text) return toast("Paste a conversation first", "error");
  setBusy(button, true, "Generating…");
  try {
    const payload = await api("/api/capsules", {
      method: "POST",
      body: JSON.stringify({
        text,
        platform: $("#platform").value || null,
        mode: $("#mode").value,
      }),
    });
    renderResult(payload);
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function buildResultPrompt() {
  const card = $("#result-card");
  const id = card.dataset.id;
  if (!id) return toast("Create a capsule first", "error");
  const button = $("#btn-result-prompt");
  setBusy(button, true, "Building…");
  try {
    const destination = $("#result-destination").value;
    const payload = await api(`/api/capsules/${id}/prompt?destination=${encodeURIComponent(destination)}`, { method: "GET" });
    $("#result-prompt").value = payload.prompt;
    toast(`Prompt ready for ${destination}`, "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    setBusy(button, false);
  }
}

async function copyText(value, label = "Copied") {
  try {
    await navigator.clipboard.writeText(value);
    toast(label, "success");
  } catch {
    const area = document.createElement("textarea");
    area.value = value;
    document.body.append(area);
    area.select();
    document.execCommand("copy");
    area.remove();
    toast(label, "success");
  }
}

/* ------------------------------------------------------------------ */
/* Library                                                             */
/* ------------------------------------------------------------------ */
function capsuleCard(capsule) {
  return h("article", { class: "capsule-card" },
    h("div", { class: "capsule-meta" },
      h("span", { class: "badge" }, capsule.platform),
      h("span", { class: "badge violet" }, capsule.mode),
      capsule.draft ? h("span", { class: "badge warn" }, "DRAFT") : null,
    ),
    h("h3", null, capsule.title),
    h("p", null, capsule.summary || capsule.next_action || "No summary stored yet."),
    h("div", { class: "tiny muted" }, `${formatDate(capsule.created_at)} · ~${capsule.tokens.toLocaleString()} tokens`),
    h("div", { class: "capsule-actions" },
      h("button", { class: "ghost tiny-btn", onclick: () => openCapsule(capsule.id) }, "Open"),
      h("button", { class: "ghost tiny-btn", onclick: () => quickPrompt(capsule.id) }, "Prompt"),
      h("button", { class: "ghost tiny-btn", onclick: () => download(capsule.id, "scapsule") }, "Export"),
      h("button", { class: "danger tiny-btn", onclick: () => removeCapsule(capsule.id, capsule.title) }, "Delete"),
    ),
  );
}

async function loadLibrary(term = $("#search").value.trim()) {
  const list = $("#library-list");
  list.replaceChildren(h("div", { class: "empty" }, "Loading capsules…"));
  try {
    const payload = await api(`/api/capsules?q=${encodeURIComponent(term)}`);
    state.capsules = payload.capsules;
    if (!payload.capsules.length) {
      list.replaceChildren(
        h("div", { class: "empty" },
          h("div", null, term ? `No capsule matches “${term}”.` : "No capsules yet."),
          h("div", { class: "tiny", style: "margin-top:8px" }, "Capture a conversation to create your first capsule."),
        ),
      );
      return;
    }
    list.replaceChildren(...payload.capsules.map(capsuleCard));
  } catch (error) {
    list.replaceChildren(h("div", { class: "empty" }, error.message));
  }
}

async function quickPrompt(id) {
  try {
    const payload = await api(`/api/capsules/${id}/prompt?destination=ChatGPT`);
    await copyText(payload.prompt, "Continuation prompt copied for ChatGPT");
  } catch (error) {
    toast(error.message, "error");
  }
}

async function removeCapsule(id, title) {
  if (!confirm(`Delete “${title}”? This removes the capsule and its stored conversation from this computer.`)) return;
  try {
    await api(`/api/capsules/${id}`, { method: "DELETE" });
    toast("Capsule deleted", "success");
    loadStatus();
    loadLibrary();
  } catch (error) {
    toast(error.message, "error");
  }
}

function download(id, format) {
  const link = document.createElement("a");
  link.href = `/api/capsules/${id}/export?format=${format}`;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
  toast(`Downloading ${format}`, "success");
}

function exportButtons(id) {
  return [
    ["scapsule", ".scapsule"],
    ["json", "JSON"],
    ["markdown", "Markdown"],
    ["txt", "TXT"],
    ["zip", "ZIP"],
  ].map(([format, label]) =>
    h("button", { class: "ghost tiny-btn", onclick: () => download(id, format) }, label),
  );
}

/* ------------------------------------------------------------------ */
/* Detail                                                              */
/* ------------------------------------------------------------------ */
function listOrEmpty(items, render, empty) {
  if (!items || !items.length) return h("p", { class: "tiny muted" }, empty);
  return h("ul", { class: "list" }, ...items.map((item) => h("li", null, render(item))));
}

async function openCapsule(id) {
  showView("detail");
  const overview = $("#detail-overview");
  overview.replaceChildren(h("div", { class: "muted" }, "Loading capsule…"));
  try {
    const payload = await api(`/api/capsules/${id}`);
    state.current = payload;
    renderDetail(payload);
  } catch (error) {
    toast(error.message, "error");
    showView("library");
  }
}

function renderDetail(payload) {
  const { capsule, document: doc } = payload;
  const project = doc.project || {};
  const progress = doc.progress || {};
  const technical = doc.technical || {};
  const compression = doc.compression || {};

  $("#view-title").textContent = project.name || capsule.title;
  $("#view-sub").textContent = `${capsule.platform} · ${compression.mode || capsule.mode} compression · ${formatDate(capsule.created_at)}`;

  setChildren(
    $("#detail-overview"),
    h("div", { class: "card-head" },
      h("h2", null, "Project state"),
      h("span", { class: "badge success" }, `${(compression.capsule_tokens || 0).toLocaleString()} tokens`),
    ),
    h("dl", { class: "kv" },
      h("dt", null, "Objective"), h("dd", null, project.objective || "not stated"),
      h("dt", null, "Description"), h("dd", null, project.description || "—"),
      h("dt", null, "Stage"), h("dd", null, `${project.stage || "unknown"} (inferred)`),
      h("dt", null, "Stack"), h("dd", null, (project.technologies || []).join(", ") || "not identified"),
      h("dt", null, "Source"), h("dd", null, `${capsule.platform} · ${(doc.source && doc.source.message_count) || 0} messages`),
    ),
    h("div", { class: "section-title" }, "Summary"),
    h("pre", { class: "code-block" }, doc.summary || "No summary."),
    (doc.warnings && doc.warnings.length)
      ? h("div", { class: "warnings", style: "margin-top:12px" }, ...doc.warnings.map((warning) => h("div", null, `⚠ ${warning}`)))
      : null,
  );

  const instructions = (doc.instructions || []).map((item) => `${item.text} (${item.kind}, ${item.certainty})`);
  const decisions = (doc.decisions || []).map((item) => item.text);
  const completed = (progress.completed || []).map((item) => item.task);
  const pending = (progress.pending || []).map((item) => item.task);
  const errors = (progress.errors || []).map((item) => `${item.error}${item.solution ? ` → ${item.solution}` : " (unresolved)"}`);

  $("#detail-progress").replaceChildren(
    h("div", { class: "card-head" }, h("h2", null, "Working state")),
    h("div", { class: "section-title" }, "Next action"),
    h("p", null, progress.next_action || "Not recorded."),
    h("div", { class: "section-title" }, "Pending"),
    listOrEmpty(pending, (item) => item, "No pending tasks detected."),
    h("div", { class: "section-title" }, "Completed"),
    listOrEmpty(completed, (item) => item, "Nothing marked as complete."),
    h("div", { class: "section-title" }, "Errors and solutions"),
    listOrEmpty(errors, (item) => item, "No errors recorded."),
    h("div", { class: "section-title" }, "User instructions"),
    listOrEmpty(instructions, (item) => item, "No explicit instructions found."),
    h("div", { class: "section-title" }, "Decisions"),
    listOrEmpty(decisions, (item) => item, "No decisions recorded."),
    h("div", { class: "section-title" }, "Technical"),
    h("p", { class: "tiny muted" },
      `Languages: ${(technical.languages || []).join(", ") || "—"} · Frameworks: ${(technical.frameworks || []).join(", ") || "—"} · Tools: ${(technical.libraries || []).join(", ") || "—"}`),
  );

  const code = doc.code || [];
  $("#detail-code").replaceChildren(
    h("div", { class: "card-head" }, h("h2", null, "Code"), h("span", { class: "tiny muted" }, `${code.length} block(s)`)),
    code.length
      ? h("div", null, ...code.slice(0, 6).map((item) =>
          h("div", { style: "margin-bottom:12px" },
            h("div", { class: "tiny muted", style: "margin-bottom:6px" }, item.purpose || item.language),
            h("pre", { class: "code-block" }, item.content),
          )))
      : h("p", { class: "tiny muted" }, "No code blocks in this capsule."),
  );

  $("#detail-edit").replaceChildren(
    h("div", { class: "card-head" }, h("h2", null, "Edit capsule")),
    h("div", { class: "edit-grid" },
      h("label", null, "Project name", h("input", { type: "text", id: "edit-name", value: project.name || "" })),
      h("label", null, "Objective", h("input", { type: "text", id: "edit-objective", value: project.objective || "" })),
      h("label", null, "Next action", h("input", { type: "text", id: "edit-next", value: progress.next_action || "" })),
    ),
    h("div", { class: "controls" },
      h("button", { class: "primary", onclick: () => saveEdits(capsule.id) }, "Save changes"),
      h("span", { class: "tiny muted" }, "Creates a new version"),
    ),
  );

  $("#detail-prompt").replaceChildren(
    h("div", { class: "card-head" }, h("h2", null, "Resume elsewhere")),
    h("div", { class: "controls" },
      h("label", null, "Destination", h("select", { id: "detail-destination" },
        ...state.destinations.map((name) => h("option", { value: name }, name)))),
      h("button", { class: "ghost", onclick: () => loadDetailPrompt(capsule.id) }, "Build prompt"),
      h("button", { class: "primary", onclick: () => copyText($("#detail-prompt-box").value, "Prompt copied") }, "Copy"),
      h("button", { class: "ghost", onclick: () => openDestination() }, "Open AI"),
    ),
    h("textarea", { class: "prompt-box", id: "detail-prompt-box", readonly: "readonly", placeholder: "Build a destination-specific continuation prompt." }),
  );

  $("#detail-meta").replaceChildren(
    h("div", { class: "card-head" }, h("h2", null, "Metadata")),
    h("dl", { class: "kv" },
      h("dt", null, "Capsule id"), h("dd", null, capsule.id),
      h("dt", null, "Created"), h("dd", null, formatDate(capsule.created_at)),
      h("dt", null, "Updated"), h("dd", null, formatDate(capsule.updated_at)),
      h("dt", null, "Compression"), h("dd", null, `${compression.mode} · ${compression.token_method || "estimate"}`),
      h("dt", null, "Original data"), h("dd", null, compression.original_included ? "included" : "not stored in the document"),
      h("dt", null, "Versions"), h("dd", null, String((payload.versions || []).length)),
    ),
  );

  $("#detail-exports").replaceChildren(...exportButtons(capsule.id));
  $("#detail-prompt-box").value = payload.prompt || "";
}

async function saveEdits(id) {
  const body = {
    name: $("#edit-name").value.trim(),
    objective: $("#edit-objective").value.trim(),
    next_action: $("#edit-next").value.trim(),
  };
  try {
    const payload = await api(`/api/capsules/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    toast("Capsule updated", "success");
    await loadLibrary($("#search").value.trim());
    openCapsule(id);
    return payload;
  } catch (error) {
    toast(error.message, "error");
  }
}

async function loadDetailPrompt(id) {
  const destination = $("#detail-destination").value;
  try {
    const payload = await api(`/api/capsules/${id}/prompt?destination=${encodeURIComponent(destination)}`);
    $("#detail-prompt-box").value = payload.prompt;
    $("#detail-prompt").dataset.url = payload.url || "";
    toast(`Prompt ready for ${destination}`, "success");
  } catch (error) {
    toast(error.message, "error");
  }
}

function openDestination() {
  const url = $("#detail-prompt").dataset.url;
  if (!url) return toast("Build a prompt first to choose a destination", "error");
  window.open(url, "_blank", "noopener");
}

/* ------------------------------------------------------------------ */
/* Import                                                              */
/* ------------------------------------------------------------------ */
async function importFile(file) {
  if (!file) return;
  const result = $("#import-result");
  result.classList.remove("hidden");
  result.replaceChildren(h("div", { class: "muted" }, `Importing ${file.name}…`));
  try {
    const response = await fetch(`/api/import?filename=${encodeURIComponent(file.name)}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Import failed");

    result.replaceChildren(
      h("div", { class: "preview-title" }, payload.capsule.title),
      h("div", { class: "capsule-meta" },
        h("span", { class: "badge success" }, "Imported"),
        h("span", { class: "badge" }, payload.capsule.platform),
        h("span", { class: "badge violet" }, payload.capsule.mode),
      ),
      payload.warnings && payload.warnings.length
        ? h("div", { class: "warnings" }, ...payload.warnings.map((warning) => h("div", null, `⚠ ${warning}`)))
        : h("p", { class: "tiny muted" }, "All checks passed."),
      h("div", { class: "controls" },
        h("button", { class: "primary", onclick: () => openCapsule(payload.capsule.id) }, "Open capsule"),
      ),
    );
    toast("Capsule imported", "success");
    loadStatus();
  } catch (error) {
    result.replaceChildren(h("div", { class: "warnings" }, error.message));
    toast(error.message, "error");
  }
}

/* ------------------------------------------------------------------ */
/* Wiring                                                              */
/* ------------------------------------------------------------------ */
document.querySelectorAll(".nav-item").forEach((item) => {
  item.addEventListener("click", () => showView(item.dataset.view));
});

$("#btn-refresh").addEventListener("click", () => {
  loadStatus();
  if (state.view === "library") loadLibrary();
  toast("Refreshed", "success");
});
$("#btn-preview").addEventListener("click", previewCapture);
$("#btn-create").addEventListener("click", createCapsule);
$("#btn-result-prompt").addEventListener("click", buildResultPrompt);
$("#btn-copy-result").addEventListener("click", () => copyText($("#result-prompt").value, "Prompt copied"));
$("#result-destination").addEventListener("change", buildResultPrompt);

$("#btn-search").addEventListener("click", () => loadLibrary());
$("#search").addEventListener("keydown", (event) => {
  if (event.key === "Enter") loadLibrary();
});

$("#btn-back").addEventListener("click", () => {
  showView("library");
  if (state.status) loadStatus();
});

const dropzone = $("#dropzone");
dropzone.addEventListener("click", () => $("#import-file").click());
$("#import-file").addEventListener("change", (event) => importFile(event.target.files[0]));
["dragenter", "dragover"].forEach((name) =>
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.add("dragover");
  }),
);
["dragleave", "drop"].forEach((name) =>
  dropzone.addEventListener(name, (event) => {
    event.preventDefault();
    dropzone.classList.remove("dragover");
  }),
);
dropzone.addEventListener("drop", (event) => importFile(event.dataTransfer.files[0]));

$("#source").addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter") createCapsule();
});

loadStatus();
