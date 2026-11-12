# 凭证与外部服务清单

本清单只记录**变量名、用途、映射关系和校验方式**，不记录真实 Key 或 Cookie 内容。机器可读真值在
[`config/credentials.manifest.json`](../config/credentials.manifest.json)，本机可编辑模板在
[`config/daily-briefing.env.example`](../config/daily-briefing.env.example)。

## 真值位置

| 层级 | 位置 | 说明 |
| --- | --- | --- |
| 本机 Key/URL/模型 | `~/.codex/daily-briefing.env` | `env_config.py` 会加载；已存在的进程环境变量优先 |
| 淘股吧 Cookie | `~/.codex/tgb_cookies.json` | JSON 数组，必须含 `tgbpwd`、`tgbuser` |
| 抖音 Cookie | `~/.codex/daily-briefing-pro/data/douyin_cookies.json` | `sessionid` 缺失时只能按公开页运行 |
| 雪球 Cookie | `~/.codex/daily-briefing-pro/data/xueqiu_cookies.json` | 必须含 `xq_a_token`、`xq_is_login` |
| GitHub Actions | 仓库 Settings → Secrets and variables → Actions | 工作流引用的 Secret 名称，见下表 |
| 自托管 Compose | `plugins/daily-briefing-pro/deploy/cloud/secrets/` | 独立于 GitHub Actions，需要单独填充 |

不要把真实值写入 `config/`、`docs/`、`work/` 或任何会被 Git 跟踪的文件。

## 一键检查

```powershell
# 本机必填项 + GitHub Secret 名称 + Cookie 登录标记/过期时间
python tools\credential_manifest.py check --github --all --strict

# 生成可读的 Markdown 清单
python tools\credential_manifest.py check --github --all --markdown

# 只预览将同步哪些 Secret，不写入
python tools\credential_manifest.py sync-github

# 把本机配置文件和三份 Cookie 同步到 GitHub Actions
python tools\credential_manifest.py sync-github --apply
```

输出中的 `sha256:` 只是值指纹，不能还原 Key。Cookie 文件只显示路径、数量和过期时间，不显示 Cookie 值。
`--github` 只能确认 Secret 名称是否存在，GitHub API 不会返回 Secret 值，所以无法判断远端值是否与本机一致。
本机替换 Key/Cookie 后，必须运行 `sync-github --apply` 并触发一次 CI，不能把“名称存在”当成“值已更新”。

## 主要配置

| 本机变量 | GitHub Secret | 用途 | 替换后验证 |
| --- | --- | --- | --- |
| `FUYAO_API_KEY` | `FUYAO_API_KEY` | 扶摇 REST 行情、个股/行业报告 | `python plugins\daily-briefing-pro\cloud_cli.py doctor --probe` |
| `IWENCAI_API_KEY` | `IWENCAI_API_KEY` | 可选问财 OpenAPI；不是扶摇 Key | 无 Key/额度耗尽时跑一次 `stock-report`，确认东方财富补位 |
| `DAILY_BRIEFING_AI_BASE_URL` | 同名 | 文本 AI Relay 地址 | `doctor --probe` |
| `DAILY_BRIEFING_AI_API_KEY` | 同名 | 语义总结 | 运行一次 `briefing --resume` |
| `DAILY_BRIEFING_AI_MODEL` | 同名 | 主模型 | 观察 AI 摘要是否成功 |
| `DAILY_BRIEFING_AI_FALLBACK_MODEL` | 同名 | 回退模型 | 主模型失败时观察日志 |
| `DEEPSEEK_BASE_URL` | 同名 | 抖音/旧调用兼容的 Relay 地址 | `fetch_douyin.py` |
| `DEEPSEEK_API_KEY` | 同名 | 抖音/旧调用兼容 Key | 同上 |
| `DEEPSEEK_MODEL` | 同名 | 抖音/旧调用兼容主模型 | 同上 |
| `DEEPSEEK_FALLBACK_MODEL` | 同名 | 抖音/旧调用兼容回退模型 | 同上 |
| `TGB_COOKIE_PATH` | `TGB_COOKIE_GZ_B64` | 淘股吧登录 Cookie 文件 | 重新采集淘股吧 |
| `DOUYIN_COOKIE_PATH` | `DOUYIN_COOKIE_GZ_B64` | 抖音 Cookie 文件 | 重新采集抖音 |
| `XUEQIU_COOKIE_PATH` | `XUEQIU_COOKIE_GZ_B64` | 雪球 Cookie 文件 | 重新采集雪球 |
| `DOUYIN_ASR_BASE_URL` | 同名 | 通用 OpenAI Compatible ASR 地址 | 配置后跑一条真实抖音视频 |
| `DOUYIN_ASR_API_KEY` | 同名 | 通用 ASR Key；不能使用文本 Relay Key | 同上 |
| `DOUYIN_ASR_MODEL` | 同名 | 通用 ASR 服务模型名 | 同上 |
| `GROQ_API_KEY` | `GROQ_API_KEY` | Groq Whisper 音频转录（推荐，免费额度） | 同上 |
| `SILICONFLOW_API_KEY` | `SILICONFLOW_API_KEY` | SiliconFlow SenseVoice 中文转录（推荐） | 同上 |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | OpenAI Whisper 音频转录（付费） | 同上 |

