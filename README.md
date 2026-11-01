# cpa-imagegen

面向 AI Agent 的 CPA 生图工具：独立 Python CLI + Codex Skill，通过兼容 OpenAI Images API 的网关生成和编辑图片。

核心不依赖 Codex 安装目录、内置脚本或登录状态。其他能执行命令的 Agent 可以使用同一 CLI；首版实际 Agent 集成以 Codex 为范围，暂不提供 MCP。

## 安装

需要 Python 3.11+。下载或克隆仓库后进入项目目录。当前从源码安装，尚未发布到 PyPI。

Windows PowerShell：

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

macOS / Linux：

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
```

安装后运行 `cpa-imagegen --help`，也可使用 `python -m cpa_imagegen`。非开发安装可使用 `python -m pip install .`。Skill 绑定的 Python 环境应保持可用。

## 配置 CPA

### 显式导入当前 Codex provider

```sh
cpa-imagegen config import-codex --json
```

命令输出实际的用户级私人配置位置。只导入所选 provider 的 `base_url` 和 `experimental_bearer_token`，或保存 `env_key` 对应的环境变量名；不导入文本模型、项目设置、OAuth 或 `auth.json`。图像模型默认是 `gpt-image-2`。

可用 `--codex-config PATH` 指定源文件，`--provider NAME` 指定 provider，`--config PATH` 指定私人配置目标。已有目标不会覆盖，除非添加 `--overwrite`。普通运行不会再读取 Codex。

私人配置路径由 platformdirs 根据操作系统和进程环境确定；桌面应用与独立终端的环境可能不同，必要时在后续命令添加 `--config` 指向导入时输出的路径。

### 独立配置

在本机设置环境变量，不要把真实密钥粘贴到聊天或提交到仓库：

```powershell
$env:CPA_IMAGEGEN_BASE_URL = "https://gateway.example.invalid/v1"
$env:CPA_IMAGEGEN_API_KEY = "YOUR_GATEWAY_KEY"
$env:CPA_IMAGEGEN_MODEL = "gpt-image-2"
```

macOS / Linux 用 `export CPA_IMAGEGEN_BASE_URL=...` 等方式设置。也可参考 [config.example.toml](config.example.toml)，用 `--config` 指定自己的 TOML 文件。配置支持 `api_key` 或 `api_key_env`，后者引用本机环境变量。

优先级：命令参数 > `CPA_IMAGEGEN_*` 环境变量 > TOML 配置 > 非敏感默认值。密钥不接受命令行参数。地址和密钥缺失时停止，不默认切到官方服务，也不使用 `OPENAI_API_KEY` / `OPENAI_BASE_URL`。

导入的字面密钥保存在用户私人配置中；Unix 新建文件权限为 0600，Windows 继承用户目录权限。真实配置、日志和生成图片不纳入版本控制。

## 使用

```sh
# 检查配置、连接和模型列表，不调用生图
cpa-imagegen doctor --json

# 不联网，只检查本地输入并展示即将发送的参数
cpa-imagegen generate --prompt "A ceramic mug in soft daylight" --out output/imagegen/mug.png --dry-run --json

# 生成一张图片
cpa-imagegen generate --prompt "A ceramic mug in soft daylight" --out output/imagegen/mug.png --json

# 编辑图片，可重复添加 --image 作为参考
cpa-imagegen edit --image output/imagegen/mug.png --prompt "Change only the mug to green" --out output/imagegen/mug-green.png --json
```

默认：`gpt-image-2`、1024×1024、medium、单张 PNG。可用 `--model`、`--size`、`--quality`、`--timeout` 调整。尺寸接受 `auto` 或 `WIDTHxHEIGHT`，具体模型支持由上游验证，不按模型名称前缀限制兼容模型。此版本输出路径必须以 `.png` 结尾；输入支持 PNG、JPEG、WebP，每个文件不超过 50 MiB。

复杂提示词建议保存为 UTF-8 文件，通过 `--prompt-file PATH` 传入。已有图片不会覆盖，明确替换时添加 `--overwrite`；输入和输出必须是不同文件。`--dry-run` 输出包含提示词，不应作为公开日志。

普通输出显示保存路径。`--json` 返回绝对路径、实际尺寸、模型、请求 ID 和上游提供的用量，不包含图片 Base64；运行错误返回 `error.category`、脱敏消息和可用的请求 ID，退出码为 1；命令语法错误遵循 argparse 的退出码 2。

若上游未返回实际模型，结果的 `model` 使用请求模型，并用 `model_source: "requested"` 标记，不能据此证明上游实际路由。网关也可能忽略尺寸请求；工具保留原始尺寸，不静默缩放，并报告请求与实际尺寸是否一致。

### 精确输出尺寸：本地补边或裁剪

继续使用 CPA 中登录的订阅账号即可。需要精确尺寸时，先保存原图，再运行独立的本地命令，不需要密钥、不联网、不消耗生图额度：

```sh
# 等比缩放，居中放入透明画布，保留完整画面
cpa-imagegen resize --image output/imagegen/mug.png --size 1024x1024 --mode pad --out output/imagegen/mug-padded.png --json

