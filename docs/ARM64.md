# Linux ARM64 兼容性说明

PCL Linux ARM64 面向 `aarch64` / `arm64` Linux。启动器本身是纯 Python，任何架构都能运行；能否启动 Minecraft 客户端，取决于该版本使用的 LWJGL 是否有 Linux ARM64 原生库。

## 原生库替换

安装时，启动器会检查依赖库中的 LWJGL 版本：

- LWJGL **3.3+**：把 `org.lwjgl:*:natives-linux` 替换为 `natives-linux-arm64`，从 Maven Central 下载。
- LWJGL **3.1 / 3.2**：Maven Central 没有对应的 arm64 构建，界面会给出提示。
- LWJGL **2**：官方没有 arm64 原生库，无法在纯 ARM64 环境启动。

可通过设置中的“ARM64 原生库替换”关闭该行为，但通常不建议。

## 版本兼容性（经验范围）

| Minecraft 版本 | LWJGL | ARM64 支持 | 说明 |
| --- | --- | --- | --- |
| 1.19 – 最新 | 3.3+ | 可用 | 自动替换 arm64 natives，需要对应 Java |
| 1.13 – 1.18 | 3.1 / 3.2 | 通常不可用 | 无官方 arm64 natives |
| 1.6 – 1.12 | LWJGL 2 | 不可用 | 官方无 arm64 natives |
| 远古版 | LWJGL 2 | 不可用 | 同上 |

上表是经验结论，最终以实际版本 JSON 的依赖库和启动日志为准。

## Java 版本建议

| Minecraft | 建议 Java |
| --- | --- |
| 1.20.5+ | Java 21 |
| 1.18 – 1.20.4 | Java 17 |
| 1.17 | Java 16 / 17 |
| 1.16.5 及以下 | Java 8 |

启动器会根据版本 JSON 的 `javaVersion.majorVersion` 选择 Java；缺失时可自动下载 Adoptium ARM64 JDK。

## 图形环境

Minecraft 客户端需要可用的 OpenGL 驱动和桌面会话。以下环境只能使用下载、安装、内容管理与诊断功能：

- 纯 SSH 无 X11 / Wayland；
- 无 GPU 驱动的容器；
- 未安装 Mesa / 厂商 OpenGL 驱动的精简系统。

在 ARM64 单板电脑（如树莓派）上，建议使用 64 位系统、至少 4 GB 内存，并为大型整合包分配 4–8 GB 堆内存。

## 故障排查

1. 确认 `uname -m` 输出 `aarch64`。
2. 在“工具箱 → 崩溃诊断”查看 `latest.log` 和 crash report。
3. 检查启动日志中是否有 `Failed to create window`、`GLFW error`、`UnsupportedClassVersionError`。
4. 旧版本提示 LWJGL 2 时，说明该版本无法在纯 ARM64 环境运行，不是启动器配置问题。
5. 如果 Java 路径错误，在“设置 → Java 运行时”手动选择 ARM64 JDK。
