"use strict";
let report, page = 0, selected = null;
let notesById = new Map(), interactionsBound = false, askSequence = 0;
const PAGE_SIZE = 8;
const $ = (id) => document.getElementById(id);
const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = (number) => number === null ? "N/A" : Number(number).toFixed(2);
const change = (number) => number === null ? "N/A" : `${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
const verdict = (row) => row.flagged === "Yes" ? "Unexplained" : row.flagged === "No (justified)" ? "Note-supported" : "Normal";
const badge = (row) => `<span class="badge ${row.flagged === "Yes" ? "review" : row.flagged === "No (justified)" ? "justified" : ""}">${verdict(row)}</span>`;

async function requestJson(url, options = {}, {attempts = 2, timeoutMs = 8000, onRetry = () => {}} = {}) {
  for (let attempt = 1; attempt <= attempts; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {...options, signal: controller.signal});
      if (!response.ok) {
        let detail = "Request failed.";
        try { detail = (await response.json()).error || detail; } catch (_) { /* HTTP error can have a non-JSON body. */ }
        const error = new Error(detail);
        error.retryable = response.status >= 500 || response.status === 429;
        throw error;
      }
      return await response.json();
    } catch (error) {
      const transient = error.name === "AbortError" || error instanceof TypeError || error.retryable;
      if (!transient || attempt === attempts) {
        if (error.name === "AbortError") throw new Error("The request timed out. Please try again.");
        throw error;
      }
      onRetry(attempt, attempts);
      await new Promise((resolve) => setTimeout(resolve, 250 * attempt));
    } finally { clearTimeout(timer); }
  }
}

function hydrateNotes(row) {
  return row.retrieved_notes.map((reference) => ({...notesById.get(reference.note_id), ...reference}));
}

function calendarX(rows, index, left, right) {
  const first = Date.parse(rows[0].week_of), last = Date.parse(rows.at(-1).week_of);
  return left + (Date.parse(rows[index].week_of) - first) / Math.max(last - first, 1) * (right - left);
}

function selectRoute(route) {
  page = 0;
  const rows = report.rows.filter((row) => row.route === route);
  inspect(rows.find((row) => row.week_of === selected?.week_of) || rows.filter((row) => row.candidate).at(-1) || rows.at(-1));
}

function chart() {
  const rows = report.rows.filter((r) => r.route === $("route-select").value);
  $("route-kind").textContent = `${rows[0].route_type} route`;
  $("route-latest").textContent = `Latest: INR ${money(rows.at(-1).cost_per_tonne_km)}`;
  const W = 700, H = 250, left = 43, top = 15, bottom = 216, right = 681;
  const values = rows.flatMap((r) => [r.cost_per_tonne_km, r.history_average]).filter((n) => n !== null);
  const low = Math.floor((Math.min(...values) - .12) * 5) / 5;
  const high = Math.ceil((Math.max(...values) + .12) * 5) / 5;
  const x = (i) => calendarX(rows, i, left, right);
  const y = (v) => bottom - (v - low) / (high - low) * (bottom - top);
  let markup = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Weekly cost and previous eight-week baseline for ${escapeHtml(rows[0].route)}">`;
  for (let i = 0; i < 5; i++) {
    const value = low + (high - low) * i / 4;
    markup += `<line x1="${left}" y1="${y(value)}" x2="${right}" y2="${y(value)}" stroke="#e9ede4"/><text x="${left - 10}" y="${y(value) + 4}" text-anchor="end">${value.toFixed(1)}</text>`;
  }
  const line = (field) => {
    let previous = false;
    return rows.map((r, i) => {
      if (r[field] === null) { previous = false; return ""; }
      const consecutive = i > 0 && Date.parse(r.week_of) - Date.parse(rows[i - 1].week_of) === 7 * 86400000;
      const command = previous && consecutive ? "L" : "M"; previous = true;
      return `${command}${x(i).toFixed(2)},${y(r[field]).toFixed(2)}`;
    }).join(" ");
  };
  markup += `<path d="${line("history_average")}" fill="none" stroke="#9ba79b" stroke-width="1.8" stroke-dasharray="5 4"/>`;
  markup += `<path d="${line("cost_per_tonne_km")}" fill="none" stroke="#ab8b2e" stroke-width="2.3" stroke-linejoin="round"/>`;
  rows.forEach((r, i) => {
    if (!r.candidate) return;
    markup += `<circle class="chart-dot" tabindex="0" role="button" aria-label="${escapeHtml(r.week_of)}, ${verdict(r)}" data-week="${escapeHtml(r.week_of)}" cx="${x(i)}" cy="${y(r.cost_per_tonne_km)}" r="${selected?.week_of === r.week_of && selected?.route === r.route ? 5 : 3.3}" fill="${r.flagged === "Yes" ? "#b9503b" : "#2a7655"}"><title>${escapeHtml(r.week_of)} · ${money(r.cost_per_tonne_km)} · ${verdict(r)}</title></circle>`;
  });
  [0, Math.floor((rows.length - 1) / 3), Math.floor((rows.length - 1) * 2 / 3), rows.length - 1].forEach((i) => {
    markup += `<text x="${x(i)}" y="243" text-anchor="${i === 0 ? "start" : i === rows.length - 1 ? "end" : "middle"}">${escapeHtml(rows[i].week_of.slice(0, 7))}</text>`;
  });
  $("chart").innerHTML = markup + "</svg>";
  document.querySelectorAll(".chart-dot").forEach((dot) => {
    const open = () => {
      const focused = document.activeElement === dot;
      inspect(rows.find((r) => r.week_of === dot.dataset.week));
      if (focused) [...document.querySelectorAll(".chart-dot")].find((item) => item.dataset.week === dot.dataset.week)?.focus();
    };
    dot.addEventListener("click", open);
    dot.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); } });
  });
}

