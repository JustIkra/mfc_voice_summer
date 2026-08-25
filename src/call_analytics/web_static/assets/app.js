const state = {
  filters: { dateFrom: "", dateTo: "", operatorExtension: "", satisfaction: "", resolution: "", sort: "asc", query: "" },
  page: 1,
  pageSize: 50,
  summary: null,
  operators: [],
  calls: [],
  totalItems: 0,
  selectedCallId: null,
  controller: null,
};

const labels = {
  satisfied: "Позитивно",
  neutral: "Нейтрально",
  dissatisfied: "Негативно",
  yes: "Да",
  no: "Нет",
  partial: "Частично",
  unknown: "Не определено",
  operator: "Оператор",
  client: "Клиент",
};

const emotionLabels = {
  neutral: "Спокойствие",
  happy: "Позитив",
  angry: "Раздражение",
  sad: "Грусть",
  fearful: "Тревога",
  disgusted: "Недовольство",
  surprised: "Удивление",
};

const nodes = {
  form: document.querySelector("#filterForm"),
  dateFrom: document.querySelector("#dateFrom"),
  dateTo: document.querySelector("#dateTo"),
  operator: document.querySelector("#operatorSelect"),
  satisfaction: document.querySelector("#satisfactionSelect"),
  resolution: document.querySelector("#resolutionSelect"),
  sort: document.querySelector("#sortSelect"),
  search: document.querySelector("#callSearch"),
  journal: document.querySelector("#callJournal"),
  operators: document.querySelector("#operatorBoard"),
  pagination: document.querySelector("#pagination"),
  dialog: document.querySelector("#reportDialog"),
  reportContent: document.querySelector("#reportContent"),
  downloadPdf: document.querySelector("#downloadPdf"),
  toast: document.querySelector("#toast"),
};

const customSelects = [...document.querySelectorAll("[data-custom-select]")].map(setupCustomSelect);

initializeDates();

nodes.form.addEventListener("submit", (event) => {
  event.preventDefault();
  readFilters();
  state.page = 1;
  refresh();
});

document.querySelector("#resetFilters").addEventListener("click", () => {
  initializeDates();
  setCustomSelectValue(nodes.operator, "");
  setCustomSelectValue(nodes.satisfaction, "");
  setCustomSelectValue(nodes.resolution, "");
  setCustomSelectValue(nodes.sort, "asc");
  nodes.search.value = "";
  readFilters();
  state.page = 1;
  refresh();
});

document.querySelector("#closeReport").addEventListener("click", closeReport);
document.querySelector("#closeReportBottom").addEventListener("click", closeReport);
nodes.dialog.addEventListener("click", (event) => {
  if (event.target === nodes.dialog) closeReport();
});

nodes.journal.addEventListener("click", (event) => {
  const button = event.target.closest("[data-call-id]");
  if (button) openReport(button.dataset.callId);
});

nodes.pagination.addEventListener("click", (event) => {
  const button = event.target.closest("[data-page]");
  if (!button) return;
  state.page = Number(button.dataset.page);
  refresh({ keepOperators: true });
});

document.addEventListener("click", (event) => {
  customSelects.forEach((select) => {
    if (!select.control.contains(event.target)) closeCustomSelect(select);
  });
});

document.querySelector("#syncStatus").addEventListener("click", () => {
  showToast(document.querySelector("#syncStatus").title || "Синхронизация ещё не запускалась");
});

window.setInterval(pollSyncStatus, 10000);

