// ── State ────────────────────────────────────────────────
const state = {
  deviceId: null,
  ws: null,
  devices: [],
  selectedFile: null,
  selectedMode: "fast_transfer",
  transferFilter: "all",
  clips: [],
  transfers: [],
  reconnectDelay: 1000,
  pingInterval: null,
  currentFolder: "/",
  folders: ["/"],
  renameTargetId: null,
};

// ── DOM refs ────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const statusDot = $("#status-dot");
const statusText = $("#status-text");
const deviceList = $("#device-list");
const deviceCount = $("#device-count");
const noDevices = $("#no-devices");
const dropZone = $("#drop-zone");
const fileInput = $("#file-input");
const sendPreview = $("#send-preview");
const sendFilename = $("#send-filename");
const sendMeta = $("#send-meta");
const sendBtn = $("#send-btn");
const sendCancel = $("#send-cancel");
const sendProgress = $("#send-progress");
const sendProgressFill = $("#send-progress-fill");
const transferList = $("#transfer-list");
const noTransfers = $("#no-transfers");
const refreshTransfersBtn = $("#refresh-transfers");
const toastContainer = $("#toast-container");
const modeFastBtn = $("#mode-fast");
const modeStorageBtn = $("#mode-storage");
const transferTabs = $("#transfer-tabs");
const folderBar = $("#folder-bar");
const breadcrumb = $("#breadcrumb");
const newFolderBtn = $("#new-folder-btn");
const deleteFolderBtn = $("#delete-folder-btn");
const renameModal = $("#rename-modal");
const renameInput = $("#rename-input");
const renameConfirm = $("#rename-confirm");
const renameCancel = $("#rename-cancel");
const folderModal = $("#folder-modal");
const folderNameInput = $("#folder-name-input");
const folderConfirm = $("#folder-confirm");
const folderCancel = $("#folder-cancel");
const sendFolderSelect = $("#send-folder-select");
const clipInput = $("#clip-input");
const clipShareBtn = $("#clip-share-btn");
const clipList = $("#clip-list");
const clipCount = $("#clip-count");
const noClips = $("#no-clips");
const notifyInput = $("#notify-input");
const notifyTarget = $("#notify-target");
const notifySendBtn = $("#notify-send-btn");
const notifyPermissionBtn = $("#notify-permission-btn");