function filteredRows() {
  const value = $("status-filter").value;
  return report.rows.filter((r) => (value === "all" || (value === "candidate" ? r.candidate : r.flagged === value)) && (!$("route-filter").checked || r.route === $("route-select").value)).sort((a, b) => b.week_of.localeCompare(a.week_of) || a.route.localeCompare(b.route));
}

function table() {
  const rows = filteredRows();
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(page, pages - 1);
  $("finding-count").textContent = `${rows.length} observations`;
  const slice = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  $("findings").innerHTML = slice.map((r, i) => `<tr tabindex="0" role="button" aria-label="Inspect ${escapeHtml(r.route)}, ${escapeHtml(r.week_of)}" data-index="${i}" class="${selected?.route === r.route && selected?.week_of === r.week_of ? "active" : ""}"><td><strong>${escapeHtml(r.route)}</strong><small>${escapeHtml(r.week_of)}</small></td><td>${money(r.cost_per_tonne_km)}</td><td class="${r.history_change_percent > 0 ? "up" : ""}">${change(r.history_change_percent)}</td><td>${change(r.peer_change_percent)}</td><td>${badge(r)}</td></tr>`).join("") || '<tr><td colspan="5">No observations match these filters.</td></tr>';
  $("page-label").textContent = `${page + 1} / ${pages}`;
  $("prev-page").disabled = page === 0;
  $("next-page").disabled = page === pages - 1;
  $("findings").querySelectorAll("tr[data-index]").forEach((tr) => {
    const open = () => {
      const focused = document.activeElement === tr;
      inspect(slice[Number(tr.dataset.index)]);
      if (focused) $("findings").querySelector(`tr[data-index="${Number(tr.dataset.index)}"]`)?.focus();
    };
    tr.addEventListener("click", open);
    tr.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); } });
  });
}

function inspect(row) {
  if (!row) return;
  selected = row;
  $("route-select").value = row.route;
  $("detail-route").textContent = row.route;
  $("detail-week").textContent = `Week of ${row.week_of} · ${row.shipment_count} shipments · ${row.route_type}`;
  const retrieved = hydrateNotes(row);
  const note = retrieved.find((n) => n.note_id === row.matched_note_id);
  const rejected = retrieved.filter((n) => !n.eligible && [row.route, "All Routes"].includes(n.applies_to)).slice(0, 4);
  let html = badge(row) + `<div class="detail-stat"><div><small>Weekly cost / tonne-km</small><strong>INR ${money(row.cost_per_tonne_km)}</strong></div><div><small>vs. prior history</small><strong class="${row.history_change_percent > 0 ? "up" : ""}">${change(row.history_change_percent)}</strong></div></div><p class="reason-box">${escapeHtml(row.reason)}</p><p class="evidence-title">${note ? "CITED SOURCE NOTE" : "EVIDENCE CHECK"}</p>`;
  html += note ? `<div class="evidence"><strong>${escapeHtml(note.note_id)} · ${escapeHtml(note.date)}</strong><p>${escapeHtml(note.text)}</p><small>${escapeHtml(note.applies_to)} · ${escapeHtml(note.check)}</small></div>` : `<div class="no-evidence">${row.candidate ? "No eligible note explains this increase. The result stays unexplained." : "No unusual increase was detected. No justification is asserted."}</div>`;
  html += `<details><summary>Why nearby notes were rejected</summary>${rejected.map((n) => `<div class="rejected-note"><strong>${escapeHtml(n.note_id)} · ${escapeHtml(n.date)} · ${escapeHtml(n.applies_to)}</strong><p>${escapeHtml(n.check)}</p></div>`).join("") || "No rejected notes."}</details><p class="baseline-note">History: INR ${money(row.history_average)} from ${escapeHtml(row.history_week_count)} prior weeks.<br>Peers: INR ${money(row.peer_average)} across ${escapeHtml(row.peer_count)} other ${escapeHtml(row.route_type.toLowerCase())} route(s).<br>Weekly cost = sum(freight cost) / sum(tonnes × shipment distance).</p>`;
  if (note?.exposure) html += `<p class="baseline-note">Event exposure: ${(note.exposure.affected_tonne_km_fraction * 100).toFixed(1)}% of weekly tonne-km. Uncovered contribution: ${money(note.exposure.uncovered_rise_percent)} percentage points.</p>`;
  $("detail-content").innerHTML = html;
  chart(); table();
}

