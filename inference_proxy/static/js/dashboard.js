// ponytail: vanilla fetch + DOM, no framework needed

function showToast(message, type) {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = "toast toast-" + (type || "info");
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("toast-visible"));
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function stepBadgeClass(step) {
  if (step === "complete" || step === "teardown_complete") return "badge-complete";
  if (step === "failed") return "badge-failed";
  return "badge-in-progress";
}

function renderTasks(tasks) {
  const tbody = document.getElementById("tasks-table-body");
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6">No provisioning tasks</td></tr>';
    return;
  }
  tbody.innerHTML = "";
  for (const task of tasks) {
    const tr = document.createElement("tr");

    const tdHost = document.createElement("td");
    tdHost.textContent = task.hostname;
    tr.appendChild(tdHost);

    const tdStep = document.createElement("td");
    const stepBadge = document.createElement("span");
    stepBadge.className = "badge " + stepBadgeClass(task.current_step);
    stepBadge.textContent = task.current_step;
    tdStep.appendChild(stepBadge);
    tr.appendChild(tdStep);

    const tdStatus = document.createElement("td");
    if (task.failed_step) {
      const failBadge = document.createElement("span");
      failBadge.className = "badge badge-failed";
      failBadge.textContent = "failed at " + task.failed_step;
      tdStatus.appendChild(failBadge);
    } else if (task.current_step === "complete" || task.current_step === "teardown_complete") {
      const doneBadge = document.createElement("span");
      doneBadge.className = "badge badge-complete";
      doneBadge.textContent = task.current_step;
      tdStatus.appendChild(doneBadge);
    } else {
      const progBadge = document.createElement("span");
      progBadge.className = "badge badge-in-progress";
      progBadge.textContent = "in progress";
      tdStatus.appendChild(progBadge);
    }
    tr.appendChild(tdStatus);

    const tdError = document.createElement("td");
    if (task.error) {
      tdError.className = "error-text";
      tdError.textContent = task.error;
    } else {
      tdError.textContent = "—";
    }
    tr.appendChild(tdError);

    const tdStarted = document.createElement("td");
    tdStarted.textContent = new Date(task.started_at).toLocaleString();
    tr.appendChild(tdStarted);

    const tdUpdated = document.createElement("td");
    tdUpdated.textContent = new Date(task.updated_at).toLocaleString();
    tr.appendChild(tdUpdated);

    tbody.appendChild(tr);
  }
}

// ponytail: data-driven action dispatch replaces per-action functions
const ACTION_CONFIG = {
  setup: {
    method: "POST",
    url: () => "/admin/nodes/setup",
    body: (nodeId) => ({ hostname: nodeId }),
    confirm: false,
    confirmMsg: null,
    label: "Setup Node",
    css: "btn-setup",
    successMsg: (nodeId) => `Setup started for ${nodeId}`,
  },
  teardown: {
    method: "DELETE",
    url: (nodeId) => `/admin/nodes/${nodeId}`,
    body: null,
    confirm: true,
    confirmMsg: (nodeId) =>
      `Teardown node ${nodeId}? This will drain connections and stop the container.`,
    label: "Teardown",
    css: "btn-teardown",
    successMsg: (nodeId) => `Teardown started for ${nodeId}`,
  },
  retry: {
    method: "POST",
    url: () => "/admin/nodes/setup",
    body: (nodeId) => ({ hostname: nodeId }),
    confirm: false,
    confirmMsg: null,
    label: "Retry",
    css: "btn-retry",
    successMsg: (nodeId) => `Retry started for ${nodeId}`,
  },
  cancel: {
    method: "DELETE",
    url: (nodeId) => `/admin/nodes/${nodeId}`,
    body: null,
    confirm: true,
    confirmMsg: (nodeId) => `Cancel provisioning for ${nodeId}?`,
    label: "Cancel",
    css: "btn-cancel",
    successMsg: (nodeId) => `Cancelled provisioning for ${nodeId}`,
  },
  force_teardown: {
    method: "DELETE",
    url: (nodeId) => `/admin/nodes/${nodeId}?force=true`,
    body: null,
    confirm: true,
    confirmMsg: (nodeId) =>
      `Force teardown ${nodeId}? This will immediately stop the container without draining.`,
    label: "Force Teardown",
    css: "btn-force-teardown",
    successMsg: (nodeId) => `Teardown started for ${nodeId}`,
  },
};

