// Presentation tier logic. The browser only ever talks to /api/... on the
// same origin; nginx forwards those calls to the FastAPI container.

const COLORS = [
  { id: "default", name: "Plain" },
  { id: "butter", name: "Butter" },
  { id: "mint", name: "Mint" },
  { id: "sky", name: "Sky" },
  { id: "lilac", name: "Lilac" },
  { id: "rose", name: "Rose" },
];

const $ = (id) => document.getElementById(id);
const composer = $("composer");
const cTitle = $("c-title");
const cText = $("c-text");
const editor = $("editor");
const eTitle = $("e-title");
const eText = $("e-text");
const tpl = $("note-tpl");

let notes = [];
let lastStatus = {};          // note id -> status from the previous poll
let pollTimer = null;
const hidden = new Set();     // ids deleted locally, waiting out the undo window
let editingId = null;

// ---------- API ----------
async function api(path, options = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.status === 204 ? null : res.json();
}

// ---------- Loading & polling ----------
async function loadNotes() {
  try {
    notes = await api("/notes");
  } catch {
    showToast("Couldn't load notes. Check that the API is running.");
    return;
  }

  // A note that was "pending" last time and is "notified" now was just
  // processed by the worker -> show the in-app notification.
  const justNotified = new Set();
  for (const n of notes) {
    if (lastStatus[n.id] === "pending" && n.status === "notified") {
      justNotified.add(n.id);
      showToast(`Saved "${label(n)}"`);
    }
  }
  lastStatus = Object.fromEntries(notes.map((n) => [n.id, n.status]));

  render(justNotified);

  // Keep polling every 2s only while some work is still waiting on the worker.
  clearTimeout(pollTimer);
  if (notes.some((n) => n.status === "pending")) {
    pollTimer = setTimeout(loadNotes, 2000);
  }
}

function label(n) {
  const s = n.title || n.text;
  return s.length > 28 ? s.slice(0, 27) + "…" : s;
}

// ---------- Rendering ----------
function render(justNotified = new Set()) {
  const visible = notes.filter((n) => !hidden.has(n.id));
  const pinned = visible.filter((n) => n.pinned);
  const others = visible.filter((n) => !n.pinned);

  $("pinned").replaceChildren(...pinned.map((n) => noteEl(n, justNotified.has(n.id))));
  $("others").replaceChildren(...others.map((n) => noteEl(n, justNotified.has(n.id))));

  $("pinned-section").hidden = pinned.length === 0;
  $("others-heading").hidden = pinned.length === 0 || others.length === 0;
  $("empty").hidden = visible.length > 0;
}

function noteEl(n, justNotified) {
  const el = tpl.content.firstElementChild.cloneNode(true);
  el.dataset.id = n.id;
  el.dataset.color = n.color || "default";
  el.dataset.status = n.status;
  // textContent everywhere user text goes, so notes can't inject HTML.
  el.querySelector(".n-title").textContent = n.title || "";
  el.querySelector(".n-text").textContent = n.text || "";
  el.querySelector(".status-label").textContent = n.status === "notified" ? "Saved" : "Saving…";
  const time = el.querySelector(".n-time");
  const stamp = n.updated_at || n.created_at;
  if (stamp) {
    time.dateTime = stamp;
    time.textContent = relativeTime(stamp);
    time.title = new Date(stamp).toLocaleString();
  }
  el.querySelector(".pin").setAttribute("aria-label", n.pinned ? "Unpin note" : "Pin note");
  el.setAttribute("aria-label", `Edit note: ${label(n)}`);

  if (justNotified) {
    el.classList.add("just-notified");
    requestAnimationFrame(() => setTimeout(() => el.classList.remove("just-notified"), 450));
  }
  return el;
}

function relativeTime(iso) {
  const secs = Math.round((Date.now() - new Date(iso)) / 1000);
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (secs < 45) return "just now";
  if (secs < 3600) return rtf.format(-Math.round(secs / 60), "minute");
  if (secs < 86400) return rtf.format(-Math.round(secs / 3600), "hour");
  if (secs < 604800) return rtf.format(-Math.round(secs / 86400), "day");
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------- Color swatches ----------
function buildSwatches(container, onPick) {
  container.replaceChildren(
    ...COLORS.map((c) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "swatch";
      b.setAttribute("role", "radio");
      b.setAttribute("aria-label", c.name);
      b.title = c.name;
      b.dataset.value = c.id;
      b.style.setProperty("--sw", `var(--paper-${c.id})`);
      b.addEventListener("click", () => onPick(c.id));
      return b;
    })
  );
}

function setColor(slip, color) {
  slip.dataset.color = color;
  for (const b of slip.querySelectorAll(".swatch")) {
    b.setAttribute("aria-checked", String(b.dataset.value === color));
  }
}

// ---------- Composer ----------
buildSwatches(composer.querySelector(".swatches"), (c) => setColor(composer, c));
setColor(composer, "default");

function openComposer() { composer.classList.add("open"); }
function closeComposer() {
  composer.classList.remove("open");
  composer.reset();
  setColor(composer, "default");
  $("c-error").textContent = "";
  autoGrow(cText);
}

cText.addEventListener("focus", openComposer);
cTitle.addEventListener("focus", openComposer);
$("c-cancel").addEventListener("click", closeComposer);
composer.addEventListener("keydown", (e) => { if (e.key === "Escape") closeComposer(); });
cText.addEventListener("input", () => autoGrow(cText));

