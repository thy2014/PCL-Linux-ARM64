# PCL Linux ARM64

**Plain Craft Launcher · Linux ARM64 社区版** — 在 ARM64 Linux 上运行的 PCL 风格 Minecraft 启动器。

无需 Electron，无需第三方 Python 依赖，启动一个本地 Web 界面即可完成版本下载、加载器安装、模组/资源包/光影/存档管理、Modrinth 资源检索、账户与服务器管理、启动和崩溃诊断。

> 本项目是非官方社区实现，与 Mojang Studios、Microsoft、Plain Craft Launcher 官方没有隶属关系。请购买正版 Minecraft。

---

## 界面预览

| 主页 | 下载 |
| --- | --- |
| ![主页](docs/screenshots/home.png) | ![下载](docs/screenshots/download.png) |

| 资源（Modrinth） | 服务器 |
| --- | --- |
| ![资源](docs/screenshots/resources.png) | ![服务器](docs/screenshots/servers.png) |

| 版本内容管理 | 工具箱 |
| --- | --- |
| ![版本内容](docs/screenshots/version-manage.png) | ![工具箱](docs/screenshots/toolbox.png) |

| 设置与账户 | 加载器安装 |
| --- | --- |
| ![设置](docs/screenshots/settings.png) | ![加载器](docs/screenshots/loader-modal.png) |

---

## 功能

### 版本与启动

- Mojang 官方版本清单：正式版、快照、远古版本，支持搜索与筛选。
- 原版完整安装：客户端 jar、依赖库、资源索引、全部资源对象、natives。
- 文件 SHA1 校验、断点下载、并发下载、安装任务取消与实时进度。
- 安装进度展示下载速度、文件计数、字节计数、当前文件、日志。
- 多版本共存、版本大小统计、最近启动时间、删除版本。
- 版本隔离：每个版本独立的 `mods / config / saves / options.txt`，与 PCL 的版本隔离逻辑一致。
- 全局与单版本设置：内存、JVM 参数、Java 路径、窗口尺寸、全屏。
- 启动命令构建：规则解析、参数模板替换、classpath、natives、资源目录、账户 UUID/token。
- 游戏进程实时日志、退出码、PID、日志落盘、复制启动命令、结束进程。
- 快速进入服务器：为支持 Quick Play 的版本附加 `--quickPlayMultiplayer`。

### ARM64 Linux

- 自动检测 `aarch64 / arm64`，也可用 `PCL_ARCH=arm64` 覆盖。
- 自动把 LWJGL 3.3+ 的 `natives-linux` 替换为 Maven Central 的 `natives-linux-arm64`。
- 识别使用 LWJGL 2 / 旧版 LWJGL 3 的版本，并在界面给出无法运行提示。
- Adoptium ARM64 JDK 下载：JDK 8 / 17 / 21，SHA256 校验、解压、可执行权限设置。
- 系统 Java 自动发现，支持按版本要求挑选 Java 大版本。

详见 [docs/ARM64.md](docs/ARM64.md)。

### 实测记录（2026-11-24）

测试机为 Linux `x86_64`，通过 `PCL_ARCH=arm64` 模拟目标架构；ARM64 JDK 是真实下载并校验的 Adoptium 构建，但 x86 宿主无法执行 ARM64 ELF，因此“游戏进程真正进入主菜单”这一步需在 ARM64 桌面环境完成。以下项目均已跑通到安装/命令构建层面：

