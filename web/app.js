/* ==========================================================================
   TELEGRAM BOT SENTINEL — App Logic v2.1
   ========================================================================== */

let timelineChart = null;
let distributionChart = null;
let signalsChart = null;

let currentAnalyses = [];
let selectedAnalyse = null;
let ws = null;

// Pagination
let currentPage = 1;
const PAGE_SIZE = 20;
let allAnalysesCache = [];
let filteredAnalyses = [];

// ============================================================
// INIT
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  initCharts();
  initNavigation();
  initSidebar();
  loadDashboard();
  setupWebSocket();

  document.getElementById("btn-refresh").addEventListener("click", () => {
    refreshCurrentPage();
    showToast("Données actualisées");
  });
});

// ============================================================
// NAVIGATION (SPA)
// ============================================================
function initNavigation() {
  document.querySelectorAll(".nav-item[data-page]").forEach(link => {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      navigateTo(link.dataset.page);
    });
  });
}

function navigateTo(page) {
  // Update nav items
  document.querySelectorAll(".nav-item").forEach(n => n.classList.remove("active"));
  const activeLink = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (activeLink) activeLink.classList.add("active");

  // Show/hide pages
  document.querySelectorAll(".page").forEach(p => p.classList.add("hidden"));
  const targetPage = document.getElementById(`page-${page}`);
  if (targetPage) targetPage.classList.remove("hidden");

  // Update topbar title
  const titles = {
    dashboard: "Dashboard",
    analyses: "Analyses",
    surveillances: "Surveillances",
    parametres: "Paramètres",
  };
  document.getElementById("topbar-title").textContent = titles[page] || page;

  // Load data for page
  switch (page) {
    case "dashboard":    loadDashboard(); break;
    case "analyses":     loadAllAnalyses(); break;
    case "surveillances":loadSurveillances(); break;
    case "parametres":   loadParametres(); break;
  }
}

function refreshCurrentPage() {
  const active = document.querySelector(".nav-item.active");
  if (active) navigateTo(active.dataset.page);
}

// ============================================================
// SIDEBAR TOGGLE
// ============================================================
function initSidebar() {
  document.getElementById("btn-toggle-sidebar").addEventListener("click", () => {
    const sidebar = document.getElementById("sidebar");
    const main = document.querySelector(".main-wrapper");
    sidebar.classList.toggle("collapsed");
    main.classList.toggle("expanded");
  });
}

