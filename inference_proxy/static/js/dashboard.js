// ponytail: vanilla fetch + DOM, no framework needed

function stepBadgeClass(step) {
  if (step === "complete" || step === "teardown_complete") return "badge-complete";
  if (step === "failed") return "badge-failed";
  return "badge-in-progress";
}

function renderTasks(tasks) {
  const tbody = document.getElementById("tasks-table-body");
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = '<tr><td colspan="5">No provisioning tasks</td></tr>';
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
      tdStatus.textContent = "failed";
    } else if (task.current_step === "complete" || task.current_step === "teardown_complete") {
      tdStatus.textContent = task.current_step;
    } else {
      tdStatus.textContent = "in progress";
    }
    tr.appendChild(tdStatus);

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
    if (!resp.ok) {
      alert(`Teardown failed: HTTP ${resp.status}`);
    }
  } catch (err) {
    alert(`Teardown failed: ${err.message}`);
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
      "Last updated: " + new Date().toLocaleTimeString();
    lastUpdatedEl.className = "last-updated";
  } catch (err) {
    warningEl.textContent = "Update failed -- retrying...";
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
    const status = document.getElementById("setup-status");
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
        status.textContent = `Setup started for ${hostname}`;
        input.value = "";
        setTimeout(function () { btn.disabled = false; }, 2000);
      } else {
        const err = await resp.json().catch(() => ({ detail: `HTTP ${resp.status}` }));
        status.textContent = err.detail || `Error: HTTP ${resp.status}`;
        btn.disabled = false;
      }
    } catch (err) {
      status.textContent = `Error: ${err.message}`;
      btn.disabled = false;
    }
  });
});
