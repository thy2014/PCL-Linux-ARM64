/* 服务器页：服务器列表、状态协议测速、快速进入 */
import { api } from "../api.js";
import { icon, esc, toast, modal } from "../ui.js";

export function serversPage(ctx) {
  const { state, actions } = ctx;
  const installed = state.installed || [];
  if (!state.serverUi) {
    state.serverUi = { target: installed[0]?.id || "", pings: {}, checking: {} };
  }
  const ui = state.serverUi;
  if (!ui.target && installed[0]) ui.target = installed[0].id;
  const servers = state.servers || [];
  const root = document.createElement("div");
  root.className = "page";

  const targetOptions = installed.length
    ? installed.map((item) => `<option value="${esc(item.id)}" ${item.id === ui.target ? "selected" : ""}>${esc(item.id)} · ${esc(item.loader || "vanilla")} · ${esc(item.game_version || "")}</option>`).join("")
    : `<option value="">尚无已安装版本</option>`;

  root.innerHTML = `
    <div class="card page-toolbar">
      <div>
        <strong style="font-size:14px">服务器列表</strong>
        <span class="count" style="margin-left:8px;font-size:11.5px;color:var(--muted)">${servers.length} 个服务器</span>
      </div>
      <div class="toolbar-right">
        <select class="select" id="serverTarget" title="启动进入时使用的版本">${targetOptions}</select>
        <button class="btn btn-light btn-sm" data-ping-all>${icon("refresh")}全部测速</button>
        <button class="btn btn-primary btn-sm" data-add-server>${icon("plus")}添加服务器</button>
      </div>
    </div>
    <div class="server-tip card">
      <div class="res-note-icon">${icon("globe")}</div>
      <div><strong>使用 Minecraft 服务器列表协议测速</strong><span>延迟与在线人数由服务器实时返回；需要目标版本可正常启动。启动时会使用快速进入参数加入服务器。</span></div>
      <span class="badge ${installed.length ? "ok" : "warn"}">${installed.length ? `${installed.length} 个版本可用` : "没有可用版本"}</span>
    </div>
    <div id="serverList" class="server-list"></div>`;

  const listEl = root.querySelector("#serverList");
  const targetEl = root.querySelector("#serverTarget");
  targetEl?.addEventListener("change", () => { ui.target = targetEl.value; });

  function paint() {
    if (!servers.length) {
      listEl.innerHTML = `<div class="card card-pad"><div class="empty">
        <div class="empty-art">${icon("server")}</div>
        <h3>还没有添加服务器</h3>
        <p>添加常用服务器后可以一键测速，并直接从启动器进入游戏。</p>
        <button class="btn btn-primary" data-empty-add>${icon("plus")}添加服务器</button>
      </div></div>`;
      listEl.querySelector("[data-empty-add]")?.addEventListener("click", () => openEditor());
      return;
    }
    listEl.innerHTML = servers.map((server) => {
      const ping = ui.pings[server.id];
      const checking = ui.checking[server.id];
      const online = ping?.ok;
      return `<div class="server-card card">
        <div class="server-favicon">${online && ping.favicon ? `<img src="${esc(ping.favicon)}" alt="">` : icon("server")}</div>
        <div class="server-main">
          <div class="server-title"><h3>${esc(server.name)}</h3><span class="mono">${esc(server.host)}:${Number(server.port) || 25565}</span></div>
          <p class="server-motd">${esc(stripMc(online ? ping.motd : (ping?.error || "尚未测速"))) || "—"}</p>
          <div class="server-meta">
            ${checking ? `<span class="badge muted">测速中…</span>` : online ? `
              <span class="badge ok">${ping.latency} ms</span>
              <span class="badge muted">${esc(ping.version || "未知版本")}</span>
              <span class="badge release">${ping.online} / ${ping.max} 人</span>` : ping ? `<span class="badge warn">${esc(ping.error || "离线")}</span>` : `<span class="badge muted">未测速</span>`}
          </div>
        </div>
        <div class="server-actions">
          <button class="btn btn-light btn-sm" data-ping="${esc(server.id)}">${icon("refresh")}测速</button>
          <button class="btn btn-soft btn-sm" data-join="${esc(server.id)}">${icon("play")}进入</button>
          <button class="icon-btn" data-edit="${esc(server.id)}" title="编辑">${icon("sliders")}</button>
          <button class="icon-btn" data-del="${esc(server.id)}" title="删除">${icon("trash")}</button>
        </div>
      </div>`;
    }).join("");
  }

  async function pingServer(server, silent = false) {
    ui.checking[server.id] = true;
    paint();
    try {
      const data = await api(`/api/servers/ping?host=${encodeURIComponent(server.host)}&port=${Number(server.port) || 25565}`);
      ui.pings[server.id] = data.ping;
    } catch (error) {
      ui.pings[server.id] = { ok: false, error: error.message };
      if (!silent) toast(error.message, "error");
    } finally {
      ui.checking[server.id] = false;
      paint();
    }
  }

  async function pingAll() {
    const pending = servers.filter((server) => !ui.checking[server.id]);
    if (!pending.length) return;
    toast(`正在检测 ${pending.length} 个服务器…`, "info", 1800);
    let index = 0;
    const workers = Array.from({ length: Math.min(6, pending.length) }, async () => {
      while (index < pending.length) {
        const server = pending[index++];
        await pingServer(server, true);
      }
    });
    await Promise.all(workers);
    toast("服务器测速完成", "success");
  }

  function openEditor(server = null) {
    const body = document.createElement("div");
    body.innerHTML = `
      <div class="form-stack">
        <div class="field"><label>名称</label><input class="input" data-f-name maxlength="40" value="${esc(server?.name || "")}" placeholder="例如：Hypixel"></div>
        <div class="field"><label>地址</label><input class="input mono" data-f-host value="${esc(server?.host || "")}" placeholder="mc.example.com 或 127.0.0.1" spellcheck="false"></div>
        <div class="field"><label>端口</label><input class="input" data-f-port type="number" min="1" max="65535" value="${Number(server?.port) || 25565}"></div>
      </div>
      <p class="hint" style="margin:10px 0 0">支持域名或 IP；暂不自动解析 SRV 记录。</p>`;
    const foot = document.createElement("div");
    foot.style.cssText = "display:flex;align-items:center;gap:9px;width:100%";
    foot.innerHTML = `<span class="spacer"></span><button class="btn btn-light" data-cancel>取消</button><button class="btn btn-primary" data-save>${icon("check")}保存</button>`;
    const handle = modal({ title: server ? "编辑服务器" : "添加服务器", subtitle: "名称 / 地址 / 端口", iconName: "server", body, footer: foot, slim: true });
    foot.querySelector("[data-cancel]").addEventListener("click", () => handle.close());
    foot.querySelector("[data-save]").addEventListener("click", async () => {
      const name = body.querySelector("[data-f-name]").value.trim();
      const host = body.querySelector("[data-f-host]").value.trim();
      const port = Number(body.querySelector("[data-f-port]").value) || 25565;
      if (!host) { toast("请填写服务器地址", "error"); return; }
      foot.querySelector("[data-save]").disabled = true;
      try {
        const data = server
          ? await api("/api/servers/update", { method: "POST", body: { id: server.id, name, host, port } })
          : await api("/api/servers/add", { method: "POST", body: { name, host, port } });
        state.servers = data.servers || [];
        handle.close();
        actions.render();
        toast(server ? "服务器已更新" : "服务器已添加", "success");
      } catch (error) {
        toast(error.message, "error", 5000);
        foot.querySelector("[data-save]").disabled = false;
      }
    });
  }

  async function joinServer(server) {
    if (!ui.target) { toast("请先在下载页安装一个版本", "error"); actions.navigate("download"); return; }
    if (!state.launch?.running) {
      try {
        const data = await api("/api/launch", {
          method: "POST",
          body: { version: ui.target, server: { host: server.host, port: server.port } },
        });
        state.launch = data.launch;
        toast(`正在启动 ${ui.target} 并进入 ${server.name}`, "success");
        actions.openLaunchModal(data.launch);
      } catch (error) {
        toast(error.message, "error", 6000);
      }
    } else {
      toast("游戏已在运行；请先在游戏中添加服务器地址", "info");
    }
  }

  listEl.addEventListener("click", (event) => {
    const ping = event.target.closest("[data-ping]");
    if (ping) { const server = servers.find((item) => item.id === ping.dataset.ping); if (server) pingServer(server); return; }
    const join = event.target.closest("[data-join]");
    if (join) { const server = servers.find((item) => item.id === join.dataset.join); if (server) joinServer(server); return; }
    const edit = event.target.closest("[data-edit]");
    if (edit) { const server = servers.find((item) => item.id === edit.dataset.edit); if (server) openEditor(server); return; }
    const del = event.target.closest("[data-del]");
    if (del) {
      const server = servers.find((item) => item.id === del.dataset.del);
      if (server) actions.confirm({
        title: `删除 ${server.name}`,
        message: `只会从列表中移除 ${server.host}:${server.port}，不会影响游戏内的 servers.dat。`,
        confirmText: "删除",
        danger: true,
        iconName: "trash",
      }).then(async (ok) => {
        if (!ok) return;
        try {
          const data = await api("/api/servers/delete", { method: "POST", body: { id: server.id } });
          state.servers = data.servers || [];
          delete ui.pings[server.id];
          actions.render();
          toast("服务器已删除", "success");
        } catch (error) { toast(error.message, "error", 5000); }
      });
    }
  });

  root.querySelector("[data-add-server]").addEventListener("click", () => openEditor());
  root.querySelector("[data-ping-all]").addEventListener("click", pingAll);
  paint();
  if (servers.length && !Object.keys(ui.pings).length) {
    pingAll();
  }
  return root;
}

function stripMc(value) {
  return String(value || "").replace(/§[0-9a-fk-orx]/gi, "").replace(/\s+/g, " ").trim();
}