// ============================================================
// CHARTS INITIALIZATION
// ============================================================
function initCharts() {
  const tooltip = {
    backgroundColor: "rgba(9,12,18,.95)",
    titleColor: "#38bdf8",
    bodyColor: "#f1f5f9",
    borderColor: "rgba(56,189,248,.25)",
    borderWidth: 1,
    padding: 10,
    cornerRadius: 8,
  };

  // 1. Timeline
  timelineChart = new Chart(
    document.getElementById("timelineChart").getContext("2d"),
    {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Automatisation (%)",
            data: [],
            borderColor: "#38bdf8",
            backgroundColor: "rgba(56,189,248,.12)",
            borderWidth: 2,
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: "#38bdf8",
          },
          {
            label: "Dangerosité (%)",
            data: [],
            borderColor: "#ef4444",
            backgroundColor: "rgba(239,68,68,.08)",
            borderWidth: 2,
            borderDash: [5, 4],
            tension: 0.35,
            fill: true,
            pointRadius: 3,
            pointBackgroundColor: "#ef4444",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: "#94a3b8", font: { family: "Inter", size: 11 } } }, tooltip },
        scales: {
          x: { grid: { color: "rgba(255,255,255,.04)" }, ticks: { color: "#4b5a72", font: { family: "JetBrains Mono", size: 9 }, maxRotation: 30 } },
          y: { min: 0, max: 100, grid: { color: "rgba(255,255,255,.04)" }, ticks: { color: "#4b5a72" } },
        },
      },
    }
  );

  // 2. Distribution Donut
  distributionChart = new Chart(
    document.getElementById("distributionChart").getContext("2d"),
    {
      type: "doughnut",
      data: {
        labels: ["Bots ≥60%", "Suspects 30-59%", "Humains <30%"],
        datasets: [{
          data: [0, 0, 0],
          backgroundColor: ["#ef4444", "#f59e0b", "#10b981"],
          borderColor: "#090c12",
          borderWidth: 3,
          hoverOffset: 5,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: { position: "bottom", labels: { color: "#94a3b8", font: { family: "Inter", size: 11 }, padding: 12 } },
          tooltip,
        },
      },
    }
  );

  // 3. Signals Bar
  signalsChart = new Chart(
    document.getElementById("signalsChart").getContext("2d"),
    {
      type: "bar",
      data: {
        labels: [],
        datasets: [{
          label: "Occurrences",
          data: [],
          backgroundColor: "rgba(168,85,247,.38)",
          borderColor: "#a855f7",
          borderWidth: 1.5,
          borderRadius: 5,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        indexAxis: "y",
        plugins: { legend: { display: false }, tooltip },
        scales: {
          x: { grid: { color: "rgba(255,255,255,.04)" }, ticks: { color: "#4b5a72", precision: 0 } },
          y: { grid: { display: false }, ticks: { color: "#94a3b8", font: { size: 9 } } },
        },
      },
    }
  );
}

// ============================================================
// PAGE : DASHBOARD
// ============================================================
async function loadDashboard() {
  try {
    const [statsRes, analysesRes] = await Promise.all([
      fetch("/api/stats"),
      fetch("/api/analyses?limit=30"),
    ]);
    if (!statsRes.ok || !analysesRes.ok) return;

    const stats    = await statsRes.json();
    const analyses = await analysesRes.json();

    // KPIs
    animateCount("kpi-total",   stats.total_analyses);
    animateCount("kpi-bots",    stats.total_bots);
    animateCount("kpi-suspects",stats.total_suspects);
    animateCount("kpi-humans",  stats.total_humains);
    animateCount("kpi-dangers", stats.total_dangers);
    animateCount("kpi-surv",    stats.total_surveilles);

    // Nav badges
    document.getElementById("nav-badge-analyses").textContent = stats.total_analyses;
    document.getElementById("nav-badge-surv").textContent     = stats.total_surveilles;

    // Charts
    const labels = stats.timeline.map(t => t.nom);
    timelineChart.data.labels = labels;
    timelineChart.data.datasets[0].data = stats.timeline.map(t => t.auto);
    timelineChart.data.datasets[1].data = stats.timeline.map(t => t.danger);
    timelineChart.update();

    distributionChart.data.datasets[0].data = [stats.total_bots, stats.total_suspects, stats.total_humains];
    distributionChart.update();

    signalsChart.data.labels = stats.top_signaux.map(s => s.signal);
    signalsChart.data.datasets[0].data = stats.top_signaux.map(s => s.count);
    signalsChart.update();

    // Mini-table
    renderMiniTable(analyses);

    if (analyses.length > 0 && !selectedAnalyse) {
      renderInspector(analyses[0]);
    }

  } catch (err) {
    console.error("Dashboard load error:", err);
  }
}

function renderMiniTable(analyses) {
  const tbody = document.getElementById("analyses-table-body");
  document.getElementById("table-count").textContent = `${analyses.length} entrées`;

  if (!analyses.length) {
    tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;padding:2rem;color:var(--text-dim);">Aucune analyse enregistrée.</td></tr>`;
    return;
  }

  tbody.innerHTML = analyses.map(a => {
    const cls  = a.score_automatisation >= 60 ? "score-bot" : a.score_automatisation >= 30 ? "score-suspect" : "score-human";
    const icon = a.score_automatisation >= 60 ? "🤖" : a.score_automatisation >= 30 ? "⚠️" : "👤";
    const nom  = a.first_name || a.username || "Inconnu";
    const hdl  = a.username ? `@${a.username}` : "—";
    const ini  = (a.first_name || a.username || "?")[0].toUpperCase();
    const dateStr = a.date_analyse ? new Date(a.date_analyse).toLocaleTimeString([], { hour:"2-digit", minute:"2-digit" }) : "—";
    const retour = a.retour_verdict
      ? `<span style="font-weight:700;color:${a.retour_verdict === "bot" ? "#f87171" : "#34d399"}">${a.retour_verdict.toUpperCase()}</span>`
      : `<span style="color:var(--text-dim);font-size:.72rem;">—</span>`;

    return `<tr class="row-item${selectedAnalyse?.id === a.id ? " selected" : ""}" onclick="onSelectRow(${a.id})">
      <td>
        <div class="user-cell">
          <div class="user-avatar-mini">${ini}</div>
          <div><div class="user-meta-name">${escHtml(nom)}</div><div class="user-meta-handle">${escHtml(hdl)}</div></div>
        </div>
      </td>
      <td><span class="score-pill ${cls}">${icon} ${a.score_automatisation}%</span></td>
      <td style="font-family:var(--font-mono);font-weight:600;color:${a.score_danger > 0 ? "#ef4444" : "var(--text-dim)"};">${a.score_danger}%</td>
      <td style="color:var(--text-muted);font-size:.78rem;">${dateStr}</td>
      <td>${retour}</td>
    </tr>`;
  }).join("");
}

function onSelectRow(id) {
  const item = currentAnalyses.find(a => a.id === id) ||
               allAnalysesCache.find(a => a.id === id);
  if (item) renderInspector(item);
}

// ============================================================
// INSPECTOR
// ============================================================
function renderInspector(item) {
  selectedAnalyse = item;
  document.getElementById("inspector-badge").textContent = `ID #${item.id}`;

  const isBot     = item.score_automatisation >= 60;
  const isSuspect = item.score_automatisation >= 30;
  const color     = isBot ? "var(--status-bot)" : isSuspect ? "var(--status-suspect)" : "var(--status-human)";
  const nom       = item.first_name || item.username || "Sans Nom";
  const handle    = item.username ? `@${item.username}` : "Aucun identifiant";
  const ini       = (nom[0] || "?").toUpperCase();

  const autoTags = (item.signaux_automatisation || []).map(s =>
    `<div class="signal-tag">${escHtml(s)}</div>`).join("") || `<span style="color:var(--text-dim);font-size:.78rem;">Aucun signal détecté</span>`;

  const dangerTags = (item.signaux_danger || []).map(s =>
    `<div class="signal-tag danger">${escHtml(s)}</div>`).join("");

  document.getElementById("inspector-container").innerHTML = `
    <div class="detail-content">
      <div style="display:flex;align-items:center;gap:.85rem;padding-bottom:.9rem;border-bottom:1px solid rgba(255,255,255,.05);">
        <div class="user-avatar-mini" style="width:46px;height:46px;border-radius:12px;font-size:1.1rem;">${ini}</div>
        <div>
          <div style="font-size:1rem;font-weight:700;color:#fff;">${escHtml(nom)}</div>
          <div style="color:var(--accent-cyan);font-family:var(--font-mono);font-size:.8rem;">${escHtml(handle)}</div>
          <div style="color:var(--text-dim);font-size:.72rem;">ID : ${item.chat_id}</div>
        </div>
      </div>

      <div style="display:flex;gap:.75rem;">
        <div style="flex:1;background:rgba(255,255,255,.03);padding:.75rem;border-radius:8px;border:1px solid var(--border-subtle);">
          <div style="font-size:.65rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:.3rem;">Automatisation</div>
          <div style="font-size:1.5rem;font-weight:800;color:${color};font-family:var(--font-mono);">${item.score_automatisation}%</div>
        </div>
        <div style="flex:1;background:rgba(255,255,255,.03);padding:.75rem;border-radius:8px;border:1px solid var(--border-subtle);">
          <div style="font-size:.65rem;color:var(--text-muted);text-transform:uppercase;margin-bottom:.3rem;">Dangerosité</div>
          <div style="font-size:1.5rem;font-weight:800;color:${item.score_danger > 0 ? "#ef4444" : "var(--text-dim)"};font-family:var(--font-mono);">${item.score_danger}%</div>
        </div>
      </div>

      <div>
        <div style="font-size:.72rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;margin-bottom:.5rem;">Signaux profil</div>
        <div class="signals-list">${autoTags}</div>
      </div>

      ${dangerTags ? `
      <div>
        <div style="font-size:.72rem;font-weight:700;color:#ef4444;text-transform:uppercase;margin-bottom:.5rem;">Signaux de danger</div>
        <div class="signals-list">${dangerTags}</div>
      </div>` : ""}

      <div class="detail-verdict-actions">
        <button class="btn-action btn-bot" onclick="submitVerdict(${item.id},'bot')">🤖 Bot</button>
        <button class="btn-action btn-humain" onclick="submitVerdict(${item.id},'humain')">👤 Humain</button>
      </div>
    </div>
  `;
}

// ============================================================
// PAGE : ANALYSES (toutes)
// ============================================================
async function loadAllAnalyses() {
  try {
    const res = await fetch("/api/analyses?limit=500");
    if (!res.ok) return;
    allAnalysesCache = await res.json();
    filteredAnalyses = [...allAnalysesCache];
    currentPage = 1;
    renderAllAnalysesTable();

    document.getElementById("analyses-count-badge").textContent = `${allAnalysesCache.length} au total`;
  } catch (err) {
    console.error("loadAllAnalyses error:", err);
  }
}

function renderAllAnalysesTable() {
  const tbody = document.getElementById("all-analyses-body");
  const start = (currentPage - 1) * PAGE_SIZE;
  const slice = filteredAnalyses.slice(start, start + PAGE_SIZE);

  document.getElementById("page-info").textContent = `Page ${currentPage} / ${Math.max(1, Math.ceil(filteredAnalyses.length / PAGE_SIZE))}`;
  document.getElementById("btn-prev").disabled = currentPage <= 1;
  document.getElementById("btn-next").disabled = start + PAGE_SIZE >= filteredAnalyses.length;

  if (!slice.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;padding:2rem;color:var(--text-dim);">Aucune analyse trouvée.</td></tr>`;
    return;
  }

  tbody.innerHTML = slice.map(a => {
    const cls  = a.score_automatisation >= 60 ? "score-bot" : a.score_automatisation >= 30 ? "score-suspect" : "score-human";
    const icon = a.score_automatisation >= 60 ? "🤖" : a.score_automatisation >= 30 ? "⚠️" : "👤";
    const nom  = a.first_name || a.username || "Inconnu";
    const hdl  = a.username ? `@${a.username}` : "—";
    const ini  = (a.first_name || a.username || "?")[0].toUpperCase();
    const date = a.date_analyse ? new Date(a.date_analyse).toLocaleString("fr-FR", { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" }) : "—";
    const retour = a.retour_verdict
      ? `<span style="font-weight:700;color:${a.retour_verdict === "bot" ? "#f87171" : "#34d399"}">${a.retour_verdict.toUpperCase()}</span>`
      : `<span style="color:var(--text-dim);">—</span>`;

    return `<tr class="row-item" onclick="showInspectorFromAll(${a.id})">
      <td style="color:var(--text-dim);font-family:var(--font-mono);font-size:.75rem;">#${a.id}</td>
      <td>
        <div class="user-cell">
          <div class="user-avatar-mini">${ini}</div>
          <div><div class="user-meta-name">${escHtml(nom)}</div><div class="user-meta-handle">${escHtml(hdl)}</div></div>
        </div>
      </td>
      <td style="font-family:var(--font-mono);color:var(--text-dim);font-size:.75rem;">${a.chat_id}</td>
      <td><span class="score-pill ${cls}">${icon} ${a.score_automatisation}%</span></td>
      <td style="font-family:var(--font-mono);font-weight:600;color:${a.score_danger > 0 ? "#ef4444" : "var(--text-dim)"};">${a.score_danger}%</td>
      <td style="color:var(--text-muted);font-size:.78rem;">${date}</td>
      <td>${retour}</td>
      <td>
        <button class="btn-page" style="padding:.25rem .6rem;font-size:.72rem;" onclick="event.stopPropagation();deleteAnalyse(${a.id})">🗑</button>
      </td>
    </tr>`;
  }).join("");
}

function showInspectorFromAll(id) {
  const item = allAnalysesCache.find(a => a.id === id);
  if (item) {
    navigateTo("dashboard");
    renderInspector(item);
  }
}

// Search
document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("search-analyses")?.addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    filteredAnalyses = allAnalysesCache.filter(a =>
      (a.username || "").toLowerCase().includes(q) ||
      (a.first_name || "").toLowerCase().includes(q) ||
      String(a.chat_id).includes(q)
    );
    currentPage = 1;
    renderAllAnalysesTable();
  });

  document.getElementById("btn-prev")?.addEventListener("click", () => { currentPage--; renderAllAnalysesTable(); });
  document.getElementById("btn-next")?.addEventListener("click", () => { currentPage++; renderAllAnalysesTable(); });
});

