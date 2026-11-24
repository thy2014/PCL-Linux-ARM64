/* 主页 */
import { icon, esc, cubeTile, typeBadge, fmtBytes, timeAgo, grassBlockSvg } from "../ui.js";

export function homePage(ctx) {
  const { state, actions } = ctx;
  const settings = state.settings || {};
  const installed = state.installed || [];
  const java = state.java || [];
  const latest = state.latest || {};
  const bestJava = java[0] || null;
  const last = installed[0] || null;
  const sourceLabel = settings.download_source === "bmclapi" ? "BMCLAPI 镜像" : "官方源";
  const memoryGb = ((Number(settings.memory_mb) || 4096) / 1024).toFixed(1).replace(/\.0$/, "");
  const latestRelease = latest.release || "";
  const releases = (state.versions || []).filter((item) => item.type === "release").slice(0, 4);
  const installedSet = new Set(installed.map((item) => item.id));

  const root = document.createElement("div");
  root.className = "page";

  const installedRows = installed.slice(0, 4).map((item) => `
    <div class="version-row">
      ${cubeTile(item.type)}
      <div class="version-name">
        <strong>${esc(item.id)}</strong>
        <span>${esc(typeLabelText(item.type))} · ${esc(timeAgo(item.last_played || item.installed_at))}${item.size ? ` · ${fmtBytes(item.size)}` : ""}</span>
      </div>
      <div class="version-meta">${typeBadge(item.type)}</div>
      <button class="btn btn-soft btn-sm" data-launch="${esc(item.id)}">${icon("play")}启动</button>
    </div>`).join("");

  const javaRows = java.slice(0, 2).map((item) => `
    <div class="java-item">
      <div class="java-icon">${icon("coffee")}</div>
      <div class="java-text">
        <strong>${esc(item.vendor)} Java ${esc(item.version)}</strong>
        <span title="${esc(item.path)}">${esc(item.path)}</span>
      </div>
      <span class="badge ${item.major >= 21 ? "ok" : "muted"}">${esc(item.source)}</span>
    </div>`).join("");

  const latestRows = releases.map((item) => `
    <div class="latest-row">
      <span class="ver">${esc(item.id)}</span>
      <span class="date">${esc(item.releaseDate || "")}</span>
      <span class="badge release">正式版</span>
      ${installedSet.has(item.id)
        ? `<button class="text-btn" data-launch="${esc(item.id)}" title="启动 ${esc(item.id)}">${icon("play", "ico-sm")}启动</button>`
        : `<button class="text-btn" data-install="${esc(item.id)}" title="安装 ${esc(item.id)}">${icon("plus", "ico-sm")}安装</button>`}
    </div>`).join("");

  const javaBlock = java.length
    ? `<div class="java-mini">${javaRows}</div>
       <div class="mini-actions">
         <button class="btn btn-light btn-sm" data-refresh-java>${icon("refresh")}重新检测</button>
         <button class="btn btn-soft btn-sm" data-java-major="21">${icon("download")}下载 Java 21</button>
       </div>`
    : `<div class="warn-line">${icon("warning")}尚未检测到 Java。安装版本时可自动下载匹配平台的 JDK，也可以现在手动下载。</div>
       <div class="mini-actions">
         <button class="btn btn-primary btn-sm" data-java-major="21">${icon("download")}下载 Java 21（${esc(state.app.arch_label)}）</button>
         <button class="btn btn-light btn-sm" data-refresh-java>${icon("refresh")}重新检测</button>
       </div>`;

  root.innerHTML = `
    <section class="hero">
      <div class="hero-copy">
        <div class="hero-eyebrow"><span class="pulse"></span>NATIVE LAUNCHER</div>
        <h2>为你的系统而生的<br><em>我的世界</em>启动器</h2>
        <p>PCL 风格的跨平台 Minecraft 启动器。版本、依赖库、资源文件与 Java 运行时一站式下载，原生库会按当前系统自动匹配。</p>
        <div class="hero-actions">
          ${last
            ? `<button class="btn btn-primary btn-lg" data-launch="${esc(last.id)}">${icon("play")}启动 ${esc(last.id)}</button>`
            : `<button class="btn btn-primary btn-lg" data-goto="download">${icon("download")}下载第一个版本</button>`}
          <button class="btn btn-ghost btn-lg" data-goto="${last ? "download" : "settings"}">${last ? `${icon("download")}下载新版本` : `${icon("sliders")}先完成设置`}</button>
        </div>
        <div class="hero-meta">
          <span>${icon("coffee", "ico-sm")}${bestJava ? `Java ${bestJava.major}` : "Java 待安装"}</span>
          <span>${icon("layers", "ico-sm")}已安装 ${installed.length} 个版本</span>
          <span>${icon("globe", "ico-sm")}${sourceLabel}</span>
        </div>
      </div>
      <div class="hero-art">
        <div class="hero-glow-ring"></div>
        <div class="block-scene">${grassBlockSvg()}</div>
        <div class="hero-float one">
          <div class="hf-icon">${icon("spark")}</div>
          <div class="hf-text"><strong>${latestRelease ? esc(latestRelease) : "版本列表"}</strong><span>${latestRelease ? "最新正式版" : "等待加载"}</span></div>
        </div>
        <div class="hero-float two">
          <div class="hf-icon blue">${icon("chip")}</div>
          <div class="hf-text"><strong>原生库适配</strong><span>按系统自动匹配</span></div>
        </div>
      </div>
    </section>

    <section class="stat-grid">
      <div class="stat">
        <div class="stat-icon">${icon("layers")}</div>
        <div class="stat-body"><div class="value">${installed.length} 个</div><div class="label">本地已安装版本</div></div>
      </div>
      <div class="stat">
        <div class="stat-icon green">${icon("coffee")}</div>
        <div class="stat-body"><div class="value">${bestJava ? `Java ${bestJava.major}` : "未检测到"}</div><div class="label">${bestJava ? esc(bestJava.vendor) : "建议安装 JDK"}</div></div>
      </div>
      <div class="stat">
        <div class="stat-icon amber">${icon("memory")}</div>
        <div class="stat-body"><div class="value">${memoryGb} GB</div><div class="label">分配给游戏的内存</div></div>
      </div>
      <div class="stat">
        <div class="stat-icon purple">${icon("globe")}</div>
        <div class="stat-body"><div class="value">${sourceLabel}</div><div class="label">${settings.download_threads || 16} 线程并行下载</div></div>
      </div>
    </section>

    <section class="home-grid">
      <div class="card card-pad">
        <div class="panel-title">
          <h3>最近使用的版本</h3>
          <span class="spacer"></span>
          <button class="text-btn" data-goto="versions">管理 ${icon("arrow", "ico-sm")}</button>
        </div>
        ${installed.length ? installedRows : `
          <div class="empty" style="padding:30px 18px 18px">
            <div class="empty-art">${icon("cube", "ico")}</div>
            <h3>还没有安装任何版本</h3>
            <p>去下载页选一个正式版，客户端、依赖库与资源会自动下载并校验 SHA1。</p>
            <div class="quick-start">
              <div class="step"><span class="num">1</span><strong>安装 Java</strong><p>按版本要求自动下载匹配 JDK</p></div>
              <div class="step"><span class="num">2</span><strong>下载版本</strong><p>选择正式版或快照并等待进度完成</p></div>
              <div class="step"><span class="num">3</span><strong>启动游戏</strong><p>离线账户即可进入单人游戏</p></div>
            </div>
            <button class="btn btn-primary" data-goto="download">${icon("download")}前往下载页</button>
          </div>`}
      </div>

      <div class="home-side">
        <div class="card card-pad">
          <div class="panel-title">
            <h3>运行环境</h3>
            <span class="spacer"></span>
            <span class="badge ${java.length ? "ok" : "warn"}">${java.length ? `${java.length} 个 Java` : "待配置"}</span>
          </div>
          ${javaBlock}
        </div>

        <div class="card card-pad">
          <div class="panel-title">
            <h3>最新版本</h3>
            <span class="spacer"></span>
            <button class="text-btn" data-goto="download">全部 ${icon("arrow", "ico-sm")}</button>
          </div>
          ${releases.length ? `<div class="latest-list">${latestRows}</div>` : `<div class="loading-row" style="padding:18px 0">${state.versionsLoading ? '<div class="spinner" style="margin:0 auto"></div>' : "打开下载页后加载版本列表"}</div>`}
        </div>
      </div>
    </section>`;

  root.querySelectorAll("[data-goto]").forEach((el) => {
    el.addEventListener("click", () => actions.navigate(el.dataset.goto));
  });
  root.querySelectorAll("[data-launch]").forEach((el) => {
    el.addEventListener("click", () => actions.launch(el.dataset.launch));
  });
  root.querySelectorAll("[data-install]").forEach((el) => {
    el.addEventListener("click", () => actions.openInstall(el.dataset.install));
  });
  root.querySelectorAll("[data-java-major]").forEach((el) => {
    el.addEventListener("click", () => actions.downloadJava(Number(el.dataset.javaMajor)));
  });
  root.querySelectorAll("[data-refresh-java]").forEach((el) => {
    el.addEventListener("click", () => actions.refreshJava());
  });
  return root;
}

function typeLabelText(type) {
  return { release: "正式版", snapshot: "快照", old_beta: "远古 Beta", old_alpha: "远古 Alpha" }[type] || "版本";
}
