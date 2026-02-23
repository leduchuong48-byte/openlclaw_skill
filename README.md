# OpenClaw Skills Collection

这个仓库用于存放 OpenClaw 自定义 skill，每个 skill 独立在一个分支中，方便单独拉取、维护和回滚。

## 分支列表

- `skill/android_atx_control`
- `skill/comfyui-local`
- `skill/docker-upgrader`
- `skill/ins-phone-downloader`
- `skill/md-to-pdf`
- `skill/monitor-downloader`

## 各 Skill 功能说明

| 分支 | 功能简介 |
| --- | --- |
| `skill/android_atx_control` | 通过 `android_*` 工具链直接控制 Android 物理机（截图、点击、滑动、输入、打开目标）并支持 ADB 文件管理（读取/上传/下载/删除）。 |
| `skill/comfyui-local` | 连接本机 ComfyUI，提交工作流并轮询生成结果，把图片/视频输出到工作区并用于 Telegram 回传。 |
| `skill/docker-upgrader` | 提供 Docker 容器升级 SOP：检查可升级项、用户确认、执行升级、失败自动回滚、最后汇总结果。 |
| `skill/ins-phone-downloader` | 自动控制手机处理 Instagram 链接下载，优先高画质，拉取到宿主机并归档到 NAS，可回传到 Telegram。 |
| `skill/md-to-pdf` | 将 Markdown 渲染为可打印 PDF（WeasyPrint，含表格排版），经用户确认后通过 Telegram 发送文件。 |
| `skill/monitor-downloader` | 监听 Telegram 链接消息（X/小红书/微博），路由到对应下载服务，收集产物并回传当前会话。 |

## 使用方式

只拉取某一个 skill 分支：

```bash
git clone --single-branch --branch skill/md-to-pdf https://github.com/leduchuong48-byte/openlclaw_skill.git
```

或在已克隆仓库中切换：

```bash
git fetch origin
git checkout skill/md-to-pdf
```

## 说明

`main` 分支仅作为目录和说明页，不承载具体 skill 代码。
