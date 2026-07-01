// ponytail: vanilla fetch + DOM, no framework needed
async function loadNodes() {
  const tbody = document.getElementById("node-table-body");
  const countEl = document.getElementById("node-count");
  try {
    const response = await fetch("/admin/nodes");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const nodes = await response.json();

    if (nodes.length === 0) {
      countEl.textContent = "0 nodes registered";
      tbody.innerHTML =
        '<tr><td colspan="6">No nodes registered</td></tr>';
      return;
    }

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

      tbody.appendChild(tr);
    }
  } catch (err) {
    countEl.textContent = "";
    tbody.innerHTML =
      '<tr><td colspan="6">Failed to load node data. Check that the proxy is running and try refreshing the page.</td></tr>';
  }
}

document.addEventListener("DOMContentLoaded", loadNodes);
