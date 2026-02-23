# OpenClaw Skills Collection

这个仓库用于存放 OpenClaw 自定义 skill，每个 skill 独立在一个分支中，方便单独拉取、维护和回滚。

## 分支列表

- `skill/android_atx_control`
- `skill/comfyui-local`
- `skill/docker-upgrader`
- `skill/ins-phone-downloader`
- `skill/md-to-pdf`
- `skill/monitor-downloader`

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
