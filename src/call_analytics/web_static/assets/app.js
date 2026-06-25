const stages = ["transcribe", "diarize", "emotion", "report"];
const stageLabels = {
  transcribe: "ASR",
  diarize: "Роли",
  emotion: "Эмоции",
  report: "Отчёт",
};
const statusLabels = {
  pending: "в очереди",
  running: "в работе",
  done: "готово",
  failed: "ошибка",
};

const state = {
  recordings: [],
  selectedId: null,
};

const recordingsNode = document.querySelector("#recordings");
const detailsNode = document.querySelector("#details");
const toastNode = document.querySelector("#toast");
const wavInput = document.querySelector("#wavInput");

document.querySelector("#refreshButton").addEventListener("click", () => refresh());
document.querySelector("#uploadButton").addEventListener("click", () => wavInput.click());
wavInput.addEventListener("change", () => uploadSelectedFile());

recordingsNode.addEventListener("click", (event) => {
  const button = event.target.closest("[data-recording-id]");
  if (!button) return;
  state.selectedId = button.dataset.recordingId;
  render();
});

detailsNode.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  const recording = selectedRecording();
  if (!recording) return;
  await runAction(button.dataset.action, recording);
});

async function refresh() {
  try {
    state.recordings = await requestJson("/api/recordings");
    if (!state.selectedId && state.recordings.length > 0) {
      state.selectedId = state.recordings[0].id;
    }
    if (!state.recordings.some((item) => item.id === state.selectedId)) {
      state.selectedId = state.recordings[0]?.id ?? null;
    }
    render();
  } catch (error) {
    recordingsNode.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
    showToast(error.message);
  }
}

async function runAction(action, recording) {
  const job = recording.job;
  try {
    if (action === "enqueue") {
      await requestJson(`/api/recordings/${encodeURIComponent(recording.id)}/jobs`, {
        method: "POST",
      });
      showToast("Запись поставлена в обработку");
    } else if (action === "process" && job) {
      await requestJson(`/api/jobs/${encodeURIComponent(job.id)}/process`, {
        method: "POST",
      });
      showToast("Обработка выполнена");
    } else if (action === "retry" && job) {
      await requestJson(`/api/jobs/${encodeURIComponent(job.id)}/retry`, {
        method: "POST",
      });
      showToast("Повтор включён");
    }
    await refresh();
  } catch (error) {
    showToast(error.message);
  }
}

async function uploadSelectedFile() {
  const file = wavInput.files?.[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  try {
    const uploaded = await requestJson("/api/recordings", {
      method: "POST",
      body: formData,
      headers: {},
    });
    state.selectedId = uploaded.id;
    showToast("WAV загружен");
    await refresh();
  } catch (error) {
    showToast(error.message);
  } finally {
    wavInput.value = "";
  }
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    ...options,
  });
  if (!response.ok) {
    const message = await response
      .json()
      .then((payload) => payload.detail)
      .catch(() => response.statusText);
    throw new Error(message || `HTTP ${response.status}`);
  }
  return await response.json();
}

function render() {
  const done = state.recordings.filter((item) => item.job?.status === "done").length;
  const failed = state.recordings.filter((item) => item.job?.status === "failed").length;
  document.querySelector("#totalCount").textContent = String(state.recordings.length);
  document.querySelector("#doneCount").textContent = String(done);
  document.querySelector("#failedCount").textContent = String(failed);
  document.querySelector("#lastUpdated").textContent = new Date().toLocaleTimeString("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  if (state.recordings.length === 0) {
    recordingsNode.innerHTML =
      '<div class="empty">Положите WAV-файлы в каталог записей и обновите список.</div>';
  } else {
    recordingsNode.innerHTML = state.recordings.map(renderRecording).join("");
  }
  renderDetails();
}

function renderRecording(recording) {
  const job = recording.job;
  const selected = recording.id === state.selectedId;
  return `
    <button class="recording" type="button" data-recording-id="${escapeAttr(recording.id)}" aria-selected="${selected}">
      <span>
        <span class="recording-name">${escapeHtml(recording.filename)}</span>
        <span class="recording-meta">${formatDate(recording.started_at)} · ${formatDuration(recording.duration_seconds)} · ${recording.channel_layout}</span>
      </span>
      ${renderStages(job)}
      <span class="status ${job?.status ?? ""}">${statusLabels[job?.status] ?? "не начато"}</span>
    </button>
  `;
}

function renderDetails() {
  const recording = selectedRecording();
  if (!recording) {
    detailsNode.innerHTML = "<h2>Отчёт</h2><p class=\"muted\">Выберите запись из списка.</p>";
    return;
  }
  const job = recording.job;
  detailsNode.innerHTML = `
    <div class="details-title">
      <div>
        <h2>${escapeHtml(recording.filename)}</h2>
        <p class="muted">${formatDate(recording.started_at)} · ${formatDuration(recording.duration_seconds)}</p>
      </div>
      <span class="status ${job?.status ?? ""}">${statusLabels[job?.status] ?? "не начато"}</span>
    </div>
    ${renderStages(job)}
    <div class="button-row">
      ${job ? "" : '<button class="action primary" type="button" data-action="enqueue">Поставить</button>'}
      ${job ? '<button class="action primary" type="button" data-action="process">Обработать</button>' : ""}
      ${job?.status === "failed" ? '<button class="action danger" type="button" data-action="retry">Повторить</button>' : ""}
    </div>
    ${renderArtifacts(recording)}
    ${renderError(job)}
  `;
}

function renderStages(job) {
  const completed = new Set(job?.completed_stages ?? []);
  const next = job?.next_stage;
  return `
    <div class="stage-rail" aria-label="Стадии пайплайна">
      ${stages
        .map((stage) => {
          const classes = ["stage"];
          if (completed.has(stage)) classes.push("done");
          if (next === stage && job?.status !== "failed") classes.push("current");
          if (next === stage && job?.status === "failed") classes.push("failed");
          return `<span class="${classes.join(" ")}" title="${stageLabels[stage]}"></span>`;
        })
        .join("")}
    </div>
  `;
}

function renderArtifacts(recording) {
  if (recording.job?.status !== "done") {
    return '<p class="muted">PDF и JSON появятся после завершения стадии отчёта.</p>';
  }
  const encoded = encodeURIComponent(recording.job.id);
  return `
    <div class="artifact-list">
      <a href="/api/jobs/${encoded}/report" target="_blank" rel="noreferrer">Открыть JSON отчёт</a>
      <a href="/api/jobs/${encoded}/report.pdf" target="_blank" rel="noreferrer">Открыть PDF отчёт</a>
    </div>
  `;
}

function renderError(job) {
  if (!job?.last_error) return "";
  return `<p class="error">${escapeHtml(job.last_error.join(": "))}</p>`;
}

function selectedRecording() {
  return state.recordings.find((item) => item.id === state.selectedId) ?? null;
}

function formatDate(value) {
  return new Date(value).toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDuration(seconds) {
  const total = Math.round(seconds);
  const minutes = Math.floor(total / 60);
  const rest = total % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function showToast(message) {
  toastNode.textContent = message;
  toastNode.hidden = false;
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => {
    toastNode.hidden = true;
  }, 3600);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttr(value) {
  return escapeHtml(value);
}

refresh();
