/**
 * DeadlinePilot - Frontend Reactive Controller
 * Handles Todo task interactions, 4-hour countdown, on-demand rescan,
 * search filtering, and optimistic completion animations.
 */

// Application state
let state = {
  activeItems: [],
  completedItems: [],
  stats: {},
  config: {},
  status: {},
  currentFilter: "all",
  searchQuery: "",
  nextAutoScanTime: null,
  isCompletedDrawerOpen: false
};

// Initialize on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  fetchDeadlines();
  startCountdownTimer();
  // Poll background status every 30 seconds
  setInterval(fetchDeadlinesSilently, 30000);
});

/**
 * Loads deadlines and server state from REST API
 */
async function fetchDeadlines() {
  try {
    const res = await fetch("/api/deadlines");
    if (!res.ok) throw new Error("Failed to load deadlines");
    const data = await res.json();

    state.activeItems = data.active_items || [];
    state.completedItems = data.completed_items || [];
    state.stats = data.stats || {};
    state.config = data.config || {};
    state.status = data.status || {};

    if (data.status && data.status.next_auto_scan_at) {
      state.nextAutoScanTime = new Date(data.status.next_auto_scan_at);
    }

    updateHeaderUI();
    updateMetricsUI();
    renderTasks();
  } catch (err) {
    console.error("Error loading deadlines:", err);
    showToast("Could not connect to server. Retrying...", "error");
  }
}

async function fetchDeadlinesSilently() {
  try {
    const res = await fetch("/api/deadlines");
    if (!res.ok) return;
    const data = await res.json();
    state.activeItems = data.active_items || [];
    state.completedItems = data.completed_items || [];
    state.stats = data.stats || {};
    if (data.status && data.status.next_auto_scan_at) {
      state.nextAutoScanTime = new Date(data.status.next_auto_scan_at);
    }
    updateMetricsUI();
    renderTasks();
  } catch (e) {
    // silent fallback
  }
}

/**
 * Updates header badges (Email, Auto-sync info)
 */
function updateHeaderUI() {
  const emailEl = document.getElementById("userEmail");
  if (emailEl && state.config.email_address) {
    emailEl.textContent = state.config.email_address;
    emailEl.title = `Connected via IMAP (Model: ${state.config.model})`;
  }
}

/**
 * Updates metrics overview grid & tab counts
 */
function updateMetricsUI() {
  const s = state.stats;
  document.getElementById("statActive").textContent = s.total_active || 0;
  document.getElementById("statApproaching").textContent = s.approaching_1h || 0;
  document.getElementById("statUrgent").textContent = s.urgent || 0;
  document.getElementById("statCompleted").textContent = s.completed || 0;

  // Highlight approaching card if any < 1 hour
  const appCard = document.getElementById("approachingCard");
  if (appCard) {
    if (s.approaching_1h > 0) {
      appCard.classList.add("is-approaching");
    } else {
      appCard.classList.remove("is-approaching");
    }
  }

  // Update tab counters
  document.getElementById("tabCountAll").textContent = state.activeItems.length;
  document.getElementById("tabCountUrgent").textContent = state.activeItems.filter(i => i.urgency === "Urgent").length;
  document.getElementById("tabCountUpcoming").textContent = state.activeItems.filter(i => i.urgency === "Upcoming").length;
  document.getElementById("tabCountLater").textContent = state.activeItems.filter(i => i.urgency === "Later").length;
  document.getElementById("tabCountCompleted").textContent = state.completedItems.length;
  document.getElementById("drawerCount").textContent = state.completedItems.length;
}

/**
 * Renders the Todo list cards according to active filters & search query
 */