| 项目 | 结果 |
| --- | --- |
| Minecraft 1.0 原版 | 480 文件、约 50.8 MB，客户端 SHA1 校验通过 |
| Minecraft 1.21.4 原版 | 4114 文件、约 694 MB，含 assets / libraries / natives |
| Adoptium Java 21 ARM64 | 206,031,041 B，SHA256 校验通过，解压可用 |
| Fabric 0.20.1 + 1.21.4 | 4120 文件安装完成，ARM64 原生库替换 8 个 |
| Quilt 0.20.0-beta.9 + 1.21.4 | 4126 文件安装完成 |
| Forge 47.4.28 + 1.20.1 | 官方 installer 执行成功，生成 `1.20.1-forge-47.4.28`；3661/3661 文件补齐，启动命令含 60 个参数 |
| NeoForge | 代码与 installer 流程已接入；测试网络访问 `maven.neoforged.net` 返回 502，未能实测 |
| Modrinth 模组 | Sodium 0.6.13、Iris 1.8.8 安装成功，Iris 的必需前置 Sodium 正确复用 |
| Modrinth 资源包 | Simple Wool v1.4 安装并写入实例 |
| Modrinth 整合包 | Simply Optimized & Up to Date 安装成功，写入 22 个覆盖文件 |
| 服务器状态 | Hypixel 真实 ping：679 ms、12934 / 200000 人 |
| 启动命令 | 1.0、1.21.4、Fabric、Quilt、整合包实例均可构建完整命令 |

> Forge 安装器需要在目标机上执行 Java。本项目把安装器工作目录设为游戏目录，并在安装完成后清理安装器临时生成的原版版本目录，避免“版本管理”里出现未完整安装的假版本。

### 模组加载器

- **Fabric**：官方 meta profile 合并安装。
- **Quilt**：官方 meta profile 合并安装。
- **Forge**：下载官方 installer，执行 `--installClient`，合并生成版本。
- **NeoForge**：下载官方 installer，执行 `--installClient`。
- 加载器版本列表、推荐版本、Beta 标记。
- 加载器安装复用原版安装器，自动准备 Java、资源与依赖。
- 安装完成后自动识别 `loader` / `game_version`，在版本卡片显示。

### 资源下载（Modrinth）

- 模组、整合包、资源包、光影四类搜索。
- 按已安装版本的游戏版本与加载器过滤。
- 项目版本选择、SHA1 校验、必需前置模组递归安装。
- `.mrpack` 整合包安装：基于所选版本创建独立实例，复制基础客户端与依赖。
- 资源安装任务与进度、失败原因提示。
- 内容来自 Modrinth 官方 API，不内置第三方资源站。

### 内容管理

- 模组：扫描 `.jar` / `.jar.disabled`，读取 `fabric.mod.json`、`quilt.mod.json`、`mods.toml`、`mcmod.info`，启停与删除。
- 资源包：扫描 zip/目录，读取 `pack.mcmeta`，启停同步写入 `options.txt` 的 `resourcePacks`。
- 光影：扫描 `shaderpacks`，显示文件大小与修改时间。
- 存档：扫描 `saves`，读取 `level.dat` 的 NBT（存档名、游戏模式、版本、最后游玩时间、硬核标记）。
- 导入：从本机路径复制模组/资源包到版本目录。
- 存档备份：zip 打包到 `backups/`。
- 每个版本独立的内容目录管理弹窗。

### 账户、服务器与诊断

- 多离线账户：新增、切换、删除，按玩家名生成离线 UUID。
- 服务器列表：新增、编辑、删除、持久化。
- Minecraft Server List Ping：延迟、MOTD、在线/最大玩家、版本、favicon。
- 一键测速全部服务器；从服务器页直接带地址启动。
- 崩溃诊断：扫描 `latest.log`、`crash-reports`、模组数量和常见错误特征（内存、Java 版本、OpenGL、模组冲突、重复模组、类缺失、权限、网络、LWJGL 2）。
- 打开游戏目录、版本目录、日志目录、崩溃报告目录、Java 目录、数据目录。
- 主题：经典蓝、草地方块、紫水晶、熔岩橙、红石、海洋青、夜间。

### 设置与安全

- 下载源：官方 Mojang / BMCLAPI 镜像（失败回退官方清单）。
- 并行下载线程数、ARM64 原生库替换开关。
- 配置持久化到 `~/.pcl-arm64/config.json`。
- 本地服务默认只绑定 `127.0.0.1`。
- 所有写操作携带启动时生成的 CSRF token。
- 版本名、文件名、路径均做白名单/越界校验。

---

## 快速开始

### 环境要求

