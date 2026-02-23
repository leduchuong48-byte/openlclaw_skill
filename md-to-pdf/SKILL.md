---
name: md-to-pdf
description: 将 Markdown 文本排版为可打印 PDF，并在用户明确确认后通过 Telegram 通道把 PDF 文件发送给用户。
user-invocable: true
metadata: { "openclaw": { "emoji": "🧾", "requires": { "bins": ["python3"], "config": ["channels.telegram.enabled"] } } }
---

# md-to-pdf

当用户要求把 Markdown 转成 PDF 时，执行以下固定流程。

## 触发场景

- 用户说“把这段 md/markdown 变成 pdf”
- 用户发来 Markdown 文本并要求打印版
- 用户使用 `/md_to_pdf`

## 严格流程

1. 先检查是否拿到 Markdown 内容。
如果没有内容，先让用户粘贴 Markdown（可用代码块）。

2. 拿到 Markdown 后，必须先二次确认。
确认话术示例：
“我可以把这段 Markdown 排版为可打印 PDF，并通过 Telegram 发回给你。是否现在开始？（回复：是/确认）”

3. 只有在用户明确肯定后才执行转换。
肯定词包括：`是`、`确认`、`开始`、`ok`、`yes`。

4. 执行转换：

```bash
python3 {baseDir}/scripts/md_to_pdf.py --input-file "<md_file>" --output-file "<pdf_file>" --title "<title>"
```

实现建议：
- 把收到的 Markdown 先写到临时文件（例如 `/tmp/md_to_pdf_<timestamp>.md`）。
- 输出 PDF 到绝对路径（例如 `/tmp/md_to_pdf_<timestamp>.pdf`）。
- 当前脚本使用 `Markdown -> HTML -> WeasyPrint` 渲染，表格会按打印样式输出（含边框、表头底色、自动换行、分页页脚）。
- 依赖策略：脚本会自动补装 Python 依赖（`markdown`、`weasyprint`）；中文字体建议保留 `fonts-noto-cjk`。

5. 通过 Telegram 发送 PDF 给用户：
- 优先使用当前消息上下文中的 `sender_id` 作为 `target`。
- 优先使用当前消息上下文中的 `account_id` 作为 `accountId`（多账号场景必须）；若缺失则回退到 `main`。
- 若上下文无 `sender_id`，再询问用户提供 Telegram 目标 ID。

发送时用 `message` 工具，参数：
- `action: "send"`
- `channel: "telegram"`
- `target: "<sender_id>"`
- `accountId: "<account_id_or_main>"`
- `message: "已生成 PDF，请查收。"`
- `media: "<pdf_absolute_path>"`

## 失败处理

- 转换失败：返回错误原因，并提示用户缩短内容或去掉异常字符后重试。
- 若提示缺少系统库/字体：在容器中安装 `libgdk-pixbuf2.0-0`、`fonts-noto-cjk` 后重试。
- 发送失败：保留本地 PDF 路径并告知用户，随后重试一次发送。
