---
name: android_atx_control
description: 使用 android_* 工具链接管 Android 物理机（ATX），用于截图、点击、滑动、输入、目标打开与 ADB 文件系统管理（读取/上传/下载/删除）。
metadata: {"openclaw":{"always":true}}
allowed-tools: ["android_snapshot", "android_tap", "android_swipe", "android_input", "android_open", "android_fs_list", "android_fs_read", "android_fs_remove", "android_fs_download", "android_fs_upload"]
---

# android_atx_control

## 核心指令（强覆盖）

- 你已安装 `android_atx_control`。
- 当用户要求“看屏幕/控制手机/打开 App/执行端侧操作”时，必须优先使用 `android_*` 工具链。
- 当用户需要查看或处理手机文件时，优先使用 `android_fs_*` 工具链。
- 绝对禁止调用 `nodes` 工具。
- 绝对禁止提示用户进行 `pairing required (1008)` 配对流程。

## 标准执行顺序

1. 先调用 `android_snapshot` 获取最新屏幕状态。
2. 仅基于最新结果决定动作。
3. 需要点击时调用 `android_tap(x, y)`。
4. 需要滚动时调用 `android_swipe(direction)`。
5. 需要输入时先点击输入框，再调用 `android_input(text)`。
6. 需要文件系统操作时使用 `android_fs_list/read/remove/download/upload`。
7. 每次动作后重新 `android_snapshot`，形成闭环。

## 文件系统能力

- 你现在不仅能控制手机屏幕，还拥有 Android 底层文件系统（ADB FS）管理权限。
- 可直接读取、上传、下载、删除并分析手机内部文件。

## 红线约束

- 禁止复用过期坐标，禁止坐标臆测。
- 禁止在搜索场景乱点结果，默认只点击第一条符合目标的结果。
- 非用户明确要求时，禁止使用 `android_open` 直接跳过 UI 路径。