async function handleAction(action, nodeId) {
  const config = ACTION_CONFIG[action];
  if (!config) return;
  if (config.confirm && !window.confirm(config.confirmMsg(nodeId))) return;
  const options = { method: config.method };
  if (config.body) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(config.body(nodeId));
  }
  try {
    const resp = await fetch(config.url(nodeId), options);
    if (resp.ok) {
      showToast(config.successMsg(nodeId), "success");
    } else {
      const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
      showToast(data.detail || `HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    showToast(`${config.label} failed: ${err.message}`, "error");
  }
}

function relativeTime(isoString) {
  if (!isoString) return "";
  const diffMs = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 60) return `${mins}m`;
  return `${Math.floor(mins / 60)}h`;
}

function renderQuadsStatus(data) {
  const el = document.getElementById("quads-status");
  el.textContent = "";
  const badge = document.createElement("span");
  badge.className = "badge";
  if (data.status === "connected") {
    badge.classList.add("badge-healthy");
    badge.textContent = `QUADS: connected — ${relativeTime(data.last_sync)} ago`;
  } else if (data.status === "stale") {
    badge.classList.add("badge-draining");
    badge.textContent = `QUADS: stale — last sync ${relativeTime(data.last_sync)} ago`;
  } else {
    badge.classList.add("badge-unhealthy");
    badge.textContent = "QUADS: unavailable";
  }
  el.appendChild(badge);
}

function createActionButton(action, nodeId) {
  const config = ACTION_CONFIG[action];
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = config.css;
  btn.textContent = config.label;
  btn.addEventListener("click", function () {
    btn.disabled = true;
    handleAction(action, nodeId);
  });
  return btn;
}

async function refreshDashboard() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");
  const lastUpdatedEl = document.getElementById("last-updated");
  const warningEl = document.getElementById("poll-warning");
  try {
    const [nodesResp, metricsResp, tasksResp, quadsResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
      fetch("/admin/provisioning/tasks"),
      fetch("/admin/quads/status"),
    ]);
    if (!nodesResp.ok) throw new Error(`HTTP ${nodesResp.status}`);
    if (!metricsResp.ok) throw new Error(`HTTP ${metricsResp.status}`);
    const nodes = await nodesResp.json();
    const metrics = await metricsResp.json();
    const tasks = tasksResp.ok ? await tasksResp.json() : [];
    const perNode = metrics.per_node || {};

    // ponytail: graceful degradation if QUADS endpoint unavailable
    if (quadsResp.ok) {
      renderQuadsStatus(await quadsResp.json());
    }

    warningEl.textContent = "";
    warningEl.className = "";

    if (nodes.length === 0) {
      countEl.textContent = "0 nodes";
      tbody.textContent = "";
      const emptyRow = document.createElement("tr");
      const emptyCell = document.createElement("td");
      emptyCell.colSpan = 10;
      emptyCell.textContent = "No nodes found";
      emptyRow.appendChild(emptyCell);
      tbody.appendChild(emptyRow);
    } else {
      countEl.textContent = `${nodes.length} nodes`;
      tbody.textContent = "";

      for (const node of nodes) {
        const tr = document.createElement("tr");

        const tdId = document.createElement("td");
        tdId.textContent = node.node_id;
        tr.appendChild(tdId);

        const tdGpuVendor = document.createElement("td");
        tdGpuVendor.textContent = node.gpu_vendor || "—";
        tr.appendChild(tdGpuVendor);

        const tdGpuModel = document.createElement("td");
        tdGpuModel.textContent = node.gpu_model || "—";
        tr.appendChild(tdGpuModel);

        const tdEndpoint = document.createElement("td");
        tdEndpoint.textContent = node.state === "available" ? "—" : node.endpoint;
        tr.appendChild(tdEndpoint);

        const tdModel = document.createElement("td");
        tdModel.textContent = node.state === "available" ? "—" : node.model;
        tr.appendChild(tdModel);

        const tdState = document.createElement("td");
        const stateBadge = document.createElement("span");
        stateBadge.className = `badge badge-${node.state}`;
        stateBadge.textContent = node.state;
        tdState.appendChild(stateBadge);
        tr.appendChild(tdState);

        const tdConn = document.createElement("td");
        tdConn.textContent = node.state === "available" ? "—" : node.active_connections;
        tr.appendChild(tdConn);

        const tdCb = document.createElement("td");
        if (node.state === "available") {
          tdCb.textContent = "—";
        } else {
          const cbBadge = document.createElement("span");
          cbBadge.className = `badge badge-${node.circuit_breaker_state}`;
          cbBadge.textContent = node.circuit_breaker_state;
          tdCb.appendChild(cbBadge);
        }
        tr.appendChild(tdCb);

        const tdReqs = document.createElement("td");
        tdReqs.textContent = node.state === "available" ? "—" : (perNode[node.node_id] || 0);
        tr.appendChild(tdReqs);

        const tdActions = document.createElement("td");
        const actions = node.actions || [];
        if (actions.length === 1) {
          tdActions.appendChild(createActionButton(actions[0], node.node_id));
        } else if (actions.length > 1) {
          const group = document.createElement("div");
          group.className = "action-group";
          group.appendChild(createActionButton(actions[0], node.node_id));

          const caret = document.createElement("button");
          caret.type = "button";
          caret.className = ACTION_CONFIG[actions[0]].css + " action-caret";
          caret.textContent = "▾";
          const menu = document.createElement("div");
          menu.className = "action-menu";
          for (let i = 1; i < actions.length; i++) {
            const menuBtn = createActionButton(actions[i], node.node_id);
            menu.appendChild(menuBtn);
          }
          caret.addEventListener("click", function (e) {
            e.stopPropagation();
            menu.classList.toggle("open");
          });
          group.appendChild(caret);
          group.appendChild(menu);
          tdActions.appendChild(group);
        }
        tr.appendChild(tdActions);

        tbody.appendChild(tr);
      }
    }

    renderTasks(tasks);

    lastUpdatedEl.textContent =
      "Updated " + new Date().toLocaleTimeString();
    lastUpdatedEl.className = "last-updated";
  } catch (err) {
    warningEl.textContent = "Update failed — retrying...";
    warningEl.className = "poll-warning";
  }
}

document.addEventListener("DOMContentLoaded", function () {
  refreshDashboard();
  setInterval(refreshDashboard, POLL_INTERVAL_MS);

  // Dropdown dismissal on outside click
  document.addEventListener("click", function (e) {
    if (!e.target.closest(".action-group")) {
      document.querySelectorAll(".action-menu.open").forEach(function (m) {
        m.classList.remove("open");
      });
    }
  });

  // Manual setup toggle (D-05)
  const toggle = document.getElementById("manual-setup-toggle");
  const setupRow = document.getElementById("manual-setup-row");
  toggle.addEventListener("click", function (e) {
    e.preventDefault();
    if (setupRow.style.display === "none") {
      setupRow.style.display = "flex";
      toggle.textContent = "- Manual setup";
    } else {
      setupRow.style.display = "none";
      toggle.textContent = "+ Manual setup";
    }
  });

  // Setup form handler
  const form = document.getElementById("setup-form");
  form.addEventListener("submit", async function (e) {
    e.preventDefault();
    const input = document.getElementById("setup-hostname");
    const btn = document.getElementById("setup-btn");
    const hostname = input.value.trim();
    if (!hostname) return;
    btn.disabled = true;
    try {
      const resp = await fetch("/admin/nodes/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hostname }),
      });
      if (resp.ok) {
        showToast(`Setup started for ${hostname}`, "success");
        input.value = "";
        setTimeout(function () { btn.disabled = false; }, 2000);
      } else {
        const data = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        showToast(data.detail || `Error: HTTP ${resp.status}`, "error");
        btn.disabled = false;
      }
    } catch (err) {
      showToast(`Error: ${err.message}`, "error");
      btn.disabled = false;
    }
  });
});
