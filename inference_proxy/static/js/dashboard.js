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

async function handleTeardown(nodeId) {
  if (!window.confirm(`Teardown node ${nodeId}? This will drain connections and stop the container.`)) {
    return;
  }
  try {
    const resp = await fetch(`/admin/nodes/${nodeId}`, { method: "DELETE" });
    if (resp.ok) {
      showToast(`Teardown started for ${nodeId}`, "success");
    } else {
      showToast(`Teardown failed: HTTP ${resp.status}`, "error");
    }
  } catch (err) {
    showToast(`Teardown failed: ${err.message}`, "error");
  }
}

async function refreshDashboard() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");
  const lastUpdatedEl = document.getElementById("last-updated");
  const warningEl = document.getElementById("poll-warning");
  try {
    const [nodesResp, metricsResp, tasksResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
      fetch("/admin/provisioning/tasks"),
    ]);
    if (!nodesResp.ok) throw new Error(`HTTP ${nodesResp.status}`);
    if (!metricsResp.ok) throw new Error(`HTTP ${metricsResp.status}`);
    const nodes = await nodesResp.json();
    const metrics = await metricsResp.json();
    const tasks = tasksResp.ok ? await tasksResp.json() : [];
    const perNode = metrics.per_node || {};

    warningEl.textContent = "";
    warningEl.className = "";

    if (nodes.length === 0) {
      countEl.textContent = "0 nodes registered";
      tbody.innerHTML =
        '<tr><td colspan="8">No nodes registered</td></tr>';
    } else {
      countEl.textContent = `${nodes.length} nodes registered`;
      tbody.innerHTML = "";

      for (const node of nodes) {
        const tr = document.createElement("tr");

        const tdId = document.createElement("td");
        tdId.textContent = node.node_id;
        tr.appendChild(tdId);

        const tdEndpoint = document.createElement("td");
        tdEndpoint.textContent = node.endpoint;
        tr.appendChild(tdEndpoint);

        const tdModel = document.createElement("td");
        tdModel.textContent = node.model;
        tr.appendChild(tdModel);

        const tdStatus = document.createElement("td");
        const statusBadge = document.createElement("span");
        statusBadge.className = `badge badge-${node.status}`;
        statusBadge.textContent = node.status;
        tdStatus.appendChild(statusBadge);
        tr.appendChild(tdStatus);

        const tdConn = document.createElement("td");
        tdConn.textContent = node.active_connections;
        tr.appendChild(tdConn);

        const tdCb = document.createElement("td");
        const cbBadge = document.createElement("span");
        cbBadge.className = `badge badge-${node.circuit_breaker_state}`;
        cbBadge.textContent = node.circuit_breaker_state;
        tdCb.appendChild(cbBadge);
        tr.appendChild(tdCb);

        const tdReqs = document.createElement("td");
        tdReqs.textContent = perNode[node.node_id] || 0;
        tr.appendChild(tdReqs);

        const tdActions = document.createElement("td");
        const teardownBtn = document.createElement("button");
        teardownBtn.type = "button";
        teardownBtn.textContent = "Teardown";
        teardownBtn.disabled = ["provisioning", "draining"].includes(node.status);
        teardownBtn.addEventListener("click", function () {
          teardownBtn.disabled = true;
          handleTeardown(node.node_id);
        });
        tdActions.appendChild(teardownBtn);
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