async function deleteAnalyse(id) {
  openModal(
    "Supprimer cette analyse",
    "Cette action est irréversible. Les données seront définitivement supprimées.",
    async () => {
      const res = await fetch(`/api/analyses/${id}`, { method: "DELETE" });
      if (res.ok) {
        showToast("Analyse supprimée");
        loadAllAnalyses();
      }
    }
  );
}

// ============================================================
// PAGE : SURVEILLANCES
// ============================================================
async function loadSurveillances() {
  try {
    const res = await fetch("/api/surveillances");
    if (!res.ok) return;
    const data = await res.json();

    document.getElementById("surv-count-badge").textContent = `${data.length} actif(s)`;
    document.getElementById("nav-badge-surv").textContent = data.length;

    const tbody = document.getElementById("surv-table-body");
    const empty = document.getElementById("surv-empty");

    if (!data.length) {
      tbody.innerHTML = "";
      empty.classList.remove("hidden");
      return;
    }

    empty.classList.add("hidden");
    tbody.innerHTML = data.map(s => {
      const ini  = (s.pseudo || "?")[0].toUpperCase();
      const date = s.date_debut ? new Date(s.date_debut).toLocaleString("fr-FR", { day:"2-digit", month:"2-digit", hour:"2-digit", minute:"2-digit" }) : "—";
      return `<tr class="row-item">
        <td style="color:var(--text-dim);font-family:var(--font-mono);font-size:.75rem;">#${s.id}</td>
        <td>
          <div class="user-cell">
            <div class="user-avatar-mini">${ini}</div>
            <div><div class="user-meta-name">${escHtml(s.pseudo || "Inconnu")}</div></div>
          </div>
        </td>
        <td style="font-family:var(--font-mono);color:var(--text-dim);font-size:.75rem;">${s.chat_id}</td>
        <td style="color:var(--text-muted);font-size:.78rem;">${date}</td>
      </tr>`;
    }).join("");

  } catch (err) {
    console.error("loadSurveillances error:", err);
  }
}