function renderTasks() {
  const listEl = document.getElementById("taskList");
  const drawerEl = document.getElementById("completedDrawer");
  const query = state.searchQuery.toLowerCase().trim();

  // If filter is explicitly 'completed', render completed view
  if (state.currentFilter === "completed") {
    document.getElementById("boardTitle").textContent = "Archived Completed Tasks";
    document.getElementById("boardHint").textContent = "Completed tasks remain archived here";
    drawerEl.style.display = "none";

    let filteredCompleted = state.completedItems;
    if (query) {
      filteredCompleted = filteredCompleted.filter(it => 
        it.event_name.toLowerCase().includes(query) ||
        (it.source_sender && it.source_sender.toLowerCase().includes(query)) ||
        (it.summary && it.summary.toLowerCase().includes(query))
      );
    }

    if (filteredCompleted.length === 0) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📭</div>
          <div class="empty-title">No completed tasks yet</div>
          <div class="empty-desc">When you check off deadlines from the active list, they will appear here.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = filteredCompleted.map(item => `
      <div class="completed-item">
        <div>
          <span class="completed-item-title">~~${escapeHtml(item.event_name)}~~</span>
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 3px;">
            Deadline: ${escapeHtml(item.deadline_text)} &bull; Completed: ${item.completed_at || 'Recently'}
          </div>
        </div>
        <button class="undo-btn" onclick="restoreTask('${item.id}')">↩ Restore to Active</button>
      </div>
    `).join("");
    return;
  }

  // Active tasks view
  document.getElementById("boardTitle").textContent = "Active Action Items";
  document.getElementById("boardHint").textContent = "Click circle checkbox to complete a task";

  let items = state.activeItems;

  // Filter by tab
  if (state.currentFilter === "urgent") {
    items = items.filter(it => it.urgency === "Urgent");
  } else if (state.currentFilter === "upcoming") {
    items = items.filter(it => it.urgency === "Upcoming");
  } else if (state.currentFilter === "later") {
    items = items.filter(it => it.urgency === "Later");
  }

  // Filter by search query
  if (query) {
    items = items.filter(it => 
      it.event_name.toLowerCase().includes(query) ||
      (it.source_sender && it.source_sender.toLowerCase().includes(query)) ||
      (it.summary && it.summary.toLowerCase().includes(query)) ||
      (it.deadline_text && it.deadline_text.toLowerCase().includes(query))
    );
  }

  if (items.length === 0) {
    listEl.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎉</div>
        <div class="empty-title">${query ? 'No matching deadlines found' : 'All caught up!'}</div>
        <div class="empty-desc">
          ${query ? 'Try adjusting your search terms.' : 'No active deadlines pending. Click "Rescan Inbox Now" to fetch latest updates.'}
        </div>
      </div>
    `;
  } else {
    listEl.innerHTML = items.map(item => createTaskCardHtml(item)).join("");
  }

  // Render completed accordion drawer if completed items exist
  if (state.completedItems.length > 0) {
    drawerEl.style.display = "block";
    renderCompletedDrawer();
  } else {
    drawerEl.style.display = "none";
  }
}

/**
 * Creates HTML template for a single interactive Todo Card
 */
function createTaskCardHtml(item) {
  const is1Hour = item.days_remaining !== null && (item.days_remaining * 24 <= 1.0 && item.days_remaining >= 0);
  
  // Format urgency badge
  let badgeClass = "badge-later";
  let badgeText = "Later";
  if (item.urgency === "Urgent") {
    badgeClass = "badge-urgent";
    badgeText = "🔴 Urgent";
  } else if (item.urgency === "Upcoming") {
    badgeClass = "badge-upcoming";
    badgeText = "🟡 Upcoming";
  }

  // Format time remaining
  let timeStr = "N/A";
  if (item.days_remaining !== null) {
    if (item.days_remaining < 0) {
      timeStr = `${Math.abs(item.days_remaining).toFixed(1)}d ago (Expired)`;
    } else if (item.days_remaining * 24 <= 1.0) {
      const mins = Math.max(1, Math.round(item.days_remaining * 1440));
      timeStr = `⏰ ${mins} mins left!`;
    } else if (item.days_remaining <= 2) {
      timeStr = `${item.days_remaining.toFixed(1)}d left`;
    } else {
      timeStr = `${item.days_remaining.toFixed(1)} days left`;
    }
  }

  return `
    <article class="task-card ${is1Hour ? 'is-approaching' : ''}" id="task-${item.id}">
      <button class="check-btn" onclick="completeTask('${item.id}', this)" title="Mark as Completed">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
          <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
      </button>

      <div class="task-content">
        <div class="task-header">
          <h3 class="task-title">${escapeHtml(item.event_name)}</h3>
          <div class="badge-group">
            ${is1Hour ? '<span class="urgency-badge badge-alert">🚨 &lt; 1 HOUR!</span>' : ''}
            <span class="urgency-badge ${badgeClass}">${badgeText}</span>
            <span class="time-pill">${timeStr}</span>
          </div>
        </div>

        ${item.summary ? `<p class="task-summary">${escapeHtml(item.summary)}</p>` : ''}

        <div class="task-meta">
          <span class="meta-item" title="Exact deadline from email">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg>
            <strong>Due:</strong> ${escapeHtml(item.deadline_text)}
          </span>
          ${item.source_sender ? `
            <span class="meta-item" title="Sender">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
              ${escapeHtml(item.source_sender)}
            </span>
          ` : ''}
          <span class="meta-item" style="color: var(--text-dim); font-family: var(--font-mono);">
            ID: ${item.id}
          </span>
        </div>

        <div class="task-actions">
          ${item.action_link ? `
            <a href="${escapeHtml(item.action_link)}" target="_blank" rel="noopener noreferrer" class="btn-cta">
              🔗 Open Registration / Link
            </a>
          ` : ''}
          <button class="btn-icon" onclick="deleteTask('${item.id}')" title="Delete deadline">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
          </button>
        </div>
      </div>
    </article>
  `;
}

/**
 * Renders the completed tasks list in the bottom accordion drawer
 */
function renderCompletedDrawer() {
  const container = document.getElementById("completedTaskList");
  container.innerHTML = state.completedItems.map(item => `
    <div class="completed-item">
      <div>
        <span class="completed-item-title">~~${escapeHtml(item.event_name)}~~</span>
        <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 2px;">
          Due: ${escapeHtml(item.deadline_text)} &bull; Completed: ${item.completed_at || 'Archived'}
        </div>
      </div>
      <button class="undo-btn" onclick="restoreTask('${item.id}')">↩ Restore</button>
    </div>
  `).join("");
}

function toggleCompletedDrawer() {
  state.isCompletedDrawerOpen = !state.isCompletedDrawerOpen;
  const drawer = document.getElementById("completedDrawer");
  const list = document.getElementById("completedTaskList");
  const toggleText = document.getElementById("drawerToggleText");

  if (state.isCompletedDrawerOpen) {
    drawer.classList.add("open");
    list.style.display = "flex";
    toggleText.textContent = "Hide archived";
  } else {
    drawer.classList.remove("open");
    list.style.display = "none";
    toggleText.textContent = "Show archived";
  }
}

/**
 * Optimistic Completion Animation & API call
 */
async function completeTask(id, btnEl) {
  const card = document.getElementById(`task-${id}`);
  if (card) {
    card.classList.add("completing");
  }

  // Find item
  const itemIdx = state.activeItems.findIndex(i => i.id === id);
  let item = null;
  if (itemIdx !== -1) {
    item = state.activeItems[itemIdx];
    state.activeItems.splice(itemIdx, 1);
    item.is_completed = true;
    item.completed_at = new Date().toISOString().replace("T", " ").substring(0, 19) + " UTC";
    state.completedItems.unshift(item);
  }

  // Update counts immediately
  updateMetricsUI();

  setTimeout(() => {
    renderTasks();
  }, 250);

  try {
    const res = await fetch(`/api/deadlines/${id}/complete`, { method: "POST" });
    if (!res.ok) throw new Error("Server error");
    showToast(`Completed "${item ? item.event_name : id}"!`, "success");
  } catch (err) {
    console.error("Complete error:", err);
    showToast("Failed to complete task on server. Reverting...", "error");
    fetchDeadlines();
  }
}

/**
 * Restores a completed task back to active
 */
async function restoreTask(id) {
  try {
    const res = await fetch(`/api/deadlines/${id}/uncomplete`, { method: "POST" });
    if (!res.ok) throw new Error("Server error");
    showToast("Task restored to active list!", "info");
    fetchDeadlines();
  } catch (err) {
    showToast("Error restoring task", "error");
  }
}

/**
 * Deletes a task permanently
 */
async function deleteTask(id) {
  if (!confirm("Are you sure you want to remove this deadline?")) return;
  try {
    const res = await fetch(`/api/deadlines/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error("Delete failed");
    showToast("Deadline removed.", "info");
    fetchDeadlines();
  } catch (err) {
    showToast("Could not delete deadline", "error");
  }
}

