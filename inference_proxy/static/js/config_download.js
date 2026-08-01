// Config generators for OpenCode CLI and Pi coding agent.
// Generators are pure functions testable via Node.js.

function generateOpenCodeConfig(baseUrl, modelId) {
  var base = baseUrl.replace(/\/+$/, "");
  return {
    $schema: "https://opencode.ai/config.json",
    provider: {
      qiip: {
        npm: "@ai-sdk/openai-compatible",
        name: "QIIP Inference Proxy",
        options: {
          baseURL: base + "/v1",
        },
        models: {
          [modelId]: {
            name: modelId,
          },
        },
      },
    },
    model: "qiip/" + modelId,
  };
}

function generatePiConfig(baseUrl, modelId) {
  var base = baseUrl.replace(/\/+$/, "");
  return {
    providers: {
      qiip: {
        baseUrl: base + "/v1",
        api: "openai-completions",
        apiKey: "none",
        compat: {
          supportsDeveloperRole: false,
          supportsReasoningEffort: false,
        },
        models: [{ id: modelId }],
      },
    },
  };
}

function downloadConfigFile(data, filename) {
  var json = JSON.stringify(data, null, 2);
  var blob = new Blob([json], { type: "application/json" });
  var url = URL.createObjectURL(blob);
  var a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function createConfigButtons(baseUrl, modelId) {
  var frag = document.createDocumentFragment();
  var btnOC = document.createElement("button");
  btnOC.type = "button";
  btnOC.className = "btn-config";
  btnOC.textContent = "OpenCode CLI";
  btnOC.addEventListener("click", function () {
    downloadConfigFile(generateOpenCodeConfig(baseUrl, modelId), "opencode.json");
  });
  var btnPi = document.createElement("button");
  btnPi.type = "button";
  btnPi.className = "btn-config";
  btnPi.textContent = "Pi Agent";
  btnPi.addEventListener("click", function () {
    downloadConfigFile(generatePiConfig(baseUrl, modelId), "models.json");
  });
  frag.appendChild(btnOC);
  frag.appendChild(btnPi);
  return frag;
}
