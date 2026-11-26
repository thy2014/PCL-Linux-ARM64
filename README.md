# PCL Launcher · Windows / Linux ARM64

同一套 `pcl_core/` 后端与 `web/` 前端的 Minecraft 启动器，默认打开独立桌面窗口，不依赖浏览器标签页，也不需要 Electron。

## 直接下载

| 平台 | 文件 | 说明 |
| --- | --- | --- |
| Windows 10/11 x64 | [`dist/PCL-Launcher.exe`](https://raw.githubusercontent.com/thy2014/PCL-Linux-ARM64/main/dist/PCL-Launcher.exe) | 单文件窗口程序，双击运行，已自带 Python 与 WebView2 窗口壳 |
| Linux ARM64 · Debian/Ubuntu | [`dist/PCL-Launcher_1.0.0_arm64.deb`](https://raw.githubusercontent.com/thy2014/PCL-Linux-ARM64/main/dist/PCL-Launcher_1.0.0_arm64.deb) | ARM64 安装包，已自带 Python 3 运行时；系统只需 GTK3 + WebKit2GTK |
| Linux ARM64 · 通用 | [`dist/PCL-Launcher_1.0.0_linux_arm64.tar.gz`](https://raw.githubusercontent.com/thy2014/PCL-Linux-ARM64/main/dist/PCL-Launcher_1.0.0_linux_arm64.tar.gz) | 解压后直接运行或在本地安装，不要求 Python |
| 调试源码 | [`pcl-single.py`](https://raw.githubusercontent.com/thy2014/PCL-Linux-ARM64/main/pcl-single.py) | 仅此文件需要系统 Python 3.10+ |

> Linux 安装包里的 `PCL-Launcher` 是 ARM aarch64 ELF，PyInstaller 已把 Python 3 解释器、`gi`/GTK 绑定与网页资源一起打包。**不需要运行 `apt install python3`，也不需要 `pip install` 任何东西。**

### Windows

1. 下载 `PCL-Launcher.exe`。
2. 双击运行，会出现标题为 `PCL Launcher` 的独立桌面窗口。
3. 首次启动会在 `%APPDATA%\PCL-Launcher` 创建配置与日志。

### Linux ARM64 · `.deb`

```bash
sudo apt install ./PCL-Launcher_1.0.0_arm64.deb
pcl-launcher
```

安装后创建：

- `/usr/bin/pcl-launcher`（ARM64 单文件程序，自带 Python 3）
- `/usr/share/applications/pcl-launcher.desktop`
- `/usr/share/icons/hicolor/256x256/apps/pcl-launcher.png`

也可以在文件管理器里双击 `.deb`，用系统软件中心安装；装好后从应用菜单搜索 `PCL Launcher` 打开。

`.deb` 的依赖只有窗口外壳所需：

```text
gir1.2-gtk-3.0
gir1.2-webkit2-4.0 | gir1.2-webkit2-4.1
```

不再依赖 `python3`、`python3-gi` 或 `python3-gi-cairo`。如果系统只装了 WebKit2 4.0，启动器会加载系统的 4.0 typelib；如果装的是 4.1，则加载 4.1，不会把某个版本硬编码进安装包。

### Linux ARM64 · `tar.gz`

```bash
tar -xzf PCL-Launcher_1.0.0_linux_arm64.tar.gz
cd PCL-Launcher_1.0.0_linux_arm64
./install.sh
```

默认安装到 `~/.local/share/pcl-launcher`，命令链接到 `~/.local/bin/pcl-launcher`，并创建桌面入口。也可以不安装，直接运行解压目录里的 `./PCL-Launcher`。

```bash
./install.sh --prefix=/opt/pcl --run
./uninstall.sh            # 保留 ~/.pcl-arm64 数据
./uninstall.sh --purge    # 连同数据目录一起删除
```

tar 包不包含 Python，运行的是与 `.deb` 相同的自带运行时二进制。只要求系统提供 GTK3 与 WebKit2GTK：

```bash
# Debian / Ubuntu
sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.0
# 或 WebKit2 4.1 的系统
sudo apt install gir1.2-gtk-3.0 gir1.2-webkit2-4.1
```

## 桌面窗口与目录选择

- Windows 使用系统 WebView2；Linux 使用 GTK3 + WebKit2GTK。两端都是 `pywebview` 原生窗口，窗口内没有浏览器地址栏。
- 设置页“游戏与账户 → 游戏目录”右侧点“选择”，会打开系统原生文件夹选择框；选择后保存即可。
- 数据目录：Windows `%APPDATA%\PCL-Launcher`，Linux `~/.pcl-arm64`。日志在数据目录的 `logs/server.log`。
- 没有图形显示服务时可加 `--browser` 回退到浏览器模式；正常桌面环境不要加这个参数。

## 功能状态

- 版本下载、安装、启动；Fabric / Forge / NeoForge / Quilt / OptiFine 加载器。
- **加载器安装已合并进“安装版本”弹窗**：选择游戏版本时直接勾选“模组加载器（可选）”，可手输加载器版本；安装流程会先装原版，再装加载器。
- 下载页不再单独显示“模组加载器”卡片；版本页也不再提供独立“安装加载器”入口。
- 加载器元数据使用 BMCLAPI 镜像回退与缓存（Fabric / Forge / NeoForge），避免官方源超时。
- Modrinth 资源搜索与下载、整合包安装、账户离线登录、服务器列表与测速、Java 检测、启动命令构建、崩溃日志诊断。
- Linux ARM64：LWJGL 3.3+ 的 `natives-linux` 自动替换为 `natives-linux-arm64`；旧 LWJGL 2 / 旧版 LWJGL 3 会在界面提示无法运行。
- 设置页支持内存、JVM 参数、Java 路径、窗口尺寸、全屏、主题、下载源、代理与游戏目录。

## 从源码运行

环境：Python 3.10+、Node 不需要；Linux 还需要 GTK3 + WebKit2GTK 和 `python3-gi`。

```bash
python3 -m pip install -r requirements.txt
python3 pcl.py
```

默认打开 `PCL Launcher` 桌面窗口。浏览器调试：

```bash
python3 pcl.py --browser
```

## 构建

### Linux ARM64（自带 Python 的 `.deb` / `tar.gz`）

```bash
# Ubuntu 24.04 ARM64 或相同依赖的环境
sudo apt install python3 python3-venv python3-gi python3-gi-cairo \
    gir1.2-gtk-3.0 gir1.2-soup-2.4
# 按系统实际版本二选一
sudo apt install gir1.2-webkit2-4.1 || sudo apt install gir1.2-webkit2-4.0

python3 -m venv --system-site-packages .venv
. .venv/bin/activate
pip install -r requirements.txt pyinstaller
bash packaging/linux/build_pyinstaller.sh
```

输出：

```text
dist/PCL-Launcher-linux-arm64
dist/PCL-Launcher_1.0.0_arm64.deb
dist/PCL-Launcher_1.0.0_linux_arm64.tar.gz
```

构建脚本先用 `tools/build_single.py` 生成 `pcl-single.py`，再用 PyInstaller `--onefile` 打包 `pcl.py`，最后生成 `.deb` 与 `tar.gz`。PyInstaller 内置 Python、`gi`、GTK 绑定和 `web/` 资源；**WebKit2/Soup typelib 不打进包内**，运行时由 `pcl.py` 的 `_ensure_gi_typelib_path()` 把系统 `girepository-1.0` 加入 `GI_TYPELIB_PATH`，因此 WebKit 4.0 与 4.1 都能用。

### Windows x64 单文件 exe

在 Windows 上执行：

```powershell
powershell -File packaging/windows/build.ps1
```

输出 `dist/PCL-Launcher.exe`。Windows 构建会用 PyInstaller 打包 Python 3 运行时与 `web/`，窗口壳使用系统 WebView2。

## 项目结构

```text
pcl.py                     # 桌面窗口入口（pywebview）
pcl_core/                  # 配置、下载、安装、启动、账户、服务器、诊断
web/                       # PCL 风格前端（HTML/CSS/JS）
packaging/linux/           # build_pyinstaller.sh、install.sh、desktop、图标
packaging/windows/         # build.ps1、version_info.txt、icon
dist/                      # Windows exe、Linux ARM64 deb/tar.gz
.github/workflows/         # Windows 与 Linux ARM64 构建
```

## 常见问题

| 现象 | 处理 |
| --- | --- |
| Windows 双击后打开浏览器而不是窗口 | 确认下载的是 `dist/PCL-Launcher.exe` 窗口版，不是旧版浏览器壳或 `pcl-single.py` |
| Linux 提示 `Namespace WebKit2 not available` | 安装 `gir1.2-webkit2-4.0` 或 `gir1.2-webkit2-4.1`；启动器会使用系统 typelib，不需要 Python |
| Linux 提示 `Namespace Soup not available` | 安装 `gir1.2-soup-2.4`（或对应发行版的 `libsoup` GI 包） |
| Linux `pcl-launcher: command not found` | `~/.local/bin` 不在 PATH；运行 `~/.local/bin/pcl-launcher` 或把它加入 `~/.profile` |
| 只下载了脚本，报 `can't open file 'pcl.py'` | 使用 `pcl-single.py`，或下载完整仓库；不要只拿旧脚本 |
| 提示“当前不是 ARM64” | 当前机器是 x86_64；界面与下载可用，但 ARM64 原生库替换不会生效 |

## 仓库

- GitHub：<https://github.com/thy2014/PCL-Linux-ARM64>
- 最新源码 ZIP：<https://github.com/thy2014/PCL-Linux-ARM64/archive/refs/heads/main.zip>
- Issues：<https://github.com/thy2014/PCL-Linux-ARM64/issues>
