/* 版本管理 */
import { icon, esc, cubeTile, typeBadge, fmtBytes, timeAgo, fmtDate } from "../ui.js";

export function versionsPage(ctx) {
  const { state, actions } = ctx;
  const installed = state.installed || [];
  const root = document.createElement("div");
  root.className = "page";

  const cards = installed.map((item) => {
    const arm = item.arm64 || {};
    const patched = Number(arm.patched || 0);
    const unsupported = Boolean(arm.unsupported);
    return `<div class="installed-card ${esc(item.type)}">
      <div class="installed-head">
        ${cubeTile(item.type)}
        <div class="title">
          <h3 title="${esc(item.id)}">${esc(item.id)}</h3>
          <div class="sub">${typeBadge(item.type)}${item.loader && item.loader !== "vanilla" ? `<span class="badge release">${esc(item.loader)}</span>` : ""}${item.isolated ? `<span class="badge muted">隔离</span>` : ""}${patched ? `<span class="badge ok">ARM64 ×${patched}</span>` : "<span class=\"badge muted\">官方原生库</span>"}</div>
        </div>
      </div>
      ${unsupported ? `<div class="warn-line">${icon("warning")}该版本依赖 LWJGL 2 / 旧版原生库，当前平台可能没有对应的官方构建，启动可能失败。</div>` : ""}
      <div class="installed-meta">
        <div class="kv"><span>需要 Java</span><strong>Java ${Number(item.java_major) || 8}+</strong></div>
        <div class="kv"><span>版本文件</span><strong>${fmtBytes(item.size)}</strong></div>
        <div class="kv"><span>上次启动</span><strong>${esc(item.last_played ? timeAgo(item.last_played) : "从未启动")}</strong></div>
        <div class="kv"><span>安装时间</span><strong>${esc(fmtDate(item.installed_at) || "—")}</strong></div>
      </div>
      <div class="installed-actions">
        <button class="btn btn-primary" data-launch="${esc(item.id)}">${icon("play")}启动游戏</button>
        <button class="btn btn-soft btn-sm" data-manage="${esc(item.id)}">${icon("sliders")}内容与设置</button>
        <button class="btn btn-light btn-sm btn-icon-only" data-folder="${esc(item.id)}" title="打开版本文件夹">${icon("folder")}</button>
        <span class="spacer"></span>
        <button class="btn btn-danger btn-sm" data-delete="${esc(item.id)}">${icon("trash")}删除</button>
      </div>
    </div>`;
  }).join("");

  root.innerHTML = `
    <div class="card page-toolbar">
      <div>
        <strong style="font-size:14px">本地版本</strong>
        <span class="count" style="margin-left:8px;font-size:11.5px;color:var(--muted)">${installed.length} 个已安装</span>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-light btn-sm" data-open-game>${icon("folder")}游戏目录</button>
        <button class="btn btn-soft btn-sm" data-goto-download>${icon("download")}下载新版本</button>
        <button class="icon-btn" data-refresh title="刷新">${icon("refresh")}</button>
      </div>
    </div>
    ${installed.length
      ? `<div class="version-grid">${cards}</div>`
      : `<div class="card card-pad"><div class="empty">
          <div class="empty-art">${icon("cube")}</div>
          <h3>版本库还是空的</h3>
          <p>下载页提供正式版、快照与远古版本。安装完成后，客户端、依赖库、资源和 Java 会一并就绪。</p>
          <button class="btn btn-primary" data-goto-download>${icon("download")}去下载页看看</button>
        </div></div>`}`;

  root.querySelectorAll("[data-launch]").forEach((button) => {
    button.addEventListener("click", () => actions.launch(button.dataset.launch));
  });
  root.querySelectorAll("[data-manage]").forEach((button) => {
    button.addEventListener("click", () => actions.openVersionManage(button.dataset.manage));
  });
  root.querySelectorAll("[data-folder]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("version", button.dataset.folder));
  });
  root.querySelectorAll("[data-delete]").forEach((button) => {
    button.addEventListener("click", () => actions.deleteVersion(button.dataset.delete));
  });
  root.querySelectorAll("[data-goto-download]").forEach((button) => {
    button.addEventListener("click", () => actions.navigate("download"));
  });
  root.querySelectorAll("[data-open-game]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("game"));
  });
  root.querySelectorAll("[data-refresh]").forEach((button) => {
    button.addEventListener("click", () => actions.refreshInstalled());
  });
  return root;
}