composer.addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { title: cTitle.value, text: cText.value, color: composer.dataset.color };
  if (!body.title.trim() && !body.text.trim()) {
    $("c-error").textContent = "Add a title or some text to save this note.";
    return;
  }
  try {
    await api("/notes", { method: "POST", body: JSON.stringify(body) });
  } catch {
    $("c-error").textContent = "Couldn't save the note. Try again.";
    return;
  }
  closeComposer();
  loadNotes();
});

function autoGrow(t) {
  t.style.height = "auto";
  t.style.height = `${t.scrollHeight}px`;
}

// ---------- Note actions (event delegation on both grids) ----------
for (const grid of [$("pinned"), $("others")]) {
  grid.addEventListener("click", (e) => {
    const el = e.target.closest(".note");
    if (!el) return;
    const id = Number(el.dataset.id);
    if (e.target.closest(".pin")) return togglePin(id);
    if (e.target.closest(".del")) return deleteNote(id, el);
    openEditor(id);
  });
  grid.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.classList.contains("note")) openEditor(Number(e.target.dataset.id));
  });
}

async function togglePin(id) {
  const n = notes.find((x) => x.id === id);
  if (!n) return; // note vanished since the last refresh
  try {
    await api(`/notes/${id}`, { method: "PATCH", body: JSON.stringify({ pinned: !n.pinned }) });
  } catch {
    return showToast("Couldn't update the note. Try again.");
  }
  loadNotes();
}

// Deletes still inside their undo window: id -> timer.
const pendingDeletes = new Map();

// If the tab closes during an undo window, send those deletes anyway
// (keepalive lets the request outlive the page).
addEventListener("pagehide", () => {
  for (const [id, timer] of pendingDeletes) {
    clearTimeout(timer);
    fetch(`/api/notes/${id}`, { method: "DELETE", keepalive: true });
  }
  pendingDeletes.clear();
});

// Delete waits out a short undo window before the request is sent.
function deleteNote(id, el) {
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    hidden.add(id);
    render();
    let undone = false;
    const timer = setTimeout(async () => {
      if (undone) return;
      pendingDeletes.delete(id);
      try {
        await api(`/notes/${id}`, { method: "DELETE" });
      } catch {
        showToast("Couldn't delete the note. It's back in your list.");
      }
      hidden.delete(id);
      loadNotes();
    }, 5000);
    pendingDeletes.set(id, timer);
    showToast("Note deleted", {
      action: "Undo",
      onAction: () => { undone = true; clearTimeout(timer); pendingDeletes.delete(id); hidden.delete(id); render(); },
      duration: 5000,
    });
  };
  if (el && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
    el.classList.add("leaving");
    el.addEventListener("animationend", finish, { once: true });
    setTimeout(finish, 300); // in case a re-render replaced the element mid-animation
  } else {
    finish();
  }
}

// ---------- Editor dialog ----------
buildSwatches(editor.querySelector(".swatches"), (c) => setColor(editor, c));

function openEditor(id) {
  const n = notes.find((x) => x.id === id);
  if (!n) return;
  editingId = id;
  eTitle.value = n.title || "";
  eText.value = n.text || "";
  setColor(editor, n.color || "default");
  $("e-error").textContent = "";
  editor.showModal();
  eText.focus();
}

$("e-cancel").addEventListener("click", () => editor.close());
editor.addEventListener("click", (e) => { if (e.target === editor) editor.close(); }); // backdrop click
$("e-delete").addEventListener("click", () => {
  const id = editingId;
  editor.close();
  deleteNote(id, document.querySelector(`.note[data-id="${id}"]`));
});

$("editor-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = { title: eTitle.value, text: eText.value, color: editor.dataset.color };
  if (!body.title.trim() && !body.text.trim()) {
    $("e-error").textContent = "A note needs a title or some text. Use Delete to remove it.";
    return;
  }
  try {
    await api(`/notes/${editingId}`, { method: "PATCH", body: JSON.stringify(body) });
  } catch {
    $("e-error").textContent = "Couldn't save changes. Try again.";
    return;
  }
  editor.close();
  loadNotes();
});

// ---------- Toasts ----------
function showToast(message, { action, onAction, duration = 3000 } = {}) {
  const t = document.createElement("div");
  t.className = "toast";
  const span = document.createElement("span");
  span.textContent = message;
  t.append(span);
  if (action) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = action;
    b.addEventListener("click", () => { onAction(); t.remove(); });
    t.append(b);
  }
  $("toasts").append(t);
  setTimeout(() => t.remove(), duration);
}

// ---------- Theme ----------
function currentTheme() {
  const set = document.documentElement.dataset.theme;
  if (set) return set;
  return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function syncThemeLabel() {
  $("theme-toggle").setAttribute(
    "aria-label",
    currentTheme() === "dark" ? "Switch to light theme" : "Switch to dark theme"
  );
}
$("theme-toggle").addEventListener("click", () => {
  const next = currentTheme() === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("theme", next); } catch {}
  syncThemeLabel();
});
syncThemeLabel();

// ---------- Build version (set by the CI/CD pipeline) ----------
api("/version")
  .then((v) => {
    const sha = v.commit.slice(0, 7);
    $("version").textContent = v.version === "dev" ? "Local build" : `Build ${v.version} (${sha})`;
  })
  .catch(() => { $("version").textContent = ""; });

// Refresh relative times once a minute.
setInterval(() => render(), 60000);

loadNotes();