// ============================================================
// PAGE : PARAMÈTRES
// ============================================================
const SCORING_KEYS = ["seuil_bot", "seuil_suspect", "version_regles"];
const TOGGLE_KEYS  = ["cas_active"];

async function loadParametres() {
  try {
    const res = await fetch("/api/parametres");
    if (!res.ok) return;
    const params = await res.json();

    renderParamsGroup("params-scoring", params, SCORING_KEYS, false);
    renderParamsGroup("params-system",  params, TOGGLE_KEYS,  true);

  } catch (err) {
    console.error("loadParametres error:", err);
  }
}

function renderParamsGroup(containerId, params, keys, asToggle) {
  const el = document.getElementById(containerId);
  if (!el) return;

  const filtered = params.filter(p => keys.includes(p.cle));

  el.innerHTML = filtered.map(p => {
    if (asToggle) {
      const checked = p.valeur === "1" ? "checked" : "";
      return `<div class="param-row">
        <div class="param-info">
          <div class="param-key">${escHtml(p.cle)}</div>
          <div class="param-desc">${escHtml(p.description || "")}</div>
        </div>
        <label class="param-toggle">
          <input type="checkbox" ${checked} onchange="saveParam('${escHtml(p.cle)}', this.checked ? '1' : '0')">
          <span class="param-toggle-slider"></span>
        </label>
      </div>`;
    } else {
      return `<div class="param-row">
        <div class="param-info">
          <div class="param-key">${escHtml(p.cle)}</div>
          <div class="param-desc">${escHtml(p.description || "")}</div>
        </div>
        <div style="display:flex;align-items:center;gap:.5rem;">
          <input class="param-input" type="number" value="${escHtml(p.valeur)}" id="inp-${escHtml(p.cle)}" min="0" max="100">
          <button class="param-save-btn" onclick="saveParamInput('${escHtml(p.cle)}')">Sauver</button>
        </div>
      </div>`;
    }
  }).join("");

  // Bind danger zone buttons once (avoid duplicates)
  const exportBtn = document.getElementById("btn-export-csv");
  const clearBtn  = document.getElementById("btn-clear-data");

  if (exportBtn && !exportBtn._bound) {
    exportBtn._bound = true;
    exportBtn.addEventListener("click", exportCSV);
  }
  if (clearBtn && !clearBtn._bound) {
    clearBtn._bound = true;
    clearBtn.addEventListener("click", () => {
      openModal(
        "Purger toutes les analyses",
        "Cette action supprimera TOUTES les analyses enregistrées. Cette opération est irréversible.",
        purgeAllAnalyses
      );
    });
  }
}

