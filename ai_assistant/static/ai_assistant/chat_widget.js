/**
 * Accessible AI chat widget using the authenticated Django AI endpoints.
 */
(function () {
  "use strict";

  const widget = document.getElementById("ai-assistant-widget");
  if (!widget) return;

  const toggle = document.getElementById("ai-widget-toggle");
  const panel = document.getElementById("ai-chat-panel");
  const close = document.getElementById("ai-minimize-btn");
  const reset = document.getElementById("ai-reset-btn");
  const statusText = document.getElementById("ai-status-text");
  const emptyState = document.getElementById("ai-empty-state");
  const emptyTitle = document.getElementById("ai-empty-title");
  const emptyDescription = document.getElementById("ai-empty-description");
  const messages = document.getElementById("ai-messages-container");
  const typing = document.getElementById("ai-typing");
  const typingLabel = document.getElementById("ai-typing-label");
  const form = document.getElementById("ai-chat-form");
  const input = document.getElementById("ai-input-text");
  const send = document.getElementById("ai-send-btn");
  const modelRow = document.getElementById("ai-model-row");
  const modelSelect = document.getElementById("ai-model-select");
  const modelMessage = document.getElementById("ai-model-message");
  const modelRetry = document.getElementById("ai-model-retry");
  const chatTab = document.getElementById("ai-tab-chat");
  const jobsTab = document.getElementById("ai-tab-search");
  // Bump the version whenever the model identity or status vocabulary changes
  // so a selection persisted by an older widget version can never be replayed.
  const modelStoragePrefix = "ai-assistant-selected-model:v4:";

  // Statuses that mean "this model cannot be used right now". ``unknown`` is
  // deliberately absent: an unchecked model is not a broken model.
  const FAILURE_STATUSES = new Set([
    "missing_api_key",
    "not_configured",
    "authentication_required",
    "rate_limited",
    "timeout_gateway",
    "request_rejected",
    "unsupported_model",
    "provider_unavailable",
  ]);

  let history = [];
  let isAuthenticated = false;
  let aiEnabled = false;
  let isSending = false;
  let isLoadingStatus = false;
  let currentMode = "chat";
  let activeProvider = "";
  let configuredModels = [];
  let configurationWarnings = [];

  function loginUrl() {
    const next = window.location.pathname + window.location.search;
    return `/accounts/login/?next=${encodeURIComponent(next)}`;
  }

  function csrfToken() {
    const field = form.querySelector('input[name="csrfmiddlewaretoken"]');
    if (field && field.value) return field.value;
    const match = document.cookie.match(/(^|;)\s*csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[2]) : "";
  }

  function setPanelOpen(open) {
    panel.hidden = !open;
    widget.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    if (open) {
      if (!isSending) loadStatus();
      window.setTimeout(() => input.focus(), 40);
    } else {
      toggle.focus();
    }
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = value == null ? "" : String(value);
    return node.innerHTML;
  }

  function formatMessage(text) {
    const lines = escapeHtml(text).split("\n");
    const output = [];
    let listType = "";
    let codeLines = null;

    function closeList() {
      if (listType) output.push(`</${listType}>`);
      listType = "";
    }

    lines.forEach((line) => {
      const trimmed = line.trim();
      if (/^```/.test(trimmed)) {
        closeList();
        if (codeLines === null) {
          codeLines = [];
        } else {
          output.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
          codeLines = null;
        }
        return;
      }
      if (codeLines !== null) {
        codeLines.push(line);
        return;
      }

      const unordered = /^[-*]\s+/.test(trimmed);
      const ordered = /^\d+\.\s+/.test(trimmed);
      if (unordered || ordered) {
        const nextType = unordered ? "ul" : "ol";
        if (listType !== nextType) {
          closeList();
          output.push(`<${nextType}>`);
          listType = nextType;
        }
        output.push(`<li>${trimmed.replace(unordered ? /^[-*]\s+/ : /^\d+\.\s+/, "")}</li>`);
        return;
      }

      closeList();
      if (trimmed) {
        const paragraph = trimmed
          .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
          .replace(/`([^`]+)`/g, "<code>$1</code>")
          .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (match, label, url) =>
            `<a href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
          );
        output.push(`<p>${paragraph}</p>`);
      }
    });

    closeList();
    if (codeLines !== null) {
      output.push(`<pre><code>${codeLines.join("\n")}</code></pre>`);
    }
    return output.join("");
  }

  function scrollToLatest() {
    messages.scrollTop = messages.scrollHeight;
  }

  function updateSendState() {
    send.disabled = isSending || !input.value.trim();
  }

  function addMessage(role, text, isError) {
    emptyState.hidden = true;
    const message = document.createElement("article");
    message.className = `ai-msg ai-msg--${role}`;
    const body = document.createElement("div");
    body.className = `ai-msg-body${isError ? " ai-msg-body--error" : ""}`;
    if (role === "user") {
      body.textContent = text;
    } else {
      body.innerHTML = formatMessage(text);
    }
    message.appendChild(body);
    messages.appendChild(message);
    scrollToLatest();
  }

  function setModelMessage(message, isError) {
    modelMessage.textContent = message || "";
    modelMessage.classList.toggle("is-error", Boolean(isError));
  }

  function modelUnavailable(message, retryable, label = "Unknown") {
    configuredModels = [];
    modelSelect.replaceChildren();
    const option = document.createElement("option");
    option.value = "";
    option.textContent = label;
    modelSelect.appendChild(option);
    modelSelect.disabled = true;
    setModelMessage(message || "Models unavailable.", retryable);
    modelRetry.hidden = !retryable;
    modelRetry.disabled = false;
  }

  function storageKey() {
    return `${modelStoragePrefix}all`;
  }

  function persistSelectedModel() {
    if (!modelSelect.value) return;
    try {
      window.localStorage.setItem(storageKey(), modelSelect.value);
    } catch (error) {
      // Browser storage is optional; the active selection remains in memory.
    }
  }

  function renderModelOptions(data) {
    const modelList = Array.isArray(data.models)
      ? data.models.filter((model) =>
        model &&
        typeof model.id === "string" &&
        model.id.length > 0 &&
        typeof model.label === "string" &&
        model.label.length > 0 &&
        typeof model.provider === "string" &&
        typeof model.model === "string"
      )
      : [];

    activeProvider = typeof data.provider === "string" ? data.provider : "";
    configuredModels = modelList;
    if (!modelList.length) {
      modelUnavailable(
        data.message || "No models are explicitly configured.",
        true
      );
      statusText.textContent = "No models available";
      statusText.classList.remove("is-ready");
      return false;
    }

    let savedModel = "";
    try {
      savedModel = window.localStorage.getItem(storageKey()) || "";
    } catch (error) {
      savedModel = "";
    }

    modelSelect.replaceChildren();
    modelList.forEach((model) => {
      const option = document.createElement("option");
      option.value = model.id;
      option.textContent = `${model.label} · ${model.availability}`;
      option.title = model.id;
      modelSelect.appendChild(option);
    });

    const availableIds = new Set(modelList.map((model) => model.id));
    const preferredModel = availableIds.has(savedModel)
      ? savedModel
      : availableIds.has(`${data.provider}:${data.model}`)
        ? `${data.provider}:${data.model}`
        : modelList[0].id;
    modelSelect.value = preferredModel;
    modelSelect.disabled = !isAuthenticated;
    modelRetry.hidden = true;
    setSelectedModelState();
    persistSelectedModel();
    return true;
  }

  function selectedModelEntry() {
    return configuredModels.find((model) => model.id === modelSelect.value) || null;
  }

  function updateSelectedModelOption(model) {
    const option = Array.from(modelSelect.options).find(
      (candidate) => candidate.value === model.id
    );
    if (option) {
      option.textContent = `${model.label} · ${model.availability}`;
      option.title = `${model.id} — ${model.availability}`;
    }
  }

  function setSelectedModelState() {
    const model = selectedModelEntry();
    if (!model) {
      if (configurationWarnings.length) {
        setModelMessage(configurationWarnings.join(" "), true);
      }
      return;
    }
    const warningText = configurationWarnings.length
      ? ` Configuration: ${configurationWarnings.join(" ")}`
      : "";
    modelMessage.textContent = `${model.availability}: ${model.message}${warningText}`;
    modelMessage.classList.toggle(
      "is-error",
      !model.configured ||
        FAILURE_STATUSES.has(model.status) ||
        configurationWarnings.length > 0
    );
  }

  async function fetchModels() {
    modelRetry.disabled = true;
    modelRetry.hidden = true;
    if (!configuredModels.length) {
      modelSelect.replaceChildren();
      const loadingOption = document.createElement("option");
      loadingOption.value = "";
      loadingOption.textContent = "Loading...";
      modelSelect.appendChild(loadingOption);
    }
    modelSelect.disabled = true;
    setModelMessage("Contacting provider…", false);

    try {
      const response = await fetch("/api/ai/models/", {
        headers: { "Accept": "application/json" },
      });
      const data = await response.json().catch(() => ({}));
      if (typeof data.provider === "string") activeProvider = data.provider;
      if (response.status === 401) {
        isAuthenticated = false;
        modelUnavailable("Sign in to load configured models.", false, "Authentication required");
        statusText.textContent = "Authentication required";
        statusText.classList.remove("is-ready");
        return;
      }
      if (!response.ok) {
        throw new Error(data.error || "Could not load models from the provider.");
      }
      activeProvider = typeof data.provider === "string" ? data.provider : "";
      configurationWarnings = Array.isArray(data.configuration_errors)
        ? data.configuration_errors.filter((item) => typeof item === "string")
        : [];
      if (data.status === "disabled" || data.status === "unconfigured") {
        modelUnavailable(data.message || "The assistant is not configured.", false);
        statusText.textContent = data.message || "Assistant unavailable";
        statusText.classList.remove("is-ready");
        return;
      }
      if (data.status === "empty") {
        renderModelOptions(data);
        setModelMessage(data.message, true);
        modelRetry.hidden = false;
        return;
      }
      if (renderModelOptions(data)) {
        statusText.textContent = `${data.provider || "AI"} · ${modelSelect.selectedOptions[0].textContent}`;
        statusText.classList.add("is-ready");
      }
    } catch (error) {
      if (configuredModels.length) {
        setModelMessage(`Model list refresh failed: ${error.message}`, true);
        modelSelect.disabled = !isAuthenticated;
      } else {
        modelUnavailable(error.message, true);
      }
      statusText.textContent = "Model list unavailable";
      statusText.classList.remove("is-ready");
    } finally {
      modelRetry.disabled = false;
      updateSendState();
    }
  }

  async function loadStatus() {
    if (isLoadingStatus) return;
    isLoadingStatus = true;
    statusText.textContent = "Checking assistant…";
    statusText.classList.remove("is-ready");
    try {
      const response = await fetch("/api/ai/status/", {
        headers: { "Accept": "application/json" },
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        isAuthenticated = false;
        modelUnavailable("Sign in to load configured models.", false, "Authentication required");
        statusText.textContent = "Authentication required";
        return;
      }
      if (!response.ok) {
        throw new Error(data.error || "Could not check assistant status.");
      }
      isAuthenticated = true;
      aiEnabled = data.enabled === true;
      activeProvider = data.provider || "";
      await fetchModels();
      if (!aiEnabled) {
        statusText.textContent = data.message || "AI assistant is disabled.";
        statusText.classList.remove("is-ready");
      }
    } catch (error) {
      if (configuredModels.length) {
        setModelMessage(`Assistant status check failed: ${error.message}`, true);
        modelSelect.disabled = !isAuthenticated;
      } else {
        modelUnavailable(error.message, true);
      }
      statusText.textContent = "Assistant connection unavailable";
    } finally {
      isLoadingStatus = false;
      updateSendState();
    }
  }

  function safeLink(rawUrl, label, container) {
    try {
      const url = new URL(rawUrl, window.location.origin);
      if (url.protocol !== "https:" && url.protocol !== "http:") return;
      const link = document.createElement("a");
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = label;
      container.appendChild(link);
    } catch (error) {
      return;
    }
  }

  function addJobResults(data) {
    emptyState.hidden = true;
    const article = document.createElement("article");
    article.className = "ai-msg ai-msg--assistant";
    const body = document.createElement("div");
    body.className = "ai-msg-body";
    const summary = document.createElement("p");
    summary.textContent = data.message || `Found ${data.total || 0} verified jobs.`;
    body.appendChild(summary);

    const results = Array.isArray(data.results) ? data.results : [];
    if (results.length) {
      const cards = document.createElement("div");
      cards.className = "ai-job-results";
      results.forEach((job) => {
        const card = document.createElement("section");
        card.className = "ai-job-card";
        const title = document.createElement("h3");
        title.textContent = job.title || "Government job";
        card.appendChild(title);
        const meta = document.createElement("p");
        meta.textContent = [job.organization, job.qualification, job.location]
          .filter(Boolean)
          .join(" · ");
        if (meta.textContent) card.appendChild(meta);
        safeLink(job.official_notification_url, "Official notice", card);
        safeLink(job.application_url, "Apply online", card);
        cards.appendChild(card);
      });
      body.appendChild(cards);
    }
    article.appendChild(body);
    messages.appendChild(article);
    scrollToLatest();
  }

  async function sendMessage(text) {
    if (!text || isSending) return;
    if (!isAuthenticated) {
      window.location.assign(loginUrl());
      return;
    }
    const selectedModel = currentMode === "chat" ? selectedModelEntry() : null;
    if (currentMode === "chat" && !selectedModel) {
      setModelMessage("Select a configured provider/model pair.", true);
      return;
    }
    // An unchecked model is still usable: the backend verifies the exact
    // provider/model pair and reports a real error. Only a model whose provider
    // credentials are unusable is blocked up front.
    if (selectedModel && !selectedModel.configured) {
      setModelMessage(`${selectedModel.availability}: ${selectedModel.message}`, true);
      return;
    }

    addMessage("user", text, false);
    input.value = "";
    input.style.height = "auto";
    isSending = true;
    typing.hidden = false;
    typingLabel.textContent = currentMode === "chat" ? "Thinking" : "Searching verified jobs";
    updateSendState();

    try {
      const isJobSearch = currentMode === "jobs";
      const response = await fetch(isJobSearch ? "/api/ai/jobs/" : "/api/ai/chat/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
          "Accept": "application/json",
        },
        body: JSON.stringify(
          isJobSearch
            ? { query: text, page: 1, limit: 8 }
            : {
              message: text,
              history,
              // ``config_id`` is the stable registry identity: it selects the
              // exact configured account even when two accounts share a model.
              config_id: selectedModel.id,
              provider: selectedModel.provider,
              model: selectedModel.model,
            }
        ),
      });
      const data = await response.json().catch(() => ({}));
      if (response.status === 401) {
        isAuthenticated = false;
        window.location.assign(data.login_url || loginUrl());
        return;
      }
      if (!response.ok || data.status === "error") {
        if (data.code === "invalid_model") await fetchModels();
        if (data.code === "provider_error" && selectedModel) {
          // Reflect the real provider verdict instead of leaving a stale status.
          Object.assign(selectedModel, {
            status: data.category || selectedModel.status,
            availability: data.availability || selectedModel.availability,
            message: data.error || "The provider rejected this request.",
          });
          updateSelectedModelOption(selectedModel);
          setSelectedModelState();
        }
        throw new Error(data.error || "The assistant could not complete your request. Please try again.");
      }
      if (isJobSearch && data.status === "success") {
        addJobResults(data);
      } else if (data.status === "success") {
        addMessage("assistant", data.reply || "No response was returned.", false);
        history.push({ role: "user", content: text });
        history.push({ role: "model", content: data.reply || "" });
        history = history.slice(-12);
      } else if (data.status === "disabled" || data.status === "unconfigured") {
        addMessage("assistant", data.reply || "The assistant is currently unavailable.", true);
      } else {
        throw new Error("The assistant returned an unexpected response. Please try again.");
      }
    } catch (error) {
      addMessage("assistant", error.message, true);
    } finally {
      isSending = false;
      typing.hidden = true;
      updateSendState();
      scrollToLatest();
    }
  }

  function setMode(mode) {
    currentMode = mode;
    const isChat = mode === "chat";
    chatTab.classList.toggle("is-active", isChat);
    jobsTab.classList.toggle("is-active", !isChat);
    chatTab.setAttribute("aria-pressed", String(isChat));
    jobsTab.setAttribute("aria-pressed", String(!isChat));
    modelRow.hidden = !isChat;
    input.placeholder = isChat
      ? "Message AI Assistant..."
      : "Search verified government jobs...";
    emptyTitle.textContent = isChat
      ? "How can I help you today?"
      : "Find verified government jobs";
    emptyDescription.textContent = isChat
      ? "Ask a question to start a conversation."
      : "Search current, verified listings from the site database.";
  }

  function resetConversation() {
    history = [];
    messages.replaceChildren();
    emptyState.hidden = false;
    setMode("chat");
    input.value = "";
    input.style.height = "auto";
    updateSendState();
  }

  toggle.addEventListener("click", () => setPanelOpen(panel.hidden));
  close.addEventListener("click", () => setPanelOpen(false));
  reset.addEventListener("click", resetConversation);
  chatTab.addEventListener("click", () => setMode("chat"));
  jobsTab.addEventListener("click", () => setMode("jobs"));
  modelRetry.addEventListener("click", () => loadStatus());
  modelSelect.addEventListener("change", () => {
    persistSelectedModel();
    setSelectedModelState();
    if (modelSelect.selectedOptions.length) {
      const selected = selectedModelEntry();
      statusText.textContent = selected
        ? `${selected.provider_label} · ${selected.model}`
        : modelSelect.selectedOptions[0].textContent;
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = `${Math.min(input.scrollHeight, 144)}px`;
    updateSendState();
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (!send.disabled) sendMessage(input.value.trim());
    }
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!send.disabled) sendMessage(input.value.trim());
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !panel.hidden) setPanelOpen(false);
  });

  updateSendState();
  loadStatus();
})();
