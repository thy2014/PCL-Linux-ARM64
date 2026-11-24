/* 应用装配：路由、全局状态、任务与启动流程 */
import { api, qs, setToken } from "./api.js";
import {
  $, $$, icon, esc, modal, confirmDialog, toast, hydrateIcons,
  fmtBytes, fmtSpeed, fmtDuration, timeAgo, cubeTile, typeBadge, copyText,
} from "./ui.js";
import { homePage } from "./pages/home.js";
import { downloadPage } from "./pages/download.js";
import { versionsPage } from "./pages/versions.js";
import { settingsPage } from "./pages/settings.js";
import { aboutPage } from "./pages/about.js";
import { resourcesPage } from "./pages/resources.js";
import { serversPage } from "./pages/servers.js";
import { toolboxPage } from "./pages/toolbox.js";

const ROUTES = {
  home: homePage,
  download: downloadPage,
  versions: versionsPage,
  resources: resourcesPage,
  servers: serversPage,
  toolbox: toolboxPage,
  settings: settingsPage,
  about: aboutPage,
};
const TITLES = {
  home: ["主页", "欢迎回来"],
  download: ["下载", "Minecraft 版本、加载器与 Java 运行时"],
  versions: ["版本管理", "本地已安装的版本与内容"],
  resources: ["资源", "Modrinth 模组 / 整合包 / 资源包 / 光影"],
  servers: ["服务器", "收藏服务器与状态测速"],
  toolbox: ["工具箱", "崩溃诊断与运行环境"],
  settings: ["设置", "启动参数与下载偏好"],
  about: ["关于", "关于 PCL Launcher"],
};

const state = {
  ready: false,
  app: null,
  dirs: {},
  settings: null,
  java: [],
  installed: [],
  servers: [],
  accounts: [],
  activeAccount: "",
  latest: {},
  versions: null,
  versionsLoading: false,
  versionsError: "",
  versionsSource: "",
  downloadUi: null,
  tasks: [],
  launch: null,
  route: "home",
  token: "",
};

const main = $("#main");
let versionsSeq = 0;
let launchModalHandle = null;

function currentRoute() {
  const name = location.hash.replace(/^#\/?/, "");
  return ROUTES[name] ? name : "home";
}

function navigate(route) {
  if (currentRoute() === route) {
    render();
    return;
  }
  location.hash = `#/${route}`;
}

function applyBootstrap(data) {
  state.app = data.app;
  state.dirs = data.dirs || {};
  state.settings = data.settings;
  state.java = data.java || [];
  state.installed = data.installed || [];
  state.latest = data.latest || {};
  state.tasks = data.tasks || [];
  state.launch = data.launch || state.launch;
  state.servers = data.servers || state.servers || [];
  const accountBox = data.accounts && !Array.isArray(data.accounts) ? data.accounts : {};
  state.accounts = Array.isArray(data.accounts) ? data.accounts : (accountBox.accounts || state.accounts || []);
  state.activeAccount = accountBox.selected?.id || data.account?.id || state.activeAccount || "";
  state.token = data.token || state.token;
  document.documentElement.dataset.theme = data.settings?.theme || "blue";
  if (!state.downloadUi) {
    state.downloadUi = { type: "release", query: "", source: state.settings?.download_source || "official" };
  }
  if (!state.versionsSource) state.versionsSource = state.settings?.download_source || "official";
}

async function refreshBootstrap() {
  const data = await api("/api/bootstrap");
  setToken(data.token);
  applyBootstrap(data);
  updateChrome();
  return data;
}

function updateChrome() {
  const [title, sub] = TITLES[state.route] || TITLES.home;
  $("#pageTitle").textContent = title;
  $("#pageSub").textContent = state.route === "home" && state.settings?.username
    ? `${sub}，${state.settings.username}`
    : sub;
  $("#accountName").textContent = state.settings?.username || "Steve";
  const accountType = $("#accountType");
  if (accountType) accountType.textContent = (state.accounts || []).length > 1 ? `${state.accounts.length} 个离线账户 · 点击切换` : "离线账户 · 点击切换";
  const arch = state.app?.arch_label || "—";
  const osLabel = { windows: "Windows", linux: "Linux", osx: "macOS" }[state.app?.os] || (state.app?.os || "—");
  $("#sideArch").innerHTML = `<span class="dot"></span>${esc(arch)} · ${esc(osLabel)}`;
  $$(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.route === state.route));

  const bestJava = (state.java || [])[0];
  const source = state.settings?.download_source === "bmclapi" ? "BMCLAPI" : "官方源";
  const chips = [];
  chips.push(`<span class="meta-chip ${bestJava ? "" : "warn"}"><span class="dot"></span>${bestJava ? `Java ${bestJava.major}` : "Java 未安装"}</span>`);
  chips.push(`<span class="meta-chip">${esc(arch)}</span>`);
  chips.push(`<span class="meta-chip">${esc(source)}</span>`);
  if (state.launch?.running) chips.push(`<span class="meta-chip brand"><span class="dot"></span>游戏运行中</span>`);
  const activeTasks = (state.tasks || []).filter((task) => task.status === "running" || task.status === "cancelling");
  if (activeTasks.length) chips.push(`<button class="meta-chip warn" id="taskChip" type="button"><span class="dot"></span>任务 ${activeTasks.length}</button>`);
  $("#topbarMeta").innerHTML = chips.join("");
  const taskChip = $("#taskChip");
  if (taskChip) {
    taskChip.addEventListener("click", () => {
      const task = activeTasks[0];
      if (task) openTaskModal(task.id, { kind: task.kind, title: task.title });
    });
  }
  $("#logBtn").classList.toggle("active", Boolean(state.launch?.running));
}

function render() {
  if (!state.ready) return;
  const route = currentRoute();
  const changed = route !== state.route;
  state.route = route;
  updateChrome();
  let page;
  try {
    page = ROUTES[route]({ state, actions });
  } catch (error) {
    console.error(error);
    page = errorPage("页面渲染失败", error.message);
  }
  main.replaceChildren(page);
  if (changed) main.scrollTop = 0;
  if (!state.versions && !state.versionsLoading && !state.versionsError) {
    loadVersions(false, state.downloadUi?.source || state.settings?.download_source || "official");
  }
}

async function loadVersions(refresh = false, source = null) {
  const src = source || state.downloadUi?.source || state.settings?.download_source || "official";
  if (state.downloadUi) state.downloadUi.source = src;
  state.versionsLoading = true;
  state.versionsError = "";
  if (state.route === "home" || state.route === "download") render();
  else updateChrome();
  const seq = ++versionsSeq;
  try {
    const data = await api(`/api/versions${qs({ source: src, refresh: refresh ? 1 : "" })}`);
    if (seq !== versionsSeq) return;
    state.versions = data.versions || [];
    state.latest = data.latest || state.latest;
    state.versionsSource = data.source || src;
    state.versionsError = "";
  } catch (error) {
    if (seq !== versionsSeq) return;
    state.versionsError = error.message;
  } finally {
    if (seq === versionsSeq) {
      state.versionsLoading = false;
      if (state.route === "home" || state.route === "download") render();
      else updateChrome();
    }
  }
}

