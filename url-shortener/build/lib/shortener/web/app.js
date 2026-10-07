"use strict";
const element = (id) => document.getElementById(id);
let createdLink = null;
const reserved = new Set(["api", "health", "docs", "redoc", "openapi.json"]);

function message(id, text, isError = false) {
  const node = element(id);
  node.textContent = text;
  node.className = `message ${isError ? "error" : "success"}`;
}

async function api(path, options = {}) {
  let response;
  try {
    response = await fetch(path, { ...options, cache: "no-store" });
  } catch {
    throw new Error("Could not reach the service. Check that it is running, then try again.");
  }
  const data = await response.json();
  if (!response.ok) {
    const detail = data.error?.message || "The request could not be completed.";
    throw new Error(`${detail} (${response.status})`);
  }
  return data;
}

function localTime(value) {
  return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "long" });
}

async function lookup(code) {
  const button = element("stats-button");
  button.disabled = true;
  element("stats-result").hidden = true;
  element("stats-empty").hidden = true;
  message("stats-message", "Loading statistics…");
  try {
    const data = await api(`/api/urls/${encodeURIComponent(code)}/stats`);
    element("clicks").textContent = data.clicks.toLocaleString();
    element("stats-destination").textContent = data.destination;
    element("stats-created").textContent = localTime(data.created_at);
    element("stats-expiration").textContent = data.expires_at ? localTime(data.expires_at) : "Never";
    const expired = data.expires_at && Date.now() >= Date.parse(data.expires_at);
    element("link-status").textContent = expired ? "Expired" : "Active";
    element("link-status").className = `badge${expired ? " expired" : ""}`;
    element("stats-result").hidden = false;
    message("stats-message", `Statistics for ${data.code}`);
  } catch (error) {
    message("stats-message", error.message, true);
  } finally {
    button.disabled = false;
  }
}

element("create-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const destination = element("destination").value.trim();
  const alias = element("alias").value.trim();
  const expiration = element("expiration").value;
  element("created-result").hidden = true;
  createdLink = null;
  message("create-message", "");
  const body = { destination };
  try {
    const url = new URL(destination);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) {
      throw new Error("Use an http:// or https:// destination without embedded credentials.");
    }
    if (alias) {
      if (reserved.has(alias)) throw new Error("That alias is reserved. Please choose another.");
      body.alias = alias;
    }
    if (expiration) {
      const instant = new Date(expiration);
      if (!Number.isFinite(instant.getTime()) || instant.getTime() <= Date.now()) {
        throw new Error("Choose an expiration in the future, using your local time.");
      }
      body.expires_at = instant.toISOString();
    }
  } catch (error) {
    message("create-message", error instanceof TypeError ? "Enter a valid absolute http:// or https:// URL." : error.message, true);
    return;
  }
  const button = element("create-button");
  button.disabled = true;
  message("create-message", "Creating your link…");
  try {
    const data = await api("/api/urls", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    createdLink = data;
    element("created-link").textContent = data.short_url;
    element("created-link").href = data.short_url;
    element("created-result").hidden = false;
    element("copy-button").textContent = "Copy";
    message("create-message", "Short link created.");
  } catch (error) {
    message("create-message", error.message, true);
  } finally {
    button.disabled = false;
  }
});

element("stats-form").addEventListener("submit", (event) => {
  event.preventDefault();
  lookup(element("stats-code").value.trim());
});

element("view-stats").addEventListener("click", () => {
  if (!createdLink) return;
  element("stats-code").value = createdLink.code;
  element("stats-code").focus();
  lookup(createdLink.code);
});

element("copy-button").addEventListener("click", async () => {
  if (!createdLink) return;
  try {
    await navigator.clipboard.writeText(createdLink.short_url);
    element("copy-button").textContent = "Copied!";
    message("create-message", "Short link copied to clipboard.");
  } catch {
    message("create-message", "Clipboard unavailable. Select the short link above and copy it manually.", true);
  }
});
