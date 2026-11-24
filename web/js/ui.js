/* 通用 UI 工具：图标、格式化、弹窗、Toast */

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const TYPE_LABELS = {
  release: "正式版",
  snapshot: "快照",
  old_beta: "远古 Beta",
  old_alpha: "远古 Alpha",
  special: "特殊版本",
};

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

export function icon(name, className = "ico") {
  return `<svg class="${className}" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
}

export function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => {
    el.innerHTML = icon(el.dataset.icon, "ico");
  });
}

export function fmtBytes(bytes, digits = 1) {
  const value = Number(bytes);
  if (!Number.isFinite(value) || value < 0) return "—";
  if (value === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let index = 0;
  let size = value;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return index === 0 ? `${Math.round(size)} B` : `${size.toFixed(size >= 100 ? 0 : digits)} ${units[index]}`;
}

export function fmtSpeed(bytesPerSecond) {
  const value = Number(bytesPerSecond);
  if (!value || value < 1) return "—";
  return `${fmtBytes(value)}/s`;
}

export function fmtDuration(seconds) {
  const value = Math.max(0, Math.round(Number(seconds) || 0));
  if (value < 60) return `${value} 秒`;
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  if (minutes < 60) return `${minutes} 分 ${rest} 秒`;
  return `${Math.floor(minutes / 60)} 时 ${minutes % 60} 分`;
}

export function parseDate(value) {
  if (!value) return null;
  if (typeof value === "number") return new Date(value);
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function fmtDate(value) {
  const date = parseDate(value);
  if (!date) return "—";
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function timeAgo(value) {
  const date = parseDate(value);
  if (!date) return "—";
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.floor(diff / 86400)} 天前`;
  return fmtDate(date);
}

export function typeLabel(type) {
  return TYPE_LABELS[type] || type || "未知";
}

export function typeBadge(type) {
  const cls = TYPE_LABELS[type] ? type : "special";
  return `<span class="badge ${cls}">${esc(typeLabel(type))}</span>`;
}

export function cubeTile(type = "release", size = "") {
  const cls = TYPE_LABELS[type] ? type : "release";
  return `<div class="cube-tile ${cls}" ${size ? `style="width:${size}px;height:${size}px"` : ""}>${icon("cube")}</div>`;
}

export function logoBadge() {
  return `<svg viewBox="0 0 48 48" aria-hidden="true">
    <defs>
      <linearGradient id="logoBg2" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#2f5bea"/><stop offset="1" stop-color="#6f9bff"/>
      </linearGradient>
    </defs>
    <rect x="1" y="1" width="46" height="46" rx="14" fill="url(#logoBg2)"/>
    <rect x="1" y="1" width="46" height="46" rx="14" fill="none" stroke="rgba(255,255,255,.2)"/>
    <path d="M13 11h9v26h-6V17H13z" fill="#fff"/>
    <path d="M22 11h9.5a7 7 0 0 1 0 14H22z" fill="#fff"/>
    <rect x="25" y="14" width="6" height="8" rx="1" fill="#2f5bea"/>
    <rect x="13" y="31" width="6" height="6" fill="#ffb23f"/>
  </svg>`;
}

export function grassBlockSvg() {
  return `<svg viewBox="0 0 260 270" role="img" aria-label="Minecraft 草方块">
    <defs>
      <linearGradient id="gbTop" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="#9ade6b"/><stop offset="1" stop-color="#5fb43a"/>
      </linearGradient>
      <linearGradient id="gbLeft" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#a9744c"/><stop offset="1" stop-color="#79502f"/>
      </linearGradient>
      <linearGradient id="gbRight" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#8b5f3c"/><stop offset="1" stop-color="#5f3d23"/>
      </linearGradient>
    </defs>
    <ellipse cx="130" cy="246" rx="96" ry="15" fill="rgba(0,0,0,.35)"/>
    <polygon points="130,37 226,86 130,135 34,86" fill="url(#gbTop)"/>
    <polygon points="34,86 130,135 130,234 34,185" fill="url(#gbLeft)"/>
    <polygon points="226,86 130,135 130,234 226,185" fill="url(#gbRight)"/>
    <polygon points="34,86 130,135 130,151 34,102" fill="#65b53e"/>
    <polygon points="226,86 130,135 130,151 226,102" fill="#4f9a30"/>
    <rect x="70" y="84" width="7" height="7" fill="#8bd35f" opacity=".8"/>
    <rect x="150" y="60" width="9" height="9" fill="#b5e88e" opacity=".55"/>
    <rect x="188" y="92" width="6" height="6" fill="#4c8f2b" opacity=".7"/>
    <rect x="96" y="112" width="6" height="6" fill="#7cc44e" opacity=".6"/>
    <rect x="48" y="126" width="10" height="10" fill="#6b4427" opacity=".5"/>
    <rect x="162" y="176" width="12" height="12" fill="#4b2e19" opacity=".55"/>
    <rect x="62" y="158" width="8" height="8" fill="#a9744c" opacity=".5"/>
    <rect x="188" y="142" width="8" height="8" fill="#3f2715" opacity=".5"/>
    <polygon points="196,34 222,47 196,60 170,47" fill="#b5e88e"/>
    <polygon points="170,47 196,60 196,80 170,67" fill="#7cbf4e"/>
    <polygon points="222,47 196,60 196,80 222,67" fill="#63a93b"/>
    <polygon points="45,196 68,207 45,219 22,207" fill="#a9744c"/>
    <polygon points="22,207 45,219 45,238 22,226" fill="#79502f"/>
    <polygon points="68,207 45,219 45,238 68,226" fill="#5f3d23"/>
    <circle cx="234" cy="24" r="2" fill="#ffd37f" opacity=".9"/>
    <circle cx="24" cy="44" r="1.6" fill="#8fb4ff" opacity=".9"/>
    <circle cx="244" cy="140" r="2.2" fill="#fff" opacity=".5"/>
  </svg>`;
}