// ── Utilities ───────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  const val = bytes / Math.pow(1024, i);
  return `${val.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function timeAgo(isoString) {
  const diff = Date.now() - new Date(isoString).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// ── Toast notifications ─────────────────────────────────
function toast(message, durationMs = 4000) {
  const el = document.createElement("div");
  el.className = "toast";
  el.textContent = message;
  toastContainer.appendChild(el);
  setTimeout(() => {
    el.classList.add("toast-exit");
    el.addEventListener("animationend", () => el.remove());
  }, durationMs);
}

// ── Connection status ───────────────────────────────────
function setConnected(connected) {
  statusDot.classList.toggle("connected", connected);
  statusText.textContent = connected ? "Connected" : "Disconnected";
}

// ── Device name ─────────────────────────────────────────
function getDeviceName() {
  let name = localStorage.getItem("boobiki_device_name");
  if (!name) {
    const ua = navigator.userAgent;
    if (/Mobile|Android/i.test(ua)) {
      name = "Phone";
    } else if (/Tablet|iPad/i.test(ua)) {
      name = "Tablet";
    } else {
      name = "Browser";
    }
    name += " " + Math.random().toString(36).substring(2, 6);
    localStorage.setItem("boobiki_device_name", name);
  }
  return name;
}

// ── Folder helpers ──────────────────────────────────────
async function fetchFolders() {
  try {
    const res = await fetch("/api/folders");
    if (!res.ok) return;
    state.folders = await res.json();
    renderFolderSelect();
    renderBreadcrumb();
  } catch { /* silent */ }
}

function renderFolderSelect() {
  sendFolderSelect.innerHTML = "";
  for (const f of state.folders) {
    const opt = document.createElement("option");
    opt.value = f;
    opt.textContent = f;
    sendFolderSelect.appendChild(opt);
  }
  sendFolderSelect.classList.toggle("hidden", state.selectedMode !== "storage");
}

function renderBreadcrumb() {
  breadcrumb.innerHTML = "";
  const parts = state.currentFolder.split("/").filter(Boolean);
  // Root segment
  if (parts.length === 0) {
    const span = document.createElement("span");
    span.className = "breadcrumb-segment current";
    span.textContent = "/";
    breadcrumb.appendChild(span);
    return;
  }
  const rootBtn = document.createElement("button");
  rootBtn.className = "breadcrumb-segment";
  rootBtn.textContent = "/";
  rootBtn.addEventListener("click", () => navigateToFolder("/"));
  breadcrumb.appendChild(rootBtn);

  parts.forEach((part, i) => {
    const sep = document.createElement("span");
    sep.className = "breadcrumb-separator";
    sep.textContent = ">";
    breadcrumb.appendChild(sep);

    const isLast = i === parts.length - 1;
    if (isLast) {
      const span = document.createElement("span");
      span.className = "breadcrumb-segment current";
      span.textContent = part;
      breadcrumb.appendChild(span);
    } else {
      const btn = document.createElement("button");
      btn.className = "breadcrumb-segment";
      btn.textContent = part;
      const path = "/" + parts.slice(0, i + 1).join("/");
      btn.addEventListener("click", () => navigateToFolder(path));
      breadcrumb.appendChild(btn);
    }
  });
}

function navigateToFolder(path) {
  state.currentFolder = path;
  renderBreadcrumb();
  fetchTransfers();
}

function getSubFolders() {
  const prefix = state.currentFolder === "/" ? "/" : state.currentFolder + "/";
  return state.folders.filter(f => {
    if (f === state.currentFolder) return false;
    if (!f.startsWith(prefix)) return false;
    const rest = f.slice(prefix.length);
    return rest.length > 0 && !rest.includes("/");
  });
}

// ── Mode toggle ─────────────────────────────────────────
function setMode(mode) {
  state.selectedMode = mode;
  modeFastBtn.classList.toggle("active", mode === "fast_transfer");
  modeStorageBtn.classList.toggle("active", mode === "storage");
  sendFolderSelect.classList.toggle("hidden", mode !== "storage");
}

modeFastBtn.addEventListener("click", () => setMode("fast_transfer"));
modeStorageBtn.addEventListener("click", () => setMode("storage"));

// ── WebSocket ───────────────────────────────────────────
function connectWS() {
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const ws = new WebSocket(`${proto}//${location.host}/ws`);
  state.ws = ws;

  ws.addEventListener("open", () => {
    ws.send(JSON.stringify({ type: "register", name: getDeviceName() }));
  });

  ws.addEventListener("message", (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }
    handleWSMessage(msg);
  });

  ws.addEventListener("close", () => {
    setConnected(false);
    clearInterval(state.pingInterval);
    state.pingInterval = null;
    setTimeout(() => {
      connectWS();
    }, state.reconnectDelay);
    state.reconnectDelay = Math.min(state.reconnectDelay * 2, 15000);
  });

  ws.addEventListener("error", () => {
    // close event will fire next; handled there
  });
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case "registered":
      state.deviceId = msg.device_id;
      state.reconnectDelay = 1000;
      setConnected(true);
      startPing();
      fetchDevices();
      fetchTransfers();
      fetchFolders();
      fetchClips();
      break;

    case "clip_added":
      toast(`New clip: "${msg.text.substring(0, 50)}${msg.text.length > 50 ? '...' : ''}"`);
      fetchClips();
      break;

    case "device_joined":
      if (msg.device_id !== state.deviceId) {
        if (!state.devices.find((d) => d.id === msg.device_id)) {
          state.devices.push({
            id: msg.device_id,
            name: msg.name,
            device_type: "browser",
          });
          renderDevices();
        }
        toast(`${msg.name} joined`);
      }
      break;

    case "device_left":
      state.devices = state.devices.filter((d) => d.id !== msg.device_id);
      renderDevices();
      toast(`${msg.name} left`);
      break;

    case "transfer_ready":
      toast(
        `New file: ${msg.filename} (${formatBytes(msg.size)}) [${msg.mode === "storage" ? "Storage" : "Fast"}]`
      );
      fetchTransfers();
      break;

    case "transfer_updated":
      fetchTransfers();
      break;

    case "notification":
      if (Notification.permission === "granted" && document.hidden) {
        const notif = new Notification("Boobiki", {
          body: msg.text,
          icon: "/static/icons/icon-192.png",
          tag: "boobiki-notify",
        });
        notif.addEventListener("click", () => {
          window.focus();
          notif.close();
        });
      }
      toast(`\u{1F4E2} ${msg.text}`);
      break;

    case "pong":
      break;
  }
}