function setupCustomSelect(control) {
  const select = {
    control,
    input: control.querySelector('input[type="hidden"]'),
    trigger: control.querySelector("[aria-haspopup='listbox']"),
    menu: control.querySelector("[role='listbox']"),
    value: control.querySelector(".custom-select-trigger > span:first-child"),
  };
  select.trigger.addEventListener("click", () => {
    if (select.menu.hidden) openCustomSelect(select);
    else closeCustomSelect(select);
  });
  select.trigger.addEventListener("keydown", (event) => {
    if (!["Enter", " ", "ArrowDown", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    openCustomSelect(select, event.key === "ArrowUp" ? -1 : 1);
  });
  select.menu.addEventListener("click", (event) => {
    const option = event.target.closest("[data-select-value]");
    if (!option) return;
    setCustomSelectValue(select.input, option.dataset.selectValue);
    closeCustomSelect(select, { restoreFocus: true });
  });
  select.menu.addEventListener("keydown", (event) => {
    const options = customSelectOptions(select);
    const current = Math.max(options.indexOf(document.activeElement), 0);
    if (event.key === "Escape") {
      event.preventDefault();
      closeCustomSelect(select, { restoreFocus: true });
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const direction = event.key === "ArrowDown" ? 1 : -1;
      options[(current + direction + options.length) % options.length].focus();
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      options[event.key === "Home" ? 0 : options.length - 1].focus();
    }
  });
  control.addEventListener("focusout", (event) => {
    if (!control.contains(event.relatedTarget)) closeCustomSelect(select);
  });
  return select;
}

function openCustomSelect(select, focusDirection = 0) {
  customSelects.forEach((item) => {
    if (item !== select) closeCustomSelect(item);
  });
  select.menu.hidden = false;
  select.trigger.setAttribute("aria-expanded", "true");
  select.control.classList.add("is-open");
  if (focusDirection === 0) return;
  const options = customSelectOptions(select);
  const selectedIndex = Math.max(
    options.findIndex((option) => option.dataset.selectValue === select.input.value),
    0,
  );
  options[focusDirection < 0 ? options.length - 1 : selectedIndex].focus();
}

function closeCustomSelect(select, { restoreFocus = false } = {}) {
  select.menu.hidden = true;
  select.trigger.setAttribute("aria-expanded", "false");
  select.control.classList.remove("is-open");
  if (restoreFocus) select.trigger.focus();
}

function setCustomSelectValue(input, value) {
  const select = customSelects.find((item) => item.input === input);
  if (!select) return;
  const options = customSelectOptions(select);
  const selected = options.find((option) => option.dataset.selectValue === value) || options[0];
  if (!selected) return;
  input.value = selected.dataset.selectValue;
  select.value.textContent = selected.textContent;
  options.forEach((option) => option.setAttribute("aria-selected", String(option === selected)));
}

function setCustomSelectOptions(input, options, selectedValue) {
  const select = customSelects.find((item) => item.input === input);
  if (!select) return;
  select.menu.innerHTML = options
    .map(
      (option) =>
        `<button type="button" role="option" data-select-value="${escapeHtml(option.value)}" aria-selected="false">${escapeHtml(option.label)}</button>`,
    )
    .join("");
  setCustomSelectValue(input, selectedValue);
}

function customSelectOptions(select) {
  return [...select.menu.querySelectorAll("[data-select-value]")];
}

async function pollSyncStatus() {
  if (document.hidden) return;
  try {
    renderSync(await requestJson("/api/sync/status"));
  } catch {
    return;
  }
}

async function refresh({ keepOperators = false } = {}) {
  if (state.controller) state.controller.abort();
  const controller = new AbortController();
  state.controller = controller;
  renderLoading();
  try {
    const filterParams = buildParams();
    const callParams = buildParams({ includePage: true });
    const operatorParams = buildParams({ includeOperator: false });
    const requests = [
      requestJson(`/api/dashboard/summary?${filterParams}`, controller.signal),
      keepOperators
        ? Promise.resolve(state.operators)
        : requestJson(`/api/operators?${operatorParams}`, controller.signal),
      requestJson(`/api/calls?${callParams}`, controller.signal),
      requestJson("/api/sync/status", controller.signal),
    ];
    const [summary, operators, calls, sync] = await Promise.all(requests);
    if (controller.signal.aborted) return;
    state.summary = summary;
    state.operators = operators;
    state.calls = calls.items;
    state.totalItems = calls.total_items;
    renderSummary();
    renderOperators();
    renderCalls();
    renderPagination();
    renderSync(sync);
  } catch (error) {
    if (error.name === "AbortError") return;
    renderError(error.message);
    showToast(error.message);
  }
}

function buildParams({ includePage = false, includeOperator = true } = {}) {
  const params = new URLSearchParams();
  if (state.filters.dateFrom) params.set("date_from", state.filters.dateFrom);
  if (state.filters.dateTo) params.set("date_to", state.filters.dateTo);
  if (includeOperator && state.filters.operatorExtension) {
    params.set("operator_extension", state.filters.operatorExtension);
  }
  if (state.filters.satisfaction) params.set("satisfaction", state.filters.satisfaction);
  if (state.filters.resolution) params.set("question_resolved", state.filters.resolution);
  if (state.filters.query) params.set("query", state.filters.query);
  if (includePage) {
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort", state.filters.sort);
  }
  return params.toString();
}

function readFilters() {
  state.filters = {
    dateFrom: nodes.dateFrom.value,
    dateTo: nodes.dateTo.value,
    operatorExtension: nodes.operator.value,
    satisfaction: nodes.satisfaction.value,
    resolution: nodes.resolution.value,
    sort: nodes.sort.value,
    query: nodes.search.value.trim(),
  };
}

function initializeDates() {
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - 29);
  nodes.dateFrom.value = toDateInput(start);
  nodes.dateTo.value = toDateInput(today);
  readFilters();
}

function renderSummary() {
  const summary = state.summary;
  const total = summary.total_calls;
  const satisfaction = summary.satisfaction;
  const resolution = summary.resolution || { yes: 0, partial: 0, no: 0, unknown: 0 };
  const satisfiedPercent = percent(satisfaction.satisfied, total);
  const neutralPercent = percent(satisfaction.neutral, total);
  const dissatisfiedPercent = percent(satisfaction.dissatisfied, total);
  setText("heroTotal", total);
  setText("metricTotal", total);
  setText("metricResolved", `${percent(summary.resolved_calls, total)}%`);
  setText("metricResolvedCount", `${summary.resolved_calls} разговоров`);
  setText("metricDuration", formatDuration(summary.average_duration_seconds));
  setText("metricAttention", summary.attention_calls);
  setText("qualityCount", `${total} отчётов`);
  setText("countGood", satisfaction.satisfied);
  setText("countNeutral", satisfaction.neutral);
  setText("countBad", satisfaction.dissatisfied);
  setText("percentGood", `${satisfiedPercent}%`);
  setText("percentNeutral", `${neutralPercent}%`);
  setText("percentBad", `${dissatisfiedPercent}%`);
  setText("qualityGood", `${satisfiedPercent}% позитивный фон`);
  setText("qualityNeutral", `${neutralPercent}% нейтральный фон`);
  setText("qualityBad", `${dissatisfiedPercent}% негативный фон`);
  setText("resolutionCount", `${total} отчётов`);
  setText("resolutionYes", resolution.yes);
  setText("resolutionPartial", resolution.partial);
  setText("resolutionNo", resolution.no);
  setText("resolutionUnknown", resolution.unknown);
  setText("resolutionYesPercent", `${percent(resolution.yes, total)}%`);
  setText("resolutionPartialPercent", `${percent(resolution.partial, total)}%`);
  setText("resolutionNoPercent", `${percent(resolution.no, total)}%`);
  setText("resolutionUnknownPercent", `${percent(resolution.unknown, total)}%`);
  document.querySelectorAll(".quality-ribbon").forEach((ribbon) => {
    ribbon.style.setProperty("--good-share", `${Math.max(satisfiedPercent, 1)}fr`);
    ribbon.style.setProperty("--neutral-share", `${Math.max(neutralPercent, 1)}fr`);
    ribbon.style.setProperty("--bad-share", `${Math.max(dissatisfiedPercent, 1)}fr`);
  });
  setText("activePeriod", `${formatDate(state.filters.dateFrom)} — ${formatDate(state.filters.dateTo)}`);
}

function renderOperators() {
  setText("operatorCount", `${state.operators.length} человек`);
  const selected = state.filters.operatorExtension;
  const options = [
    { value: "", label: "Все операторы" },
    ...state.operators.map((operator) => ({
      value: operator.operator_extension,
      label: `${operator.operator_name} · ${operator.operator_extension}`,
    })),
  ];
  if (selected && !state.operators.some((operator) => operator.operator_extension === selected)) {
    options.push({ value: selected, label: `Выбранный оператор · ${selected}` });
  }
  setCustomSelectOptions(nodes.operator, options, selected);
  if (!state.operators.length) {
    nodes.operators.innerHTML = '<div class="empty">Нет данных за выбранный период.</div>';
    return;
  }
  nodes.operators.innerHTML = state.operators
    .map(
      (operator, index) => `
        <button class="operator" type="button" data-operator-extension="${escapeHtml(operator.operator_extension)}">
          <span class="operator-rank">${String(index + 1).padStart(2, "0")}</span>
          <span><strong>${escapeHtml(operator.operator_name)}</strong><small>Внутренний ${escapeHtml(operator.operator_extension)}</small></span>
          <span class="operator-score resolved" title="Доля обращений этого оператора с результатом «Да»">${operator.resolved_percent}%</span>
        </button>`,
    )
    .join("");
  nodes.operators.querySelectorAll("[data-operator-extension]").forEach((button) => {
    button.addEventListener("click", () => {
      setCustomSelectValue(nodes.operator, button.dataset.operatorExtension);
      readFilters();
      state.page = 1;
      refresh({ keepOperators: true });
    });
  });
}

function renderCalls() {
  setText("journalCount", `${state.totalItems} звонков`);
  if (!state.calls.length) {
    nodes.journal.innerHTML = '<tr><td colspan="9"><div class="empty">За выбранный период готовых отчётов нет.</div></td></tr>';
    return;
  }
  nodes.journal.innerHTML = state.calls
    .map(
      (call) => `
        <tr>
          <td>${formatDateTime(call.started_at)}</td>
          <td class="id">${escapeHtml(call.call_id)}</td>
          <td class="person"><strong>${escapeHtml(call.operator_name)}</strong><small>Внутренний ${escapeHtml(call.operator_extension)}</small></td>
          <td class="person"><strong>${escapeHtml(call.caller_name || "Имя не определено")}</strong><small>${escapeHtml(call.caller_id || "Caller ID отсутствует")}</small></td>
          <td>${escapeHtml(call.summary)}</td>
          <td class="id">${formatDuration(call.duration_seconds)}</td>
          <td><span class="pill ${call.satisfaction}">${labels[call.satisfaction] || "Не определено"}</span></td>
          <td><span class="pill resolution ${call.question_resolved}">${labels[call.question_resolved] || "Не определено"}</span></td>
          <td><button class="report-link" type="button" data-call-id="${escapeHtml(call.call_id)}">Открыть →</button></td>
        </tr>`,
    )
    .join("");
}

function renderPagination() {
  const pages = Math.ceil(state.totalItems / state.pageSize);
  nodes.pagination.hidden = pages <= 1;
  if (pages <= 1) return;
  nodes.pagination.innerHTML = `
    <button class="button ghost" type="button" data-page="${state.page - 1}" ${state.page === 1 ? "disabled" : ""}>Назад</button>
    <span>Страница ${state.page} из ${pages}</span>
    <button class="button ghost" type="button" data-page="${state.page + 1}" ${state.page === pages ? "disabled" : ""}>Далее</button>`;
}

function renderSync(sync) {
  const button = document.querySelector("#syncStatus");
  const processing = sync.processing || {};
  const pending = Number(processing.pending || 0);
  const running = Number(processing.running || 0);
  const active = pending + running;
  const processingText = `Готово: ${processing.done || 0}; ожидают: ${pending}; обрабатываются: ${running}; ошибок: ${processing.failed || 0}`;
  if (sync.status === "never") {
    button.textContent = active ? `Очередь: ${active}` : "Синхронизация не запускалась";
    button.title = processingText;
    button.classList.remove("failed");
    return;
  }
  const stamp = sync.finished_at || sync.started_at;
  if (active) {
    button.textContent = `Очередь: ${active}`;
  } else if (sync.status === "running") {
    button.textContent = "Получение звонков";
  } else if (sync.status === "failed") {
    button.textContent = "Синхронизация прервана";
  } else {
    button.textContent = `Обновлено ${formatDateTime(stamp)}`;
  }
  const runText = `Последний запуск: найдено ${sync.discovered}; загружено ${sync.queued}; пропущено ${sync.skipped}; ошибок ${sync.failed}`;
  button.title = `${processingText}. ${runText}`;
  button.classList.toggle("failed", sync.status === "failed");
}

async function openReport(callId) {
  state.selectedCallId = callId;
  nodes.reportContent.innerHTML = '<div class="empty">Загрузка отчёта…</div>';
  nodes.downloadPdf.href = `/api/calls/${encodeURIComponent(callId)}/report.pdf`;
  nodes.dialog.showModal();
  try {
    const report = await requestJson(`/api/calls/${encodeURIComponent(callId)}/report`);
    renderReport(report);
  } catch (error) {
    nodes.reportContent.innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
  }
}

function renderReport(report) {
  const call = report.call || {};
  const caller = report.caller || {};
  const operator = report.operator || {};
  const analysis = report.analysis || {};
  const emotional = analysis.emotional_assessment || {};
  const satisfaction = analysis.client_satisfaction?.value || analysis.satisfaction || "unknown";
  const resolution = analysis.question_resolved?.value || "unknown";
  const transcript = report.transcript?.segments || [];
  document.querySelector("#reportTitle").textContent = `Звонок ${call.id || ""}`;
  nodes.reportContent.innerHTML = `
    <section class="report-meta">
      ${meta("Оператор", `${operator.name || "—"} · ID ${operator.id || "—"} · ${operator.extension || "—"}`)}
      ${meta("Звонящий", `${caller.name || "Имя не определено"} · ${caller.id || "Caller ID отсутствует"}`)}
      ${meta("Дата", formatDateTime(call.started_at))}
      ${meta("Длительность", formatDuration(call.duration_seconds))}
      ${meta("Файл", (call.recording_filenames || []).join(", ") || "—")}
      ${meta("Очередь", `${call.queue?.name || "—"} · ${call.queue?.extension || "—"}`)}
    </section>
    <section class="outcome-grid" aria-label="Результат и эмоциональная оценка">
      ${outcome("Эмоция клиента", labels[satisfaction] || "Не определено", satisfaction)}
      ${outcome("Вопрос решён", labels[resolution] || "Не определено", `resolution ${resolution}`)}
    </section>
    <section class="report-section"><h3>Итог разговора</h3><p>${escapeHtml(analysis.summary || "Нет данных")}</p></section>
    <section class="report-section emotion-section">
      <h3>Эмоциональный окрас</h3>
      <p class="emotion-overall">${escapeHtml(emotional.overall || "Эмоциональный окрас не определён")}</p>
      <div class="emotion-grid">
        ${renderEmotionRole("Клиент", emotional.client_emotions)}
        ${renderEmotionRole("Оператор", emotional.operator_emotions)}
      </div>
    </section>
    <section class="report-section"><h3>Расшифровка</h3><div class="transcript">${transcript.map(renderTranscript).join("") || '<div class="empty">Расшифровка отсутствует.</div>'}</div></section>`;
}

function renderTranscript(segment) {
  const start = Number(segment.start_seconds || 0).toFixed(1);
  return `<article class="utterance"><span class="utterance-time">${start}</span><div><strong>${labels[segment.speaker] || "Роль не определена"}</strong><p>${escapeHtml(segment.text || "")}</p></div></article>`;
}

function renderEmotionRole(title, emotions = []) {
  const values = [...new Set(emotions.map((value) => emotionLabel(value)))];
  const tags = values.length
    ? values.map((value) => `<span class="emotion-tag">${escapeHtml(value)}</span>`).join("")
    : '<span class="emotion-tag muted">Не определён</span>';
  return `<article class="emotion-role"><strong>${title}</strong><div class="emotion-tags">${tags}</div></article>`;
}

function emotionLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return emotionLabels[normalized] || String(value || "Не определён");
}