async function refreshJava({ silent = false } = {}) {
  try {
    const data = await api("/api/java?refresh=1");
    state.java = data.java || [];
    updateChrome();
    if (!silent) {
      toast(`已检测到 ${state.java.length} 个 Java`, state.java.length ? "success" : "info");
      if (state.route !== "settings") render();
    }
  } catch (error) {
    toast(error.message, "error");
  }
}

async function refreshInstalled() {
  try {
    const data = await api("/api/installed");
    state.installed = data.installed || [];
    updateChrome();
    if (state.route !== "settings") render();
    return state.installed;
  } catch (error) {
    toast(error.message, "error");
    return state.installed;
  }
}

async function manualRefresh() {
  const button = $("#refreshBtn");
  button.classList.add("active");
  button.disabled = true;
  try {
    const results = await Promise.allSettled([
      refreshBootstrap(),
      api("/api/java?refresh=1").then((data) => { state.java = data.java || []; }),
    ]);
    if (state.route !== "settings") render();
    else updateChrome();
    const failed = results.find((item) => item.status === "rejected");
    if (failed) toast(failed.reason?.message || "刷新失败", "error");
    else toast("状态已刷新", "success");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    button.classList.remove("active");
    button.disabled = false;
  }
}

/* ---------- 启动 ---------- */
async function launch(version) {
  if (!version) {
    const fallback = (state.installed || [])[0];
    if (!fallback) {
      toast("还没有安装任何版本，请先下载一个版本", "info");
      navigate("download");
      return;
    }
    version = fallback.id;
  }
  try {
    toast(`正在构建 ${version} 的启动命令…`, "info", 1800);
    const data = await api("/api/launch", { method: "POST", body: { version } });
    state.launch = data.launch;
    updateChrome();
    openLaunchModal(data.launch);
  } catch (error) {
    toast(error.message, "error", 6000);
    if (String(error.message).includes("Java")) navigate("settings");
  }
}

function openLaunchModal(initial = null) {
  if (launchModalHandle) {
    launchModalHandle.focus ? launchModalHandle.focus() : null;
    return;
  }
  let version = initial?.version || state.launch?.version || "";
  const body = document.createElement("div");
  body.innerHTML = `
    <div class="launch-status"><span class="dot" data-l-dot></span><strong data-l-status>准备中</strong><span data-l-elapsed></span></div>
    <div class="launch-meta">
      <div class="task-stat"><span>Java</span><strong data-l-java>—</strong></div>
      <div class="task-stat"><span>PID</span><strong data-l-pid>—</strong></div>
      <div class="task-stat"><span>版本</span><strong data-l-version>${esc(version || "—")}</strong></div>
    </div>
    <pre class="log-panel big" data-l-log>正在读取日志…</pre>`;
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  foot.innerHTML = `
    <button class="btn btn-danger btn-sm" data-l-stop>${icon("stop")}结束游戏</button>
    <button class="btn btn-light btn-sm" data-l-copy>${icon("copy")}复制启动命令</button>
    <span class="spacer"></span>
    <span class="hint">退出后日志仍会保存在 logs/launch-*.log</span>
    <button class="btn btn-light" data-l-close>关闭</button>`;
  const handle = modal({
    title: initial?.running ? `游戏运行中 · ${version}` : "启动日志",
    subtitle: initial?.java ? `${initial.java}${initial.pid ? ` · PID ${initial.pid}` : ""}` : "查看游戏进程输出",
    iconName: "terminal",
    wide: true,
    body,
    footer: foot,
    onClose: () => { launchModalHandle = null; clearInterval(timer); },
  });
  launchModalHandle = handle;
  let stopped = false;
  let wasRunning = Boolean(initial?.running ?? state.launch?.running);

  const dot = body.querySelector("[data-l-dot]");
  const statusEl = body.querySelector("[data-l-status]");
  const elapsedEl = body.querySelector("[data-l-elapsed]");
  const javaEl = body.querySelector("[data-l-java]");
  const pidEl = body.querySelector("[data-l-pid]");
  const versionEl = body.querySelector("[data-l-version]");
  const logEl = body.querySelector("[data-l-log]");
  const stopBtn = foot.querySelector("[data-l-stop]");
  const copyBtn = foot.querySelector("[data-l-copy]");

  function paint(data) {
    const running = Boolean(data.running);
    dot.classList.toggle("off", !running);
    statusEl.textContent = running ? "游戏运行中" : data.exit_code === null || data.exit_code === undefined ? "未在运行" : `已退出（代码 ${data.exit_code}）`;
    elapsedEl.textContent = running ? fmtDuration(data.elapsed) : (data.log_file ? "日志已保存" : "");
    javaEl.textContent = data.java || "—";
    pidEl.textContent = data.pid ?? "—";
    versionEl.textContent = data.version || version || "—";
    if (data.running) version = data.version || version;
    const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 30;
    const logs = data.logs || [];
    logEl.textContent = logs.length ? logs.join("\n") : "暂无输出，游戏启动可能需要几秒…";
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;
    stopBtn.style.display = running ? "" : "none";
    copyBtn.disabled = !(data.command && data.command.length);
    if (running) {
      handle.setHead({ title: `游戏运行中 · ${version}`, subtitle: `${data.java || ""}${data.pid ? ` · PID ${data.pid}` : ""}`, iconName: "terminal" });
    } else {
      const code = data.exit_code;
      handle.setHead({
        title: data.version ? "游戏已结束" : "未在运行",
        subtitle: data.log_file ? `日志：${data.log_file}` : "进程已结束",
        iconName: code === 0 ? "check" : "warning",
        tone: code === 0 ? "ok" : "warn",
      });
    }
  }

  async function refresh() {
    try {
      const data = await api("/api/launch");
      state.launch = data.launch;
      paint(data.launch);
      updateChrome();
      if (!data.launch.running) {
        const previouslyRunning = wasRunning;
        wasRunning = false;
        clearInterval(timer);
        if (previouslyRunning && !stopped) {
          const code = data.launch.exit_code;
          toast(code === 0 ? "游戏已正常退出" : `游戏已退出（代码 ${code}）`, code === 0 ? "success" : "error", 6000);
        }
        await refreshInstalled();
      }
    } catch (error) {
      statusEl.textContent = "无法读取状态";
      logEl.textContent = error.message;
      clearInterval(timer);
    }
  }

  let timer = setInterval(refresh, 800);

  stopBtn.addEventListener("click", async () => {
    stopped = true;
    stopBtn.disabled = true;
    try {
      const data = await api("/api/launch/stop", { method: "POST", body: {} });
      state.launch = data.launch;
      paint(data.launch);
      toast("已请求结束游戏进程", "info");
    } catch (error) {
      toast(error.message, "error");
    } finally {
      stopBtn.disabled = false;
    }
  });
  copyBtn.addEventListener("click", async () => {
    const command = state.launch?.command || initial?.command || [];
    if (!command.length) return;
    const ok = await copyText(command.join(" "));
    toast(ok ? "启动命令已复制" : "复制失败，请手动记录日志中的命令", ok ? "success" : "error");
  });
  foot.querySelector("[data-l-close]").addEventListener("click", () => handle.close());

  if (initial) paint(initial);
  refresh();
}

