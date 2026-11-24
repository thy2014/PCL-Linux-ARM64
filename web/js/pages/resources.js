/* 资源页：Modrinth 模组 / 整合包 / 资源包 / 光影 */
import { api, qs } from "../api.js";
import { icon, esc, fmtBytes, debounce, toast, typeBadge } from "../ui.js";

const TYPES = [
  ["mod", "模组", "package", "为已安装的模组版本添加内容"],
  ["modpack", "整合包", "layers", "从 Modrinth 创建独立整合包实例"],
  ["resourcepack", "资源包", "image", "更换材质、界面与音效"],
  ["shader", "光影", "spark", "为支持 Iris / OptiFine 的版本添加光影"],
];

const TYPE_LABEL = { mod: "模组", modpack: "整合包", resourcepack: "资源包", shader: "光影" };

export function resourcesPage(ctx) {
  const { state, actions } = ctx;
  const installed = state.installed || [];
  if (!state.resourceUi) {
    state.resourceUi = {
      type: "mod",
      query: "",
      target: installed[0]?.id || "",
      results: null,
      total: 0,
      loading: false,
      error: "",
      offset: 0,
    };
  }
  const ui = state.resourceUi;
  if (!ui.target && installed[0]) ui.target = installed[0].id;
  const target = installed.find((item) => item.id === ui.target) || installed[0] || null;
  const game = target?.game_version || "";
  const loader = target?.loader || "vanilla";
  const root = document.createElement("div");
  root.className = "page";

  const tabs = TYPES.map(([value, label, ico, desc]) => `
    <button type="button" class="res-tab ${ui.type === value ? "active" : ""}" data-res-type="${value}">
      <span class="res-tab-icon">${icon(ico)}</span>
      <span><strong>${label}</strong><small>${desc}</small></span>
    </button>`).join("");

  const targetOptions = installed.length
    ? installed.map((item) => `<option value="${esc(item.id)}" ${item.id === ui.target ? "selected" : ""}>${esc(item.id)} · ${esc(item.loader || "vanilla")} · ${esc(item.game_version || "")}</option>`).join("")
    : `<option value="">尚无已安装版本</option>`;

  root.innerHTML = `
    <div class="resource-tabs card">${tabs}</div>
    <div class="card page-toolbar resource-toolbar">
      <div class="search-box resource-search">${icon("search")}<input class="input" id="resQuery" type="search" placeholder="搜索 Modrinth 项目，例如 Sodium、Iris、Fabulously Optimized" autocomplete="off"></div>
      <div class="toolbar-right">
        <select class="select" id="resTarget" title="安装目标版本">${targetOptions}</select>
        <button class="btn btn-primary btn-sm" id="resSearch">${icon("search")}搜索</button>
      </div>
    </div>
    <div class="resource-note card">
      <div class="res-note-icon">${icon("shield")}</div>
      <div><strong>内容来自 Modrinth 官方 API</strong><span>下载文件会校验 SHA1；必需前置模组会自动解析并安装。整合包会基于所选版本创建独立实例。</span></div>
      <span class="badge ${target ? "ok" : "warn"}">${target ? `${esc(target.id)} · ${esc(target.game_version || "")}` : "未选择版本"}</span>
    </div>
    ${target && ui.type === "mod" && ["vanilla", "optifine", "liteloader"].includes(loader) ? `<div class="warn-line card">${icon("warning")}目标版本是原版，安装模组前请先在“版本管理”或“下载”页安装 Fabric / Forge / NeoForge / Quilt 加载器。</div>` : ""}
    <div id="resResults" class="resource-results"></div>`;

  const resultsEl = root.querySelector("#resResults");
  const queryEl = root.querySelector("#resQuery");
  const targetEl = root.querySelector("#resTarget");
  queryEl.value = ui.query || "";

  root.querySelectorAll("[data-res-type]").forEach((button) => {
    button.addEventListener("click", () => {
      if (ui.type === button.dataset.resType) return;
      ui.type = button.dataset.resType;
      ui.results = null;
      ui.offset = 0;
      ui.error = "";
      ui.loading = false;
      ui.seq = (ui.seq || 0) + 1;
      actions.render();
    });
  });

  targetEl.addEventListener("change", () => {
    ui.target = targetEl.value;
    ui.results = null;
    ui.offset = 0;
    ui.loading = false;
    ui.seq = (ui.seq || 0) + 1;
    actions.render();
  });

  const runSearch = () => {
    ui.query = queryEl.value.trim();
    ui.results = null;
    ui.offset = 0;
    load(false);
  };
  root.querySelector("#resSearch").addEventListener("click", runSearch);
  queryEl.addEventListener("keydown", (event) => { if (event.key === "Enter") runSearch(); });
  queryEl.addEventListener("input", debounce(() => {
    if (queryEl.value.trim().length >= 2 || queryEl.value.trim() === "") runSearch();
  }, 420));

  resultsEl.addEventListener("click", (event) => {
    const more = event.target.closest("[data-more]");
    if (more) { load(true); return; }
    const install = event.target.closest("[data-res-install]");
    if (install) {
      const hit = (ui.results || []).find((item) => item.slug === install.dataset.resInstall);
      if (hit) openProject(hit, target);
    }
  });

  function paintEmpty() {
    resultsEl.innerHTML = `<div class="card card-pad"><div class="empty">
      <div class="empty-art">${icon(TYPES.find((t) => t[0] === ui.type)?.[2] || "package")}</div>
      <h3>${installed.length ? "搜索 Modrinth 资源" : "先安装一个 Minecraft 版本"}</h3>
      <p>${installed.length ? "输入关键词开始搜索，或直接按搜索浏览热门项目。" : "资源需要安装到某个版本；先在下载页安装原版与模组加载器。"}</p>
      ${installed.length ? `<button class="btn btn-primary" data-empty-search>${icon("search")}浏览热门</button>` : `<button class="btn btn-primary" data-res-download>${icon("download")}去下载</button>`}
    </div></div>`;
    resultsEl.querySelector("[data-empty-search]")?.addEventListener("click", () => { ui.query = ""; queryEl.value = ""; load(false); });
    resultsEl.querySelector("[data-res-download]")?.addEventListener("click", () => actions.navigate("download"));
  }

  function paintResults() {
    const items = ui.results || [];
    if (!items.length) {
      resultsEl.innerHTML = `<div class="card card-pad"><div class="empty"><div class="empty-art">${icon("search")}</div><h3>没有找到结果</h3><p>换个关键词，或调整目标版本。部分项目只支持特定加载器。</p></div></div>`;
      return;
    }
    resultsEl.innerHTML = `<div class="resource-grid">${items.map((item) => `
      <div class="resource-card card">
        <div class="res-head">
          ${item.icon ? `<img class="res-icon" src="${esc(item.icon)}" alt="" loading="lazy">` : `<div class="res-icon fallback">${icon("package")}</div>`}
          <div class="res-title"><h3>${esc(item.title)}</h3><span>${esc(item.author || "Modrinth")}</span></div>
          <span class="badge ${item.project_type === "modpack" ? "release" : "muted"}">${esc(TYPE_LABEL[item.project_type] || item.project_type)}</span>
        </div>
        <p class="res-desc">${esc(item.description || "暂无简介")}</p>
        <div class="res-foot">
          <span class="res-stat">${icon("download")}${fmtCount(item.downloads)}</span>
          <span class="res-stat">${icon("heart")}${fmtCount(item.follows)}</span>
          <span class="spacer"></span>
          <button class="btn btn-soft btn-sm" data-res-install="${esc(item.slug)}">${icon("download")}安装</button>
        </div>
      </div>`).join("")}</div>
      ${items.length < ui.total ? `<div class="load-more"><button class="btn btn-light" data-more>${icon("chevron")}加载更多（${items.length} / ${ui.total}）</button></div>` : ""}`;
  }

  async function load(more) {
    if (ui.loading) return;
    if (!target && ui.type !== "modpack") { paintEmpty(); return; }
    if (!ui.target || !target) {
      resultsEl.innerHTML = `<div class="card card-pad"><div class="empty"><div class="empty-art">${icon("cube")}</div><h3>还没有可用的目标版本</h3><p>先在下载页安装一个版本，再回来添加资源。</p><button class="btn btn-primary" data-to-download>${icon("download")}去下载</button></div></div>`;
      resultsEl.querySelector("[data-to-download]")?.addEventListener("click", () => actions.navigate("download"));
      return;
    }
    const seq = (ui.seq || 0) + 1;
    ui.seq = seq;
    ui.loading = true;
    ui.error = "";
    if (!more) { ui.results = []; ui.offset = 0; }
    resultsEl.innerHTML = `<div class="card card-pad"><div class="loading-row"><div class="spinner" style="margin:0 auto 10px"></div>正在连接 Modrinth…</div></div>`;
    try {
      const offset = more ? (ui.results || []).length : 0;
      const data = await api(`/api/modrinth/search${qs({
        type: ui.type,
        q: ui.query,
        game: ui.type === "modpack" ? "" : game,
        loader: ui.type === "mod" ? loader : "",
        offset,
        limit: 24,
      })}`);
      if (seq !== ui.seq) return;
      ui.results = more ? [...(ui.results || []), ...(data.hits || [])] : (data.hits || []);
      ui.total = data.total || ui.results.length;
      ui.error = "";
      paintResults();
    } catch (error) {
      if (seq !== ui.seq) return;
      ui.error = error.message;
      resultsEl.innerHTML = `<div class="card card-pad"><div class="empty"><div class="empty-art">${icon("warning")}</div><h3>Modrinth 请求失败</h3><p>${esc(error.message)}</p><button class="btn btn-light" data-retry>${icon("refresh")}重试</button></div></div>`;
      resultsEl.querySelector("[data-retry]")?.addEventListener("click", () => load(false));
    } finally {
      if (seq === ui.seq) ui.loading = false;
    }
  }

  function openProject(hit, base) {
    if (!base) { toast("请先安装目标版本", "error"); return; }
    if (hit.project_type === "mod" && ["vanilla", "optifine", "liteloader"].includes(base.loader || "vanilla")) {
      toast("请先为目标版本安装 Fabric / Forge / NeoForge / Quilt 加载器，再安装模组", "info", 6000);
      return;
    }
    if (hit.project_type === "modpack") {
      openModpackDialog(hit, base);
    } else {
      openProjectDialog(hit, base);
    }
  }

  async function openProjectDialog(hit, base) {
    const body = document.createElement("div");
    body.innerHTML = `<div class="loading-row"><div class="spinner" style="margin:0 auto 10px"></div>正在读取 ${esc(hit.title)} 的版本…</div>`;
    const foot = document.createElement("div");
    foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
    foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-close>关闭</button>`;
    const handle = actions.modal({
      title: hit.title,
      subtitle: `${TYPE_LABEL[hit.project_type] || "资源"} · 安装到 ${base.id}`,
      iconName: "package",
      wide: true,
      body,
      footer: foot,
    });
    foot.querySelector("[data-close]").addEventListener("click", () => handle.close());
    try {
      const data = await api(`/api/modrinth/versions${qs({ slug: hit.slug, game: base.game_version || "", loader: hit.project_type === "mod" ? base.loader : "" })}`);
      const versions = data.versions || [];
      if (!versions.length) {
        body.innerHTML = `<div class="empty" style="padding:40px 10px"><div class="empty-art">${icon("warning")}</div><h3>没有兼容版本</h3><p>${esc(base.id)} 的 Minecraft 版本或加载器与该资源不匹配。</p></div>`;
        return;
      }
      body.innerHTML = `
        <div class="install-summary">
          <div class="res-icon mini">${hit.icon ? `<img src="${esc(hit.icon)}" alt="">` : icon("package")}</div>
          <div class="t"><strong>${esc(hit.title)}</strong><span>${esc(hit.description || "")}</span></div>
        </div>
        <div class="version-pick">
          ${versions.slice(0, 12).map((version, index) => `
            <label class="pick-row">
              <input type="radio" name="resVersion" value="${esc(version.id)}" ${index === 0 ? "checked" : ""}>
              <span class="pick-name">${esc(version.name || version.version_number)}</span>
              <span class="badge ${version.version_type === "release" ? "release" : "snapshot"}">${esc(version.version_type)}</span>
              <span class="pick-meta">${esc((version.game_versions || []).slice(-2).join(" / "))} · ${esc((version.loaders || []).join(", ") || "通用")}</span>
            </label>`).join("")}
        </div>
        <p class="hint" style="margin:10px 0 0">安装时会自动处理必需的依赖模组；文件会写入 ${esc(base.game_dir || base.id)} 对应的内容目录。</p>`;
      const installFoot = document.createElement("div");
      installFoot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
      installFoot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-close>取消</button><button class="btn btn-primary" data-install>${icon("download")}安装</button>`;
      handle.setFooter(installFoot);
      installFoot.querySelector("[data-close]").addEventListener("click", () => handle.close());
      installFoot.querySelector("[data-install]").addEventListener("click", async () => {
        const versionId = body.querySelector('input[name="resVersion"]:checked')?.value;
        installFoot.querySelector("[data-install]").disabled = true;
        try {
          const result = await api("/api/modrinth/install", {
            method: "POST",
            body: { version: base.id, type: hit.project_type, slug: hit.slug, project_version_id: versionId, game: base.game_version || "" },
          });
          handle.close();
          actions.openTaskModal(result.task_id, { kind: "resource", title: `安装 ${hit.title}`, version: base.id });
        } catch (error) {
          toast(error.message, "error", 5000);
          installFoot.querySelector("[data-install]").disabled = false;
        }
      });
    } catch (error) {
      body.innerHTML = `<div class="empty" style="padding:40px 10px"><div class="empty-art">${icon("warning")}</div><h3>无法读取版本</h3><p>${esc(error.message)}</p></div>`;
    }
  }

  async function openModpackDialog(hit, base) {
    const body = document.createElement("div");
    body.innerHTML = `<div class="loading-row"><div class="spinner" style="margin:0 auto 10px"></div>正在读取整合包版本…</div>`;
    const foot = document.createElement("div");
    foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
    foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-close>关闭</button>`;
    const handle = actions.modal({
      title: hit.title,
      subtitle: `整合包 · 基于 ${base.id} 创建独立实例`,
      iconName: "layers",
      wide: true,
      body,
      footer: foot,
    });
    foot.querySelector("[data-close]").addEventListener("click", () => handle.close());
    try {
      const data = await api(`/api/modrinth/versions${qs({ slug: hit.slug })}`);
      const versions = data.versions || [];
      if (!versions.length) {
        body.innerHTML = `<div class="empty" style="padding:40px 10px"><div class="empty-art">${icon("warning")}</div><h3>没有可用整合包版本</h3><p>该项目暂时没有 .mrpack 文件。</p></div>`;
        return;
      }
      body.innerHTML = `
        <div class="install-summary">
          <div class="res-icon mini">${hit.icon ? `<img src="${esc(hit.icon)}" alt="">` : icon("layers")}</div>
          <div class="t"><strong>${esc(hit.title)}</strong><span>${esc(hit.description || "")}</span></div>
        </div>
        <div class="disclaimer" style="margin-bottom:14px">将以 <strong>${esc(base.id)}</strong> 为模板创建一个新的版本实例，独立保存 mods、config 与存档；不会修改原版本。</div>
        <div class="version-pick">
          ${versions.slice(0, 12).map((version, index) => `
            <label class="pick-row">
              <input type="radio" name="packVersion" value="${esc(version.id)}" ${index === 0 ? "checked" : ""}>
              <span class="pick-name">${esc(version.name || version.version_number)}</span>
              <span class="badge ${version.version_type === "release" ? "release" : "snapshot"}">${esc(version.version_type)}</span>
              <span class="pick-meta">${esc((version.game_versions || []).join(" / "))}</span>
            </label>`).join("")}
        </div>`;
      const installFoot = document.createElement("div");
      installFoot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
      installFoot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-close>取消</button><button class="btn btn-primary" data-install>${icon("download")}创建实例</button>`;
      handle.setFooter(installFoot);
      installFoot.querySelector("[data-close]").addEventListener("click", () => handle.close());
      installFoot.querySelector("[data-install]").addEventListener("click", async () => {
        const versionId = body.querySelector('input[name="packVersion"]:checked')?.value;
        installFoot.querySelector("[data-install]").disabled = true;
        try {
          const result = await api("/api/modrinth/install_modpack", {
            method: "POST",
            body: { source_version: base.id, slug: hit.slug, project_version_id: versionId },
          });
          handle.close();
          actions.openTaskModal(result.task_id, { kind: "modpack", title: `安装整合包 ${hit.title}`, version: base.id });
        } catch (error) {
          toast(error.message, "error", 5000);
          installFoot.querySelector("[data-install]").disabled = false;
        }
      });
    } catch (error) {
      body.innerHTML = `<div class="empty" style="padding:40px 10px"><div class="empty-art">${icon("warning")}</div><h3>无法读取整合包</h3><p>${esc(error.message)}</p></div>`;
    }
  }

  paintEmpty();
  if (target && (ui.query.trim() || ui.results)) {
    paintResults();
  } else if (target) {
    load(false);
  }
  return root;
}

function fmtCount(value) {
  const number = Number(value) || 0;
  if (number >= 1000000) return `${(number / 1000000).toFixed(1)}M`;
  if (number >= 1000) return `${(number / 1000).toFixed(1)}K`;
  return String(number);
}