function startPing() {
  clearInterval(state.pingInterval);
  state.pingInterval = setInterval(() => {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 30000);
}

// ── REST: Clips ────────────────────────────────────────
async function fetchClips() {
  try {
    const res = await fetch("/api/clips");
    if (!res.ok) return;
    state.clips = await res.json();
    renderClips();
  } catch { /* silent */ }
}

function renderClips() {
  clipCount.textContent = state.clips.length ? `${state.clips.length} clip${state.clips.length > 1 ? "s" : ""}` : "";

  if (state.clips.length === 0) {
    noClips.classList.remove("hidden");
    clipList.querySelectorAll(".clip-item").forEach(el => el.remove());
    return;
  }

  noClips.classList.add("hidden");
  clipList.innerHTML = "";

  for (const clip of state.clips) {
    const li = document.createElement("li");
    li.className = "clip-item";
    li.innerHTML = `
      <div class="clip-content">
        <div class="clip-text">${escapeHtml(clip.text)}</div>
        <div class="clip-meta">${timeAgo(clip.created_at)}</div>
      </div>
      <div class="clip-actions">
        <button class="btn btn-ghost btn-small btn-copy" data-text="${escapeHtml(clip.text)}" data-id="${clip.id}">Copy</button>
        <button class="btn btn-ghost btn-small btn-delete" data-clip-id="${clip.id}">Delete</button>
      </div>
    `;
    clipList.appendChild(li);
  }
}

async function shareClip() {
  const text = clipInput.value.trim();
  if (!text || !state.deviceId) return;

  try {
    const res = await fetch("/api/clips", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, uploader_id: state.deviceId }),
    });
    if (res.ok) {
      clipInput.value = "";
      clipShareBtn.disabled = true;
      toast("Clip shared");
      fetchClips();
    } else {
      toast("Share failed");
    }
  } catch { toast("Share failed"); }
}

// ── REST: Devices ───────────────────────────────────────
async function fetchDevices() {
  try {
    const res = await fetch("/api/devices");
    if (!res.ok) return;
    const all = await res.json();
    state.devices = all.filter((d) => d.id !== state.deviceId);
    renderDevices();
  } catch {
    // Silently fail; devices will be populated by WS events
  }
}

function renderDevices() {
  const filtered = state.devices;
  deviceCount.textContent = filtered.length
    ? `${filtered.length} device${filtered.length > 1 ? "s" : ""}`
    : "";

  if (filtered.length === 0) {
    noDevices.classList.remove("hidden");
    deviceList.querySelectorAll(".device-item").forEach((el) => el.remove());
    return;
  }

  noDevices.classList.add("hidden");
  deviceList.innerHTML = "";

  for (const device of filtered) {
    const li = document.createElement("li");
    li.className = "device-item";
    li.dataset.id = device.id;

    const icon =
      device.device_type === "server" ? "&#128421;" : "&#128187;";

    li.innerHTML = `
      <div class="device-info">
        <span class="device-icon" aria-hidden="true">${icon}</span>
        <span class="device-name">${escapeHtml(device.name)}</span>
      </div>
      <span class="device-type">${device.device_type}</span>
    `;

    deviceList.appendChild(li);
  }

  updateNotifyTargets();
}

function updateNotifyTargets() {
  notifyTarget.innerHTML = '<option value="all">All Devices</option>';
  for (const d of state.devices) {
    const opt = document.createElement("option");
    opt.value = d.id;
    opt.textContent = d.name;
    notifyTarget.appendChild(opt);
  }
}