/* ---------- 安装 / Java 任务 ---------- */
function openInstall(version) {
  const meta = (state.versions || []).find((item) => item.id === version);
  const installed = (state.installed || []).some((item) => item.id === version);
  const source = state.downloadUi?.source || state.settings?.download_source || "official";
  const body = document.createElement("div");
  body.innerHTML = `
    <div class="install-summary">
      ${cubeTile(meta?.type || "release")}
      <div class="t">
        <strong>Minecraft ${esc(version)}</strong>
        <span>${meta ? `${typeBadge(meta.type)} · ${esc(meta.releaseDate || "")}` : "来自 Mojang 版本清单"}</span>
      </div>
      ${installed ? `<span class="badge ok">已安装</span>` : ""}
    </div>
    <div class="install-option">
      <div class="txt"><strong>下载源</strong><span>${source === "bmclapi" ? "BMCLAPI 镜像（失败时回退官方清单）" : "官方 Mojang 源"}</span></div>
      <span class="badge ${source === "bmclapi" ? "warn" : "release"}">${source === "bmclapi" ? "镜像" : "官方"}</span>
    </div>
    <div class="install-option">
      <div class="txt"><strong>自动安装缺失的 Java</strong><span>按版本要求从 Adoptium 下载匹配平台与架构的 JDK，并校验 SHA256</span></div>
      <label class="switch"><input type="checkbox" data-auto-java ${installed ? "" : "checked"}><span class="track"></span></label>
    </div>
    <div class="disclaimer" style="margin-top:14px">
      将下载客户端 jar、全部依赖库、资源索引与数千个资源对象，并逐个校验 SHA1。已有文件会自动跳过，因此重复安装很快。
      ${installed ? "<br><strong>该版本已安装，重新安装只会覆盖版本文件，不会删除存档。</strong>" : ""}
      <br>安装位置：<span class="mono">${esc(state.settings?.game_dir || "")}/versions/${esc(version)}</span>
    </div>`;
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  foot.innerHTML = `
    <span class="spacer"></span>
    <button class="btn btn-light" data-cancel>取消</button>
    ${installed ? `<button class="btn btn-primary" data-launch-installed>${icon("play")}启动游戏</button>` : ""}
    <button class="btn btn-primary" data-start>${icon("download")}${installed ? "重新安装" : "开始安装"}</button>`;
  const handle = modal({
    title: `安装 ${version}`,
    subtitle: "客户端 / 依赖库 / 资源文件",
    iconName: "download",
    wide: true,
    body,
    footer: foot,
  });
  foot.querySelector("[data-cancel]").addEventListener("click", () => handle.close());
  const launchBtn = foot.querySelector("[data-launch-installed]");
  if (launchBtn) launchBtn.addEventListener("click", async () => { handle.close(); await launch(version); });
  foot.querySelector("[data-start]").addEventListener("click", async () => {
    const autoJava = body.querySelector("[data-auto-java]").checked;
    handle.close();
    try {
      const data = await api("/api/install", {
        method: "POST",
        body: { version, source, auto_java: autoJava },
      });
      state.tasks = [data.task, ...(state.tasks || [])];
      updateChrome();
      openTaskModal(data.task_id, { kind: "install", title: `安装 ${version}`, version, source });
    } catch (error) {
      toast(error.message, "error", 5000);
    }
  });
}

async function downloadJava(major) {
  try {
    const data = await api("/api/java/download", { method: "POST", body: { major } });
    state.tasks = [data.task, ...(state.tasks || [])];
    updateChrome();
    openTaskModal(data.task_id, { kind: "java", title: `下载 Java ${major}`, major });
  } catch (error) {
    toast(error.message, "error", 5000);
  }
}