async function ask(question) {
  const sequence = ++askSequence;
  $("question").value = question;
  $("answer").textContent = "Reading the findings...";
  const button = $("question-form").querySelector("button");
  button.disabled = true;
  $("answer").setAttribute("aria-busy", "true");
  try {
    const data = await requestJson("/api/question", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({question})}, {onRetry:() => { if (sequence === askSequence) $("answer").textContent = "Connection interrupted. Retrying once..."; }});
    if (sequence !== askSequence) return;
    if (typeof data.answer !== "string" || !Array.isArray(data.findings)) throw new Error("The response was incomplete. Please try again.");
    $("answer").textContent = data.answer;
    if (data.findings.length) inspect(report.rows.find((r) => r.route === data.findings[0].route && r.week_of === data.findings[0].week_of));
  } catch (error) { if (sequence === askSequence) $("answer").textContent = error.message; }
  finally { if (sequence === askSequence) { button.disabled = false; $("answer").setAttribute("aria-busy", "false"); } }
}

async function init() {
  $("date-coverage").textContent = "Loading analysis...";
  $("load-error").hidden = true;
  document.querySelector("main").setAttribute("aria-busy", "true");
  try {
    report = await requestJson("/api/results", {}, {onRetry:() => { $("date-coverage").textContent = "Connection interrupted. Retrying once..."; }});
    if (!report.summary || !Array.isArray(report.rows) || !report.rows.length || !Array.isArray(report.notes)) throw new Error("Saved analysis is empty or invalid. Regenerate it and retry.");
    notesById = new Map(report.notes.map((note) => [note.note_id, note]));
    const s = report.summary;
    $("shipment-count").textContent = s.shipments.toLocaleString();
    $("route-count").textContent = `${s.routes} routes · Short, Medium, Long`;
    $("week-count").textContent = s.route_weeks.toLocaleString();
    $("coverage-weeks").textContent = `${s.weeks} Monday–Sunday weeks`;
    $("review-count").textContent = s.unexplained;
    $("justified-count").textContent = s.justified;
    $("date-coverage").textContent = `${s.date_start} — ${s.date_end}`;
    const log = report.token_cost_log;
    $("engine-mode").textContent = log.accepted_quotes > 0 ? `TF-IDF retrieval · ${s.llm_model} quotes (saved run)` : "TF-IDF retrieval · Deterministic evidence explanations";
    if (log.source_quote_fallbacks) $("engine-mode").textContent += ` · ${log.source_quote_fallbacks} source fallbacks`;
    $("rule-caption").textContent = `Review rule: history rise ≥ ${s.thresholds.history_percent}%, or rise ≥ ${s.thresholds.minimum_rise_percent}% and peer difference ≥ ${s.thresholds.peer_percent}%.`;
    $("route-select").innerHTML = [...new Set(report.rows.map((r) => r.route))].sort().map((r) => `<option>${escapeHtml(r)}</option>`).join("");
    if (!interactionsBound) {
    interactionsBound = true;
    $("route-select").addEventListener("change", () => selectRoute($("route-select").value));
    $("status-filter").addEventListener("change", () => { page = 0; table(); });
    $("route-filter").addEventListener("change", () => { page = 0; table(); });
    $("prev-page").addEventListener("click", () => { page--; table(); });
    $("next-page").addEventListener("click", () => { page++; table(); });
    $("question-form").addEventListener("submit", (event) => { event.preventDefault(); if ($("question").value.trim()) ask($("question").value); });
    document.querySelectorAll("[data-question]").forEach((button) => button.addEventListener("click", () => ask(button.dataset.question)));
    }
    inspect(report.rows.find((r) => r.route === "Chennai-Bangalore" && r.week_of === "2025-03-10") || report.rows[0]);
  } catch (error) { $("load-error").hidden = false; $("load-message").textContent = error.message; $("date-coverage").textContent = "Analysis unavailable"; }
  finally { document.querySelector("main").setAttribute("aria-busy", "false"); }
}
if (typeof document !== "undefined") {
  $("retry-load").addEventListener("click", init);
  init();
}
