// Docent API Tester - vanilla JS, no build step

const state = {
  docId: "",
  chapterId: "",
  lessonId: "",
  quizQIds: [],
};

const $ = (id) => document.getElementById(id);
const baseUrl = () => $("baseUrl").value.trim().replace(/\/$/, "");

function setState(key, val) {
  if (val) state[key] = val;
  renderStateBar();
  prefill();
}

function renderStateBar() {
  const parts = [];
  if (state.docId) parts.push(`doc: ${state.docId}`);
  if (state.chapterId) parts.push(`chapter: ${state.chapterId}`);
  if (state.lessonId) parts.push(`lesson: ${state.lessonId}`);
  if (state.quizQIds.length) parts.push(`quizQs: ${state.quizQIds.length}`);
  $("state-bar").textContent = parts.length ? "State → " + parts.join(" | ") : "No state yet — start with Upload.";
}

function prefill() {
  if (state.docId) {
    ["get-doc-id", "roadmap-doc-id", "lesson-doc-id", "ask-doc-id", "qs-doc-id", "prog-doc-id", "fq-doc-id"].forEach(
      (id) => { if ($(id)) $(id).value = state.docId; }
    );
  }
  if (state.chapterId) $("lesson-id").value = state.chapterId;
  if (state.lessonId) $("qs-lesson-id").value = state.lessonId;
}

function showResponse(elId, status, data) {
  const el = $(elId);
  const statusClass = status >= 200 && status < 300 ? "ok" : "err";
  el.innerHTML = `<div class="status ${statusClass}">Status: ${status}</div><pre>${escapeHtml(
    typeof data === "string" ? data : JSON.stringify(data, null, 2)
  )}</pre>`;
}

function escapeHtml(str) {
  return str.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

async function sendJson(path, body) {
  const res = await fetch(baseUrl() + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let data;
  try { data = await res.json(); } catch { data = await res.text(); }
  return { status: res.status, data };
}

async function sendGet(path) {
  const res = await fetch(baseUrl() + path);
  let data;
  try { data = await res.json(); } catch { data = await res.text(); }
  return { status: res.status, data };
}

// ---- Actions ----

async function doUpload() {
  const file = $("upload-file").files[0];
  if (!file) return alert("Pick a PDF first");
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(baseUrl() + "/api/documents/upload", { method: "POST", body: fd });
  let data;
  try { data = await res.json(); } catch { data = await res.text(); }
  showResponse("resp-upload", res.status, data);
  if (data && data.id) setState("docId", data.id);
}

async function doGetDoc() {
  const id = $("get-doc-id").value.trim();
  const { status, data } = await sendGet(`/api/documents/${id}`);
  showResponse("resp-get-doc", status, data);
}

async function doPollDoc() {
  const id = $("get-doc-id").value.trim();
  for (let i = 0; i < 40; i++) {
    const { status, data } = await sendGet(`/api/documents/${id}`);
    showResponse("resp-get-doc", status, data);
    if (data && data.status === "ready") break;
    await new Promise((r) => setTimeout(r, 3000));
  }
}

async function doRoadmap() {
  const id = $("roadmap-doc-id").value.trim();
  const { status, data } = await sendGet(`/api/documents/${id}/roadmap`);
  showResponse("resp-roadmap", status, data);
  if (data && data.chapters && data.chapters.length) {
    setState("chapterId", data.chapters[0].id);
  }
}

async function doLesson() {
  const docId = $("lesson-doc-id").value.trim();
  const lessonId = $("lesson-id").value.trim();
  const goal = $("lesson-goal").value;
  const { status, data } = await sendGet(`/api/documents/${docId}/lessons/${lessonId}?goal=${goal}`);
  showResponse("resp-lesson", status, data);
  if (data && data.lesson) {
    setState("lessonId", data.lesson.id);
    if (data.quiz) setState("quizQIds", data.quiz.map((q) => q.id));
  }
}

async function doAsk() {
  const docId = $("ask-doc-id").value.trim();
  const question = $("ask-question").value.trim();
  const ctx = $("ask-ctx").value.trim();
  const { status, data } = await sendJson(`/api/documents/${docId}/ask`, {
    question,
    lesson_context_id: ctx || null,
  });
  showResponse("resp-ask", status, data);
}

async function doQuizSubmit() {
  const docId = $("qs-doc-id").value.trim();
  const lessonId = $("qs-lesson-id").value.trim();
  let answers;
  try {
    answers = JSON.parse($("qs-answers").value.trim());
  } catch (e) {
    return alert("Invalid JSON in answers: " + e.message);
  }
  const { status, data } = await sendJson(
    `/api/documents/${docId}/lessons/${lessonId}/quiz/submit`,
    { answers }
  );
  showResponse("resp-quiz-submit", status, data);
}

async function doProgress() {
  const id = $("prog-doc-id").value.trim();
  const { status, data } = await sendGet(`/api/documents/${id}/progress`);
  showResponse("resp-progress", status, data);
}

async function doFinalQuiz() {
  const id = $("fq-doc-id").value.trim();
  const { status, data } = await sendJson(`/api/documents/${id}/quiz/final`, {});
  showResponse("resp-final-quiz", status, data);
}

// ---- Wiring ----

const actions = {
  "upload": doUpload,
  "get-doc": doGetDoc,
  "poll-doc": doPollDoc,
  "roadmap": doRoadmap,
  "lesson": doLesson,
  "ask": doAsk,
  "quiz-submit": doQuizSubmit,
  "progress": doProgress,
  "final-quiz": doFinalQuiz,
};

document.querySelectorAll(".send").forEach((btn) => {
  btn.addEventListener("click", () => actions[btn.dataset.action]());
});

document.querySelectorAll(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".panel").forEach((p) => p.classList.add("hidden"));
    $(`panel-${btn.dataset.panel}`).classList.remove("hidden");
  });
});

renderStateBar();