function openTaskModal(taskId, meta = {}) {
  const kind = meta.kind || "install";
  const title = meta.title || (kind === "java" ? "下载 Java" : "安装版本");
  const body = document.createElement("div");
  body.innerHTML = `
    <div class="progress-hero">
      <div class="pct"><span data-t-pct>0</span><small>%</small></div>
      <div class="p-state"><strong data-t-phase>准备中</strong><span data-t-message>正在连接下载服务器…</span></div>
    </div>
    <div class="progress-track"><div class="progress-fill" data-t-fill></div></div>
    <div class="task-stats">
      <div class="task-stat"><span>速度</span><strong data-t-speed>—</strong></div>
      <div class="task-stat"><span>已下载</span><strong data-t-size>—</strong></div>
      <div class="task-stat"><span>文件</span><strong data-t-files>0 / 0</strong></div>
      <div class="task-stat"><span>已用时间</span><strong data-t-elapsed>0 秒</strong></div>
    </div>
    <div class="current-file">${icon("cube")}<span data-t-current>等待开始…</span></div>
    <pre class="log-panel" data-t-log>等待任务输出…</pre>`;
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  foot.innerHTML = `
    <button class="btn btn-danger btn-sm" data-t-cancel>${icon("stop")}取消任务</button>
    <span class="spacer"></span>
    <span class="hint">关闭窗口后任务会在后台继续</span>
    <button class="btn btn-light" data-t-close>关闭</button>`;
  const handle = modal({
    title,
    subtitle: kind === "java" ? "Adoptium JDK" : "Minecraft 版本下载与安装",
    iconName: kind === "java" ? "coffee" : "download",
    wide: true,
    locked: true,
    body,
    footer: foot,
  });
  let timer = 0;
  let finished = false;

  const pctEl = body.querySelector("[data-t-pct]");
  const phaseEl = body.querySelector("[data-t-phase]");
  const messageEl = body.querySelector("[data-t-message]");
  const fillEl = body.querySelector("[data-t-fill]");
  const speedEl = body.querySelector("[data-t-speed]");
  const sizeEl = body.querySelector("[data-t-size]");
  const filesEl = body.querySelector("[data-t-files]");
  const elapsedEl = body.querySelector("[data-t-elapsed]");
  const currentEl = body.querySelector("[data-t-current]");
  const logEl = body.querySelector("[data-t-log]");
  const cancelBtn = foot.querySelector("[data-t-cancel]");

  function setFooterDone(task) {
    const done = task.status === "done";
    const failed = task.status === "failed";
    const version = meta.version || (kind === "install" ? (task.title || "").replace(/^安装\s+/, "") : "");
    foot.innerHTML = `
      <span class="spacer"></span>
      <button class="btn btn-light" data-t-close>关闭</button>
      ${done && kind === "install" && version ? `<button class="btn btn-primary" data-t-launch>${icon("play")}启动 ${esc(version)}</button>` : ""}
      ${failed ? `<button class="btn btn-light" data-t-retry>${icon("refresh")}重试</button>` : ""}`;
    foot.querySelector("[data-t-close]").addEventListener("click", () => handle.close());
    const launchBtn = foot.querySelector("[data-t-launch]");
    if (launchBtn) {
      launchBtn.addEventListener("click", () => { handle.close(); launch(version); });
    }
    const retryBtn = foot.querySelector("[data-t-retry]");
    if (retryBtn) {
      retryBtn.addEventListener("click", () => {
        handle.close();
        if (kind === "java" && meta.major) downloadJava(meta.major);
        else if (version) openInstall(version);
      });
    }
  }

  function applyTask(task) {
    const percent = task.status === "done" ? 100 : Number(task.percent || 0);
    pctEl.textContent = percent >= 100 ? "100" : percent >= 10 ? Math.floor(percent) : percent.toFixed(1);
    fillEl.style.width = `${percent}%`;
    phaseEl.textContent = task.phase || (task.status === "running" ? "下载中" : "");
    messageEl.textContent = task.message || task.current || "正在处理…";
    speedEl.textContent = task.status === "running" ? fmtSpeed(task.speed) : "—";
    sizeEl.textContent = `${fmtBytes(task.done_bytes)} / ${task.total_bytes ? fmtBytes(task.total_bytes) : "—"}`;
    filesEl.textContent = `${task.done_files} / ${task.total_files || "—"}`;
    elapsedEl.textContent = fmtDuration(task.elapsed);
    currentEl.textContent = task.current || "—";
    const atBottom = logEl.scrollTop + logEl.clientHeight >= logEl.scrollHeight - 30;
    logEl.textContent = (task.logs && task.logs.length) ? task.logs.join("\n") : "等待任务输出…";
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;

    if (task.status === "done") {
      handle.setHead({ title: `${title} · 完成`, subtitle: task.message || "任务已完成", iconName: "check", tone: "ok" });
      cancelBtn.style.display = "none";
      setFooterDone(task);
    } else if (task.status === "failed") {
      handle.setHead({ title: `${title} · 失败`, subtitle: task.error || "任务失败", iconName: "warning", tone: "err" });
      cancelBtn.style.display = "none";
      setFooterDone(task);
    } else if (task.status === "cancelled") {
      handle.setHead({ title: `${title} · 已取消`, subtitle: "任务已被取消，可重新开始", iconName: "x", tone: "warn" });
      cancelBtn.style.display = "none";
      setFooterDone(task);
    } else if (task.status === "cancelling") {
      cancelBtn.disabled = true;
      cancelBtn.textContent = "正在取消…";
    }
  }

  async function poll() {
    if (finished) return;
    try {
      const data = await api(`/api/task/${taskId}`);
      const task = data.task;
      applyTask(task);
      if (["done", "failed", "cancelled"].includes(task.status)) {
        finished = true;
        clearInterval(timer);
        toast(`${task.title}：${task.status === "done" ? "完成" : task.status === "failed" ? task.error : "已取消"}`,
          task.status === "done" ? "success" : task.status === "failed" ? "error" : "info", 6000);
        try {
          await refreshBootstrap();
        } catch { /* 状态刷新失败不改变任务结果 */ }
        if (state.route !== "settings") render();
        else updateChrome();
      }
    } catch (error) {
      clearInterval(timer);
      finished = true;
      handle.setHead({ title: `${title} · 状态未知`, subtitle: error.message, iconName: "warning", tone: "warn" });
      messageEl.textContent = error.message;
      logEl.textContent = error.message;
    }
  }

  cancelBtn.addEventListener("click", async () => {
    cancelBtn.disabled = true;
    cancelBtn.textContent = "正在取消…";
    try {
      await api(`/api/task/${taskId}/cancel`, { method: "POST", body: {} });
    } catch (error) {
      toast(error.message, "error");
      cancelBtn.disabled = false;
    }
  });
  foot.querySelector("[data-t-close]").addEventListener("click", () => handle.close());
  timer = setInterval(poll, 450);
  poll();
}

/* ---------- 设置 / 维护 ---------- */
async function saveSettings(payload) {
  try {
    const data = await api("/api/settings", { method: "POST", body: payload });
    state.settings = data.settings;
    state.java = data.java || state.java;
    if (state.downloadUi && data.settings.download_source) state.downloadUi.source = data.settings.download_source;
    try { await refreshBootstrap(); } catch { /* 忽略局部刷新失败 */ }
    toast("设置已保存", "success");
    render();
  } catch (error) {
    toast(error.message, "error", 5000);
    throw error;
  }
}

async function deleteVersion(version) {
  const ok = await confirmDialog({
    title: `删除 ${version}`,
    message: "只会删除该版本文件夹中的客户端、版本 JSON 与 natives，不会删除存档、共享的 libraries / assets。确定继续？",
    confirmText: "删除版本",
    danger: true,
    iconName: "trash",
  });
  if (!ok) return;
  try {
    const data = await api("/api/version/delete", { method: "POST", body: { version } });
    try { await refreshBootstrap(); } catch { /* 忽略局部刷新失败 */ }
    toast(`已删除 ${version}，释放 ${fmtBytes(data.freed)}`, "success");
    render();
  } catch (error) {
    toast(error.message, "error", 5000);
  }
}

async function openPath(target, version = "", kind = "") {
  try {
    const data = await api("/api/open", { method: "POST", body: { target, version, kind } });
    toast(`已打开：${data.path}`, "success");
  } catch (error) {
    toast(error.message, "error", 5000);
  }
}

async function openFolder(target, version = "") {
  return openPath(target, version);
}

