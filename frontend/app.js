// Presentation tier logic. The browser only ever talks to /api/... on the
// same origin; nginx forwards those calls to the FastAPI container.

const form = document.getElementById("note-form");
const input = document.getElementById("note-text");
const list = document.getElementById("notes");
const errorBox = document.getElementById("error");

let lastStatus = {}; // note id -> status from the previous poll
let pollTimer = null;

async function loadNotes() {
  const notes = await (await fetch("/api/notes")).json();

  // A note that was "pending" last time and is "notified" now was just
  // processed by the worker -> show the in-app notification.
  for (const n of notes) {
    if (lastStatus[n.id] === "pending" && n.status === "notified") {
      showToast(`Note #${n.id} saved`);
    }
  }
  lastStatus = Object.fromEntries(notes.map((n) => [n.id, n.status]));

  render(notes);

  // Keep polling every 2s only while some work is still waiting on the worker.
  clearTimeout(pollTimer);
  if (notes.some((n) => n.status === "pending")) {
    pollTimer = setTimeout(loadNotes, 2000);
  }
}

function render(notes) {
  list.innerHTML = "";
  for (const n of notes) {
    const li = document.createElement("li");
    const when = n.notified_at ? new Date(n.notified_at).toLocaleTimeString() : "";
    li.innerHTML = `<span class="text"></span>
      <span class="badge ${n.status}">${n.status}</span>
      <small>${when}</small>`;
    li.querySelector(".text").textContent = n.text; // textContent avoids HTML injection
    list.appendChild(li);
  }
}

function showToast(message) {
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = message;
  document.getElementById("toasts").appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errorBox.textContent = "";
  const res = await fetch("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: input.value }),
  });
  if (!res.ok) {
    errorBox.textContent = "Note can't be empty.";
    return;
  }
  input.value = "";
  loadNotes();
});

loadNotes();