抖音无字幕视频**必须至少配置一种音频 API**：`DOUYIN_ASR_*` 三项齐全，或
`GROQ_API_KEY` / `SILICONFLOW_API_KEY` / `OPENAI_API_KEY` 任一。项目不再安装或运行本地
Whisper，也不会把文本 AI Relay 当作音频接口。

`HITHINK_API_KEY`、`HITHINK_FINANCE_API_KEY` 和 `WENCAI_API_KEY` 是兼容别名，不建议同时维护多份。
当前推荐只写 `FUYAO_API_KEY` 与 `IWENCAI_API_KEY`。

清单同时收录高级/可选运行时项，包括采集、构建和预检超时，模型缓存目录，同花顺安装目录，
Node 代理继承，Compose 镜像标签，以及 Linux 小写代理变量。完整列表用
`python tools\credential_manifest.py check --all --markdown` 查看。

## Cookie 的短命边界

| Cookie | 登录标记 | 处理建议 |
| --- | --- | --- |
| 淘股吧 | `tgbpwd`、`tgbuser` | 这两个通常最先过期；过期后重新导出完整 Cookie 数组 |
| 抖音 | `sessionid` | 缺失时公开页可尝试，但不能宣称登录态或稳定覆盖 |
| 雪球 | `xq_a_token`、`xq_is_login` | `xq_a_token` 通常先过期；刷新时保留同一浏览器的完整上下文 |

检查命令会读取每个登录标记的 `expires`（兼容 epoch 和 ISO 时间），在 72 小时内提示 `WARN`，已过期提示
`FAIL`。Cookie 过期不是“没有新帖”，不能当成空结果。

## 当前审计（2026-11-12）

- 工作流当前引用 19 个 Secret 名称；其中 13 个已存在，6 个 ASR 相关 Secret 未配置。
- 本机配置已经包含两组 Relay 变量；它们当前使用同一个 Key，避免只改一边造成不一致。
- 淘股吧 Cookie 在 2026-11-13 13:27（北京时间）前后过期，属于近期必须替换项。
- 抖音 Cookie 没有 `sessionid`，当前只能按公开页模式运行；文本 AI 与音频 ASR 必须分开配置。
- 用户提供的百度 Cookie（`BDUSS`、`BAIDUID_BFESS`、`BAIDU_WISE_UID` 等）未被本项目任何采集链路读取，因此不纳入可执行清单；不要把它们混入淘股吧、抖音或雪球 Cookie 文件。
- `DOUYIN_AI_BASE_URL`、`DOUYIN_AI_API_KEY`、`DOUYIN_AI_MODEL` 是代码未读取的旧变量，保留只会造成漂移。
- 文本 AI Relay 不支持 `/audio/transcriptions`；`DOUYIN_ASR_*` 必须指向真正的音频接口。
- **当前没有配置任何 ASR Key**：`GROQ_API_KEY`、`SILICONFLOW_API_KEY`、`OPENAI_API_KEY` 均为空，
  `DOUYIN_ASR_*` 三项也未配置。抖音视频若没有原生字幕，转录会直接失败；需要先补其中一个 Key。
- 问财现在不是启动硬依赖；无 Key 或额度耗尽时，报告会使用东方财富、腾讯和同花顺补数并标明来源。
- 本地 Whisper / faster-whisper 已从代码、依赖和镜像中移除；预检与定时任务在缺少云端 ASR Key 时直接失败，
  不会降级到本机模型，也不会用标题冒充转录。
- 当前 `thsdk` 是游客态；只有配置 `THS_USERNAME`、`THS_PASSWORD`、`THS_MAC` 才是固定账号。
- 当前未配置 `THS_SELFSTOCK_PATH`，因此自选股/分组接口属于可选不可用状态。
- 自托管 Compose 的 `secrets/` 目录目前只有 `fuyao_api_key`；如果实际启用 Compose，需要按
  `deploy/cloud/README.md` 补齐，不要误以为 GitHub Actions 已通过就代表 Compose 也已配置。
- GitHub 侧工作流引用的 Secret 名称齐全，但 GitHub 无法回读 Secret 值；远端值是否落后于本机，仍需在替换后
  通过 `sync-github --apply` 刷新并用 CI 验证。

以上是配置审计结论，不代表行情、Cookie 或外部服务永久有效。任何时候都以 `check --github --strict`
的实时结果为准。

## 防漏检查

`tests/test_credential_manifest.py` 会在每次测试时比对三件事：GitHub 工作流引用的 Secret、
清单与模板的必填变量、源码实际通过 `os.getenv` / `os.environ.get` 读取的配置变量。以后新增配置变量
但忘记登记清单时，测试会直接失败。

## 替换流程

1. 只改 `~/.codex/daily-briefing.env` 中对应变量；不要改源码里的默认 URL/模型。
2. Cookie 直接替换三个 JSON 文件，保留 JSON 数组格式和原始域名字段。
3. 运行 `python tools\credential_manifest.py check --github --all --strict`。
4. 检查通过后运行 `python tools\credential_manifest.py sync-github --apply`。
5. 触发一次 CI 或运行对应的真实采集命令，确认不是只看“配置存在”。

同步命令默认只预览，只有加 `--apply` 才会写 GitHub；写入时 Secret 从标准输入传递，不放在命令行参数里。