/* ---------- 账户管理 ---------- */
function openAccountDialog() {
  const body = document.createElement("div");
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  const handle = modal({
    title: "账户管理",
    subtitle: "离线账户 · 生成 UUID 并用于启动",
    iconName: "user",
    body,
    footer: foot,
  });
  let mode = "list";

  function paint() {
    if (mode === "add") {
      body.innerHTML = `
        <div class="account-form">
          <div class="account-big-avatar" data-avatar>${icon("user")}</div>
          <div class="field" style="flex:1">
            <label for="accountNameInput">玩家名</label>
            <input class="input" id="accountNameInput" maxlength="16" autocomplete="off" placeholder="1–16 位字母、数字或下划线">
            <span class="hint">离线账户的 UUID 由玩家名生成，可在单人游戏与离线服务器使用。</span>
          </div>
        </div>`;
      foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-cancel>返回</button><button class="btn btn-primary" data-save>${icon("check")}创建并切换</button>`;
      const input = body.querySelector("#accountNameInput");
      const avatar = body.querySelector("[data-avatar]");
      input.addEventListener("input", () => {
        avatar.textContent = (input.value.trim()[0] || "?").toUpperCase();
        avatar.style.background = avatarColor(input.value.trim());
      });
      input.focus();
      foot.querySelector("[data-cancel]").addEventListener("click", () => { mode = "list"; paint(); });
      foot.querySelector("[data-save]").addEventListener("click", async () => {
        const name = input.value.trim();
        if (!/^[A-Za-z0-9_]{1,16}$/.test(name)) { toast("玩家名只能包含字母、数字、下划线，长度 1–16", "error"); return; }
        const saveBtn = foot.querySelector("[data-save]");
        saveBtn.disabled = true;
        try {
          const data = await api("/api/accounts/add", { method: "POST", body: { name } });
          applyAccountPayload(data);
          mode = "list";
          paint();
          toast(`已创建账户 ${name}`, "success");
          refreshBootstrap().catch(() => {});
        } catch (error) {
          toast(error.message, "error", 5000);
          saveBtn.disabled = false;
        }
      });
      return;
    }
    const accounts = state.accounts || [];
    body.innerHTML = `<div class="account-list">${accounts.map((account) => {
      const active = account.id === state.activeAccount;
      return `<div class="account-row ${active ? "active" : ""}">
        <div class="account-avatar" style="background:${avatarColor(account.name)}">${esc((account.name || "?").slice(0, 1).toUpperCase())}</div>
        <div class="account-info"><strong>${esc(account.name)}</strong><span class="mono">${esc(shortUuid(account.uuid))}</span></div>
        ${active ? `<span class="badge ok">${icon("check")}当前</span>` : `<button class="btn btn-soft btn-sm" data-select="${esc(account.id)}">使用</button>`}
        <button class="icon-btn" data-remove="${esc(account.id)}" title="删除账户" ${accounts.length <= 1 ? "disabled" : ""}>${icon("trash")}</button>
      </div>`;
    }).join("")}</div>
    <p class="hint" style="margin-top:12px">离线账户仅适用于单人游戏和未开启正版验证的服务器；启动器不会上传玩家名。</p>`;
    foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-close>关闭</button><button class="btn btn-primary" data-add>${icon("plus")}添加离线账户</button>`;
    foot.querySelector("[data-close]").addEventListener("click", () => handle.close());
    foot.querySelector("[data-add]").addEventListener("click", () => { mode = "add"; paint(); });
    body.querySelectorAll("[data-select]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const data = await api("/api/accounts/select", { method: "POST", body: { id: button.dataset.select } });
          applyAccountPayload(data);
          paint();
          toast("账户已切换", "success");
          refreshBootstrap().catch(() => {});
        } catch (error) {
          toast(error.message, "error", 5000);
          button.disabled = false;
        }
      });
    });
    body.querySelectorAll("[data-remove]").forEach((button) => {
      button.addEventListener("click", async () => {
        const account = accounts.find((item) => item.id === button.dataset.remove);
        if (!account) return;
        const ok = await confirmDialog({
          title: `删除账户 ${account.name}`,
          message: "仅从启动器账户列表中移除，不会删除该玩家的存档。",
          confirmText: "删除账户",
          danger: true,
          iconName: "trash",
        });
        if (!ok) return;
        try {
          const data = await api("/api/accounts/remove", { method: "POST", body: { id: account.id } });
          applyAccountPayload(data);
          paint();
          toast("账户已删除", "success");
          refreshBootstrap().catch(() => {});
        } catch (error) { toast(error.message, "error", 5000); }
      });
    });
  }

  paint();
}

function applyAccountPayload(data) {
  const box = data && !Array.isArray(data) ? data : {};
  state.accounts = Array.isArray(data) ? data : (box.accounts || []);
  state.activeAccount = box.selected?.id || state.activeAccount;
  if (box.selected?.name) state.settings = { ...(state.settings || {}), username: box.selected.name };
  updateChrome();
}

function avatarColor(name) {
  const colors = ["#3b6ef6", "#18a86b", "#7c5cfc", "#e08b2d", "#d6557a", "#2b9bb5", "#5a6b8c"];
  let hash = 0;
  for (const ch of String(name || "?")) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  return colors[hash % colors.length];
}

function shortUuid(uuid) {
  const value = String(uuid || "").replace(/-/g, "");
  return value ? `${value.slice(0, 8)}…${value.slice(-4)}` : "—";
}

