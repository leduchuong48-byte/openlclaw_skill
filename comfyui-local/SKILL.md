---
name: comfyui-local
description: 连接本机 ComfyUI（通常 http://127.0.0.1:8188），将工作流 JSON 提交到 /prompt，轮询 /history 获取生成图片/视频，并把输出文件复制到 workspace/out 后回传到 Telegram 当前窗口。适用于“用 ComfyUI 生图/跑工作流/生成图片并回传”等请求。
---

# comfyui-local

## 目标（契约）

- 你给：工作流（workflow JSON）或 prompt 参数
- 我做：调用本机 ComfyUI 生成
- 我回：生成的媒体文件（不回传冗长日志）

## 前提

- ComfyUI 已在本机运行，默认地址：`http://127.0.0.1:8188`
- 本 skill 的脚本只用标准库（urllib），不引入额外依赖。

## Quick start（手动自检）

1) 查看 ComfyUI 是否在线：

```bash
python3 {baseDir}/scripts/comfy_run.py --ping
```

2) 提交一个工作流（你提供 workflow.json）：

```bash
python3 {baseDir}/scripts/comfy_run.py \
  --workflow workflow.json \
  --out-dir out/comfyui-local
```

脚本会输出 `MANIFEST_JSON=...`，其中包含复制到 `out/` 的文件列表。

3) 基础 Flux 文生图（推荐保留）：

```bash
python3 {baseDir}/scripts/comfy_patch_and_run.py \
  --template {baseDir}/scripts/workflows/flux-basic-t2i.json \
  --prompt 'your prompt here' \
  --out-dir out/comfyui-local
```

## 触发建议

- 当用户说“用 ComfyUI 生成/跑工作流/生图/出图/渲染”时，使用本 skill。
- 若用户只给了文字描述但没给 workflow：先让用户提供 workflow JSON（或你根据现有模板生成一个最小 workflow）。