// ── REST: Transfers ─────────────────────────────────────
async function fetchTransfers() {
  try {
    let url = "/api/transfers";
    const params = new URLSearchParams();
    if (state.transferFilter !== "all") params.set("mode", state.transferFilter);
    if (state.transferFilter === "storage") params.set("folder", state.currentFolder);
    if (params.toString()) url += "?" + params.toString();
    const res = await fetch(url);
    if (!res.ok) return;
    state.transfers = await res.json();
    renderTransfers();
  } catch {
    // silent
  }
}

function renderTransfers() {
  transferList.innerHTML = "";

  // Render sub-folders first (Storage mode only)
  if (state.transferFilter === "storage") {
    const subFolders = getSubFolders();
    for (const f of subFolders) {
      const name = f.split("/").pop();
      const li = document.createElement("li");
      li.className = "folder-item";
      li.innerHTML = `<span class="folder-icon">📁</span><span class="folder-name">${escapeHtml(name)}</span>`;
      li.addEventListener("click", () => navigateToFolder(f));
      transferList.appendChild(li);
    }
  }

  if (state.transfers.length === 0 && (state.transferFilter !== "storage" || getSubFolders().length === 0)) {
    noTransfers.classList.remove("hidden");
    return;
  }
  noTransfers.classList.add("hidden");

  const sorted = [...state.transfers].sort(
    (a, b) => new Date(b.created_at) - new Date(a.created_at)
  );

  for (const t of sorted) {
    const li = document.createElement("li");
    li.className = "transfer-item";

    const canDownload = t.status === "ready" || t.status === "downloaded";

    li.innerHTML = `
      <div class="transfer-info">
        <div class="transfer-filename">${escapeHtml(t.filename)}</div>
        <div class="transfer-meta">
          <span>${formatBytes(t.size)}</span>
          <span>${timeAgo(t.created_at)}</span>
        </div>
      </div>
      <div class="transfer-actions" style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;">
        <span class="badge badge-mode-${t.mode}">${t.mode === 'fast_transfer' ? 'Fast' : 'Storage'}</span>
        <span class="badge badge-${t.status}">${t.status}</span>
        ${canDownload ? `<a href="/api/transfers/${t.id}/download" class="btn btn-primary btn-small" download>Download</a>` : ''}
        <button class="btn btn-ghost btn-small btn-rename" data-id="${t.id}" data-filename="${escapeHtml(t.filename)}">Rename</button>
        ${t.mode === 'storage' ? `
          <select class="move-select" data-id="${t.id}">
            ${state.folders.map(f => `<option value="${escapeHtml(f)}" ${f === t.folder ? 'selected' : ''}>${escapeHtml(f)}</option>`).join('')}
          </select>
        ` : ''}
        <button class="btn btn-ghost btn-small btn-delete" data-id="${t.id}">Delete</button>
      </div>
    `;

    transferList.appendChild(li);
  }
}

// ── Transfer filter tabs ────────────────────────────────
transferTabs.addEventListener("click", (e) => {
  const btn = e.target.closest(".tab-btn");
  if (!btn) return;
  state.transferFilter = btn.dataset.filter;
  transferTabs
    .querySelectorAll(".tab-btn")
    .forEach((b) => b.classList.toggle("active", b === btn));

  const isStorage = state.transferFilter === "storage";
  folderBar.classList.toggle("hidden", !isStorage);
  if (isStorage) {
    fetchFolders();
  } else {
    state.currentFolder = "/";
  }
  fetchTransfers();
});

// ── Transfer list click handler (rename + delete) ───────
transferList.addEventListener("click", async (e) => {
  const renameBtn = e.target.closest(".btn-rename");
  if (renameBtn) {
    state.renameTargetId = renameBtn.dataset.id;
    renameInput.value = renameBtn.dataset.filename;
    renameModal.classList.remove("hidden");
    renameInput.focus();
    renameInput.select();
    return;
  }

  const deleteBtn = e.target.closest(".btn-delete");
  if (!deleteBtn) return;
  const id = deleteBtn.dataset.id;
  try {
    const res = await fetch(`/api/transfers/${id}`, { method: "DELETE" });
    if (res.ok) {
      toast("File deleted");
      fetchTransfers();
    } else {
      toast("Delete failed");
    }
  } catch {
    toast("Delete failed");
  }
});