/* ---------- 版本内容管理 ---------- */
async function openVersionManage(version) {
  const item = (state.installed || []).find((entry) => entry.id === version);
  const body = document.createElement("div");
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  foot.innerHTML = `<span class="hint" data-vm-path>${esc(item?.game_dir || "")}</span><span class="spacer"></span><button class="btn btn-light" data-vm-open>${icon("folder")}内容目录</button><button class="btn btn-light" data-vm-close>关闭</button>`;
  const handle = modal({
    title: `管理 ${version}`,
    subtitle: `${item?.loader && item.loader !== "vanilla" ? `${item.loader} · ` : ""}${item?.game_version || ""} · 模组 / 资源包 / 光影 / 存档`,
    iconName: "layers",
    wide: true,
    body,
    footer: foot,
  });
  let active = "mods";
  let content = null;
  let settings = null;
  let loading = true;
  let error = "";

  foot.querySelector("[data-vm-close]").addEventListener("click", () => handle.close());
  foot.querySelector("[data-vm-open]").addEventListener("click", () => {
    if (active === "settings") openPath("version", version);
    else openPath("content", version, active);
  });

  const TABS = [
    ["mods", "模组", "package"],
    ["resourcepacks", "资源包", "image"],
    ["shaderpacks", "光影", "spark"],
    ["saves", "存档", "archive"],
    ["settings", "版本设置", "sliders"],
  ];

  function paint() {
    const counts = content ? {
      mods: content.mods?.length || 0,
      resourcepacks: content.resourcepacks?.length || 0,
      shaderpacks: content.shaderpacks?.length || 0,
      saves: content.saves?.length || 0,
    } : {};
    body.innerHTML = `
      <div class="vm-tabs">${TABS.map(([id, label, ico]) => `<button type="button" class="vm-tab ${active === id ? "active" : ""}" data-vm-tab="${id}">${icon(ico)}${label}${counts[id] !== undefined ? `<span>${counts[id]}</span>` : ""}</button>`).join("")}</div>
      <div id="vmPane" class="vm-pane"></div>`;
    const pane = body.querySelector("#vmPane");
    body.querySelectorAll("[data-vm-tab]").forEach((button) => {
      button.addEventListener("click", () => {
        active = button.dataset.vmTab;
        paint();
        foot.querySelector("[data-vm-open]").innerHTML = `${icon("folder")}${active === "settings" ? "版本目录" : "内容目录"}`;
        if (active === "settings" && !settings && !loading) loadSettings();
      });
    });
    foot.querySelector("[data-vm-open]").innerHTML = `${icon("folder")}${active === "settings" ? "版本目录" : "内容目录"}`;
    if (loading) {
      pane.innerHTML = `<div class="loading-row"><div class="spinner" style="margin:0 auto 10px"></div>正在扫描版本内容…</div>`;
      return;
    }
    if (error) {
      pane.innerHTML = `<div class="empty" style="padding:36px 10px"><div class="empty-art">${icon("warning")}</div><h3>读取失败</h3><p>${esc(error)}</p><button class="btn btn-light btn-sm" data-vm-retry style="margin-top:12px">${icon("refresh")}重试</button></div>`;
      pane.querySelector("[data-vm-retry]")?.addEventListener("click", () => { error = ""; loading = true; paint(); loadContent(); });
      return;
    }
    if (active === "settings") { paintSettings(pane); return; }
    paintContent(pane, active);
  }

  function paintContent(pane, kind) {
    if (!content) return;
    const items = content[kind] || [];
    const labels = { mods: "模组", resourcepacks: "资源包", shaderpacks: "光影", saves: "存档" };
    const hint = {
      mods: "停用模组会把 .jar 改名为 .jar.disabled，不会删除文件。",
      resourcepacks: "启停会同步写入 options.txt 的 resourcePacks 列表。",
      shaderpacks: "光影需要 Iris / OptiFine 等支持；此处只管理文件。",
      saves: "备份会把整个存档目录复制到 backups 目录。",
    }[kind];
    pane.innerHTML = `
      <div class="vm-head">
        <div><strong>${items.length} 个${labels[kind]}</strong><span>${esc(hint)}</span></div>
        <div class="toolbar-right">
          ${kind === "mods" ? `<button class="btn btn-soft btn-sm" data-vm-import>${icon("plus")}导入模组</button>` : ""}
          ${kind === "resourcepacks" ? `<button class="btn btn-soft btn-sm" data-vm-import>${icon("plus")}导入资源包</button>` : ""}
          <button class="icon-btn" data-vm-reload title="刷新">${icon("refresh")}</button>
        </div>
      </div>
      ${items.length ? `<div class="content-list">${items.map((entry) => contentRow(kind, entry)).join("")}</div>` : `<div class="empty" style="padding:34px 10px"><div class="empty-art">${icon(TABS.find((t) => t[0] === kind)?.[2] || "package")}</div><h3>还没有${labels[kind]}</h3><p>可从资源页安装，或把文件放入 ${esc(content.game_dir)}/${kind === "saves" ? "saves" : kind} 目录。</p></div>`}`;
    pane.querySelector("[data-vm-reload]")?.addEventListener("click", () => { loading = true; paint(); loadContent(); });
    pane.querySelector("[data-vm-import]")?.addEventListener("click", () => importContent(kind));
    pane.querySelectorAll("[data-vm-toggle]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await api("/api/content/toggle", { method: "POST", body: { version, kind, name: button.dataset.vmToggle } });
          await loadContent();
          paint();
          toast("已切换内容状态", "success", 1800);
        } catch (error) { toast(error.message, "error", 5000); button.disabled = false; }
      });
    });
    pane.querySelectorAll("[data-vm-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        const name = button.dataset.vmDelete;
        const ok = await confirmDialog({
          title: `删除 ${name}`,
          message: kind === "saves" ? "将永久删除该存档目录，建议先备份。" : "将永久删除该文件。",
          confirmText: "删除",
          danger: true,
          iconName: "trash",
        });
        if (!ok) return;
        try {
          await api("/api/content/delete", { method: "POST", body: { version, kind, name } });
          await loadContent();
          paint();
          toast("已删除", "success");
        } catch (error) { toast(error.message, "error", 5000); }
      });
    });
    pane.querySelectorAll("[data-vm-backup]").forEach((button) => {
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const data = await api("/api/content/backup", { method: "POST", body: { version, name: button.dataset.vmBackup } });
          toast(`备份完成：${data.backup?.filename || "backups"}`, "success", 6000);
        } catch (error) { toast(error.message, "error", 5000); }
        finally { button.disabled = false; }
      });
    });
  }

  function contentRow(kind, entry) {
    const enabled = entry.enabled;
    const meta = [entry.version, entry.authors, entry.game_type, entry.version && kind === "saves" ? `游戏 ${entry.version}` : ""].filter(Boolean).join(" · ");
    const size = entry.size ? fmtBytes(entry.size) : "";
    const iconName = kind === "mods" ? "package" : kind === "saves" ? "archive" : kind === "shaderpacks" ? "spark" : "image";
    return `<div class="content-row ${kind === "mods" && enabled === false ? "disabled" : ""}">
      <div class="content-icon">${icon(iconName)}</div>
      <div class="content-info">
        <strong title="${esc(entry.filename)}">${esc(entry.name)}</strong>
        <span>${esc(entry.description || meta || entry.filename)}</span>
        <small>${esc(entry.modified || "")}${size ? ` · ${size}` : ""}${entry.last_played ? ` · 上次 ${entry.last_played}` : ""}</small>
      </div>
      ${kind === "saves" ? `<button class="btn btn-light btn-sm" data-vm-backup="${esc(entry.filename)}">${icon("archive")}备份</button>` : kind === "mods" || kind === "resourcepacks" ? `<label class="switch" title="${enabled ? "已启用" : "已停用"}"><input type="checkbox" data-vm-toggle="${esc(entry.filename)}" ${enabled ? "checked" : ""}><span class="track"></span></label>` : `<span class="badge muted">文件</span>`}
      <button class="icon-btn" data-vm-delete="${esc(entry.filename)}" title="删除">${icon("trash")}</button>
    </div>`;
  }

  function paintSettings(pane) {
    if (!settings) return;
    const overrides = settings.overrides || {};
    pane.innerHTML = `
      <div class="vm-settings">
        <div class="switch-row">
          <div class="switch-text"><strong>版本隔离</strong><span>开启后，该版本的 mods、config、存档写入独立目录；关闭则与全局游戏目录共用。</span></div>
          <label class="switch"><input type="checkbox" id="vmIsolated" ${settings.isolated ? "checked" : ""}><span class="track"></span></label>
        </div>
        <div class="version-path mono">${esc(settings.game_dir || "")}</div>
        <div class="form-grid-2" style="margin-top:14px">
          <div class="field"><label>最大内存（MB）</label><input class="input" id="vmMemory" type="number" min="512" max="65536" step="512" placeholder="继承全局" value="${overrides.memory_mb || ""}"></div>
          <div class="field"><label>Java 路径</label><input class="input mono" id="vmJava" placeholder="继承全局 Java" value="${esc(overrides.java_path || "")}"></div>
        </div>
        <div class="field" style="margin-top:12px"><label>额外 JVM 参数</label><textarea class="textarea" id="vmJvm" placeholder="继承全局参数">${esc(overrides.jvm_args || "")}</textarea></div>
        <div class="form-grid-2" style="margin-top:12px">
          <div class="field"><label>窗口宽度</label><input class="input" id="vmWidth" type="number" min="0" max="7680" placeholder="继承全局" value="${Number(overrides.width) || ""}"></div>
          <div class="field"><label>窗口高度</label><input class="input" id="vmHeight" type="number" min="0" max="4320" placeholder="继承全局" value="${Number(overrides.height) || ""}"></div>
        </div>
        <div class="switch-row" style="margin-top:6px">
          <div class="switch-text"><strong>全屏启动</strong><span>覆盖全局全屏设置</span></div>
          <label class="switch"><input type="checkbox" id="vmFullscreen" ${overrides.fullscreen ? "checked" : ""}><span class="track"></span></label>
        </div>
        <div class="mini-actions" style="margin-top:14px">
          <button class="btn btn-primary btn-sm" data-vm-save>${icon("check")}保存版本设置</button>
          <button class="btn btn-light btn-sm" data-vm-open-dir>${icon("folder")}打开版本目录</button>
        </div>
      </div>`;
    pane.querySelector("[data-vm-open-dir]").addEventListener("click", () => openPath("version", version));
    pane.querySelector("[data-vm-save]").addEventListener("click", async () => {
      const save = pane.querySelector("[data-vm-save]");
      save.disabled = true;
      const payload = {
        version,
        isolated: pane.querySelector("#vmIsolated").checked,
        memory_mb: Number(pane.querySelector("#vmMemory").value) || 0,
        java_path: pane.querySelector("#vmJava").value.trim(),
        jvm_args: pane.querySelector("#vmJvm").value,
        width: Number(pane.querySelector("#vmWidth").value) || 0,
        height: Number(pane.querySelector("#vmHeight").value) || 0,
        fullscreen: pane.querySelector("#vmFullscreen").checked,
      };
      try {
        const data = await api("/api/version/settings", { method: "POST", body: payload });
        settings.overrides = data.overrides;
        settings.isolated = data.isolated;
        settings.game_dir = data.game_dir;
        await refreshBootstrap();
        toast("版本设置已保存", "success");
      } catch (error) {
        toast(error.message, "error", 5000);
      } finally { save.disabled = false; }
    });
  }

  async function loadContent() {
    loading = true;
    error = "";
    try {
      content = await api(`/api/content?version=${encodeURIComponent(version)}`);
    } catch (err) {
      error = err.message;
    } finally {
      loading = false;
      paint();
    }
  }

  async function loadSettings() {
    loading = true; paint();
    try {
      settings = await api(`/api/version/settings?version=${encodeURIComponent(version)}`);
    } catch (err) { error = err.message; }
    finally { loading = false; paint(); }
  }

  function importContent(kind) {
    const importBody = document.createElement("div");
    const importPlaceholder = state.app?.os === "windows" ? "C:\\Users\\你的用户名\\Downloads\\mod.jar" : "/home/user/下载/mod.jar";
    importBody.innerHTML = `<div class="field"><label>本地文件路径</label><input class="input mono" id="vmImportPath" placeholder="${esc(importPlaceholder)}" spellcheck="false"><span class="hint">将从运行启动器的这台设备复制文件到当前版本的 ${kind} 目录。</span></div>`;
    const importFoot = document.createElement("div");
    importFoot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
    importFoot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-icancel>取消</button><button class="btn btn-primary" data-import>${icon("plus")}导入</button>`;
    const importHandle = modal({ title: "导入文件", subtitle: kind === "mods" ? "复制模组 jar" : "复制资源包 zip", iconName: "folder", body: importBody, footer: importFoot, slim: true });
    importFoot.querySelector("[data-icancel]").addEventListener("click", () => importHandle.close());
    importFoot.querySelector("[data-import]").addEventListener("click", async () => {
      const source = importBody.querySelector("#vmImportPath").value.trim();
      if (!source) { toast("请填写文件路径", "error"); return; }
      importFoot.querySelector("[data-import]").disabled = true;
      try {
        await api("/api/content/import", { method: "POST", body: { version, kind, source } });
        importHandle.close();
        await loadContent();
        paint();
        toast("导入完成", "success");
      } catch (error) { toast(error.message, "error", 5000); importFoot.querySelector("[data-import]").disabled = false; }
    });
  }

  paint();
  loadContent();
}

/* ---------- 加载器安装 ---------- */
function openLoaderInstall(baseGame = "") {
  const games = (state.versions || []).filter((item) => item.type === "release" || item.type === "snapshot").map((item) => item.id);
  const installedGames = [...new Set((state.installed || []).map((item) => item.game_version).filter(Boolean))];
  const defaultGame = baseGame || state.latest?.release || installedGames[0] || games[0] || "";
  const dataList = [...new Set([...games, ...installedGames])].slice(0, 400);
  const body = document.createElement("div");
  const foot = document.createElement("div");
  foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
  const handle = modal({
    title: "安装模组加载器",
    subtitle: "Fabric / Quilt / Forge / NeoForge",
    iconName: "plug",
    wide: true,
    body,
    footer: foot,
  });
  let type = "fabric";
  let game = defaultGame;
  let versions = [];
  let recommended = "";
  let loading = false;
  let error = "";
  let seq = 0;

  body.innerHTML = `
    <div class="loader-types">${["fabric", "forge", "neoforge", "quilt"].map((id) => `<button type="button" class="loader-type ${id === type ? "active" : ""}" data-loader-type="${id}"><span class="lt-logo ${id}">${id.slice(0, 1).toUpperCase()}</span><strong>${id === "neoforge" ? "NeoForge" : id[0].toUpperCase() + id.slice(1)}</strong><small>${loaderDesc(id)}</small></button>`).join("")}</div>
    <div class="form-grid-2" style="margin-top:14px">
      <div class="field"><label>Minecraft 版本</label><input class="input" id="loaderGame" list="loaderGameList" value="${esc(game)}" placeholder="例如 1.21.4" spellcheck="false"><datalist id="loaderGameList">${dataList.map((id) => `<option value="${esc(id)}"></option>`).join("")}</datalist></div>
      <div class="field"><label>加载器版本</label><select class="select" id="loaderVersion"><option>正在获取…</option></select></div>
    </div>
    <div class="loader-note" id="loaderNote"><span class="spinner"></span>正在读取加载器版本列表…</div>
    <div class="switch-row" style="margin-top:10px">
      <div class="switch-text"><strong>自动准备所需 Java</strong><span>检测到本机缺少对应 Java 时从 Adoptium 下载匹配平台的 JDK</span></div>
      <label class="switch"><input type="checkbox" id="loaderAutoJava" checked><span class="track"></span></label>
    </div>
    <p class="hint" style="margin-top:10px">Fabric / Quilt 直接合并官方 profile；Forge / NeoForge 会下载官方 installer 并执行 --installClient，耗时较长。安装完成后会出现在“版本管理”中。</p>`;
  foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-lcancel>取消</button><button class="btn btn-primary" data-linstall>${icon("download")}安装加载器</button>`;
  const gameEl = body.querySelector("#loaderGame");
  const versionEl = body.querySelector("#loaderVersion");
  const noteEl = body.querySelector("#loaderNote");

  function paintTypes() {
    body.querySelectorAll("[data-loader-type]").forEach((button) => {
      button.classList.toggle("active", button.dataset.loaderType === type);
      button.addEventListener("click", () => { type = button.dataset.loaderType; paintTypes(); fetchVersions(); });
    });
  }

  async function fetchVersions() {
    const current = ++seq;
    game = gameEl.value.trim();
    if (!/^[A-Za-z0-9._+-]{1,64}$/.test(game)) {
      versionEl.innerHTML = `<option value="">请输入有效版本</option>`;
      noteEl.innerHTML = `${icon("warning")}请输入 Minecraft 版本号，例如 1.21.4。`;
      return;
    }
    loading = true;
    error = "";
    versionEl.innerHTML = `<option>读取中…</option>`;
    noteEl.innerHTML = `<span class="spinner"></span>正在读取 ${type} 的版本列表…`;
    try {
      const data = await api(`/api/loader/versions?type=${encodeURIComponent(type)}&game=${encodeURIComponent(game)}`);
      if (current !== seq) return;
      versions = data.versions || [];
      recommended = data.recommended || "";
      if (!versions.length) {
        versionEl.innerHTML = `<option value="">没有可用版本</option>`;
        noteEl.innerHTML = `${icon("warning")}${esc(data.note || "该游戏版本没有对应的加载器版本。")}`;
        return;
      }
      versionEl.innerHTML = versions.map((item) => `<option value="${esc(item.version)}" ${item.version === recommended ? "selected" : ""}>${esc(item.version)}${item.version === recommended ? " · 推荐" : item.recommended ? " · 推荐" : ""}${item.stable === false ? " · Beta" : ""}</option>`).join("");
      noteEl.innerHTML = `<div class="loader-pick"><span>${icon("check")}已找到 ${versions.length} 个版本</span><span>推荐 <strong>${esc(recommended || versions[0].version)}</strong></span></div>`;
    } catch (err) {
      if (current !== seq) return;
      error = err.message;
      versionEl.innerHTML = `<option value="">获取失败</option>`;
      noteEl.innerHTML = `${icon("warning")}${esc(err.message)} <button class="btn btn-light btn-sm" data-lretry>重试</button>`;
      noteEl.querySelector("[data-lretry]")?.addEventListener("click", fetchVersions);
    } finally {
      if (current === seq) loading = false;
    }
  }

  gameEl.addEventListener("change", fetchVersions);
  gameEl.addEventListener("blur", fetchVersions);
  foot.querySelector("[data-lcancel]").addEventListener("click", () => handle.close());
  foot.querySelector("[data-linstall]").addEventListener("click", async () => {
    game = gameEl.value.trim();
    const loaderVersion = versionEl.value;
    if (!game || !loaderVersion) { toast("请选择游戏版本与加载器版本", "error"); return; }
    const button = foot.querySelector("[data-linstall]");
    button.disabled = true;
    try {
      const data = await api("/api/loader/install", {
        method: "POST",
        body: { type, game, loader: loaderVersion, auto_java: body.querySelector("#loaderAutoJava").checked, source: state.settings?.download_source || "official" },
      });
      handle.close();
      openTaskModal(data.task_id, { kind: "loader", title: `安装 ${type} ${loaderVersion}`, version: game });
    } catch (error) {
      toast(error.message, "error", 6000);
      button.disabled = false;
    }
  });

  paintTypes();
  fetchVersions();
}

