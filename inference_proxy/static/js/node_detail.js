// ponytail: vanilla fetch + DOM, same pattern as dashboard.js

function showToast(message, type) {
  var container = document.getElementById("toast-container");
  var toast = document.createElement("div");
  toast.className = "toast toast-" + (type || "info");
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(function () { toast.classList.add("toast-visible"); });
  setTimeout(function () {
    toast.classList.remove("toast-visible");
    setTimeout(function () { toast.remove(); }, 300);
  }, 4000);
}

var ACTION_CONFIG = {
  setup: {
    method: "POST", url: function () { return "/admin/nodes/setup"; },
    body: function (id) { return { hostname: id }; }, confirm: false,
    label: "Setup Node", css: "btn-setup",
    successMsg: function (id) { return "Setup started for " + id; },
  },
  teardown: {
    method: "DELETE", url: function (id) { return "/admin/nodes/" + id; },
    body: null, confirm: true,
    confirmMsg: function (id) { return "Teardown " + id + "? This will drain connections and stop the container."; },
    label: "Teardown", css: "btn-teardown",
    successMsg: function (id) { return "Teardown started for " + id; },
  },
  retry: {
    method: "POST", url: function () { return "/admin/nodes/setup"; },
    body: function (id) { return { hostname: id }; }, confirm: false,
    label: "Retry", css: "btn-retry",
    successMsg: function (id) { return "Retry started for " + id; },
  },
  cancel: {
    method: "DELETE", url: function (id) { return "/admin/nodes/" + id; },
    body: null, confirm: true,
    confirmMsg: function (id) { return "Cancel provisioning for " + id + "?"; },
    label: "Cancel", css: "btn-cancel",
    successMsg: function (id) { return "Cancelled provisioning for " + id; },
  },
  force_teardown: {
    method: "DELETE", url: function (id) { return "/admin/nodes/" + id + "?force=true"; },
    body: null, confirm: true,
    confirmMsg: function (id) { return "Force teardown " + id + "? This will immediately stop the container without draining."; },
    label: "Force Teardown", css: "btn-force-teardown",
    successMsg: function (id) { return "Teardown started for " + id; },
  },
};

async function handleAction(action, nodeId) {
  var config = ACTION_CONFIG[action];
  if (!config) return;
  if (config.confirm && !window.confirm(config.confirmMsg(nodeId))) return;
  var options = { method: config.method };
  if (config.body) {
    options.headers = { "Content-Type": "application/json" };
    options.body = JSON.stringify(config.body(nodeId));
  }
  try {
    var resp = await fetch(config.url(nodeId), options);
    if (resp.ok) {
      showToast(config.successMsg(nodeId), "success");
      if (action === "setup" || action === "retry") { logStreamDone = false; }
    } else {
      var data = await resp.json().catch(function () { return { detail: "HTTP " + resp.status }; });
      showToast(data.detail || "HTTP " + resp.status, "error");
    }
  } catch (err) {
    showToast(config.label + " failed: " + err.message, "error");
  }
}

function createActionButton(action, nodeId) {
  var config = ACTION_CONFIG[action];
  var btn = document.createElement("button");
  btn.type = "button";
  btn.className = config.css;
  btn.textContent = config.label;
  btn.addEventListener("click", async function () {
    btn.disabled = true;
    try { await handleAction(action, nodeId); } finally { btn.disabled = false; }
  });
  return btn;
}

function stepBadgeClass(step) {
  if (step === "complete" || step === "teardown_complete") return "badge-complete";
  if (step === "failed") return "badge-failed";
  return "badge-in-progress";
}

