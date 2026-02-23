---
name: docker-upgrader
description: 在宿主机上对 Docker 容器做“可升级检查→拉取更新→生成可升级清单→推送给用户确认升级序号→执行升级（失败自动回滚）→回报结果”。适用于维护固定端口服务（如 3000 端口 open-webui）或批量升级运行中的容器镜像。
---

# docker-upgrader

目标：把 Docker 升级变成可控的 SOP：先检查、再确认、再升级、失败可回滚、最后汇报。

## 核心原则

- **默认先确认**：升级会 stop/rm/rename 容器，必须先把“可升级清单”发给用户确认序号。
- **不泄露敏感信息**：汇报中不要打印完整环境变量值；只显示 key 或已脱敏版本。
- **失败必须回滚**：新容器起不来/健康检查不通过/端口不可用 → 立即恢复旧容器。

## 标准流程（推荐）

### 1) 检查并拉取更新，生成“可升级清单”

运行：

```bash
python3 skills/docker-upgrader/scripts/check_upgrades.py --hosts local,192.168.100.21 --json
```

要点：
- 该脚本会枚举 **运行中的容器**，对其镜像（tag）执行 `docker pull`，然后对比“升级前后镜像 ID”。
- 输出包含 `upgradable` 列表，并按 `index` 编号。

将清单（可升级的容器：index/name/image/ports）发给用户，让用户回复“升级序号”。

可选过滤：

```bash
python3 skills/docker-upgrader/scripts/check_upgrades.py --filter-port 3000 --json
python3 skills/docker-upgrader/scripts/check_upgrades.py --filter-name open-webui --json
```

### 2) 用户确认升级序号后，执行升级（失败回滚）

对单个容器：

```bash
python3 skills/docker-upgrader/scripts/upgrade_container.py --host 192.168.100.21 --container <name> --wait-seconds 120
```

脚本行为：
- 记录旧容器配置（端口映射/卷/重启策略/网络/环境变量 key 列表等）
- `docker pull` 最新镜像
- stop 旧容器 → rename 备份 → 用相同配置启动新容器
- 若容器有 `HEALTHCHECK`：等待变为 `healthy`
- 若失败：停止并删除新容器 → 把旧容器 rename 回原名并启动（回滚）

### 3) 汇总回报（必须）

升级动作可能涉及多个容器。最终必须给用户一个**汇总回报**（一条消息/一份表格），包含：
- 每个容器：OK/FAIL、image tag、升级前后 image id（可截断）、是否回滚、失败原因（若有）
- 总体：成功数 / 失败数 / 总数

建议做法：把每次 `upgrade_container.py` 的输出（JSON）按行追加到一个 `results.jsonl`，最后用脚本生成汇总文本：

```bash
python3 skills/docker-upgrader/scripts/render_summary.py --jsonl results.jsonl --format markdown
```

> Telegram 推送动作：由上层用 `message` 工具发送汇总文本给用户。

## 注意

- 如果某容器是 `docker compose` 管理的，最佳实践仍是走 compose（该 skill 先用“容器级回放配置”的方式兼容多数 `docker run` 场景）。
- 如遇到无法重建的复杂配置（cap-add/devices/tmpfs 等），脚本会提示“不可安全升级”，需要人工处理。