// ── Move handler (event delegation) ─────────────────────
transferList.addEventListener("change", async (e) => {
  const select = e.target.closest(".move-select");
  if (!select) return;
  try {
    const res = await fetch(`/api/transfers/${select.dataset.id}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({folder: select.value}),
    });
    if (res.ok) { toast("File moved"); fetchTransfers(); }
    else { toast("Move failed"); }
  } catch { toast("Move failed"); }
});

// ── Rename modal handlers ───────────────────────────────
renameConfirm.addEventListener("click", async () => {
  if (!state.renameTargetId || !renameInput.value.trim()) return;
  try {
    const res = await fetch(`/api/transfers/${state.renameTargetId}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({filename: renameInput.value.trim()}),
    });
    if (res.ok) { toast("File renamed"); fetchTransfers(); }
    else { const data = await res.json(); toast(data.detail || "Rename failed"); }
  } catch { toast("Rename failed"); }
  renameModal.classList.add("hidden");
  state.renameTargetId = null;
});

renameCancel.addEventListener("click", () => {
  renameModal.classList.add("hidden");
  state.renameTargetId = null;
});

renameModal.addEventListener("click", (e) => {
  if (e.target === renameModal) {
    renameModal.classList.add("hidden");
    state.renameTargetId = null;
  }
});

// ── Folder modal handlers ───────────────────────────────
newFolderBtn.addEventListener("click", () => {
  folderNameInput.value = "";
  folderModal.classList.remove("hidden");
  folderNameInput.focus();
});

folderConfirm.addEventListener("click", async () => {
  const name = folderNameInput.value.trim();
  if (!name) return;
  const path = state.currentFolder === "/" ? "/" + name : state.currentFolder + "/" + name;
  try {
    const res = await fetch("/api/folders", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({path}),
    });
    if (res.ok) { toast("Folder created"); fetchFolders(); fetchTransfers(); }
    else { const data = await res.json(); toast(data.detail || "Create failed"); }
  } catch { toast("Create failed"); }
  folderModal.classList.add("hidden");
});

folderCancel.addEventListener("click", () => folderModal.classList.add("hidden"));
folderModal.addEventListener("click", (e) => { if (e.target === folderModal) folderModal.classList.add("hidden"); });

// ── Delete folder handler ───────────────────────────────
deleteFolderBtn.addEventListener("click", async () => {
  if (state.currentFolder === "/") { toast("Cannot delete root folder"); return; }
  try {
    const res = await fetch(`/api/folders?path=${encodeURIComponent(state.currentFolder)}`, {method: "DELETE"});
    if (res.ok) {
      toast("Folder deleted");
      const parts = state.currentFolder.split("/").filter(Boolean);
      parts.pop();
      state.currentFolder = parts.length ? "/" + parts.join("/") : "/";
      fetchFolders();
      fetchTransfers();
    } else { const data = await res.json(); toast(data.detail || "Delete failed"); }
  } catch { toast("Delete failed"); }
});

// ── File selection & uploading ──────────────────────────
function updateSendButton() {
  sendBtn.disabled = !state.selectedFile;
}

function showFilePreview(file) {
  state.selectedFile = file;
  sendFilename.textContent = file.name;
  sendMeta.textContent = formatBytes(file.size);
  sendPreview.classList.remove("hidden");
  sendProgress.classList.add("hidden");
  sendProgressFill.style.width = "0%";
  updateSendButton();
}

function clearFileSelection() {
  state.selectedFile = null;
  fileInput.value = "";
  sendPreview.classList.add("hidden");
  updateSendButton();
}

async function uploadFile() {
  if (!state.selectedFile || !state.deviceId) return;

  sendBtn.disabled = true;
  sendProgress.classList.remove("hidden");

  const form = new FormData();
  form.append("uploader_id", state.deviceId);
  form.append("mode", state.selectedMode);
  form.append("file", state.selectedFile);
  if (state.selectedMode === "storage") {
    form.append("folder", sendFolderSelect.value);
  }

  try {
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/transfers");

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const pct = Math.round((e.loaded / e.total) * 100);
          sendProgressFill.style.width = `${pct}%`;
        }
      });

      xhr.addEventListener("load", () => {
        if (xhr.status === 201) {
          resolve();
        } else {
          reject(new Error(`Upload failed: ${xhr.status}`));
        }
      });

      xhr.addEventListener("error", () => reject(new Error("Network error")));
      xhr.send(form);
    });

    toast("File uploaded successfully");
    clearFileSelection();
    fetchTransfers();
  } catch (err) {
    toast(`Upload failed: ${err.message}`);
    sendBtn.disabled = false;
  }
}

