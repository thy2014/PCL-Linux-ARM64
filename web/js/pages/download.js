/* 下载页：版本列表 / Java 运行时 / 下载源 */
import { icon, esc, cubeTile, typeBadge, fmtBytes, typeLabel, debounce } from "../ui.js";

export function downloadPage(ctx) {
  const { state, actions } = ctx;
  if (!state.downloadUi) {
    state.downloadUi = { type: "release", query: "", source: state.settings?.download_source || "official" };
  }
  const ui = state.downloadUi;
  const versions = state.versions || [];
  const installedSet = new Set((state.installed || []).map((item) => item.id));
  const java = state.java || [];
  const bestJava = java[0] || null;
  const arch = state.app?.arch_label || "ARM64";
  const sourceLabel = ui.source === "bmclapi" ? "BMCLAPI 镜像" : "官方源";
  const missingMajor = [21, 17, 8].find((major) => !java.some((item) => item.major === major)) || 21;

  const count = (type) => versions.filter((item) => matchType(item, type)).length;
  const tabs = [
    ["release", "正式版", count("release")],
    ["snapshot", "快照", count("snapshot")],
    ["old", "远古版", count("old")],
    ["all", "全部", versions.length],
  ];

  const root = document.createElement("div");
  root.className = "page";
  root.innerHTML = `
    <div class="card page-toolbar">
      <div class="segmented" role="tablist">
        ${tabs.map(([type, label, total]) => `<button type="button" data-type="${type}" class="${ui.type === type ? "active" : ""}">${label} <span class="muted">${total}</span></button>`).join("")}
      </div>
      <div class="toolbar-right">
        <div class="search-box">${icon("search")}<input class="input" id="versionSearch" type="search" placeholder="搜索版本号，如 1.21.4" autocomplete="off"></div>
        <select class="select" id="sourceSelect" title="下载源">
          <option value="official" ${ui.source === "official" ? "selected" : ""}>官方源</option>
          <option value="bmclapi" ${ui.source === "bmclapi" ? "selected" : ""}>BMCLAPI 镜像</option>
        </select>
        <button class="icon-btn" id="refreshVersions" title="刷新版本列表">${icon("refresh")}</button>
      </div>
    </div>

    <div class="card loader-strip">
      <div class="loader-badge">${icon("plug")}</div>
      <div class="loader-copy">
        <strong>模组加载器</strong>
        <p>Fabric / Quilt 轻量快速，Forge / NeoForge 生态成熟；加载器需要依附一个已安装的原版或对应游戏版本。</p>
      </div>
      <div class="actions">
        <button class="btn btn-soft btn-sm" data-loader-install>${icon("download")}安装加载器</button>
        <button class="btn btn-light btn-sm" data-goto-versions>${icon("layers")}管理版本</button>
      </div>
    </div>

    <div class="card java-strip">
      <div class="java-badge">${icon("coffee")}</div>
      <div class="java-copy">
        ${bestJava
          ? `<strong>Java ${bestJava.major} · ${esc(bestJava.vendor)}</strong>
             <p>${esc(bestJava.version)} · ${esc(bestJava.path)}</p>`
          : `<strong>尚未检测到 Java 运行时</strong>
             <p>安装版本时可自动下载 Adoptium ${arch} JDK，也可以现在手动下载。</p>`}
      </div>
      <div class="actions">
        <button class="btn btn-soft btn-sm" data-java-major="${missingMajor}">${icon("download")}下载 Java ${missingMajor}</button>
        <button class="btn btn-light btn-sm" data-java-major="17">${icon("coffee")}Java 17</button>
        <button class="btn btn-light btn-sm" data-refresh-java>${icon("refresh")}重新检测</button>
      </div>
    </div>

    <div class="card version-list-card">
      <div class="list-head">
        <h3>版本列表</h3>
        <span class="count" id="versionCount">${state.versionsLoading ? "正在加载…" : `${versions.length} 个版本`}</span>
        <span class="spacer"></span>
        <span class="badge ${state.versionsError ? "warn" : "muted"}" id="sourceBadge">${esc(sourceLabel)}${state.versionsSource === "bmclapi" && ui.source === "bmclapi" ? " · 镜像" : ""}</span>
      </div>
      <div class="version-list" id="versionList"></div>
    </div>`;

  const listEl = root.querySelector("#versionList");
  const countEl = root.querySelector("#versionCount");
  const searchEl = root.querySelector("#versionSearch");

  searchEl.value = ui.query || "";

  function applyFilter({ resetScroll = false } = {}) {
    root.querySelectorAll("[data-type]").forEach((button) => {
      button.classList.toggle("active", button.dataset.type === ui.type);
    });
    if (!state.versions) {
      countEl.textContent = state.versionsLoading ? "正在加载…" : "尚未加载";
      listEl.innerHTML = state.versionsError
        ? `<div class="loading-row">${icon("warning")}<div style="margin-top:8px">${esc(state.versionsError)}</div><button class="btn btn-light btn-sm" data-retry style="margin:12px auto 0">${icon("refresh")}重试</button></div>`
        : `<div class="loading-row"><div class="spinner" style="margin:0 auto 10px"></div>正在从 Mojang 获取版本清单…</div>`;
      return;
    }
    const filtered = versions.filter((item) => {
      if (!matchType(item, ui.type)) return false;
      if (!ui.query) return true;
      return item.id.toLowerCase().includes(ui.query.toLowerCase());
    });
    countEl.textContent = `${filtered.length} / ${versions.length} 个版本`;
    if (!filtered.length) {
      listEl.innerHTML = `<div class="empty" style="padding:44px 20px"><div class="empty-art" style="width:72px;height:72px;opacity:.5">${icon("cube")}</div><h3>没有匹配的版本</h3><p>换个关键词，或者切换到“全部”分类。</p></div>`;
    } else {
      listEl.innerHTML = filtered.map((item) => {
        const isInstalled = installedSet.has(item.id);
        return `<div class="dl-row">
          ${cubeTile(item.type)}
          <div class="version-name">
            <strong>${esc(item.id)}</strong>
            <span>${esc(typeLabel(item.type))}${isInstalled ? " · 已安装" : ""}</span>
          </div>
          <div class="release-date">${esc(item.releaseDate || "—")}</div>
          <div class="type-cell">${typeBadge(item.type)}</div>
          <div class="action-cell">
            ${isInstalled
              ? `<button class="btn btn-soft btn-sm" data-manage="${esc(item.id)}">${icon("sliders")}管理</button>
                 <button class="btn btn-light btn-sm" data-launch="${esc(item.id)}">${icon("play")}启动</button>`
              : `<button class="btn btn-primary btn-sm" data-install="${esc(item.id)}">${icon("download")}安装</button>`}
          </div>
        </div>`;
      }).join("");
    }
    if (resetScroll) listEl.scrollTop = 0;
  }

  listEl.addEventListener("click", (event) => {
    const retry = event.target.closest("[data-retry]");
    if (retry) { actions.loadVersions(false, ui.source); return; }
    const install = event.target.closest("[data-install]");
    if (install) { actions.openInstall(install.dataset.install); return; }
    const launch = event.target.closest("[data-launch]");
    if (launch) actions.launch(launch.dataset.launch);
    const manage = event.target.closest("[data-manage]");
    if (manage) actions.openVersionManage(manage.dataset.manage);
  });

  const applySearch = debounce(() => {
    ui.query = searchEl.value.trim();
    applyFilter({ resetScroll: true });
  }, 160);
  searchEl.addEventListener("input", applySearch);

  root.querySelectorAll("[data-type]").forEach((button) => {
    button.addEventListener("click", () => {
      ui.type = button.dataset.type;
      applyFilter({ resetScroll: true });
    });
  });

  root.querySelector("#sourceSelect").addEventListener("change", (event) => {
    ui.source = event.target.value;
    actions.loadVersions(false, ui.source);
  });
  root.querySelector("#refreshVersions").addEventListener("click", () => {
    actions.loadVersions(true, ui.source);
  });
  root.querySelector("[data-loader-install]").addEventListener("click", () => {
    actions.openLoaderInstall("");
  });
  root.querySelector("[data-goto-versions]").addEventListener("click", () => actions.navigate("versions"));
  root.querySelectorAll("[data-java-major]").forEach((button) => {
    button.addEventListener("click", () => actions.downloadJava(Number(button.dataset.javaMajor)));
  });
  root.querySelectorAll("[data-refresh-java]").forEach((button) => {
    button.addEventListener("click", () => actions.refreshJava());
  });

  applyFilter();
  return root;
}

function matchType(item, type) {
  if (type === "all") return true;
  if (type === "old") return item.type === "old_beta" || item.type === "old_alpha";
  return item.type === type;
}
