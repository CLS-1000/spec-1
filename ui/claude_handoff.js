// claude_handoff.js — Narrative Desk: the by-hand Claude path.
//
// "Copy for Claude"     fetches the run's handoff (the same prompts the local
//                       model gets), copies it and downloads it as a .md file,
//                       ready to paste into claude.ai.
// "Paste Claude's brief" saves Claude's write-up as a draft for that run. It
//                       then sits in the draft list and goes through the same
//                       publishing gate as any other draft.
//
// Reads the desk's own Voice, Ingestion source and Run date controls, and the
// page's ?api= / ?api_key= parameters, so it follows whatever the desk is set to.
(function () {
  "use strict";

  const qs = new URLSearchParams(location.search);
  const BASE = (qs.get("api") || "").replace(/\/+$/, "");
  const KEY = qs.get("api_key") || "";
  let lastHandoff = null;

  function apiUrl(path, params) {
    const url = new URL(BASE + path, location.origin);
    Object.entries(params || {}).forEach(([k, v]) => v && url.searchParams.set(k, v));
    if (KEY) url.searchParams.set("api_key", KEY);
    return url.toString();
  }

  async function call(method, path, params, body) {
    const headers = KEY ? { "X-API-Key": KEY } : {};
    if (body) headers["Content-Type"] = "application/json";
    const res = await fetch(apiUrl(path, params), {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail ? JSON.stringify(data.detail) : "HTTP " + res.status);
    return data;
  }

  function selection() {
    const val = (id) => (document.getElementById(id) || {}).value || "";
    return { voice: val("voice") || "standard", desk: val("desk") || "standard", date: val("gen-date") };
  }

  function say(text, isProblem) {
    status.textContent = text;
    status.style.color = isProblem ? "#e8735a" : "";
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (err) {
      const area = document.createElement("textarea");
      area.value = text;
      area.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      area.remove();
      return ok;
    }
  }

  function download(name, text) {
    const link = document.createElement("a");
    link.href = URL.createObjectURL(new Blob([text], { type: "text/markdown" }));
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  }

  async function copyForClaude() {
    say("Building the handoff…");
    try {
      const h = await call("GET", "/api/v1/narrative/handoff", selection());
      lastHandoff = h;
      const copied = await copyText(h.markdown);
      download(h.filename, h.markdown);
      const tier = h.records_tier === "llm_verified"
        ? "llm_verified"
        : "rule_based — Claude can draft it, but it cannot be released";
      say((copied ? "Copied" : "Downloaded") + " · " + h.records + " records · run " + h.run_id +
          " · " + tier + ". Paste it into claude.ai.", h.records_tier !== "llm_verified");
    } catch (err) {
      say("Couldn't build the handoff: " + err.message, true);
    }
  }

  function openPaste() {
    if (!lastHandoff) {
      say("Copy for Claude first, so the brief is tied to the right run.", true);
      return;
    }
    runLabel.textContent = "Run " + lastHandoff.run_id + " · " + lastHandoff.date +
      " · voice " + lastHandoff.voice + " · " + lastHandoff.desk;
    pasteBox.value = "";
    dialog.showModal();
    pasteBox.focus();
  }

  async function savePaste(event) {
    event.preventDefault();
    const markdown = pasteBox.value.trim();
    if (!markdown) return;
    saveBtn.disabled = true;
    try {
      const h = lastHandoff;
      const r = await call("POST", "/api/v1/narrative/hand-written", null, {
        desk: h.desk, voice: h.voice, date: h.date, run_id: h.run_id, markdown: markdown,
      });
      dialog.close();
      const why = r.readiness && !r.readiness.publishable
        ? " Not releasable yet: " + r.readiness.reasons.join("; ")
        : " Ready for release.";
      say("Saved as draft " + r.draft_id + "." + why, !(r.readiness && r.readiness.publishable));
      setTimeout(() => location.reload(), 1800);
    } catch (err) {
      say("Couldn't save: " + err.message, true);
    } finally {
      saveBtn.disabled = false;
    }
  }

  // ── build the controls next to "Generate Editorial Draft" ─────────────────
  const generate = document.getElementById("generate");
  if (!generate) return;
  const btnClass = (generate.className || "btn").replace(/\bprimary\b/, "").trim() || "btn";

  const copyBtn = document.createElement("button");
  copyBtn.type = "button";
  copyBtn.className = btnClass;
  copyBtn.id = "claude-copy";
  copyBtn.textContent = "Copy for Claude";
  copyBtn.title = "Copy this run's handoff to paste into claude.ai";

  const pasteBtn = document.createElement("button");
  pasteBtn.type = "button";
  pasteBtn.className = btnClass;
  pasteBtn.id = "claude-paste";
  pasteBtn.textContent = "Paste Claude's Brief";
  pasteBtn.title = "Save what Claude wrote as a draft for this run";

  const status = document.createElement("span");
  status.id = "claude-status";
  status.setAttribute("aria-live", "polite");
  const deskFont = getComputedStyle(generate).fontFamily;
  status.style.cssText = "flex-basis:100%;font-size:12px;opacity:.85;font-family:" + deskFont;

  generate.after(copyBtn, pasteBtn);
  (generate.parentElement || document.body).appendChild(status);

  const dialog = document.createElement("dialog");
  dialog.id = "claude-dialog";
  dialog.style.cssText =
    "width:min(860px,92vw);padding:20px;border:1px solid currentColor;border-radius:8px;" +
    "background:" + getComputedStyle(document.body).backgroundColor + ";color:inherit";
  dialog.innerHTML =
    '<form method="dialog" style="display:flex;flex-direction:column;gap:10px">' +
    '<h2 class="section-title" style="margin:0">Paste Claude\'s Brief</h2>' +
    '<div class="dim" id="claude-run" style="font-family:' + deskFont.replace(/"/g, "'") + '"></div>' +
    '<textarea id="claude-text" rows="20" placeholder="Paste the brief Claude wrote, as Markdown" ' +
    'style="width:100%;font:13px/1.5 \'IBM Plex Mono\',monospace;background:transparent;color:inherit;' +
    'border:1px solid currentColor;border-radius:6px;padding:10px"></textarea>' +
    '<div style="display:flex;gap:8px;justify-content:flex-end">' +
    '<button type="button" class="' + btnClass + '" id="claude-cancel">Cancel</button>' +
    '<button type="submit" class="' + btnClass + ' primary" id="claude-save">Save as Draft</button>' +
    "</div></form>";
  document.body.appendChild(dialog);

  const runLabel = dialog.querySelector("#claude-run");
  const pasteBox = dialog.querySelector("#claude-text");
  const saveBtn = dialog.querySelector("#claude-save");

  copyBtn.addEventListener("click", copyForClaude);
  pasteBtn.addEventListener("click", openPaste);
  dialog.querySelector("form").addEventListener("submit", savePaste);
  dialog.querySelector("#claude-cancel").addEventListener("click", () => dialog.close());
})();