- Linux ARM64（aarch64）。x86_64 也能运行界面与下载，但 ARM64 原生库补丁不会生效。
- Python **3.10+**，仅使用标准库。
- 一个现代浏览器（Chromium / Firefox / Safari）。
- 桌面环境、可用的 OpenGL 驱动与音频设备用于启动游戏；纯 SSH 无 X11/Wayland 时只能下载与管理，不能启动 Minecraft 客户端。
- 首次启动游戏前，请确认 `java` 指向 ARM64 JDK（本项目的“下载 Java”会自动处理）。

### 运行

```bash
git clone https://github.com/thy2014/PCL-Linux-ARM64.git
cd PCL-Linux-ARM64
./start.sh
```

或直接：

```bash
python3 pcl.py
```

默认打开 `http://127.0.0.1:3919/`。如果端口被占用会自动顺延到后续端口，终端会打印实际地址。

### 安装到用户目录（可选）

```bash
./install.sh              # 创建 ~/.local/bin/pcl-arm64 软链接
./install.sh --desktop    # 同时创建应用菜单快捷方式
```

### 命令行参数

```text
--host        监听地址，默认 127.0.0.1
--port        监听端口，默认 3919
--data-dir    应用数据目录，默认 ~/.pcl-arm64
--game-dir    游戏目录，默认 ~/.minecraft
--arch        arm64 / x86_64（调试用）
--no-browser  不自动打开浏览器
--version     显示版本
```

示例：

```bash
python3 pcl.py --game-dir ~/Games/Minecraft --port 4000 --no-browser
```

---

## 数据目录

```text
~/.pcl-arm64/
├── config.json          # 全局设置
├── accounts.json        # 离线账户
├── servers.json         # 服务器列表
├── java/                # Adoptium JDK
├── logs/                # server.log、launch-*.log
└── cache/               # 版本清单、安装器缓存

~/.minecraft/
├── assets/              # 全局资源对象
├── libraries/           # 全局依赖库
├── versions/
│   └── <version>/       # 版本 JSON、客户端 jar、natives、pcl_meta.json
│       ├── mods/
│       ├── resourcepacks/
│       ├── shaderpacks/
│       ├── saves/
│       └── logs/
```

版本隔离开启时，`mods / config / saves / options.txt` 位于 `versions/<version>/`；关闭时与全局游戏目录共用。

---

## 项目结构

```text
pcl.py                     # 入口、CLI、本地 HTTP 服务启动
pcl_core/
├── config.py              # 配置、目录、架构检测、版本隔离
├── util.py                # 哈希、解压、UUID、原子写入、路径安全
├── http_client.py         # JSON / 断点下载 / SHA 校验
├── tasks.py               # 后台任务、进度、日志、取消
├── minecraft.py           # 版本清单、规则、库解析、ARM64、版本 JSON 合并
├── installer.py           # 原版/加载器共用安装流水线
├── java_runtime.py        # Java 发现、Adoptium 下载
├── launcher.py            # 启动参数构建与进程管理
├── loaders.py             # Fabric / Quilt / Forge / NeoForge
├── modrinth.py            # 搜索、版本、依赖、.mrpack
├── content.py             # 模组/资源包/光影/存档/NBT/备份
├── accounts.py            # 离线账户
├── servers.py             # 服务器列表与 Server List Ping
├── diagnostics.py         # 崩溃/日志启发式诊断
└── server.py              # HTTP API、静态文件、CSRF token
web/
├── index.html             # 外壳与 SVG sprite
├── css/app.css            # 全站样式
└── js/
    ├── api.js             # fetch 封装与 token
    ├── ui.js              # 图标、弹窗、Toast、格式化
    ├── app.js             # 路由、任务、启动、账户/内容/加载器弹窗
    └── pages/             # 主页/下载/版本/资源/服务器/工具箱/设置/关于
docs/
├── ARM64.md               # ARM64 兼容性说明
└── screenshots/           # 界面截图
tests/
└── test_core.py           # 核心单元测试
```

---

## API 摘要