async function refreshDetail() {
  var stateEl = document.getElementById("node-state");
  var infoBody = document.getElementById("node-info-body");
  var tasksBody = document.getElementById("tasks-table-body");
  var lastUpdatedEl = document.getElementById("last-updated");

  try {
    var [nodesResp, metricsResp, tasksResp] = await Promise.all([
      fetch("/admin/nodes"),
      fetch("/admin/metrics"),
      fetch("/admin/provisioning/tasks"),
    ]);
    if (!nodesResp.ok) throw new Error("HTTP " + nodesResp.status);
    var nodes = await nodesResp.json();
    var metrics = metricsResp.ok ? await metricsResp.json() : {};
    var allTasks = tasksResp.ok ? await tasksResp.json() : [];
    var perNode = metrics.per_node || {};

    var node = nodes.find(function (n) { return n.node_id === NODE_ID; });
    if (!node) {
      stateEl.textContent = "Node not found";
      infoBody.innerHTML = '<tr><td colspan="9">Node not found in registry</td></tr>';
    } else {
      stateEl.textContent = node.state;

      infoBody.textContent = "";
      var tr = document.createElement("tr");

      var tdGV = document.createElement("td"); tdGV.textContent = node.gpu_vendor || "—"; tr.appendChild(tdGV);
      var tdGM = document.createElement("td"); tdGM.textContent = node.gpu_model || "—"; tr.appendChild(tdGM);
      var tdEp = document.createElement("td"); tdEp.textContent = node.state === "available" ? "—" : node.endpoint; tr.appendChild(tdEp);
      var tdMo = document.createElement("td"); tdMo.textContent = node.state === "available" ? "—" : node.model; tr.appendChild(tdMo);

      var tdSt = document.createElement("td");
      var sb = document.createElement("span"); sb.className = "badge badge-" + node.state; sb.textContent = node.state;
      tdSt.appendChild(sb); tr.appendChild(tdSt);

      var tdCo = document.createElement("td"); tdCo.textContent = node.state === "available" ? "—" : node.active_connections; tr.appendChild(tdCo);

      var tdCb = document.createElement("td");
      if (node.state === "available") { tdCb.textContent = "—"; }
      else { var cb = document.createElement("span"); cb.className = "badge badge-" + node.circuit_breaker_state; cb.textContent = node.circuit_breaker_state; tdCb.appendChild(cb); }
      tr.appendChild(tdCb);

      var tdRq = document.createElement("td"); tdRq.textContent = node.state === "available" ? "—" : (perNode[node.node_id] || 0); tr.appendChild(tdRq);

      var tdAc = document.createElement("td");
      var actions = node.actions || [];
      for (var i = 0; i < actions.length; i++) {
        tdAc.appendChild(createActionButton(actions[i], node.node_id));
        if (i < actions.length - 1) tdAc.appendChild(document.createTextNode(" "));
      }
      tr.appendChild(tdAc);

      infoBody.appendChild(tr);
    }

    // ponytail: filter tasks by hostname — matching against node_id (which is the hostname)
    var tasks = allTasks.filter(function (t) { return t.hostname === NODE_ID; });
    if (tasks.length > 0) connectLogStream();
    if (tasks.length === 0) {
      tasksBody.innerHTML = '<tr><td colspan="5">No provisioning tasks for this node</td></tr>';
    } else {
      tasksBody.textContent = "";
      for (var j = 0; j < tasks.length; j++) {
        var task = tasks[j];
        var ttr = document.createElement("tr");

        var tdStep = document.createElement("td");
        var badge = document.createElement("span"); badge.className = "badge " + stepBadgeClass(task.current_step); badge.textContent = task.current_step;
        tdStep.appendChild(badge); ttr.appendChild(tdStep);

        var tdStatus = document.createElement("td");
        if (task.failed_step) {
          var fb = document.createElement("span"); fb.className = "badge badge-failed"; fb.textContent = "failed at " + task.failed_step; tdStatus.appendChild(fb);
        } else if (task.current_step === "complete" || task.current_step === "teardown_complete") {
          var db = document.createElement("span"); db.className = "badge badge-complete"; db.textContent = task.current_step; tdStatus.appendChild(db);
        } else {
          var pb = document.createElement("span"); pb.className = "badge badge-in-progress"; pb.textContent = "in progress"; tdStatus.appendChild(pb);
        }
        ttr.appendChild(tdStatus);

        var tdErr = document.createElement("td");
        if (task.error) { tdErr.className = "error-text"; tdErr.textContent = task.error; }
        else { tdErr.textContent = "—"; }
        ttr.appendChild(tdErr);

        var tdStart = document.createElement("td"); tdStart.textContent = new Date(task.started_at).toLocaleString(); ttr.appendChild(tdStart);
        var tdUpd = document.createElement("td"); tdUpd.textContent = new Date(task.updated_at).toLocaleString(); ttr.appendChild(tdUpd);

        tasksBody.appendChild(ttr);
      }
    }

    lastUpdatedEl.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (err) {
    lastUpdatedEl.textContent = "Update failed — retrying...";
  }
}

// ponytail: SSE live log viewer — poll loop triggers connection when tasks exist
var logSource = null;
var logStreamDone = false;

function connectLogStream() {
  if (logSource || logStreamDone) return;

  var panel = document.getElementById("logs-panel");
  var output = document.getElementById("logs-output");
  var status = document.getElementById("logs-status");

  output.textContent = "";
  panel.style.display = "";
  status.textContent = "connecting";
  status.className = "badge badge-in-progress";

  var es = new EventSource("/admin/provisioning/" + encodeURIComponent(NODE_ID) + "/logs");
  logSource = es;

  es.addEventListener("open", function () {
    status.textContent = "streaming";
  });

  es.addEventListener("message", function (ev) {
    try {
      var entry = JSON.parse(ev.data);
      var line = document.createElement("div");
      line.className = "log-line";
      if (entry.level) line.dataset.level = entry.level;
      if (entry.stream) line.dataset.stream = entry.stream;

      var ts = document.createElement("span");
      ts.className = "log-ts";
      ts.textContent = new Date(entry.ts).toLocaleTimeString();
      line.appendChild(ts);

      var msg = document.createElement("span");
      msg.className = "log-msg";
      msg.textContent = entry.msg;
      line.appendChild(msg);

      output.appendChild(line);
      var nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 60;
      if (nearBottom) output.scrollTop = output.scrollHeight;
    } catch (_) {}
  });

  es.addEventListener("error", function () {
    es.close();
    logSource = null;
    logStreamDone = true;
    status.textContent = "ended";
    status.className = "badge badge-complete";
  });
}

document.addEventListener("DOMContentLoaded", function () {
  refreshDetail();
  setInterval(refreshDetail, POLL_INTERVAL_MS);
});