function meta(label, value) {
  return `<div><span>${label}</span><strong>${escapeHtml(String(value))}</strong></div>`;
}

function outcome(label, value, className) {
  return `<article class="outcome-card"><span>${label}</span><strong class="pill ${className}">${escapeHtml(value)}</strong></article>`;
}

function closeReport() {
  nodes.dialog.close();
  state.selectedCallId = null;
}

function renderLoading() {
  nodes.journal.innerHTML = '<tr><td colspan="9"><div class="empty">Обновление данных…</div></td></tr>';
}

function renderError(message) {
  nodes.journal.innerHTML = `<tr><td colspan="9"><div class="error">${escapeHtml(message)}</div></td></tr>`;
}

async function requestJson(url, signal) {
  const response = await fetch(url, { headers: { Accept: "application/json" }, signal });
  if (!response.ok) {
    const detail = await response.json().then((value) => value.detail).catch(() => response.statusText);
    throw new Error(detail || `HTTP ${response.status}`);
  }
  return await response.json();
}

function showToast(message) {
  nodes.toast.textContent = message;
  nodes.toast.hidden = false;
  window.setTimeout(() => {
    nodes.toast.hidden = true;
  }, 3500);
}

function setText(id, value) {
  document.querySelector(`#${id}`).textContent = String(value);
}

function percent(value, total) {
  return total ? Math.round((Number(value) / Number(total)) * 100) : 0;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(Number(seconds) || 0));
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function formatDate(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU").format(new Date(`${value}T00:00:00`));
}

function formatDateTime(value) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function toDateInput(value) {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

refresh();