function loaderDesc(id) {
  return {
    fabric: "轻量、更新快",
    forge: "老牌模组平台",
    neoforge: "Forge 现代分支",
    quilt: "兼容 Fabric 生态",
  }[id] || "";
}

const actions = {
  navigate,
  launch,
  openInstall,
  downloadJava,
  refreshJava,
  refreshInstalled,
  loadVersions,
  saveSettings,
  deleteVersion,
  openFolder,
  openPath,
  openVersionManage,
  openLoaderInstall,
  openAccountDialog,
  openTaskModal,
  openLaunchModal,
  refreshBootstrap,
  modal,
  confirm: confirmDialog,
  render,
};

/* ---------- 启动应用 ---------- */
function errorPage(title, message) {
  const root = document.createElement("div");
  root.className = "page";
  root.innerHTML = `<div class="card card-pad"><div class="empty">
    <div class="empty-art">${icon("warning")}</div>
    <h3>${esc(title)}</h3>
    <p>${esc(message)}</p>
    <button class="btn btn-primary" data-reload>${icon("refresh")}重新加载</button>
  </div></div>`;
  root.querySelector("[data-reload]").addEventListener("click", () => location.reload());
  return root;
}

async function boot() {
  hydrateIcons(document);
  $$(".nav-item").forEach((item) => {
    item.addEventListener("click", () => navigate(item.dataset.route));
  });
  $("#logBtn").addEventListener("click", () => openLaunchModal());
  $("#refreshBtn").addEventListener("click", manualRefresh);
  $("#account").addEventListener("click", openAccountDialog);
  window.addEventListener("hashchange", () => render());
  try {
    await refreshBootstrap();
    state.ready = true;
    if (!location.hash) history.replaceState(null, "", "#/home");
    state.route = currentRoute();
    render();
  } catch (error) {
    main.replaceChildren(errorPage("无法连接本地服务", error.message));
  }
}

setInterval(async () => {
  if (!state.ready) return;
  try {
    const data = await api("/api/tasks");
    state.tasks = data.tasks || [];
    updateChrome();
  } catch { /* 忽略后台轮询错误 */ }
}, 4000);

setInterval(async () => {
  if (!state.ready || !state.launch?.running) return;
  try {
    const data = await api("/api/launch?status=1");
    state.launch = { ...state.launch, ...data.launch };
    updateChrome();
  } catch { /* 忽略 */ }
}, 3000);

boot();