/* ---------- Toast ---------- */
let toastSeq = 0;
export function toast(message, type = "info", duration = 3600) {
  const root = $("#toasts");
  if (!root) return;
  const id = ++toastSeq;
  const iconName = type === "success" ? "check" : type === "error" ? "warning" : "spark";
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.dataset.id = id;
  el.innerHTML = `<div class="t-icon">${icon(iconName, "ico")}</div><div class="t-text">${esc(message)}</div>`;
  root.appendChild(el);
  const remove = () => {
    if (!el.isConnected) return;
    el.classList.add("out");
    setTimeout(() => el.remove(), 260);
  };
  el.addEventListener("click", remove);
  setTimeout(remove, duration);
}

/* ---------- 弹窗 ---------- */
export function modal({
  title,
  subtitle = "",
  iconName = "spark",
  tone = "",
  wide = false,
  slim = false,
  body = null,
  footer = null,
  onClose = null,
  locked = false,
  closeLabel = "关闭",
} = {}) {
  const root = $("#modalRoot");
  const backdrop = document.createElement("div");
  backdrop.className = "modal-backdrop";
  backdrop.innerHTML = `
    <div class="modal ${wide ? "wide" : ""} ${slim ? "slim" : ""}" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <div class="modal-head">
        <div class="m-icon ${tone}">${icon(iconName, "ico-lg")}</div>
        <div class="m-title"><h3></h3><p></p></div>
        <button class="icon-btn m-close" type="button" title="${esc(closeLabel)}">${icon("x", "ico")}</button>
      </div>
      <div class="modal-body"></div>
      <div class="modal-foot"></div>
    </div>`;
  const modalEl = $(".modal", backdrop);
  const bodyEl = $(".modal-body", backdrop);
  const footEl = $(".modal-foot", backdrop);
  const titleEl = $(".m-title h3", backdrop);
  const subEl = $(".m-title p", backdrop);
  const closeBtn = $(".m-close", backdrop);
  titleEl.textContent = title;
  subEl.textContent = subtitle;
  if (!subtitle) subEl.style.display = "none";

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    document.removeEventListener("keydown", onKey, true);
    backdrop.style.animation = "fade-in .18s ease reverse both";
    setTimeout(() => {
      backdrop.remove();
      if (typeof onClose === "function") onClose();
    }, 160);
  };
  const onKey = (event) => {
    if (event.key === "Escape") { event.stopPropagation(); close(); }
  };
  document.addEventListener("keydown", onKey, true);
  closeBtn.addEventListener("click", close);
  backdrop.addEventListener("mousedown", (event) => {
    if (event.target === backdrop && !locked) close();
  });

  function setBody(content) {
    bodyEl.replaceChildren();
    if (content == null) return;
    if (typeof content === "string") bodyEl.innerHTML = content;
    else bodyEl.appendChild(content);
  }
  function setFooter(content) {
    footEl.replaceChildren();
    if (content == null) return;
    if (typeof content === "string") footEl.innerHTML = content;
    else footEl.appendChild(content);
  }
  function setHead({ title: newTitle, subtitle: newSubtitle, iconName: newIcon, tone: newTone }) {
    if (newTitle !== undefined) titleEl.textContent = newTitle;
    if (newSubtitle !== undefined) subEl.textContent = newSubtitle;
    if (newIcon) {
      const holder = $(".m-icon", backdrop);
      holder.className = `m-icon ${newTone ?? tone}`;
      holder.innerHTML = icon(newIcon, "ico-lg");
    }
  }

  if (body != null) setBody(body);
  if (footer != null) setFooter(footer);
  root.appendChild(backdrop);
  setTimeout(() => closeBtn.focus({ preventScroll: true }), 80);
  return { backdrop, el: modalEl, body: bodyEl, footer: footEl, close, setBody, setFooter, setHead };
}

export function confirmDialog({
  title,
  message,
  confirmText = "确认",
  cancelText = "取消",
  danger = false,
  iconName = "warning",
} = {}) {
  return new Promise((resolve) => {
    let settled = false;
    const body = document.createElement("div");
    body.className = "disclaimer";
    body.style.cssText = "background:#fff;border-style:solid;color:#344054;font-size:12.5px";
    body.textContent = message;
    const footer = document.createElement("div");
    footer.className = "modal-foot";
    footer.style.cssText = "border:0;background:none;padding:0;margin-top:4px";
    footer.innerHTML = `
      <div class="spacer"></div>
      <button class="btn btn-light" data-cancel>${esc(cancelText)}</button>
      <button class="btn ${danger ? "btn-danger" : "btn-primary"}" data-confirm>${esc(confirmText)}</button>`;
    const shell = modal({ title, iconName, tone: danger ? "err" : "warn", slim: true, body, footer, onClose: () => { if (!settled) { settled = true; resolve(false); } } });
    footer.querySelector("[data-cancel]").addEventListener("click", () => { settled = true; resolve(false); shell.close(); });
    footer.querySelector("[data-confirm]").addEventListener("click", () => { settled = true; resolve(true); shell.close(); });
  });
}

export function debounce(fn, delay = 220) {
  let timer = 0;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch { ok = false; }
    area.remove();
    return ok;
  }
}

export function openExternal(url) {
  window.open(url, "_blank", "noopener,noreferrer");
}