# 等比缩放并居中裁剪，填满画布，会丢失部分边缘
cpa-imagegen resize --image output/imagegen/mug.png --size 1024x1024 --mode crop --out output/imagegen/mug-cropped.png --json
```

`resize` 要求明确选择 `pad` 或 `crop`，不提供拉伸模式。`--size` 必须是具体的 `WIDTHxHEIGHT`，不能为 `auto`；输出像素数不能超过 Pillow 的图片像素安全阈值。输入支持 PNG、JPEG、WebP，并按 EXIF 方向处理。输出为 PNG，必须与输入路径不同；已有输出需显式添加 `--overwrite`。

JSON 用 `local_processing: true`、`source_width` / `source_height` 和 `width` / `height` 区分原图与处理结果。本地处理保证最终文件尺寸，不能证明上游原生按该尺寸生成，也不能补回原图没有的细节。默认生成、编辑流程仍保留上游尺寸。

CPA 同类尺寸问题见 [#4114](https://github.com/router-for-me/CLIProxyAPI/issues/4114#issuecomment-4901391886) 和 [#5860](https://github.com/router-for-me/CLIProxyAPI/issues/5860#issuecomment-5696646250)：仓库协作者将其归因于上游忽略参数。目前没有据此确认有效的 CPA 尺寸开关或升级修复。

## 安装 Codex Skill

在安装工具的同一 Python 环境中执行：

```sh
cpa-imagegen install-skill --agent codex --json
```

默认安装到 `$CODEX_HOME/skills/cpa-imagegen`，未设置 `CODEX_HOME` 时为 `~/.codex/skills/cpa-imagegen`。用 `--dest PATH` 指定其他技能目录。已有目录不会覆盖。安装内容绑定实际 Python 环境，不包含密钥或开发机的固定路径。

新建聊天；如果未发现 Skill，重启 Codex。示例：

> 使用 $cpa-imagegen 生成一张 1024×1024 的咖啡杯产品图，保存到项目并展示。

也可直接提出通过 CPA 生图或改图的需求，由 Agent 根据 Skill 描述选择。其他 Agent 可调用 CLI，或自行安装兼容的 Skill 目录；当前不宣称已完成其他 Agent 的安装验收。

## 故障排查

| 类别 | 含义与处理 |
|---|---|
| `config` | 检查地址、密钥来源、配置路径和 timeout |
| `authentication` | 网关返回 401/403，检查 CPA 凭据或上游权限 |
| `rate_limit` | 网关返回 429，检查额度或频率限制 |
| `connection` / `timeout` | 连接失败或超时；超时后上游是否完成未知 |
| `upstream` | 根据 HTTP 状态、脱敏错误和请求 ID 检查 CPA 路由 |
| `response` / `download` | 返回为空、图片损坏或下载失败，不重复生成 |
| `input` / `save` / `install` | 检查输入、输出权限、文件冲突或安装路径 |

SDK 自动重试为零，不自动换模型、换服务或重复生成。`doctor` 成功只说明配置和模型列表检查通过，始终返回 `image_generation_verified: false`。模型被列出不保证可以生图，也不能说明使用了哪个订阅的额度。

图片返回支持 Base64 或 HTTP(S) URL。URL 下载使用独立客户端，不携带 CPA bearer token；保存前验证图片，再以 PNG 输出。

## 验证与开发

```sh
python -m pytest -q
python -m build
```

离线测试使用模拟接口，不需要真实密钥。CI 配置覆盖 Windows / macOS / Linux × Python 3.11 / 3.14，并检查 wheel 安装和内含的 Skill 资源。

2026-11-01 本地验收：Windows + Python 3.14.7、OpenAI SDK 2.54.0、Pillow 13.0.0，通过离线测试、sdist/wheel 构建和 wheel 安装检查。

当前 CPA 已完成一次真实生成和一次真实编辑：请求 `gpt-image-2`、low、1024×1024，先生成蓝色陶瓷杯，再编辑为绿色，保存并目视检查两张 PNG。两次返回均为 1374×1145，与请求尺寸不同；工具保留原图并报告差异。上游未返回实际模型和请求 ID，不能据请求模型证明实际模型路由。测试图片保留在本机忽略目录中，不随源码提交。

本地尺寸处理已使用上述编辑结果分别验收 `pad` 和 `crop`，两者均输出 1024×1024 并目视检查；原图保留，没有新增生图请求。相关离线测试覆盖内容保留、透明度、居中裁剪、EXIF 方向、文件冲突和不联网运行。

其他平台以 GitHub Actions 实际运行结果为准，尚未推送时不视为已验证。

接口依据：[OpenAI Images API](https://developers.openai.com/api/docs/guides/image-generation)。仅实现同步 Images API；异步任务、流式预览、批量并发及各家独立接口不在首版范围内。

## 许可证

[MIT](LICENSE)，Copyright © 2026 calmlim。
