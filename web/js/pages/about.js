/* 关于页 */
import { icon, esc, logoBadge } from "../ui.js";

export function aboutPage(ctx) {
  const { state, actions } = ctx;
  const app = state.app || {};
  const dirs = state.dirs || {};
  const root = document.createElement("div");
  root.className = "page";
  const projectUrl = app.project_url || "https://github.com/thy2014/PCL-Linux-ARM64";

  const features = [
    ["download", "版本下载", "Mojang 正式版 / 快照 / 远古版，客户端、依赖库、资源索引与资源对象全量安装，SHA1 校验并可断点续传。"],
    ["chip", "ARM64 原生", "自动把 LWJGL 3.3+ 的 linux 原生库替换为 natives-linux-arm64，并识别 LWJGL 2 的不兼容版本。"],
    ["coffee", "Java 托管", "检测系统 Java，缺失时从 Adoptium 下载 ARM64 JDK 8/17/21，校验 SHA256 后解压到数据目录。"],
    ["plug", "加载器", "Fabric、Quilt、Forge、NeoForge 查询与真实安装，推荐版本、Beta 标记与自动 Java。"],
    ["package", "资源下载", "Modrinth 模组 / 整合包 / 资源包 / 光影搜索、版本匹配、前置依赖与 SHA1 校验。"],
    ["archive", "内容管理", "模组启停、资源包 options.txt 同步、光影扫描、存档 NBT 读取、导入与 zip 备份。"],
    ["layers", "版本管理", "多版本共存、版本隔离、单版本内存/JVM/Java/分辨率、打开文件夹与安全删除。"],
    ["shield", "账户", "多离线账户新增、切换、删除，按玩家名生成 UUID，并写入启动参数。"],
    ["server", "服务器", "收藏服务器、Minecraft Server List Ping 延迟/MOTD/人数/favicon，一键带地址启动。"],
    ["wrench", "崩溃诊断", "扫描 latest.log 与 crash-reports，识别内存、Java、OpenGL、模组冲突、重复模组等问题。"],
    ["terminal", "实时日志", "启动输出实时回传界面，同时写入 logs/launch-*.log，支持结束进程与复制启动命令。"],
    ["sliders", "设置与主题", "下载源、线程数、ARM64 补丁、版本隔离、七套主题与全局/版本级启动参数。"],
  ].map(([iconName, title, text]) => `
    <div class="feature">
      <div class="f-icon">${icon(iconName)}</div>
      <strong>${esc(title)}</strong>
      <p>${esc(text)}</p>
    </div>`).join("");

  root.innerHTML = `
    <section class="about-hero">
      <div class="about-logo">${logoBadge()}</div>
      <div class="about-copy">
        <h2>PCL · Linux ARM64</h2>
        <p>${esc(app.tagline || "Plain Craft Launcher · Linux ARM64 社区版")}。面向 ARM64 Linux 的轻量 Minecraft 启动器，不需要 Electron，不需要第三方依赖。</p>
        <div class="about-chips">
          <span class="meta-chip">版本 ${esc(app.version || "1.0.0")}</span>
          <span class="meta-chip">${esc(app.arch_label || "ARM64")} / ${esc(app.os || "linux")}</span>
          <span class="meta-chip">Python 3 标准库</span>
          <span class="meta-chip">MIT License</span>
        </div>
      </div>
    </section>

    <section class="feature-grid">${features}</section>

    <section class="about-grid">
      <div class="card card-pad">
        <div class="panel-title"><h3>项目与链接</h3></div>
        <div class="link-row">
          <span class="lk">${icon("globe")}GitHub 仓库</span>
          <a href="${esc(projectUrl)}" target="_blank" rel="noreferrer">thy2014/PCL-Linux-ARM64 ${icon("external")}</a>
        </div>
        <div class="link-row">
          <span class="lk">${icon("warning")}问题反馈</span>
          <a href="${esc(projectUrl)}/issues" target="_blank" rel="noreferrer">Issues ${icon("external")}</a>
        </div>
        <div class="link-row">
          <span class="lk">${icon("download")}发布页面</span>
          <a href="${esc(projectUrl)}/releases" target="_blank" rel="noreferrer">Releases ${icon("external")}</a>
        </div>
        <div class="link-row">
          <span class="lk">${icon("folder")}应用数据</span>
          <button class="text-btn" data-open-data>打开 ${icon("arrow", "ico-sm")}</button>
        </div>
        <div class="link-row">
          <span class="lk">${icon("terminal")}日志目录</span>
          <button class="text-btn" data-open-logs>打开 ${icon("arrow", "ico-sm")}</button>
        </div>
        <div class="disclaimer" style="margin-top:14px">
          本项目是非官方社区实现，与 Mojang Studios、Microsoft、Plain Craft Launcher 官方没有隶属关系。只调用公开的版本元数据与下载接口，不提供账号登录或正版验证；请购买正版 Minecraft。
        </div>
      </div>

      <div class="card card-pad">
        <div class="panel-title"><h3>目录</h3><span class="spacer"></span><span class="badge muted">${esc(app.arch || "arm64")}</span></div>
        <div class="kv"><span>数据</span><strong style="font-size:11px">${esc(dirs.data || "—")}</strong></div>
        <div class="kv"><span>游戏</span><strong style="font-size:11px">${esc(dirs.game || "—")}</strong></div>
        <div class="kv"><span>Java</span><strong style="font-size:11px">${esc(dirs.java || "—")}</strong></div>
        <div class="kv"><span>日志</span><strong style="font-size:11px">${esc(dirs.logs || "—")}</strong></div>
        <div class="disclaimer" style="margin-top:14px">
          <strong style="color:var(--ink-2)">ARM64 提示：</strong>Minecraft 1.19+ 使用 LWJGL 3.3.x，可直接使用 arm64 natives；1.13-1.18 多为 LWJGL 3.1/3.2，Maven 无 arm64 构建；1.12 及更早使用 LWJGL 2，无法在纯 ARM64 环境运行。详见仓库 <span class="mono" style="font-size:10px">docs/ARM64.md</span>。
        </div>
        <div class="disclaimer" style="margin-top:10px">
          <strong style="color:var(--ink-2)">PCL2 差异：</strong>微软正版登录、CurseForge、OptiFine 自动安装暂未内置，原因见 README 的“与 PCL2 的差异”。
        </div>
      </div>
    </section>`;

  root.querySelectorAll("[data-open-data]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("data"));
  });
  root.querySelectorAll("[data-open-logs]").forEach((button) => {
    button.addEventListener("click", () => actions.openFolder("logs"));
  });
  return root;
}
