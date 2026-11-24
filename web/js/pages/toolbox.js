/* 工具箱：崩溃诊断、环境信息、目录快捷入口 */
import { api } from "../api.js";
import { icon, esc, toast } from "../ui.js";

export function toolboxPage(ctx) {
  const { state, actions } = ctx;
  const installed = state.installed || [];
  if (!state.toolboxUi) state.toolboxUi = { version: installed[0]?.id || "", data: null, loading: false, error: "" };
  const ui = state.toolboxUi;
  if (!ui.version && installed[0]) ui.version = installed[0].id;

  const root = document.createElement("div");
  root.className = "page";

  const versionOptions = installed.length
    ? installed.map((item) => `<option value="${esc(item.id)}" ${item.id === ui.version ? "selected" : ""}>${esc(item.id)} · ${esc(item.game_version || "")}</option>`).join("")
    : `<option value="">尚无版本</option>`;

  root.innerHTML = `
    <div class="card page-toolbar">
      <div class="search-box" style="max-width:380px">
        <select class="select borderless" id="diagVersion" style="border:0;background:transparent;box-shadow:none;padding-left:14px;width:100%">${versionOptions}</select>
      </div>
      <div class="toolbar-right">
        <button class="btn btn-light btn-sm" data-open-logs>${icon("folder")}日志目录</button>
        <button class="btn btn-primary btn-sm" data-diagnose>${icon("wrench")}开始诊断</button>
      </div>
    </div>
    <div class="toolbox-grid">
      <section class="card tool-card diag-card">
        <div class="tool-head"><div class="tool-ico">${icon("activity")}</div><div><h3>崩溃诊断</h3><p>分析 latest.log、崩溃报告、JVM 参数与模组环境</p></div></div>
        <div id="diagBody" class="diag-body">${diagnosisHtml(ui)}</div>
      </section>
      <section class="card tool-card">
        <div class="tool-head"><div class="tool-ico">${icon("cpu")}</div><div><h3>运行环境</h3><p>启动器、Java 与目录状态</p></div></div>
        <div class="env-list">
          ${envRow("启动器架构", state.app?.arch_label || "—")}
          ${envRow("系统", `${state.app?.os || "—"} / ${state.app?.arch || "—"}`)}
          ${envRow("Java 运行时", (state.java || []).length ? `${state.java.length} 个已检测` : "未安装")}
          ${envRow("已安装版本", `${installed.length} 个`)}
          ${envRow("版本隔离", state.settings?.version_isolation ? "已开启" : "已关闭")}
          ${envRow("数据目录", compactPath(state.dirs?.data || ""))}
          ${envRow("游戏目录", compactPath(state.dirs?.game || ""))}
        </div>
        <div class="env-actions">
          <button class="btn btn-light btn-sm" data-open-game>${icon("folder")}游戏目录</button>
          <button class="btn btn-light btn-sm" data-open-java>${icon("cpu")}Java 目录</button>
          <button class="btn btn-light btn-sm" data-open-data>${icon("archive")}数据目录</button>
        </div>
      </section>
    </div>
    <div class="card tool-card">
      <div class="tool-head"><div class="tool-ico">${icon("file")}</div><div><h3>日志与报告</h3><p>直接查看最近的游戏日志，或检查安装任务记录</p></div></div>
      <div class="quick-grid">
        <button class="quick-action" data-open-log-file><span class="qi">${icon("file")}</span><strong>latest.log</strong><small>打开最新游戏日志</small></button>
        <button class="quick-action" data-open-crash><span class="qi">${icon("warning")}</span><strong>crash-reports</strong><small>打开崩溃报告目录</small></button>
        <button class="quick-action" data-copy-env><span class="qi">${icon("copy")}</span><strong>复制环境信息</strong><small>便于在求助时附带</small></button>
        <button class="quick-action" data-refresh><span class="qi">${icon("refresh")}</span><strong>刷新状态</strong><small>重新读取版本与目录</small></button>
      </div>
    </div>`;

  root.querySelector("#diagVersion").addEventListener("change", (event) => {
    ui.version = event.target.value;
    ui.data = null;
    ui.error = "";
    root.querySelector("#diagBody").innerHTML = diagnosisHtml(ui);
  });
  root.querySelector("[data-diagnose]").addEventListener("click", diagnose);
  root.querySelector("[data-open-logs]").addEventListener("click", () => actions.openPath("logs"));
  root.querySelector("[data-open-game]").addEventListener("click", () => actions.openPath("game"));
  root.querySelector("[data-open-java]").addEventListener("click", () => actions.openPath("java"));
  root.querySelector("[data-open-data]").addEventListener("click", () => actions.openPath("data"));
  root.querySelector("[data-open-log-file]").addEventListener("click", () => actions.openPath("version_logs", ui.version));
  root.querySelector("[data-open-crash]").addEventListener("click", () => actions.openPath("crash", ui.version));
  root.querySelector("[data-refresh]").addEventListener("click", async () => {
    await actions.refreshBootstrap();
    toast("环境信息已刷新", "success");
  });
  root.querySelector("[data-copy-env]").addEventListener("click", async () => {
    const env = [
      `${state.app?.name || "PCL Launcher"} ${state.app?.version || ""}`,
      `System: ${state.app?.os || ""} ${state.app?.arch || ""}`,
      `Arch target: ${state.app?.arch_label || ""}`,
      `Versions: ${installed.map((v) => `${v.id}(${v.loader || "vanilla"})`).join(", ") || "none"}`,
      `Data: ${state.dirs?.data || ""}`,
      `Game: ${state.dirs?.game || ""}`,
    ].join("\n");
    try { await navigator.clipboard.writeText(env); toast("环境信息已复制", "success"); }
    catch { toast("浏览器拒绝访问剪贴板", "error"); }
  });

  async function diagnose() {
    if (!ui.version) { toast("请先安装一个版本", "error"); return; }
    ui.loading = true;
    ui.error = "";
    root.querySelector("#diagBody").innerHTML = diagnosisHtml(ui);
    try {
      const data = await api(`/api/diagnose?version=${encodeURIComponent(ui.version)}`);
      ui.data = data.diagnosis || data;
    } catch (error) {
      ui.error = error.message;
    } finally {
      ui.loading = false;
      root.querySelector("#diagBody").innerHTML = diagnosisHtml(ui);
      bindDiagnosis();
    }
  }

  function bindDiagnosis() {
    root.querySelectorAll("[data-open-report]").forEach((button) => {
      button.addEventListener("click", () => actions.openPath("crash", ui.version));
    });
  }

  bindDiagnosis();
  return root;
}