// Drop zone events
dropZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  dropZone.classList.add("drag-over");
});

dropZone.addEventListener("dragleave", () => {
  dropZone.classList.remove("drag-over");
});

dropZone.addEventListener("drop", (e) => {
  e.preventDefault();
  dropZone.classList.remove("drag-over");
  const file = e.dataTransfer.files[0];
  if (file) showFilePreview(file);
});

fileInput.addEventListener("change", () => {
  const file = fileInput.files[0];
  if (file) showFilePreview(file);
});

sendBtn.addEventListener("click", uploadFile);
sendCancel.addEventListener("click", clearFileSelection);
refreshTransfersBtn.addEventListener("click", fetchTransfers);

// ── Clipboard event handlers ───────────────────────────
clipInput.addEventListener("input", () => {
  clipShareBtn.disabled = !clipInput.value.trim();
});

clipShareBtn.addEventListener("click", shareClip);

clipInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    shareClip();
  }
});

clipList.addEventListener("click", async (e) => {
  const copyBtn = e.target.closest(".btn-copy");
  if (copyBtn) {
    const clipId = copyBtn.dataset.id;
    const clip = state.clips.find(c => c.id === clipId);
    if (clip) {
      try {
        await navigator.clipboard.writeText(clip.text);
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
      } catch {
        const ta = document.createElement("textarea");
        ta.value = clip.text;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        ta.remove();
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = "Copy"; }, 1500);
      }
    }
    return;
  }

  const deleteBtn = e.target.closest("[data-clip-id]");
  if (deleteBtn) {
    const id = deleteBtn.dataset.clipId;
    try {
      const res = await fetch(`/api/clips/${id}`, { method: "DELETE" });
      if (res.ok) { toast("Clip deleted"); fetchClips(); }
      else { toast("Delete failed"); }
    } catch { toast("Delete failed"); }
  }
});

// ── Notifications ──────────────────────────────────────
function initNotifications() {
  if (!("Notification" in window)) {
    notifyPermissionBtn.textContent = "Not supported";
    notifyPermissionBtn.disabled = true;
    return;
  }
  updatePermissionBtn();
}

function updatePermissionBtn() {
  if (Notification.permission === "granted") {
    notifyPermissionBtn.textContent = "Enabled";
    notifyPermissionBtn.disabled = true;
    notifyPermissionBtn.classList.add("btn-primary");
    notifyPermissionBtn.classList.remove("btn-ghost");
  } else if (Notification.permission === "denied") {
    notifyPermissionBtn.textContent = "Blocked";
    notifyPermissionBtn.disabled = true;
  } else {
    notifyPermissionBtn.textContent = "Enable";
    notifyPermissionBtn.disabled = false;
  }
}

notifyPermissionBtn.addEventListener("click", async () => {
  const result = await Notification.requestPermission();
  updatePermissionBtn();
  if (result === "granted") {
    toast("Notifications enabled");
  }
});

async function sendNotification() {
  const text = notifyInput.value.trim();
  if (!text) return;

  const targetValue = notifyTarget.value;
  const body = {
    text,
    target_device_id: targetValue === "all" ? null : targetValue,
  };

  try {
    const res = await fetch("/api/notifications", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (res.ok) {
      notifyInput.value = "";
      notifySendBtn.disabled = true;
      toast("Notification sent");
    } else {
      toast("Send failed");
    }
  } catch { toast("Send failed"); }
}

notifyInput.addEventListener("input", () => {
  notifySendBtn.disabled = !notifyInput.value.trim();
});

notifySendBtn.addEventListener("click", sendNotification);

notifyInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    sendNotification();
  }
});

// ── Service worker registration ─────────────────────────
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {
    // SW registration failed; app works fine without it
  });
}

// ── Bootstrap ───────────────────────────────────────────
connectWS();
initNotifications();
