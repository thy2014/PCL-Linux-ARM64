/* 设置页 */
import { icon, esc } from "../ui.js";

export function settingsPage(ctx) {
  const { state, actions } = ctx;
  const settings = state.settings || {};
  const java = state.java || [];
  const memory = clamp(Number(settings.memory_mb) || 4096, 1024, 32768);
  const memoryGb = (memory / 1024).toFixed(memory % 1024 ? 1 : 0);
  const pct = ((memory - 1024) / (32768 - 1024)) * 100;
  const javaOptions = [`<option value="" ${!settings.java_path ? "selected" : ""}>自动选择（推荐）</option>`];
  java.forEach((item) => {
    javaOptions.push(`<option value="${esc(item.path)}" ${settings.java_path === item.path ? "selected" : ""}>${esc(item.vendor)} ${esc(item.version)} · Java ${item.major}（${esc(item.source)}）</option>`);
  });
  if (settings.java_path && !java.some((item) => item.path === settings.java_path)) {
    javaOptions.push(`<option value="${esc(settings.java_path)}" selected>自定义：${esc(settings.java_path)}</option>`);
  }

  const root = document.createElement("div");
  root.className = "page";
  root.innerHTML = `
    <div class="settings-grid">
      <div class="card settings-section">
        <h3>游戏与账户</h3>
        <p class="section-sub">版本、存档与资源文件都保存在游戏目录中。更换目录不会自动迁移旧文件。</p>
        <div class="form-stack">
          <div class="field">
            <label for="setGameDir">游戏目录</label>
            <div class="input-group">
              <input class="input mono" id="setGameDir" value="${esc(settings.game_dir || "")}" spellcheck="false">
              <button class="btn btn-light" data-pick-game title="选择游戏目录">${icon("folder")}选择</button>
              <button class="icon-btn" data-open-game title="在文件管理器中打开">${icon("external")}</button>
            </div>
            <span class="hint">启动游戏时使用这个目录；版本、存档、资源与模组都会写在这里。可直接输入，或点“选择”调用系统目录选择器。</span>
          </div>
          <div class="field">
            <label for="setUsername">离线玩家名</label>
            <div class="input-group">
              <input class="input" id="setUsername" maxlength="16" value="${esc(settings.username || "Steve")}" autocomplete="off">
              <button class="btn btn-soft" data-accounts>${icon("user")}管理账户</button>
            </div>
            <span class="hint">当前默认离线账户；多账户可在“管理账户”中切换。</span>
          </div>
          <div class="field">
            <label for="setJavaPath">Java 运行时</label>
            <select class="select" id="setJavaPath">${javaOptions.join("")}</select>
            <div class="mini-actions">
              <button class="btn btn-light btn-sm" data-refresh-java>${icon("refresh")}重新检测</button>
              <button class="btn btn-soft btn-sm" data-java-major="21">${icon("download")}下载 Java 21</button>
              <button class="btn btn-light btn-sm" data-java-major="17">${icon("coffee")}Java 17</button>
            </div>
            <span class="hint">${java.length ? `已检测到 ${java.length} 个 Java。自动模式按版本要求挑选，优先同版本。` : "尚未检测到 Java，可下载与当前平台匹配的 Adoptium JDK。"}</span>
          </div>
        </div>
      </div>

      <div class="card settings-section">
        <h3>性能与启动</h3>
        <p class="section-sub">内存不是越大越好。4-8 GB 适合原版，大型整合包可适当提高。</p>
        <div class="form-stack">
          <div class="field">
            <label for="setMemory">最大内存</label>
            <div class="memory-row">
              <input class="range" id="setMemory" type="range" min="1024" max="32768" step="512" value="${memory}" style="--pct:${pct}%">
              <span class="memory-value" id="memoryValue">${memoryGb} GB</span>
            </div>
            <span class="hint">初始堆固定为 512 MB（-Xms512M）。</span>
          </div>
          <div class="field">
            <label for="setJvm">额外 JVM 参数</label>
            <textarea class="textarea" id="setJvm" spellcheck="false" placeholder="例如：-XX:+UseG1GC -Dfile.encoding=UTF-8">${esc(settings.jvm_args || "")}</textarea>
            <span class="hint">附加在默认内存参数之后，可用空格分隔多个参数。</span>
          </div>
          <div class="field">
            <label>游戏窗口</label>
            <div class="form-grid-2">
              <input class="input" id="setWidth" type="number" min="0" max="7680" placeholder="宽度" value="${Number(settings.width) || 0}">
              <input class="input" id="setHeight" type="number" min="0" max="4320" placeholder="高度" value="${Number(settings.height) || 0}">
            </div>
            <span class="hint">0 × 0 表示使用游戏默认分辨率；填写后需版本支持自定义窗口。</span>
          </div>
          <div class="switch-row">
            <div class="switch-text"><strong>全屏启动</strong><span>以全屏模式打开游戏窗口</span></div>
            <label class="switch"><input type="checkbox" id="setFullscreen" ${settings.fullscreen ? "checked" : ""}><span class="track"></span></label>
          </div>
          <div class="switch-row">
            <div class="switch-text"><strong>版本隔离</strong><span>默认让每个版本使用独立的 mods、config 与存档目录；可被单个版本设置覆盖。</span></div>
            <label class="switch"><input type="checkbox" id="setIsolation" ${settings.version_isolation !== false ? "checked" : ""}><span class="track"></span></label>
          </div>
        </div>
      </div>

      <div class="card settings-section">
        <h3>外观</h3>
        <p class="section-sub">主题只改变强调色与界面色调，不修改游戏设置。</p>
        <div class="theme-grid">
          ${[["blue", "经典蓝", "#3b6ef6"], ["green", "草地方块", "#18a86b"], ["purple", "紫水晶", "#7c5cfc"], ["orange", "熔岩橙", "#e08b2d"], ["red", "红石", "#e5484d"], ["cyan", "海洋青", "#2b9bb5"], ["dark", "夜间", "#202637"]].map(([id, label, color]) => `
            <label class="theme-card ${settings.theme === id ? "active" : ""}">
              <input type="radio" name="theme" value="${id}" ${(settings.theme || "blue") === id ? "checked" : ""}>
              <span class="theme-swatch" style="--swatch:${color}"><i></i><i></i><i></i></span>
              <strong>${label}</strong>
            </label>`).join("")}
        </div>
      </div>

      <div class="card settings-section">
        <h3>下载</h3>
        <p class="section-sub">官方源最稳定；镜像适合部分国内网络，但可能缺少个别文件。</p>
        <div class="form-stack">
          <div class="field">
            <label>下载源</label>
            <div class="radio-cards">
              <label class="radio-card">
                <input type="radio" name="downloadSource" value="official" ${settings.download_source !== "bmclapi" ? "checked" : ""}>
                <strong>官方源</strong>
                <span>Mojang / Minecraft 官方 CDN，稳定、完整</span>
              </label>
              <label class="radio-card">
                <input type="radio" name="downloadSource" value="bmclapi" ${settings.download_source === "bmclapi" ? "checked" : ""}>
                <strong>BMCLAPI 镜像</strong>
                <span>国内加速，失败时回退官方清单</span>
              </label>
            </div>
          </div>
          <div class="field">
            <label for="setThreads">并行下载线程</label>
            <select class="select" id="setThreads">
              ${[4, 8, 12, 16, 24, 32].map((value) => `<option value="${value}" ${Number(settings.download_threads) === value ? "selected" : ""}>${value} 线程</option>`).join("")}
            </select>
            <span class="hint">资源文件数量多时，16-24 线程通常更快；网络不稳定时请降低。</span>
          </div>
        </div>
      </div>

      <div class="card settings-section">
        <h3>数据与维护</h3>
        <p class="section-sub">配置文件、日志与自动下载的 Java 都放在应用数据目录。</p>
        <div class="form-stack">
          <div class="field">
            <label>应用数据目录</label>
            <input class="input mono" value="${esc(state.dirs?.data || "")}" readonly>
            <div class="mini-actions">
              <button class="btn btn-light btn-sm" data-open-data>${icon("folder")}打开数据目录</button>
              <button class="btn btn-light btn-sm" data-open-logs>${icon("terminal")}打开日志目录</button>
            </div>
          </div>
          <div class="kv"><span>配置文件</span><strong class="mono" style="font-size:11px">config.json</strong></div>
          <div class="kv"><span>游戏目录</span><strong style="font-size:11px">${esc(settings.game_dir || "—")}</strong></div>
          <div class="kv"><span>启动日志</span><strong style="font-size:11px">logs/launch-*.log</strong></div>
          <div class="disclaimer">删除版本只会移除“版本文件夹”（客户端、版本 JSON、natives），不会删除共享的 libraries / assets，也不会动存档。</div>
        </div>
      </div>
    </div>

    <div class="save-bar">
      <button class="btn btn-primary" id="saveSettings">${icon("check")}保存设置</button>
      <button class="btn btn-light" id="reloadSettings">${icon("refresh")}撤销修改</button>
      <span class="spacer"></span>
      <span class="save-hint" id="saveHint">修改会写入 ${esc(state.dirs?.data || "应用数据目录")}/config.json</span>
    </div>`;

  const range = root.querySelector("#setMemory");
  const valueEl = root.querySelector("#memoryValue");
  const updateMemory = () => {
    const value = Number(range.value);
    range.style.setProperty("--pct", `${((value - 1024) / (32768 - 1024)) * 100}%`);
    valueEl.textContent = `${(value / 1024).toFixed(value % 1024 ? 1 : 0)} GB`;
  };
  range.addEventListener("input", updateMemory);

  root.querySelectorAll('input[name="theme"]').forEach((input) => {
    input.addEventListener("change", () => {
      document.documentElement.dataset.theme = input.value;
      const hint = root.querySelector("#saveHint");
      if (hint) hint.textContent = "主题已预览，保存后生效";
    });
  });

  root.querySelectorAll("[data-java-major]").forEach((button) => {
    button.addEventListener("click", () => actions.downloadJava(Number(button.dataset.javaMajor)));
  });
  root.querySelectorAll("[data-refresh-java]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      await actions.refreshJava({ silent: true });
      actions.render();
    });
  });
  root.querySelectorAll("[data-accounts]").forEach((button) => {
    button.addEventListener("click", () => actions.openAccountDialog());
  });
  root.querySelectorAll("[data-pick-game]").forEach((button) => {
    button.addEventListener("click", () => actions.chooseGameDirectory());
  });
  root.querySelectorAll("[data-open-game]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("game"));
  });
  root.querySelectorAll("[data-open-data]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("data"));
  });
  root.querySelectorAll("[data-open-logs]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("logs"));
  });

  root.querySelector("#reloadSettings").addEventListener("click", () => {
    document.documentElement.dataset.theme = state.settings?.theme || "blue";
    actions.render();
  });
  root.querySelector("#saveSettings").addEventListener("click", async () => {
    const button = root.querySelector("#saveSettings");
    const hint = root.querySelector("#saveHint");
    const payload = {
      game_dir: root.querySelector("#setGameDir").value.trim(),
      java_path: root.querySelector("#setJavaPath").value,
      username: root.querySelector("#setUsername").value.trim(),
      memory_mb: Number(range.value),
      download_source: root.querySelector('input[name="downloadSource"]:checked')?.value || "official",
      download_threads: Number(root.querySelector("#setThreads").value),
      version_isolation: root.querySelector("#setIsolation").checked,
      theme: root.querySelector('input[name="theme"]:checked')?.value || "blue",
      jvm_args: root.querySelector("#setJvm").value,
      width: Number(root.querySelector("#setWidth").value) || 0,
      height: Number(root.querySelector("#setHeight").value) || 0,
      fullscreen: root.querySelector("#setFullscreen").checked,
    };
    button.disabled = true;
    hint.textContent = "正在保存…";
    try {
      await actions.saveSettings(payload);
      hint.textContent = "已保存";
    } catch {
      hint.textContent = "保存失败";
    } finally {
      button.disabled = false;
    }
  });
  return root;
}

function clamp(value, minimum, maximum) {
  return Math.max(minimum, Math.min(maximum, value));
}