async function saveParam(cle, valeur) {
  try {
    const res = await fetch(`/api/parametres/${encodeURIComponent(cle)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ valeur }),
    });
    if (res.ok) showToast(`Paramètre "${cle}" mis à jour`);
    else showToast("Erreur lors de la mise à jour", true);
  } catch (err) {
    showToast("Erreur réseau", true);
  }
}

async function saveParamInput(cle) {
  const inp = document.getElementById(`inp-${cle}`);
  if (!inp) return;
  await saveParam(cle, inp.value);
}

async function purgeAllAnalyses() {
  try {
    // Récupérer tous les IDs et les supprimer un par un
    const res = await fetch("/api/analyses?limit=5000");
    if (!res.ok) return;
    const all = await res.json();
    await Promise.all(all.map(a => fetch(`/api/analyses/${a.id}`, { method: "DELETE" })));
    showToast(`${all.length} analyses supprimées`);
    loadAllAnalyses();
  } catch (err) {
    showToast("Erreur lors de la purge", true);
  }
}

function exportCSV() {
  if (!allAnalysesCache.length) {
    showToast("Aucune donnée à exporter", true);
    return;
  }
  const header = ["id", "chat_id", "username", "first_name", "last_name", "score_automatisation", "score_danger", "date_analyse", "retour_verdict"];
  const rows = allAnalysesCache.map(a =>
    header.map(k => JSON.stringify(a[k] ?? "")).join(",")
  );
  const csv = [header.join(","), ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `analyses_${new Date().toISOString().slice(0,10)}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  showToast("Export CSV téléchargé");
}

// ============================================================
// FEEDBACK
// ============================================================
async function submitVerdict(analyseId, verdict) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ analyse_id: analyseId, verdict }),
    });
    if (res.ok) {
      showToast(`Verdict enregistré : ${verdict.toUpperCase()}`);
      loadDashboard();
    } else {
      showToast("Erreur d'enregistrement", true);
    }
  } catch (err) {
    showToast("Erreur réseau", true);
  }
}