所有接口返回 JSON。写操作需要 `X-PCL-Token` 请求头。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/bootstrap` | 启动数据、设置、Java、版本、账户、服务器、任务、token |
| GET | `/api/versions` | Mojang 版本清单 |
| GET | `/api/installed` | 已安装版本 |
| POST | `/api/install` | 开始原版安装任务 |
| GET | `/api/java` | Java 列表 |
| POST | `/api/java/download` | 下载 Adoptium JDK |
| POST | `/api/launch` | 构建启动命令并启动 |
| GET/POST | `/api/launch` | 查询/停止进程 |
| GET | `/api/loaders` | 支持的加载器 |
| GET | `/api/loader/versions` | 加载器版本列表 |
| POST | `/api/loader/install` | 安装加载器 |
| GET | `/api/modrinth/search` | Modrinth 搜索 |
| GET | `/api/modrinth/versions` | 项目版本 |
| POST | `/api/modrinth/install` | 安装模组/资源包/光影 |
| POST | `/api/modrinth/install_modpack` | 安装 `.mrpack` |
| GET | `/api/content` | 扫描版本内容 |
| POST | `/api/content/toggle` | 启停模组/资源包 |
| POST | `/api/content/delete` | 删除内容 |
| POST | `/api/content/import` | 从本机路径导入 |
| POST | `/api/content/backup` | 备份存档 |
| GET/POST | `/api/version/settings` | 版本隔离与单版本设置 |
| GET | `/api/accounts` | 账户列表 |
| POST | `/api/accounts/add` | 新增离线账户 |
| POST | `/api/accounts/select` | 切换账户 |
| POST | `/api/accounts/remove` | 删除账户 |
| GET | `/api/servers` | 服务器列表 |
| POST | `/api/servers/add` | 新增服务器 |
| POST | `/api/servers/update` | 编辑服务器 |
| POST | `/api/servers/delete` | 删除服务器 |
| GET | `/api/servers/ping` | Server List Ping |
| GET | `/api/diagnose` | 崩溃诊断 |
| GET | `/api/task/<id>` | 任务状态 |
| POST | `/api/task/<id>/cancel` | 取消任务 |

完整参数见 `pcl_core/server.py`。

---

## 测试

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖离线 UUID、版本 JSON 合并、Maven 路径、自定义 Maven 仓库回退、配置版本隔离、账户存储等纯本地逻辑，不访问网络。

---

## 与 PCL2 的差异

本项目目标是覆盖 PCL2 在 Linux ARM64 上的主要日常功能，但不是 PCL2 源码移植。当前明确未内置的能力：

| 能力 | 状态 | 原因 |
| --- | --- | --- |
| 微软正版登录 | 未内置 | 需要 Azure 应用与 OAuth 回调；当前使用离线账户 |
| CurseForge 资源下载 | 未内置 | CurseForge API 需要 API Key，且条款限制第三方启动器 |
| OptiFine / LiteLoader 自动安装 | 未内置 | OptiFine 下载受官网验证限制；LiteLoader 已停止维护 |
| 旧版（≤1.12）在 ARM64 启动 | 不支持 | 使用 LWJGL 2，官方无 ARM64 原生库 |
| 启动器自动更新 | 未内置 | 需先设计签名与更新通道 |
| 皮肤 / 披风上传 | 未内置 | 依赖 Mojang 正版账户体系 |
| 整合包导出 / 分享码 | 未内置 | 当前只支持 `.mrpack` 导入 |
| ARM64 以外的原生库组合 | 部分支持 | 代码保留 x86_64 / arm32 分支，但主要验证目标是 Linux ARM64 |

如果某项能力对你必须，请在 Issues 中说明使用场景。

---

## License

[MIT](LICENSE)

## 致谢

- [Plain Craft Launcher 2](https://github.com/Hex-Dragon/PCL2) — 界面与功能设计灵感，本项目与官方无隶属关系。
- Mojang Studios / Microsoft — Minecraft 版本元数据与下载接口。
- FabricMC、QuiltMC、MinecraftForge、NeoForged — 加载器元数据与安装器。
- Modrinth — 资源搜索与下载 API。
- Adoptium — ARM64 JDK 构建。