/**
 * Triggers On-Demand Rescan
 */
async function triggerRescan() {
  const btn = document.getElementById("rescanBtn");
  const btnText = document.getElementById("rescanBtnText");

  btn.disabled = true;
  btn.classList.add("is-spinning");
  btnText.textContent = "Scanning Inbox...";

  showToast("Connecting to mail server & scanning with Gemini AI...", "info");

  try {
    const res = await fetch("/api/rescan", { method: "POST" });
    const data = await res.json();

    if (data.success) {
      showToast(`Scan complete! Scanned ${data.emails_scanned} emails, found ${data.deadlines_found} deadlines.`, "success");
      await fetchDeadlines();
    } else {
      showToast(`Rescan notice: ${data.message || data.error}`, "info");
      await fetchDeadlines();
    }
  } catch (err) {
    showToast(`Rescan failed: ${err.message}`, "error");
  } finally {
    btn.disabled = false;
    btn.classList.remove("is-spinning");
    btnText.textContent = "Rescan Inbox Now";
  }
}

/**
 * 4-Hour Live Countdown Timer
 */
function startCountdownTimer() {
  const timerEl = document.getElementById("autoSyncCountdown");

  setInterval(() => {
    if (!state.nextAutoScanTime) {
      timerEl.textContent = "03:59:59";
      return;
    }

    const now = new Date();
    const diffMs = state.nextAutoScanTime - now;

    if (diffMs <= 0) {
      timerEl.textContent = "Syncing...";
      // trigger refresh
      fetchDeadlinesSilently();
      return;
    }

    const totalSeconds = Math.floor(diffMs / 1000);
    const hrs = Math.floor(totalSeconds / 3600);
    const mins = Math.floor((totalSeconds % 3600) / 60);
    const secs = totalSeconds % 60;

    const pad = (n) => String(n).padStart(2, "0");
    timerEl.textContent = `${pad(hrs)}:${pad(mins)}:${pad(secs)}`;
  }, 1000);
}

/**
 * Search and Filter helpers
 */
function setFilter(filterName) {
  state.currentFilter = filterName;
  document.querySelectorAll(".filter-tab").forEach(tab => {
    if (tab.dataset.filter === filterName) {
      tab.classList.add("active");
    } else {
      tab.classList.remove("active");
    }
  });
  renderTasks();
}

function handleSearch(val) {
  state.searchQuery = val;
  const clearBtn = document.getElementById("clearSearchBtn");
  if (clearBtn) {
    clearBtn.style.display = val.length > 0 ? "block" : "none";
  }
  renderTasks();
}

function clearSearch() {
  const input = document.getElementById("searchInput");
  input.value = "";
  handleSearch("");
}

/**
 * Toast Notifications
 */
function showToast(message, type = "info") {
  const container = document.getElementById("toastContainer");
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `
    <span style="font-size: 1.1rem;">
      ${type === 'success' ? '✔' : type === 'error' ? '✖' : 'ℹ'}
    </span>
    <div>${escapeHtml(message)}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