// ============================================================
// WEBSOCKET
// ============================================================
function setupWebSocket() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  ws = new WebSocket(`${proto}//${location.host}/ws`);

  ws.onopen = () => {
    document.getElementById("live-indicator").style.borderColor = "rgba(16,185,129,.4)";
    document.getElementById("live-text").textContent = "EN DIRECT";
    setInterval(() => ws.readyState === WebSocket.OPEN && ws.send("ping"), 25000);
  };

  ws.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "new_analysis") {
        showToast(`⚡ Nouvelle analyse : ${msg.data.username || "#" + msg.data.chat_id} (${msg.data.score_automatisation}%)`);
        const active = document.querySelector(".nav-item.active")?.dataset.page;
        if (active === "dashboard") loadDashboard();
        if (active === "analyses")  loadAllAnalyses();
      } else if (msg.type === "feedback_added") {
        loadDashboard();
      }
    } catch (_) {}
  };

  ws.onclose = () => {
    document.getElementById("live-indicator").style.borderColor = "rgba(239,68,68,.4)";
    document.getElementById("live-text").textContent = "RECONNEXION...";
    setTimeout(setupWebSocket, 3500);
  };
}

// ============================================================
// MODAL
// ============================================================
let pendingConfirmCb = null;

function openModal(title, body, onConfirm) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").textContent  = body;
  pendingConfirmCb = onConfirm;
  document.getElementById("modal-overlay").classList.remove("hidden");
  feather.replace();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("modal-cancel").addEventListener("click", () => {
    document.getElementById("modal-overlay").classList.add("hidden");
    pendingConfirmCb = null;
  });
  document.getElementById("modal-confirm").addEventListener("click", async () => {
    document.getElementById("modal-overlay").classList.add("hidden");
    if (pendingConfirmCb) await pendingConfirmCb();
    pendingConfirmCb = null;
  });
});

// ============================================================
// TOAST
// ============================================================
function showToast(text, isError = false) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast";
  if (isError) toast.style.borderColor = "#ef4444";

  const iconName = isError ? "alert-circle" : "bell";
  const iconColor = isError ? "#ef4444" : "var(--accent-cyan)";
  toast.innerHTML = `<i data-feather="${iconName}" style="color:${iconColor};"></i><span>${escHtml(text)}</span>`;
  container.appendChild(toast);
  feather.replace();

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(50px)";
    toast.style.transition = "all .28s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ============================================================
// HELPERS
// ============================================================
function escHtml(str) {
  if (!str && str !== 0) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function animateCount(id, target) {
  const el = document.getElementById(id);
  if (!el) return;
  const start = parseInt(el.textContent) || 0;
  if (start === target) return;
  const step = Math.ceil(Math.abs(target - start) / 20);
  let cur = start;
  const timer = setInterval(() => {
    cur += cur < target ? step : -step;
    if ((step > 0 && cur >= target) || (step < 0 && cur <= target)) { cur = target; clearInterval(timer); }
    el.textContent = cur;
  }, 25);
}
