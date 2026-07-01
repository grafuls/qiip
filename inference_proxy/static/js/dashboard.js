// ponytail: vanilla fetch + DOM, no framework needed
async function refreshDashboard() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");
  const lastUpdatedEl = document.getElementById("last-updated");
  const warningEl = document.getElementById("poll-warning");
  try {
    const [nodesResp, metricsResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
    ]);
    if (!nodesResp.ok) throw new Error(`HTTP ${nodesResp.status}`);
    if (!metricsResp.ok) throw new Error(`HTTP ${metricsResp.status}`);
    const nodes = await nodesResp.json();
    const metrics = await metricsResp.json();
    const perNode = metrics.per_node || {};

    warningEl.textContent = "";
    warningEl.className = "";

    if (nodes.length === 0) {
      countEl.textContent = "0 nodes registered";
      tbody.innerHTML =
        '<tr><td colspan="7">No nodes registered</td></tr>';
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

        tbody.appendChild(tr);
      }
    }

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
});
