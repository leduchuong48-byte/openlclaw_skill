---
name: ins-phone-downloader
description: 接收到 Instagram/INS 链接后，需要自动控制 Android 真机打开「Download Twitter Videos」页面，在“输入您的链接”处粘贴 INS 链接，选择最高画质/全选并下载；下载完成后通过 Telegram 回传媒体文件，并把收到的文件在宿主机侧归档到 /mnt/fnos_n97/media/素材/ins。
---

# ins-phone-downloader

目标：把“发我一个 INS 链接”变成“拿到最高画质文件 + NAS 归档”。

## 约束与现实边界（务必遵守）

- 必须使用 `android_snapshot/android_tap/android_input/android_swipe` 形成闭环；禁止臆测坐标。
- 自动化下载网站的 UI 可能变化：若无法稳定识别“最高画质/全选”控件，需截图并向用户确认再继续。
- 文件拉取采用 **A 路径（手机 → 宿主机）**：通过 uiautomator2 的 `pull()` 从手机下载目录拉取媒体到宿主机，再归档到 `/mnt/fnos_n97/media/素材/ins`。
- 默认动作包含两件事：**(1) 归档到 `/mnt/fnos_n97/media/素材/ins`，(2) 通过 Telegram 把文件发回当前聊天**。仅当用户明确要求“只归档不回传”时才跳过回传。

## 关键防呆：区分「X 图标」与「关闭 ❌」

- 在点击任何“X/❌”之前，先用 uiautomator2 判断前台应用：若 `d.app_current().package == com.twitter.android`（X App），绝对禁止点击任何 X/❌，应先返回桌面再重新进入下载站。
- 只有当屏幕元素明确包含 **“您的链接 / 粘贴 / 下载”** 时，才允许点击被识别为 `btnX` 的关闭按钮。
- 若出现 `x.com`、转推/点赞/关注等 X 平台内容，视为已跑偏：立即停止自动点击并回到下载站。

## 工作流（A 路径：手机拉取到宿主机 → NAS 归档 → 可选 TG 回传）

### 1) 收到 INS 链接 → 手机页面下载

1. `android_snapshot` 获取当前屏幕。
2. 若出现带 “X/❌” 的弹窗（包括被识别为 `btnX`）：**不要点击它**（该按钮在实机上可能是跳转到 X App 的引流入口）。改为回到桌面重新打开下载站，再继续。
3. 找到输入框（常见文案“您的链接”），点击使其聚焦。
4. `android_input(<ins_url>)` 输入/粘贴链接（必要时先点“粘贴”图标）。
5. 点击“下载”按钮/图标。
6. 等待解析结果出现：
   - 若出现“全选”，优先点击“全选”。
   - 在可选清晰度里选择最高（优先级示例：4K/2160 > 1440 > 1080 > 720 > 480）。
   - 如果页面只给一个下载入口，直接点。
7. 等待下载完成（可通过浏览器下载面板/系统通知判断）。

### 2) 拉取手机下载文件到宿主机（按“批次”拉取，避免只拿到 1 张）

这次验证发现：该下载器会把一次解析结果写入 `/sdcard/Download/TweetDownloader/`，并且同一张图可能会生成多种分辨率文件。

做法：
- 按文件名里的时间戳批次（形如 `20260223_001602`）识别本次下载。
- 对每个序号（`_1_`、`_2_`…）只选择**最高分辨率**那一条拉取：
  - 图片：同一序号会有多分辨率（如 640/750/1080），挑最高。
  - 视频：通常同一序号只有一个分辨率文件（如 720x960 的 mp4）。

```bash
python3 skills/ins-phone-downloader/scripts/pull_tweetdownloader_batch.py \
  --serial 1c153785 \
  --dest-dir /root/.openclaw/workspace/out \
  --json
```

输出包含 `MANIFEST_JSON=...`，列出本次拉取的全部文件路径。

### 3) 宿主机归档到 NAS

```bash
python3 skills/ins-phone-downloader/scripts/archive_to_nas.py \
  --input-file <pulled_local_file> \
  --dest-dir /mnt/fnos_n97/media/素材/ins
```

### 4) 通过 TG 回传（默认执行：逐个发送）

- 默认把本次 `MANIFEST_JSON.pulled_files` **逐个**作为附件发送到当前 Telegram 聊天（不打包）。
- 若用户明确说“打包”，再额外提供 tgz。
- 若用户要求“只归档不回传”，则跳过此步。

## 失败兜底

- 解析页/清晰度选择不确定：要求用户确认目标项，再继续点击。
- 下载完成但找不到文件：到手机“下载/Downloads”或浏览器下载列表中定位；必要时用文件管理器搜索最近文件。
