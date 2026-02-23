---
name: monitor-downloader
description: 自动监听 Telegram 消息中的链接（仅白名单 sender_id），按域名路由到 X/XHS/微博 三个 monitor 服务触发下载；通过 logs cursor 增量提取本次下载的落盘路径，映射到本机 NFS 路径后收集到 out/ 并回传 Telegram 当前窗口。适用于 192.168.100.21:1002(xhsmonitor), :1003(weibo-monitor), :2028(xmonitor)。
---

# monitor-downloader

## 这份 skill 的“意义”（契约）

- 你发**链接**（X / 小红书 / 微博） → 我返回**下载好的媒体文件**（不发日志）。
- 仅处理白名单 sender：默认只处理你（`7856041838`）。

## 配置

配置文件：`scripts/config.json`（没有则用脚本内默认）。

- `sender_whitelist`：允许触发的 Telegram sender_id
- `services`：三套服务地址
- `nfs_map`：宿主机路径 → OpenClaw 机 NFS 路径映射
- `out_dir`：产物复制到 workspace 的目录（用于回传）

## 路由规则（按域名）

- 小红书：`xiaohongshu.com` / `xhslink.com`
- 微博：`weibo.com` / `m.weibo.cn`
- X：`x.com` / `twitter.com` / `t.co`

## 运行（手动自检 / 或被触发器调用）

给一条“消息文本”，脚本会：触发下载 → 从 logs 提取本次产物路径 → 映射到 NFS → 复制到 `out/`。

```bash
python3 skills/monitor-downloader/scripts/run_once.py \
  --sender-id 7856041838 \
  --text '红色足球袜更喜庆！ http://xhslink.com/o/5rR14y7Eu3D'
```

输出会包含一行 `MANIFEST_JSON=...`，其中列出本次复制到 `out/` 的文件路径。

## 回传 Telegram（由上层执行）

- 读取 `MANIFEST_JSON` 里的 `copied_files`，逐个作为附件回传到当前窗口。
- 不要把运行日志/接口响应发给用户；只回传媒体文件（必要时附一行简短说明）。