function diagnosisHtml(ui) {
  if (ui.loading) return `<div class="loading-row"><div class="spinner" style="margin:0 auto 12px"></div>正在读取日志并分析…</div>`;
  if (ui.error) return `<div class="empty" style="padding:34px 10px"><div class="empty-art">${icon("warning")}</div><h3>诊断失败</h3><p>${esc(ui.error)}</p></div>`;
  if (!ui.data) return `<div class="empty" style="padding:34px 10px"><div class="empty-art">${icon("activity")}</div><h3>选择版本后开始诊断</h3><p>会检查最近一次启动日志、崩溃报告、Java 版本与模组数量。</p></div>`;
  const data = ui.data;
  const issues = data.issues || [];
  const level = issues.some((item) => item.level === "error") ? "error" : issues.some((item) => item.level === "warn") ? "warn" : "ok";
  return `
    <div class="diag-summary ${level}">
      <div class="diag-sum-icon">${icon(level === "ok" ? "check" : "warning")}</div>
      <div><strong>${esc(data.summary || (level === "ok" ? "未发现明显问题" : "发现需要关注的问题"))}</strong><span>版本 ${esc(data.version || ui.version)} · 日志 ${data.log_size ? fmtBytes(data.log_size) : "无"} · ${data.mod_count || 0} 个模组</span></div>
    </div>
    ${issues.length ? `<div class="issue-list">${issues.map((item) => `<div class="issue ${esc(item.level)}"><span class="issue-dot"></span><div><strong>${esc(item.title)}</strong><p>${esc(item.detail)}</p></div></div>`).join("")}</div>` : ""}
    ${data.log_excerpt ? `<details class="log-details"><summary>查看日志片段</summary><pre class="log-pre">${esc(data.log_excerpt)}</pre></details>` : ""}
    ${data.report ? `<button class="btn btn-light btn-sm" data-open-report="${esc(data.report)}" style="margin-top:12px">${icon("file")}打开崩溃报告</button>` : ""}
    <p class="hint" style="margin-top:12px">诊断基于本地日志的启发式规则，不能替代人工排查；涉及模组冲突时请逐个禁用定位。</p>`;
}

function envRow(label, value) {
  return `<div class="env-row"><span>${esc(label)}</span><b title="${esc(value)}">${esc(value)}</b></div>`;
}

function compactPath(path) {
  if (!path) return "—";
  return path.replace(/^\/home\/[^/]+/, "~");
}

function fmtBytes(value) {
  const n = Number(value) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
