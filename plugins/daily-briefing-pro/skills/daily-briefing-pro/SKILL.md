---
name: daily-briefing-pro
description: '用于用户需要生成每日A股简报、提炼研报、筛选财经新闻或开展深度分析、分析抖音/淘股吧博主观点、进行博主多空调查、完成A股个股深度分析或查看个股K线行情时。'
metadata:
  legacy:
    trigger_words:
    - 生成每日简报
    - 简报
    - 每日推送
    - 新闻推送
    - daily briefing
    - 今天简报
    - 研报提炼
    - 新闻筛选
    - 财经新闻深度分析
    - 抖音博主观点
    - 淘股吧博主
    - 博主多空统计
    - 市场情绪调查
    - A股个股分析
    - 个股行情
    - K线
    version: 3.23.19
    author: Codex
    dependencies:
      python: '>=3.12'
      pip_packages:
      - playwright
      - httpx
      - requests
      - akshare
      - beautifulsoup4
      env_vars:
      - SILICONFLOW_API_KEY
      - GROQ_API_KEY
      - OPENAI_API_KEY
      - DOUYIN_ASR_BASE_URL
      - DOUYIN_ASR_API_KEY
      - DOUYIN_ASR_MODEL
      - DOUYIN_TRANSCRIPT_PROVIDER
      - DEEPSEEK_API_KEY
      - DOUYIN_BLOGGERS_EXTRA
      - DOUYIN_MAX_CONCURRENT
      - IMA_OPENAPI_CLIENTID
      - IMA_OPENAPI_APIKEY
      - THS_SELFSTOCK_PATH
      external_tools:
      - ffmpeg
      - node
  original_name: 每日简报专业版
---

# 每日A股简报生成器

## 概述

全自动每日投资简报生成器。覆盖市场情绪、财经新闻、龙虎榜与板块轮动、研报、博主动态、未来事件和策略等内容：

| # | 板块 | 数据源 | 执行方式 |
|---|------|--------|---------|
| ① | 市场温度与情绪周期 | 开盘啦API + 上证MA250（AkShare） | 情绪模型3.2（同景分位+接缝+六阶段） |
| ② | 财经科技新闻 | 东方财富API | HTTP抓取 |
| ③½ | 龙虎榜 | 同花顺官方龙虎榜（hithink-finance）；AkShare(东方财富) 降级 | CLI 取数：个股榜+机构榜+游资派系榜 |
| ③¾ | 板块轮动 | 行业轮动模型 v2.0.0（同花顺行业指数90板块） | 调外部模型 predict，离线打分 |
| ④ | 机构研报观点 | ima + 研报客 + 东方财富 | 三源融合 |
| ⑤½ | 博主多空统计 | 淘股吧50 + 雪球50 博主帖子 | 淘股吧urllib + 雪球浏览器内请求上下文 |
| ⑥ | 淘股吧博主 | urllib HTTP + 登录Cookie | 后台HTTP请求（v3.5.1重写） |
| ⑦ | 抖音博主观点 | Playwright（移动/桌面回退）+ 转录 | 抓取博主主页全部目标日视频；默认串行转录，可显式配置最多 2 条 |
| ⑧ | 未来大事件 | 东方财富财经日历API | 后台HTTP请求 |
| ⑧+ | 盘面补充（并入①与⑨） | 同花顺官方盘面事实（主）+ 连板网 lianban.net 补充（新高新低/融资/资金/次日观察） | CLI 取数 + Playwright 兜底渲染 |
| ⑧½ | 大小周期节点票 | 节点模型 V1.0：同花顺连板池 + 米开朗基瑞淘股吧公开主帖/楼主回复可访问片段 | `scripts/build_node_cycle.py` 滚动历史 + HTML 时间轴 |
| ⑨ | 今日策略 | 综合研判 | 基于前序模块 |
| ⑩ | 每日一句 | 投资名言库（72条+去重） | `pick_quote.py` |

## 内置能力路由

本 Skill 是唯一入口。用户提出专项请求时，仍沿用下表的输入、抓取、筛选和输出约定，但统一调用本目录 `scripts/` 下的实现；生成完整简报时统一使用 `scripts/run_all.py`，不再加载其他 Skill 文档。

| 用户请求 | 入口脚本 | 默认交付 |
|---|---|---|
| 生成每日简报 | `scripts/run_all.py` | 按固定报刊模板生成并验收 HTML + 对话总结 |
| 研报提炼 | `scripts/fetch_yanbao.py`；三源专项模式见下文 | 当日机构观点表 |
| 财经新闻深度分析 | `scripts/finance_news_pro.py` | 新闻、方向、影响层级、标的关联 |
| 新闻快筛 | `scripts/news_screener.py` | 纯文本两组新闻，各不超过 15 条 |
| 抖音博主观点 | `scripts/fetch_douyin.py`、`scripts/analyze_douyin.py` | 当日视频观点表 |
| 淘股吧博主观点 | `scripts/tgb_crawl.py` | 博主核心观点 + 标的表 |
| 博主样本多空调查 | `scripts/fetch_sentiment_survey.py` | 大盘/板块统计与核心结论 |
| A 股个股分析/行情看板 | `modules/stock-analysis/`、`modules/stock-market-board/` | HTML 分析报告或行情页面 |
| 大小周期节点票 | `scripts/build_node_cycle.py`；模型实现见 `scripts/node_cycle_model.py` | 简报内嵌嵌套时间轴、节点精简表与证据等级 |
| 报刊风（纸张质感）版式 | `scripts/build_broadsheet.py`；样式资产 `templates/broadsheet.css` | 同数据的报刊版 HTML（纸感 + 双栏长表） |

路径约定：脚本和静态资源从本 Skill 根目录读取；运行数据统一由 `scripts/runtime_paths.py` 管理，默认保存到 `~/.codex/daily-briefing-pro/data/`，可通过 `DAILY_BRIEFING_DATA_DIR` 覆盖。首次运行只把旧 Skill 目录和当前安装包中的长期文件迁入持久目录，已有持久数据优先保留；`*_today.json`、Cookie、登录态和临时交付文件不参与迁移。不要从用户目录按旧 Skill 名称拼接脚本路径，也不要保留同名脚本副本。
云端模式（`DAILY_BRIEFING_CLOUD=1`）与会话模式共用同一份长期数据白名单：干净环境会把安装包内 `data/` 的历史基线按“缺失才补”的方式迁入持久目录，已有云端数据优先保留；`*_today.json`、Cookie、登录态仍被排除。因此云端首次运行至少具备面板、节点/轮动历史和 AI 缓存基线，采集阶段再增量补齐当日数据，而不是从空面板起步。预检会校验面板 22 个模型列、历史 JSON 有效性和更新时间；基线过期会明确告警。

插件执行入口为本 Skill 目录内的 `scripts/run_all.py`。普通运行会先执行 `scripts/runtime_preflight.py`，缺模型、历史面板、AI凭证、抖音转录环境、平台Cookie、同花顺认证或可写目录时在采集前阻断；只检查不采集使用 `--preflight-only`。在源码项目中维护时，使用 `plugins/daily-briefing-pro/skills/daily-briefing-pro/scripts/run_all.py`；不要修改安装缓存。定时运行加 `--scheduled`：先用同花顺交易所日历核验，非交易日跳过；日历缺失或未覆盖目标日则报错，不用星期推断节假日。

跨平台统一入口为插件根目录的 `cloud_cli.py`，Linux/Windows/macOS 使用同一条命令：

```powershell
python {plugin_dir}/cloud_cli.py briefing --date YYYY-MM-DD
python {plugin_dir}/cloud_cli.py briefing --date YYYY-MM-DD --preflight-only
python {plugin_dir}/cloud_cli.py stock-report 600519
python {plugin_dir}/cloud_cli.py industry-report 白酒
```

`briefing` 透传 `run_all.py` 参数，仍执行完整性、凭证和报刊版视觉门禁；`stock-report` / `industry-report` 自动完成采集、HTML 生成和源数据事实校验。云端运行目录通过 `DAILY_BRIEFING_DATA_DIR`、`BRIEFING_OUTPUT_DIR` 持久化；`work/`、运行数据和 Cookie 不提交到仓库。

行业轮动模型优先从 `ROTATION_MODEL_DIR` 读取，其次读取插件根目录 `models/sw_rotation_model`；云端若两者都没有，会自动把随包分发的 `data/cloud-baseline/models/sw_rotation_model.zip` 解压到 `~/.codex/daily-briefing-pro/models/sw_rotation_model-<sha>`，无需人工上传模型目录。模型工作目录必须可写，因为行情刷新和预测会更新它的 `data/` 与 `outputs/`；缺少原始 `run.py`、配置或行情文件时不得用旧排行结果代替计算。随包模型是丢失原目录后的功能性重建，`RECONSTRUCTED.md` 记录了快照回归与已知差异；同一份压缩包保证本地和云端可复现同一组分数，但不宣称与原模型逐字节一致。

安装插件后，在本 Skill 目录执行 `python scripts/run_all.py --scheduled`。源码项目另提供 `tools/run_daily_briefing.py` 启动器，从任意工作目录调用项目源码并固定 UTF-8 编码与项目报告目录；此项目启动器不属于插件安装包。恢复指定日期已采集数据时使用 `--date YYYY-MM-DD --resume`，日期和逐模块完整性校验仍执行，不能把其他日期的数据当成本日结果。

日报转录先尝试抖音原生字幕；没有原生字幕时只调用云端 ASR API，按 `DOUYIN_TRANSCRIPT_PROVIDER=auto` 依次尝试通用 ASR、Groq、OpenAI、SiliconFlow。代码、镜像和依赖中不再包含 faster-whisper、openai-whisper、torch 或本地模型权重；没有配置任何云端 ASR Key 时预检直接报错并列出缺失变量，完整简报没有跳过转录或本地兜底模式。

博主调查按作者数及原文长度分批，通过有限并行调用语义 API，并逐批保存精确日期/原文哈希缓存。语义阶段有独立总时限；编排器的外层时限须覆盖平台采集与语义阶段之和。抖音的日期核验、媒体解析、下载及转录各自报告失败原因，成功转录保存按视频 ID 绑定的缓存，重跑不重复下载已经核验的同一视频。当前默认串行转录；`DOUYIN_MAX_CONCURRENT` 可显式配置最多 2 条，云端 ASR 并发过高会触发供应商限流。


AI 总结只使用已配置的 OpenAI-compatible API。本机 Codex CLI 登录路径已彻底移除；云端和桌面环境在缺少 API Key 时都会明确失败，不会回退到本机程序。仅传入真实采集文本，拒绝工具调用结果、缺失索引或不完整批次；失败仍阻断必选语义总结，不能用截断原文替代。不得复制登录 token 或把密钥写进源码。精确日期/原文哈希缓存仍可复用。

## 报刊风模板（纸张质感版式）

每日简报的最终交付必须使用**报刊版**：米色纸张质感 + 报头 + 头版导读 + 双栏长表，全部板块、全部数据行与图标一一保留。版式必须沿用固定模板，不得每次重新设计；模板编译或验收失败时停止交付。

- 渲染：`python scripts/build_broadsheet.py [--src <当日简报.html>] [--out <输出.html>] [--date YYYY-MM-DD]`
  - 源文件默认取 `<cwd>/报告/每日简报/` 下日期最新的 `*简报.html`（自动排除已生成的报刊版）
  - 默认输出 `<日期>简报-报刊版.html`，与源简报同目录
- 样式资产：`templates/broadsheet.css`（配色与纸张纹理；`__TEX_FINE__` / `__TEX_MOTTLE__` 占位符由渲染器注入）。调整纸感或配色只改这个文件。
- 自动验收（必做）：`scripts/run_all.py` 默认先生成源简报，再运行 `python scripts/verify_broadsheet.py --out <报刊版.html> --src <源简报.html>`
  - 自动核对板块数、数据行数（不含分栏重复的表头）、图标渲染、横向溢出，并输出桌面 1440 / 手机 390 截图与 4 段切片到 `<输出目录>/_验收/`
  - **未通过不得交付**；通过后仍要肉眼过一遍截图再报告。最终交付链接必须指向报刊版 HTML；源简报仅作为生成和核验输入。

版式规则（固定口径，不要临时更改）：

1. 板块与数据只做**搬运**：不新增、不删减、不改写数字；所有板块都必须出现，无数据时保留原样标注。
2. 每个板块必须有线描图标（`ICONS` 映射），缺图标视为未完成。
3. 顺序：报头 → 金句横幅 → 四指数行情条 → 头版导读（标题 + 左温度面板 / 右阶段柱状图）→ 大小周期节点票时间轴 → 长表与两栏板块 → 报脚。
4. 长表排布分两种：**龙虎榜与板块轮动是左右并列的两个栏目**（龙虎榜在左、板块轮动在右，各自保留一张整表，不要把自己再拆成左右两半，列宽由 `.tbl-lhb` / `.tbl-rot` 百分比固定）；**机构研报按条目对半拆左右两栏**，表头在每栏重复，样本聚焦通栏。两栏列宽用百分比统一，保证左右逐列对齐。
5. 纸张质感 = 三层内嵌纹理（细颗粒 + 纸浆斑纹 + 淡帘纹）+ 光感渐变 + 纸边阴影，占位符必须替换为 data URI；打印时自动去纹理。
6. ≤820px 全部并单栏；图表等宽表允许横向滚动，页面本身不得横向溢出。

## 专项能力规范

### 研报观点提炼

输入可为“今日研报/机构观点/研报提炼”，可选 `--date YYYY-MM-DD`。完整简报模式由 `fetch_yanbao.py` 从东方财富研报接口获取目标日前 3 天窗口（含目标日）数据，并在输出中标明数据日期；专项三源模式通过 `scripts/yanbao/run.mjs` 聚合研报客、IMA 订阅知识库和网络搜索，三者都必须以目标日期过滤。

输出至少包含：`板块 | 方向 | 机构观点总结 | 重点标的 | 来源机构`；详细版补充 `核心逻辑`。每条观点必须说明驱动因素→传导路径→受益/受损标的，不能只写“看多/看空”。同一机构同一标题去重；策略和宏观类没有明确方向时标为中性。非交易日专项查询没有当日新增时明确输出“当日暂无新增研报”，完整简报才允许使用最近工作日并标注日期。

### 财经新闻深度分析

专项分析可使用财联社、华尔街见闻、东方财富、雪球、财新、第一财经、界面、央行、证监会、国家统计局、富途和 Seeking Alpha 等源；快讯缓存 5–10 分钟、深度内容约 1 小时、宏观内容 24 小时。支持 `--source`、`--market A|HK|US`、`--keyword` 和 `--limit`。

每条新闻依次做：去重与来源核验 → 利好/利空/中性判断 → 市场/行业/公司影响分级 → 股票名称、代码、别名映射 → 风险等级。重大新闻尽量由两个来源交叉确认，保留来源、分钟级时间戳和原链接；输出“头条焦点、市场动态、行业动态、风险提示、情绪指标”。默认只提供信息和风险提示，不把新闻解读写成确定性买卖建议。

### 新闻快筛

用户说“新闻筛选/抓新闻/新闻快筛”时分两组处理，并严格只收录目标日：

1. 财经与科技新闻：优先财联社加红重要消息，再按政策/监管、行业重大、公司业绩、国际、资金面排序，剔除盘面噪声和无实质传闻，最多 15 条。
2. 自选股新闻：读取同花顺本地自选股，按公告、明确利好利空、龙虎榜、普通新闻排序，每股最多 3 条，总计最多 15 条。

每条标注来源、标的代码+名称和 `🟢利好 / 🔴利空 / 🔵中性`；输出纯文本对话，不生成 HTML/文件。入口命令为 `python scripts/news_screener.py {health|tasks|stocks|summary}`，自选股主路径由 `THS_SELFSTOCK_PATH` 或同花顺默认路径提供。禁止用静态 JSON 冒充实时结果、禁止依赖不可用的通达信接口。

### 博主观点统一规范

博主类请求先按平台分流。配置 AI 时，结果必须是语义总结，不得把原文或转录截断伪装成结论；未配置 AI 时，抖音日报可以展示明确标注为“转录摘录（未使用AI）”的真实采集文本，淘股吧仍必须标注摘要不可用。每条观点至少有方向（看多/看空/中性）、理由和具体标的/板块；无明确方向的内容标中性。输出表格优先，必要时附 3–5 条共识/分歧结论。

结构化结果字段包括 `id`、`tweet_id`、`created_at`、`content`、`ai_summary`、`ai_direction`、`symbols`、`likes`、`retweets`、`views`；`content` 只作为内部原始数据，面向用户必须优先输出 `ai_summary`，不得直接照搬原文。`--date YYYY-MM-DD` 严格按目标日期过滤，目标日无推文就明确输出暂无，不用旧帖补齐；抓取失败如实标注原因。

#### 抖音

输入博主主页 URL（支持短链），未指定博主时使用口罩哥和机构一手调研（福总）默认入口，可用 `DOUYIN_BLOGGERS_EXTRA=name|url,name|url` 追加。流程必须是：解析 `sec_uid` → Playwright headless 拦截 `/web/api/v2/aweme/post` → 逐个详情页读取 `create_time` 或可见的真实“发布时间” → 按北京时间确定可用发布日 → 仅对该日视频下载和转录 → 生成观点表。

核验细节（2026-09 起抖音改版后的实测口径）：移动端列表接口已不再返回 `create_time`，且移动端 UA 的详情页会被静默拦空（HTTP 200 但 DOM 为空），因此**详情页时间核验必须用桌面 UA 渲染**（每次约 6 秒，失败重试 1 次），只在桌面端取不到时才回退移动端。主页列表是新→旧排列，核验到早于目标窗口的条目即可停止，不必整页逐条渲染。桌面端 `/aweme/v1/web/aweme/post/` 常返回数天前的旧缓存，不能作为发布时间依据。

默认串行转录，可显式配置最多 2 条（`DOUYIN_MAX_CONCURRENT` 可调，云端 ASR 并发过高会触发供应商限流）。`auto` 依次尝试显式配置的通用 OpenAI-compatible ASR、Groq、OpenAI、SiliconFlow，不会回退到任何本地模型；没有可用 Key 时直接报错，不会把标题当转录。`DOUYIN_TRANSCRIPT_PROVIDER=cloud` 必须同时配置 `DOUYIN_ASR_BASE_URL`、`DOUYIN_ASR_API_KEY`、`DOUYIN_ASR_MODEL`，文本 Relay 不能作为音频接口。失败条目在 main() 里串行重试一次。视频下载或转录失败时可跳过该条并记录原因；成功转录但未配置 AI 时，HTML 只展示明确标注的转录摘录，不把它写成 AI 观点。

当天未更新时的回退规则：按**自然日**回退到最近一个确有视频的发布日，最多 `DOUYIN_MAX_STALE_DAYS`（默认 7）天；不做工作日跳过，因为短视频博主周末照常更新。回退时必须在 `note` 与板块 meta 里写明实际数据日期，且不得用旧视频冒充当日内容；超过窗口仍无视频则如实标注账号最近发布时间。禁止保存视频/音频/Markdown/HTML 等专项产物。表格列为 `标题 | 核心观点 | 标的 | 方向`，最后给出核心主线；无法获取时间时不得凭猜测纳入当日结果。观点提炼提示词按语音转写场景编写：在内部纠正同音错字，只输出判断+逻辑+【标的】，禁止输出纠错清单或补充转录里没有的个股。

#### 淘股吧

输入 `https://www.tgb.cn/blog/{userID}` 或使用简报默认的东北玄、太阳的微笑、九尾北极猫、狼王行千里。使用 `scripts/tgb_crawl.py` 的 urllib + Cookie 方式抓取 `moreReplyMod` 跟帖、`moreTopic` 主帖和公开博客页；Cookie 由 `TGB_COOKIE_PATH` 指定，缺失或登录页返回必须报错。

只保留目标日内容，过滤少于 10 字及签到、加油、闲聊等噪声；主帖优先并融合高赞跟帖，主帖缺失时标注“当日无主帖，仅跟帖动态”。输出 `博主 | 核心观点 + 标的` 两列，观点 cell 内可含主帖标题、AI 提炼摘要、标的标签及跟帖精华；专项查询不生成文件。

#### 博主样本多空调查

用户说“博主观点统计/多空调查/市场情绪调查”时，分别采集雪球和淘股吧经身份与页面核验的账号样本，目标各 50 人，只保留目标日帖子。样本名单不等同平台排名；披露候选池、失败排除、活跃作者和有效观点人数。淘股吧通过 Cookie 的 HTTP 接口抓取；雪球需要已登录的 Playwright 浏览器提取主页时间线。过滤“昨天/前天”等相对时间和闲聊内容，同一博主多帖合并分析。

雪球采集的实现要点（`scripts/fetch_xueqiu.py`）：**先用 Playwright 打开
`https://xueqiu.com/` 让浏览器自己过掉 WAF，再用同一个 page 的 `request`
上下文请求 `https://xueqiu.com/statuses/user_timeline.json?user_id={uid}&page=1`**。
裸 urllib/httpx 请求、外部 Chromium 指纹、以及 `/v4/statuses/...` 这个路径都会
被阿里云滑动验证拦住，只有“浏览器内发起的 `/statuses/` 请求”能拿到真实 JSON。

每位博主输出 `direction`（看多/看空/中性）、`sectors`、`is_market_view`、`reason`；板块名称要合并同义词。默认只输出大盘观点表、板块观点表、平台对比和 3–5 条核心结论；只有用户明确要求时才展开逐博主明细。数据不足时标注实际覆盖人数和原因，不用样例数据填充。

### 统一日期、回退和冲突规则

- 所有日期默认动态取北京时间当天，用户传入 `--date` 时以该日期为准；禁止硬编码历史日期。
- 完整简报允许对交易数据、淘股吧和抖音在非交易日向前回退最近工作日/最多 1 天，并在 HTML 元信息中标注“使用 X 月 X 日数据（当日无更新）”。
- 专项查询默认严格当天；没有当天数据就报告“暂无”，不暗中混入历史内容。只有用户明确要求最近交易日时才回退。
- 冲突时，数据真实性、日期过滤和来源标注优先于数量目标；任何 API、Cookie、转录或浏览器失败都要标记失败原因，禁止编造。

### 大小周期节点票（节点模型 V1.0）

这是每日简报的固定模块，不得在每次生成时临时改口径。`run_all.py` 在连板池写入后调用
`scripts/build_node_cycle.py`，补齐目标日前最近 31 个自然日内的交易日连板池，追加到
`data/node_cycle_history.json`，再由 `scripts/node_cycle_model.py` 重算 `data/node_cycle_today.json`。

模型固定规则：

1. 横轴只用真实交易日；条形的起止和宽度按实际运行日期跨度计算。同一启动日或断板日必须共享同一 x 坐标，重叠条形通过 `lane` 上下堆叠，禁止左右错位。
2. 大节点优先采用米开朗基瑞公开主帖/可访问楼主回复中明确认定的周期核心；没有明确认定时，只有同时具备周期切换、打开高度、辨识度/资金闭环等至少两项信号才可推断为大节点。
3. 小节点候选默认最高连板 ≥3；4板与5板以上优先保留，关键断板日、题材切换日或指数共振日的3板可由数据源显式标记后保留。普通跟风不进入节点表。
4. 节点确认至少满足“关键时间节点 + 辨识度 + 后续高度反馈”中的两项。无法从公开证据核验的记录保留在模型结果中时，必须标为中/低置信度，不写成确定周期核心。
5. 纯跟风、无独立题材地位、单纯被板块反推的票排除；`穿越`、`观察` 单独记录在模块边界说明中，不能被升级成新节点。周期归属按大节点周期与 `cycle_id` 划分，不按月份切割。
6. 输出固定包含：一句话当前大周期/小节点结论；最近一个月真实交易日期嵌套时间轴；证据来源与排除项说明。**不再输出下方的精简表**——名称、最高连板、定位、置信度全部并入时间轴条形内；起止日期由逐日横轴表达，不写进条形（横轴已标到每一天，条内再写一遍是冗余），完整起止与证据来源放在悬停标题里；穿越/观察票用虚线幽灵条单独一行展示。无足够历史时显示“暂无可核验节点”，不得填入样例票。

大节点认定与配色：`kind="major"` 的票用**深红实心 + ★**并置于最上层，`kind="small"` 用蓝色，两者在图例里区分配色；同一大节点周期内的重叠小节点顺延到下一行，形成嵌套关系。大节点优先取米开朗基瑞公开主帖/楼主回复的明确认定；**当该证据源不可用时**走兜底分支 `_mark_height_core()`，口径为：**周期跨度最长**的票地位最高 = 本轮周期核心。周期跨度 = 连板运行区间 + 断板后走出二波新高的延续区间（`scripts/cycle_life.py` 用日线核验后按交易日给出 `cycle_span_days`）；跨度和连板高度都并列时按启动日更早优先。最低门槛 5 个交易日，死水窗口（全场最高不足 5 板）不硬凑周期核心。没有日线数据时退回「连板高度最高 + 连板天数最长」的纯连板口径。`role` 写成「大节点（周期核心·待公开认定）」，保持中/低置信度，不写成确定周期核心。节点名单截取仍按：连板高度 → 连板天数 → 证据等级 → 是否挂靠大节点 → 启动日越早越靠前。

**地位与行序同源（用户口径，2026-09-21 起）**：连板段（实心）＋后面虚线段（断板后二波延续）的总长度最长的那条票，就是本轮周期最大、地位最高的票，**必须出现在时间轴最上面一行**。模型里 `total_span_days` 就是这个总跨度（＝`cycle_span_days`，两趟计算时按 (名称, 启动日) 精确匹配、名称兜底），第一趟探测用 `keep_all_smalls=True` 让每个候选都拿到日线核验跨度，避免第二趟换人时跨度退回纯连板天数；渲染层按跨度从长到短依次占位，落在第一行不与已有条形重叠的位置，小节点永远排在父节点下方。跨度并列时按连板高度降序、启动日更早优先。

因为大节点依赖周期跨度，`scripts/build_node_cycle.py` 走**两趟计算**：第一趟出候选节点并用日线核验各节点的周期跨度，第二趟带 `cycle_spans` 重算大节点归属与布局，最后把日线字段重新绑定到最终节点对象上（日线有磁盘缓存，第二趟几乎不增加请求）。

时间轴渲染规范（2026-09-21 起）：模型里的 `lane` 表示嵌套层级，渲染时仍要做冲突消解——**先按周期跨度（连板段＋虚线段）从长到短排序**，每条票落在第一行不与已有条形重叠的位置，重叠的条形顺延到下一行；父节点未落位时子节点顺延，**禁止让条形左右重叠压在一起，也禁止小节点排到父节点上方**。横轴**每个交易日都要有日期刻度**（不是隔几天取一个），跨周的第一个交易日用更重的网格线做节奏参照。时间轴外层为横向滚动容器（`.node-scroll`），内层轨道宽度按 `--node-zoom` 缩放（100%–400%，`.node-track`，最小宽度 920px，保证每日刻度在窄屏也不挤在一起），配 `− / ＋ / 重置` 按钮、`Ctrl+滚轮` 缩放和按住拖动平移；默认 100% 展示整月全貌，放大后再横向拖动看细节。条形内只放**名称 + 连板高度 + 置信度**，不写起止日期；太短时按“置信度 → 连板数”的顺序让位，保证个股名称优先可读；悬停标题里写明 `周期跨度 N 个交易日（连板 X＋二波延续 Y）`，便于核对行序依据。

断板 ≠ 周期结束：`break_date` 只是最后一个连板日，「没走A」的真正含义是**后面还能走出二波新高**（`scripts/cycle_life.py`）。判定口径固定为：参考高点 = 连板运行区间 `[launch, break]` 内的最高收盘价（前复权）；断板后收盘价首次超过参考高点的那天记为「二波新高日」，**窗口内始终没能创新高就不加虚线**（横盘不跌不等于周期还在走）；虚线区间 = 断板次日起，到二波重新收盘跌回参考高点之下为止，窗口末仍未跌回则视为二波仍在延续。时间轴上 **实心条 = 连板运行区间，细虚线 = 断板后走出二波新高的延续交易日**，一条票的实心与虚线共用同一行。行情按东方财富 → 新浪 → 腾讯择优取用（备用源会滞后一天，故以“覆盖到最新交易日”为准，并用 `complete` 标记支持当天补抓），价格取不到时只画实心段并在 `evidence_note` 里写明未判定数量。

数据来源优先级：同花顺官方连板池用于连板事实核对；米开朗基瑞淘股吧公开主帖及可访问楼主回复用于周期认定；其他公开连板数据只能作交叉核对。来源不完整时在模块内显示证据等级。

## 全局规则

### ⚠️ 执行前必读（重要！）

1. **文件命名规范** — 输出文件必须命名为 `YYYY-MM-DD简报.html`（如 `2026-07-06简报.html`），禁止使用英文命名如 `daily_pulse_xxx.html`，禁止使用 `每日简报_YYYY-MM-DD.html` 格式

2. **日期必须动态获取** — 所有脚本中的日期参数必须使用 `datetime.now().strftime("%Y-%m-%d")` 自动获取当日日期，**禁止硬编码日期**如 `"2025-07-03"`

3. **必须获取实际数据** — 每次执行skill时，必须从各数据源获取当日的实际数据，**禁止使用模板中的样例数据**。周末/节假日无更新时，应标注"周末无更新"而非保留旧数据

4. **严格遵循模板布局** — HTML输出必须严格遵循 `templates/briefing.html` 的布局结构：
   - `fw` class仅用于全宽独占一行的section：机构研报、抖音博主
   - 财经新闻、龙虎榜、板块轮动、淘股吧、博主多空统计、未来大事件**不带**`fw` class，落入正文两栏
   - **正文左右两栏**：`.g` 为固定两列网格（1440px 下 675px × 2，中缝 26px 并带一条竖细线），不带 `fw` 的 section 按 DOM 顺序落进左/右栏；带 `fw` 的 section 横跨两栏；≤960px 自动降为单栏
   - **报头**：`<body>` 顶部输出 `.np-mast` 报头（英文刊头 + 报名 + 「日期 / 数据日 / 板块数 / 模型版本」信息行），数值由编译器实时注入，不写死
   - **情绪指标+阶段柱状图**：强制同一行（`flex-wrap:nowrap`），柱状图 `min-width:0` 自适应填满；柱子按当日情绪阶段着色，图例只列当期真实出现过的阶段
   - **指数栏**：只保留4个指数——上证、科创50、纳斯达克、KOSPI，强制一行（`flex-wrap:nowrap`）
   - **策略section**：不带`fw`但独占一行，使用**flex一行布局**（`display:flex`），三个卡片（做多/观察/风险）等宽排列（`flex:1;min-width:0`），移动端≤600px自动换行纵向排列
   
5. **所有10个简报板块都必须存在** — 不得擅自删减板块；数据缺失时按下方规则标注原因（自选股新闻已按用户要求从完整简报移除；Serenity 板块已于 v3.14 按用户要求整块移除）

6. **⛔ 淘股吧和抖音是必选板块，必须有内容** — 这两个板块是简报核心价值，不允许为空：
   - **自动日期回退**：脚本已内置回退机制——指定日期无数据时，自动向前搜索1天（如周五→周四），确保周末/节假日也能获取到最近内容
   - **淘股吧**：4位活跃博主通常每天都有跟帖或主帖。如果指定日期+回退1天仍返回0条，说明Cookie过期或脚本故障，**必须报错并修复后重试**
   - **抖音**：博主通常每天有视频发布。如果指定日期+回退1天仍无视频，**必须报错并排查原因**（Cookie/ffmpeg/ASR Key/网络），禁止跳过或填"处理超时"
   - **禁止跳过、禁止提前输出**：必须等淘股吧和抖音数据都成功获取后，再统一编译所有板块生成简报HTML并输出链接。**绝不允许先输出简报再回来补数据**
   - **回退数据标注**：使用回退日期数据时，HTML中必须标注"使用X月X日数据（当日无更新）"

7. **禁止伪造数据** — 如果API返回错误或无数据：
   - 周末/节假日：标注"周末休市，使用最近交易日数据（X月X日）"
   - API失败：标注"数据获取失败"而非编造数值
   - 绝不可凭空捏造指数、新闻、观点等内容

8. **未来大事件：后台HTTP，禁止打开浏览器** — 该板块必须使用专用的后台Python脚本（`fetch_future_events.py`）通过urllib/httpx直接请求API获取数据。**严禁**使用Playwright、`mcp__plugin_playwright`、手动打开浏览器或任何会弹出窗口的方式获取。脚本运行时无可见界面，纯后台执行。自选股新闻抓取器仅供专项筛选使用，不属于完整简报流程。

9. **抖音转录必须使用云端 ASR，不允许本地模型兜底** — `analyze_douyin.py` 默认 `--provider auto`，优先使用抖音原生字幕；没有字幕时按通用 ASR → Groq → OpenAI → SiliconFlow 调用真实音频接口。未配置任何云端 ASR Key 时预检和运行都必须报错并列出缺失变量，禁止把标题、话题或固定回放当转录。若单条视频转录仍失败，`fetch_douyin.py` 必须**使用视频标题+话题标签兜底**并写入 warning；成功转录但无 AI 时，必须保留真实 transcript 并在 HTML 以“转录摘录（未使用AI）”标注。缓存命中必须保留原始 `transcript_source` 并标记 `transcript_cache_hit`，不能用固定回放冒充新转录。

10. **机构研报必须含看多/看空逻辑** — 机构研报板块的核心价值不在于"谁看多谁看空"，而在于**为什么看多、为什么看空**。每条研报观点必须包含：
   - **标的/板块**（必须标注具体股票代码或板块名称）
   - **方向**（看多/看空/中性）
   - **核心逻辑**（1-2句话，必须说清楚背后的逻辑链：业绩驱动？政策催化？行业拐点？估值修复？竞争格局变化？）
   - **来源机构**
   - 表格列建议：`机构 | 赛道 | 标的 | 方向 | 核心逻辑 | 来源`
   - 禁止只写结论不写逻辑，例如"XX券商看多半导体"是无效的，必须写出"XX券商看多半导体，逻辑是：AI算力需求爆发+NAND涨价周期+国产替代加速"
   - 周末/节假日时，标注"周末无新研报"并显示最近工作日的研报逻辑摘要

  11. **⛔ 博主观点优先经过AI总结提炼** — 淘股吧和抖音博主的原始内容是口语化、碎片化的，配置 AI 时**必须经过AI语义级总结提炼后才能输出到简报**，绝不允许把原文或截断文本冒充成观点结论。抖音在没有可用 AI 凭证时，允许输出明确标注来源的“转录摘录（未使用AI）”，以避免真实采集内容静默丢失。
     - **AI总结凭证不内置在源码**：`run_all.py` 只读取环境变量 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` 或 `OPENAI_API_KEY`；淘股吧有内容但没有 AI 凭证时，正式编译门禁会阻断，避免交付不完整观点
     - **总结 ≠ 摘抄**：不是从原文截取片段拼接，而是理解语义后用书面语重新表达
     - **每条观点必须包含**：方向判断（看多/看空/中性）+ 核心逻辑（为什么）+ 具体标的/板块
     - **禁止输出**：口语填充（"兄弟们""怎么说呢""就是说"）、互动引导（"点赞关注"）、无信息量的碎片句、原文截断
     - **AI总结失败时**：配置了 AI 的平台必须重试（最多3次）；仍失败时不得生成伪语义结论。抖音可以改用“转录摘录（AI总结失败）”的明确来源标记，转录失败才使用标题+话题标签并标注 warning。
     - AI总结成功的观点显示 `✦AI提炼` 标识

     **正例（AI 总结后）**：
     ```
     看多【半导体】国产替代：长鑫估值虽高但老外已将预期打满，关注设备与存储方向【寒武纪】【江波龙】
     ```

     **反例（直接照搬转录/原文截断）**：
     ```
     因为你在脸上交易 你知道老外现在怎么抢长新的吗老外现在他们你本管在拍片上面 还有很多
     ```

     **反例（正则提取半成品，仍属原文范畴）**：
     ```
     超预期也就是20日线这样子吧；大票放量联动
     ```

     > 此规则由 `build_briefing.py` 中的 `ai_summarize_opinions()` 和 `ai_summarize_blogger_batch()` 函数执行。AI 凭证不写在源码里：`scripts/env_config.py` 会读取 `~/.codex/daily-briefing.env`，系统环境变量优先。凭证缺失或返回 401 时，淘股吧板块阻断编译，不会把原始跟帖当观点交付。

### 常规规则

- **只取当天内容** — 所有模块严格 TODAY 过滤
- **颜色语义** — 红涨绿跌（A股惯例）：`#E74C3C` 上涨/利好，`#2ECC71` 下跌/利空
- **输出格式** — 自包含HTML文件，**报刊风格**：纸面米白底 + 油墨黑 + 宋体系衬线字（Noto Serif SC/思源宋体/宋体），正文左右两栏，报头居中
- **输出目录** — 相对于调用方工作空间根目录的 `报告/每日简报/`（环境变量 `BRIEFING_OUTPUT_DIR` 可覆盖），若目录不存在则自动创建
- **脚本路径** — 所有脚本在 `scripts/` 目录下，使用相对路径
  - **交付规则** — 报告生成完成后，必须在对话中输出总结内容+报告文件链接，两步缺一不可。先输出总结，最后输出链接。禁止只输出总结不输出链接。报告输出后要在对话里给个可点击的链接
  - **已有报告也要给链接** — 本次没有生成新报告时（休市、非交易日、抓取窗口不合适而主动跳过、门禁失败等），只要输出目录里已有报告，就必须把**最近一份**报告的可点击 Markdown 链接发出来（绝对路径），并说明它是哪一天的报告；不得只回一句"本次未生成"就不给链接
  - **前端浏览器零容忍** — 所有数据源优先使用后台HTTP请求（urllib/httpx/WebFetch）或headless脚本（Playwright headless模式，不打开可见窗口）。**数据获取阶段严禁使用** `mcp__plugin_playwright`（会弹出可见浏览器）、`present_files`、`powershell Start-Process`、`Bash start` 等任何可能打开前端浏览器的工具。淘股吧/抖音爬虫使用 `headless=True` 模式的Playwright（无可见界面），此方式可接受。**报告生成后也不打开外部浏览器**，只输出对话总结+文件链接
  - **只生成HTML文件** — 禁止生成图片(png/jpg/svg)、Markdown(.md)、PDF、Word等其他格式文件。唯一输出产物是HTML简报文件。中间数据JSON由脚本自动写入 `data/` 目录供编译使用，但最终交付给用户的只有HTML文件

### ⚠️ 博主观点优先总结提炼，禁止伪装来源

博主（淘股吧+抖音）的原始内容是口语化、碎片化的，配置 AI 时**必须经过AI语义级总结提炼后才能输出成观点结论**，绝不允许把原文或截断文本伪装成 AI 结论。没有 AI 凭证时，抖音日报可以展示明确标注“转录摘录（未使用AI）”的真实采集文本；淘股吧不得把失败结果写成合格观点。

**核心原则**：
- **总结 ≠ 摘抄**：不是从原文中截取片段拼接，而是理解语义后用书面语重新表达
- **每条观点必须包含**：方向判断（看多/看空/中性）+ 核心逻辑（为什么）+ 具体标的/板块
- **禁止输出**：口语填充（"兄弟们""怎么说呢""就是说"）、互动引导（"点赞关注"）、无信息量的碎片句、原文截断、正则提取半成品

**实现方式**（`build_briefing.py` 内置）：
 - **AI 总结（优先路径）**：调用 DeepSeek/OpenAI 兼容 API（`DEEPSEEK_API_KEY` 或 `OPENAI_API_KEY`）对博主原始内容做语义级提炼
   - 输入：云端 ASR 转录文本 / 淘股吧跟帖原文
   - 输出：1-3 句精炼书面语观点，标的用【】标注
   - AI 总结成功的观点显示 `✦AI提炼` 标识
 - **AI 失败时**：已配置 AI 的平台重试最多3次，仍失败时不得生成伪语义结论；抖音可降级为带来源标记的转录摘录，转录失败才使用标题+话题标签并标注 warning
  - **AI 凭证必配**：优先取系统环境变量 `DEEPSEEK_API_KEY`/`OPENAI_API_KEY`，其次取 `~/.codex/daily-briefing.env`；401/403 视为凭证失效，直接指向修复动作且不再重复重试

**正例（AI 总结后）**：
```
看多【半导体】国产替代：长鑫估值虽高但老外已将预期打满，关注设备与存储方向【寒武纪】【江波龙】
```

**反例（直接照搬转录/原文截断）**：
```
因为你在脸上交易 你知道老外现在怎么抢长新的吗老外现在他们你本管在拍片上面 还有很多
```

**反例（正则提取半成品，仍属原文范畴，禁止输出）**：
```
超预期也就是20日线这样子吧；大票放量联动
```

> 此规则由 `build_briefing.py` 中的 `ai_summarize_opinions()`、抖音转录摘录逻辑和 `ai_summarize_blogger_batch()` 函数执行。Agent 必须确保输出中的 AI/非 AI 来源标识与真实处理路径一致。

### 淘股吧博主板块规则

- **博主列表**（4位，无"只核大学生"）：东北玄、太阳的微笑、九尾北极猫、狼王行千里
- **狼王行千里主页**：`https://www.tgb.cn/blog/2747572`
- **数据获取方式（v3.5.1重写）**：
  - **禁止使用Playwright**（`add_cookies`注入失效导致页面跳转登录页）
  - 使用 **urllib HTTP请求 + Cookie header** 直接请求页面（`scripts/tgb_crawl.py`）
  - Cookie文件：`~/.codex/tgb_cookies.json`（22个cookie条目）
  - 主数据源：`moreReplyMod` 页面（`<div class="blogReply">` HTML结构解析）
  - 辅助数据源：`moreTopic`（主帖）、博客主页（公开精华帖）
  - 4位博主每天必有跟帖/主帖（日均5-20条），**返回0条=Cookie过期或脚本故障，必须报错修复**
- **主帖/跟帖处理**：
  - 优先爬取当日的**主帖**（moreTopic）和**跟帖**（moreReplyMod）
  - 若当日有主帖 → 在主帖标题下总结核心观点 + 整合高赞跟帖精华
  - 若当日无主帖仅有跟帖 → 只总结跟帖内容，标注"当日无主帖，仅跟帖动态"
  - 若当日完全无动态 → 标注"{博主名}今日无动态"
- **表格格式**（去掉"更新"列）：
  - 列：`博主 | 核心观点 + 标的`
  - 博主名高亮：`<td class="tb" style="color:var(--gld)">博主名</td>`
  - 观点列包含：主帖标题（加粗）+ 核心观点摘要 + 标的标签 + 跟帖精华（如有）
  - 观点cell宽度自适应，bot信息（如有跟帖数/赞数等）可放在内容末尾小字显示
- **共识摘要**：表格下方添加 `<div class="lbox">` 总结4位博主的共同关注点和分歧点

### 抖音博主板块规则

- **默认博主**：口罩哥（双入口合并去重）、机构一手调研（福总）
- **支持追加博主**：通过环境变量 `DOUYIN_BLOGGERS_EXTRA` 配置，格式 `name|url,name|url`，例如：
  ```bash
  export DOUYIN_BLOGGERS_EXTRA="研讯社|https://v.douyin.com/xxxxx/"
  ```
- **抓取策略（v3.13 目标日 + 移动/桌面回退 + 并发转录）**：
  - **只抓取博主今日发布的视频**，按北京时间（UTC+8）过滤 `create_time`，非今日视频直接丢弃
  - **并发转录**：同一博主的目标日视频默认串行调用云端 ASR，避免触发供应商限流；可通过环境变量 `DOUYIN_MAX_CONCURRENT` 显式配置最多 2 条
  - 抓取博主主页返回的全部今日视频，**不再做 topN 截断**
  - 转录失败/为空时，仅记录标题/话题元数据和失败原因；完整简报必须全部转录成功并取得与全文哈希一致的语义摘要，禁止用标题替代视频观点
  - 转录流程：`--provider auto` 按通用 ASR → Groq → OpenAI → SiliconFlow 尝试；没有 Key 时直接报错，不会进入本地模型
  - 标的/板块关键词库持续扩展，覆盖 A 股/港股/美股常见科技与消费标的
- **输出字段**：每条视频包含 `title/url/transcript/summary/symbols/direction/warning`；`warning` 标注转录失败；`title_source` 单独标注标题来自原始标题或转录开头
- **信息遗漏检查**：生成器逐视频核验转录、原始链接和语义摘要；任何目标视频缺失即阻断完整简报，不写出成功页面

### 每日一句板块规则

- **名言库**：`data/investment_quotes.json`（初始72条），覆盖巴菲特、芒格、格雷厄姆、段永平等经典投资格言
- **去重机制**：`pick_quote.py` 只从带 `verified=true` 和原始出处链接的名言中选择，写入 `data/used_quotes.json` 追踪ID及日期；同日重跑复用已选名言，全部用完自动重置
- **执行时机**：Step 1 Group A 并行执行（<1秒），由编排器保存HTML片段；失败时保留显式失败卡
- **模板占位**：`templates/briefing.html` 中 `<!-- QUOTE_PLACEHOLDER -->` 在编译时替换为名言HTML
- **显示内容**：名言原文 + 作者/头衔 + 原理简述 + 标签
- **数据文件**（均在 `data/` 目录）：
  - `investment_quotes.json` — 名言库（手动维护，可随时追加新名言）
  - `used_quotes.json` — 已用ID追踪（自动维护，勿手动编辑）
- **失败处理**：若 `pick_quote.py` 执行失败（名言库损坏等），只显示“每日金句数据获取失败”，禁止使用默认名言或样例内容

---

## 核心数据源

### 市场温度与情绪周期

顶部情绪卡片使用用户提供的 **A股超短情绪温度模型 3.2**（版本号
`A-SHORT-SENTIMENT-3.2`）。模型不是简单加权求和，而是「同牛熊景历史分位 +
结构接缝 + 非线性校正」的组合，运行顺序：

```text
原始收盘数据
→ 牛熊分组（上证 vs MA250）
→ 同景历史标准化（只用 t 之前样本，最多 250 个同景交易日）
→ 六因子 F/L/R/A/B/V → 基础强度 Q
→ 分歧/一致接缝 J
→ 非线性修正（高潮共振、普跌/跌停/炸板、退潮惯性）
→ 最终温度 S → Δ1/Δ2 → 六阶段状态机
```

| 因子 | 权重 | 口径 |
|---|---:|---|
| 赚钱反馈 F | 34% | 0.6×G(昨连板反馈) + 0.4×G(昨涨停反馈)，G(r)=50+50·tanh(r/3) |
| 连板生态 L | 24% | 连板数/空间/次高/连板占比的同景分位加权 |
| 风险质量 R | 18% | 0.55×100e^(−跌停/18) + 0.45×封板率分位 |
| 进攻扩散 A | 15% | 0.65×涨停分位 + 0.35×首板分位 |
| 市场广度 B | 6% | 红盘数/正常交易股票数×100 |
| 量能确认 V | 3% | 成交额20日比值分位与广度的联动确认 |

- 基础映射 `S_base = 18 + 0.87Q`，再叠加接缝修正 `C_J`、高潮共振 `C_hot`，
  并扣减普跌、跌停、炸板、降温与惯性惩罚，最后截断到 0～100。
- 六阶段：`修复 → 升温 → 高潮 → 降温 → 退潮 → 冰点`；分歧/一致不是第七阶段，
  而是阶段之间的接缝，用 `J` 标注（≥+30 强分歧→一致，≤−30 强一致→分歧）。
- `Δ1=S_t-S_{t-1}` 是速度，`Δ2=Δ1_t-Δ1_{t-1}` 是加速度；动能标签沿用
  上攻加速、向上拐点、上涨钝化、退潮加速、下跌收敛、转弱加速、动能平稳。
- 输入面板 `data/sentiment_panel_v32.csv` 逐日增量维护；首次构建会回补
  `WINDOW_DAYS=400` 个交易日（约 1.6 年，覆盖模型标定区间），单日新增约 1~2 秒。
- 模型要求「严格连续板」口径：空间/次高取自开盘啦空间梯队，不使用“N天M板”。
- 晋级率由板位数按定义推算：1进2=当日2板/昨日首板，2进3=当日3板/昨日2板，
  3板以上=当日4板以上/昨日3板及以上；分母小于 3 家时沿用前值，不放大噪声。

**脚本位置：**

| 文件 | 职责 |
|---|---|
| `scripts/panic_greed_index_enhanced.py` | 入口（保留旧文件名以兼容 run_all 编排），转发到 3.2 实现 |
| `scripts/market_temperature_v32.py` | 面板构建 + 增量补齐 + 输出 `data/panic_today.json` |
| `scripts/sentiment_model_v32.py` | 模型本体（与用户提供的 reference_impl.py 逐行一致） |
| `scripts/market_temperature.py` | 旧版 11 因子线性公式，**已停用**，仅留作历史参考 |

### 开盘啦API

| 接口 | 参数 | 返回数据 |
|------|------|---------|
| `HisZhangFuDetail` | `Day=YYYY-MM-DD` | 涨跌家数、涨跌停数、市场评语 |
| `ZhangTingExpression` | `Day=YYYY-MM-DD` | 连板梯队、连板率、市场评价 |
| `RealRankingInfo` | `Date, Type, ZSType` | 板块强度排行 |
| `SharpWithdrawal` | `Day=YYYY-MM-DD` | 大幅回撤股票 |
| `GetZsReal` | `Day=YYYY-MM-DD` | 大盘指数实时数据 |

**请求示例：**
```bash
curl -X POST "https://apphis.longhuvip.com/w1/api/index.php" \
  -H "Content-Type: application/x-www-form-urlencoded; charset=UTF-8" \
  -H "User-Agent: Dalvik/2.1.0 (Linux; U; Android 12; ALN-AL00 Build/W528JS)" \
  -d "PhoneOSNew=1&DeviceID=test&VerSion=5.23.0.4&apiv=w44&a=HisZhangFuDetail&c=HisHomeDingPan&Day=$(date +%F)"
```

### 同花顺官方金融数据（hithink-finance）

龙虎榜与盘面补充的主数据源。统一入口是 `hithink-finance` CLI（同花顺官方 A 股数据服务），
API Key 存在系统凭据库，脚本侧只调 CLI，不接触 Key。封装在 `scripts/_hithink.py`。

```bash
npm install -g @hithink-tech/hithink-finance-cli   # 安装
hithink-finance auth login                          # 安全录入 API Key
hithink-finance capabilities --format json          # 查看当前命令契约
```

| 用途 | 命令 | 产物 |
|---|---|---|
| 龙虎榜（个股/机构/游资派系） | `special dragon-tiger --board-type all\|org\|hot_money [--date D]` | `data/lhb_today.json` |
| 涨停/跌停/炸板池与连板梯队 | `special limit-up-pool`、`limit-down-pool`、`limit-break-pool`（均支持 `--date-ms`） | 并入 `data/lianban_today.json` |
| 涨跌家数（剔除停牌） | `market snapshot`（分页全市场） | 同上 |
| 两市成交 | `index history --thscode 000001.SH` + `399001.SZ` 的 `turnover` | 同上 |
| 日线历史（前复权/后复权） | `market history --adjust forward\|backward` | 备用 |

**已对齐的口径（2026-09-16 实测）**：涨停 89、跌停 4、炸板 11、封板率 89%、
炸板率 11%、连板 12 家、最高板 6、涨 4170 家、跌 1189 家、两市成交 1.84 万亿，
与连板网逐项一致；龙虎榜净买入 TOP5 与机构净买 TOP5 与东方财富（AkShare）完全一致。
前一交易日交叉验证：09-15 涨停 32、跌停 27，与模型脚本里记录的当日值一致。

**口径要点**：
- 全市场快照含停牌股，必须按 `last_price > 0` 剔除，否则家数会多 20~30 只
  （停牌股 `price_change` 为负值，会被误计入下跌家数）。
- `tradable_count`/`advance_count` 只有最近交易日有实时口径，历史回填需另补。
- 同花顺公开能力**不含**资金流、分钟 K、tick、海外行情、宏观、新闻与研报原文，
  这些继续走连板网/东方财富等既有来源。

---

## 完整执行流程（v3.13 一体化编排版）

**⚡ v3.13：使用 `run_all.py` 一体化编排，严格区分报告日与交易日，所有板块写入来源/日期/状态元信息；抖音增加移动页验证码下的桌面公开页回退**

### 执行模式

| 模式 | 说明 |
|------|------|
| **默认模式（完整）** | 全部11个板块；淘股吧和抖音必须有可核验数据，且淘股吧有内容时必须配置 AI 凭证后才能编译输出简报 |

> 淘股吧和抖音博主每天必有内容。如果获取不到数据，说明存在技术故障（Cookie过期/ffmpeg缺失/网络问题等），**必须报错并修复后重试**，禁止跳过或填"无数据"。

---

### Step 0 — 环境初始化

```bash
# 检查云端 ASR 是否已配置（任选其一；都没有时抖音无字幕视频会明确失败）
python -c "import os; keys=[k for k in ('DOUYIN_ASR_API_KEY','GROQ_API_KEY','SILICONFLOW_API_KEY','OPENAI_API_KEY') if os.environ.get(k)]; print('ASR_KEYS_OK' if keys else 'NEED_CLOUD_ASR_KEY')"
```

> 本技能不再安装或运行任何本地语音模型。无字幕视频必须配置 Groq / SiliconFlow / OpenAI 音频 Key，或完整的 `DOUYIN_ASR_*` 三项；文本 AI Relay 不能作为音频接口。

### Step 1 — 一体化执行（run_all.py）

```bash
# 自动检测最近交易日、并行采集所有数据、编译HTML
python scripts/run_all.py [--date YYYY-MM-DD]
```

**`run_all.py` 内部执行流程：**

```
┌─ 自动检测交易日 ─────────────────────────┐
│ 凌晨0-5点 → 回退到前一天                    │
│ 周末 → 回退到上周五                         │
│ 内容源使用报告日；交易源使用最近交易日        │
└──────────────────────────────────────────┘
          ↓
┌─ Group A (并行, ~30s) ─────────────────────┐
│ panic_greed  news  龙虎榜 轮动 研报          │
│ 事件 盘面补充 名言                           │
│ → 结果写入 data/*.json                      │
└────────────────────────────────────────────┘
          ↓ 等待完成
┌─ 节点模型更新 (<1s) ───────────────────────┐
│ build_node_cycle.py --date YYYY-MM-DD       │
│ → 回补并追加最近1个月交易日连板快照           │
│ → 输出 node_cycle_today.json                 │
└────────────────────────────────────────────┘
          ↓
┌─ Group B (并行, ~5min) ─────────────────────┐
│ tgb_crawl    fetch_douyin  fetch_sentiment  │
│ → 结果写入 data/*.json                      │
│ → 必选校验：淘股吧>0条 && 抖音有视频          │
│ → 淘股吧有内容时还必须有AI语义总结凭证        │
│ → 任一失败则阻断，不编译、不输出报告链接       │
└────────────────────────────────────────────┘
          ↓ 等待完成
┌─ 编译HTML (<1s) ────────────────────────────┐
│ build_briefing.py --date YYYY-MM-DD         │
│ → 读取 data/*.json + 实时指数数据           │
│ → 输出调用方目录 报告/每日简报/YYYY-MM-DD简报.html        │
└────────────────────────────────────────────┘
```

**并行脚本清单：**

| 脚本 | 耗时 | 分组 | 必选？ |
|------|------|------|--------|
| 市场温度与情绪周期 | ~10秒 | A | 可缺省 |
| 财经新闻 | ~15秒 | A | 可缺省 |
| 机构研报 | ~30秒 | A | 可缺省 |
| 未来大事件 | ~20秒 | A | 可缺省 |
| 每日一句 | <1秒 | A | 可缺省 |
| **淘股吧博主** | ~10秒 | **B** | **⛔ 必选** |
| **抖音博主** | ~90秒 | **B** | **⛔ 必选** |
| **博主多空统计** | ~120秒 | **B** | 可缺省 |

> 以上脚本均由 `run_all.py` 自动编排并行执行，无需手动运行。所有脚本均支持 `--date YYYY-MM-DD` 参数。

### Step 2 — 交付报告（总结+链接，缺一不可）

只有淘股吧和抖音门禁均通过后，`run_all.py` 才会调用 `build_briefing.py` 编译HTML并输出交付按钮；任一必选源失败时只输出失败原因，不生成可交付报告。若 `run_all.py` 成功退出，Agent按以下顺序交付：

1. **在对话中输出简报总结内容**（必须，不可跳过）
2. **在对话中输出报告文件链接**（必须，不可跳过）

**⚠️ 对话总结和报告链接是强制必做步骤，缺一不可。禁止只输出总结不输出链接。**

#### 对话总结模板（放在报告链接之前，必须输出）

```markdown
### 📊 {YYYY-MM-DD} 每日简报总结

**市场情绪**：市场温度 S {XX}（{情绪周期阶段}，Δ1={速度}，Δ2={加速度}）

**大盘观点**：{一句话总结大盘方向，如"多数博主看多，关注科技主线"}

**核心看点**：
1. {今日最重要新闻/事件1}
2. {今日最重要新闻/事件2}
3. {今日最重要新闻/事件3}

**博主共识**：
- 淘股吧：{4位博主共识方向+关注板块}
- 抖音：{博主观点方向+核心标的}

**风险提示**：{1-2条当日最需关注的风险}
```

#### 报告链接（放在对话总结之后，必须输出）

**交付样式（Codex 桌面端，只用 Markdown）：**

用「引用块卡片」交付。用户明确反馈"不需要数量，我要内容"：卡片必须讲**当天发生了什么**，不要罗列数字或条数。五行结构：标题 / 一句话大盘行情 / 一句话当日主线 / 一句话博主与风险 / 加粗可点击链接：

```markdown
> **每日简报 · {YYYY-MM-DD}（周X）**
> {一句话行情：指数方向、涨跌氛围、成交放大或缩量，如"指数走强，4500多家上涨，成交放大到2万亿"}
> 主线：{1-3个当天最强方向，如"创新药、PCB/覆铜板、存储，硬科技IPO收紧信号带动"}
> 博主：{淘股吧/抖音博主当天共识方向与分歧}；防：{当天最需要注意的风险}
> **[打开简报 →](D:/MyProjects/股票分析/报告/每日简报/{YYYY-MM-DD}简报.html)**
```

- 链接必须写成 Markdown 语法 + **绝对路径**（正斜杠即可），不要 `file:///` URI、不要 URL 编码
- **禁止裸 HTML `<a>` 标签**：Codex 桌面端不渲染 HTML，会把整段标签当纯文本显示，用户点不动（2026-09-22 实测反馈）
- 卡片前后各留一个空行；链接必须在**代码块外**，代码块内的链接不可点击
- 卡片三行内容必须取自当天简报正文的真实信息，不编造；缺数据的板块在"博主"行简短注明（如"淘股吧未抓到"），不展开技术细节
- 每行只写一句话、讲内容不讲数量；不出现"X 条""X 篇""X 只"这类条数统计；不写买卖建议

**⚠️ 禁止事项：**
- 禁止使用 `powershell Start-Process` 自动打开外部浏览器
- 禁止使用 `Bash start` 命令打开外部浏览器
- 禁止使用 `mcp__plugin_playwright` 打开报告
- 禁止把链接放在代码块(```)内 — 必须是纯Markdown才能点击
- 禁止用裸 HTML `<a>` 充当交付链接 — Codex 桌面端只会显示标签源码
- **禁止跳过对话总结** — 报告生成后必须在对话中输出总结内容
- **禁止跳过报告链接** — 报告生成后必须在对话中输出可点击的文件链接

---

## v3.13 性能与数据完整性说明

| 优化项 | 原架构 | 新架构 | 预估提速 |
|--------|--------|--------|---------|
| 脚本执行 | 8脚本顺序执行 | **Group A 8脚本并行 + Group B 3脚本并行** | **提速80%** |
| 抖音浏览器 | 每博主启动独立Chromium | **共享1个浏览器实例** | **省30s/博主** |
| 抖音滚动 | 固定10次滚动 | **早退机制（非今日即停）** | **省15s/博主** |
| 日期处理 | 全部用`datetime.now()` | **统一`--date`参数，自动回退交易日** | **Bug修复** |
| 编译输出 | Agent手动编排5步 | **`run_all.py` 一体化2步** | **省1min编排** |
| 总预估耗时 | 5-8分钟 | **3-4分钟** | **提速40-50%** |

---

## HTML 模板结构

布局采用「报章」结构：报头 → 头版要闻区（温度 + 阶段柱状图 + 指数）→ 金句 → 左右两栏正文 → 策略。实际渲染（1440px）如下，`fw` 段横跨整幅，其余按顺序落进左右栏；≤960px 全部并为单栏：
```
┌──────────────────────────────────────────────────────┐
│  顶部细条：每日简报 │ 日期 │ LIVE                       │
├──────────────────────────────────────────────────────┤
│  DAILY A-SHARE BRIEFING                               │
│                        每 日 简 报                     │  ← .np-mast 报头（上下双细线）
│  日期 / 行情数据日 / 板块数 / 情绪模型 3.2              │
├──────────────────────────────────────────────────────┤
│  市场温度 S（左，含六因子）        │  近14日温度阶段柱状  │
│  上证 │ 科创50 │ 纳斯达克 │ KOSPI（4指数强制一行）      │
├──────────────────────────────────────────────────────┤
│  💬 每日一句（引语横幅，上下粗线）                      │
╞══════════════════════╤═══════════════════════════════╡
│  📰 财经科技新闻      │  🐉 龙虎榜                     │
│  🔄 板块轮动          │  📊 博主多空统计               │  ← 不带 fw，左右两栏（中缝竖线）
│  💬 淘股吧博主        │  📅 未来大事件                 │
╞══════════════════════╧═══════════════════════════════╡
│  📈 机构研报（fw 横跨两栏）                            │
│  📱 抖音博主（fw 横跨两栏）                            │
│  📅 未来大事件（落入左栏）                             │
├──────────────────────────────────────────────────────┤
│  🎯 策略：做多 │ 观察 │ 风险（flex强制一行）            │
└──────────────────────────────────────────────────────┘
```

### 颜色系统

### 机构研报板块表格格式

机构研报（section class="sec fw"）表格必须包含以下列，**核心逻辑列必须有实质内容**：

| 列名 | 宽度 | 内容要求 |
|------|------|---------|
| 机构 | 56px | 简称，如"中信"、"天风"、"招商" |
| 赛道 | 52px | 板块标签，如`<span class="bgd">存储</span>` |
| 标的 | 自适应 | 具体股票代码+名称，如`<span class="tag r">江波龙</span>` |
| 方向 | 52px | `<span class="bg_">看多</span>` 或 `<span class="bo">看空</span>` |
| **核心逻辑** | 自适应 | **必须1-2句话讲清逻辑链**：如"存储涨价+AI需求驱动，NAND价格Q3环比涨15-20%" |
| 来源 | 52px | 公告/行业/政策等 |

**反例（禁止）**：
```html
<td class="t2">江波龙业绩爆发，存储涨价</td>  <!-- 只有结论，无逻辑 -->
```

**正例**：
```html
<td class="t2">存储涨价周期：三星Q3 DRAM提价20%+美光93亿美元HBM扩产，NAND供给持续偏紧，价格Q3环比涨15-20%，利好国内存储模组厂 <span class="tag r">江波龙</span><span class="tag r">佰维存储</span></td>
```

### 淘股吧板块表格格式

淘股吧博客（section class="sec"）表格**去掉"更新"列**，只保留2列：

| 列名 | 宽度 | 内容要求 |
|------|------|---------|
| 博主 | 56px | 博主名，金色高亮：`<td class="tb" style="color:var(--gld)">` |
| 核心观点 + 标的 | 自适应 | 主帖标题（加粗）+ 核心观点摘要 + 标的标签 + 跟帖精华 |

**主帖/跟帖规则**：
- 当日有主帖 → 主帖标题加粗显示，下方总结核心观点
- 当日无主帖仅有跟帖 → 标注"当日无主帖"，只显示跟帖精华，如"<span style='color:var(--t3);font-size:11px'>仅跟帖</span> 核心观点..."
- 当日完全无动态 → 在观点列显示"今日无动态"

正例（有主帖）：
```html
<tr><td class="tb" style="color:var(--gld)">狼王行千里</td><td class="t2"><b>周末全是利好 周一全部跪倒</b>：市场分歧加大，走弱的品种很难反转，关注修复强度 <span class="tag y">半导体</span><span class="tag y">存储</span></td></tr>
```

正例（仅跟帖）：
```html
<tr><td class="tb" style="color:var(--gld)">东北玄</td><td class="t2"><span style="color:var(--t3);font-size:11px">仅跟帖</span> <b>科技空头压力</b>：Semi唱空报告后机构分歧加大，存储方向仍是共识 <span class="tag g">半导体</span></td></tr>
```

### 颜色系统

```css
/* v3.20 报刊主题：纸面米白 + 油墨黑，红色系整体降饱和以适配纸张 */
--paper:#f5f1e8;  /* 纸面底色 */
--ink:#1b1915;    /* 油墨黑（正文/粗线） */
--bg2:#fffdf8;    /* 版面白纸（卡片底） */
--bd:rgba(27,25,21,.16);  /* 细线 */
--a:#8c1c13;--a2:#b3261e; /* 报头红/强调 */
--up:#b3261e;     /* 上涨/利好（红） */
--dn:#1c6b46;     /* 下跌/利空（绿） */
--inf:#1f4e79;    /* 信息/链接（深蓝） */
--gld:#8a6a12;    /* 高亮/金股（暗金） */
--cyn:#155e63;    /* 国产替代/景气（深青） */
--wrn:#9a5b00;    /* 中性/警告（赭黄） */
```

### 排版
- 正文字体：Noto Serif SC → Source Han Serif SC → Songti SC → SimSun 衬线栈（中文报纸体），西文与数字回落 Georgia
- 展示字体（标题/报头/大数）：同衬线栈，报头英文刊头用 Playfair Display
- 版式：报头上下双细线、板块标题下粗细线、表格用极细线分隔、徽标为「单线方框铅字章」、引语横幅上下粗线
- 分栏：正文固定左右两栏，中缝一条竖细线；报头/头版要闻/策略横跨整幅

---

## 脚本清单

| 脚本 | 功能 | 用法 |
|------|------|------|
| `scripts/run_all.py` | **一体化编排**：并行采集+编译HTML+输出按钮 | `python scripts/run_all.py [--date YYYY-MM-DD]` |
| `scripts/build_briefing.py` | 通用编译器：读取data/*.json+实时指数→生成HTML | `python scripts/build_briefing.py [--date YYYY-MM-DD]` |
| `scripts/panic_greed_index_enhanced.py` | 市场温度 S、Δ1/Δ2 与情绪周期计算 | `python scripts/panic_greed_index_enhanced.py [--date YYYY-MM-DD]` |
| `scripts/fetch_news.py` | 东方财富新闻抓取 | `python scripts/fetch_news.py --source eastmoney [--date YYYY-MM-DD]` |
| `scripts/finance_news_pro.py` | 多源财经新闻深度抓取、分析和 JSON/Markdown 输出 | `python scripts/finance_news_pro.py --source all --limit 15` |
| `scripts/yanbao/run.mjs` | 研报客/IMA/网络搜索三源专项提炼 | `node scripts/yanbao/run.mjs [--date YYYY-MM-DD]` |
| `scripts/fetch_selfstock_news.py` | 自选股新闻专项抓取（不参与完整简报） | `python scripts/fetch_selfstock_news.py [--date YYYY-MM-DD]` |
| `scripts/fetch_future_events.py` | 未来大事件抓取（后台HTTP） | `python scripts/fetch_future_events.py [--date YYYY-MM-DD]` |
| `scripts/_hithink.py` | 同花顺官方数据 CLI 封装（供下列两个脚本共用） | 库文件，不单独执行 |
| `scripts/fetch_longhubang.py` | 龙虎榜采集：同花顺官方为主，AkShare 降级 | `python scripts/fetch_longhubang.py [--date YYYY-MM-DD]` |
| `scripts/fetch_lianban.py` | 盘面补充：同花顺官方事实 + 连板网补充字段 | `python scripts/fetch_lianban.py [--date YYYY-MM-DD]` |
| `scripts/build_node_cycle.py` | 节点模型 V1.0：滚动历史、证据等级、嵌套时间轴数据 | `python scripts/build_node_cycle.py [--date YYYY-MM-DD]` |
| `scripts/node_cycle_model.py` | 节点票确定性筛选与真实日期布局 | 库文件，不单独联网 |
| `scripts/tgb_crawl.py` | 淘股吧博主爬虫（urllib HTTP+Cookie，v3.5.1重写） | `python scripts/tgb_crawl.py` |
| `scripts/fetch_sentiment_survey.py` | 博主多空统计（50+50博主观点分析） | `python scripts/fetch_sentiment_survey.py [--date YYYY-MM-DD]` |
| `scripts/fetch_douyin.py` | 抖音博主观点抓取（v3.7 共享浏览器+早退） | `python scripts/fetch_douyin.py [--date YYYY-MM-DD]` |
| `scripts/extract_douyin.py` | 抖音视频提取 | `python scripts/extract_douyin.py {URL}` |
| `scripts/analyze_douyin.py` | 抖音视频转录 | `python scripts/analyze_douyin.py --api-key KEY --json URL` |
| `scripts/pick_quote.py` | 每日一句名言去重选取 | `python scripts/pick_quote.py [--date YYYY-MM-DD]` |

---

## 依赖说明

### 必需
- Python ≥ 3.12
- Playwright (`pip install playwright && playwright install chromium`)
- httpx, requests, akshare
- OpenAI 兼容文本 API 凭证（博主观点 AI 总结提炼，**必配**）：写入 `~/.codex/daily-briefing.env` 或设为环境变量，例如 `DEEPSEEK_API_KEY` + `DEEPSEEK_BASE_URL` + `DEEPSEEK_MODEL`；该接口只做文本，不能用于音频

### 可选
- ffmpeg（抖音音频提取，如未安装则analyze_douyin.py会失败）
- node.js（研报客搜索）
- `hithink-finance` CLI（同花顺官方数据，龙虎榜与盘面补充的主源）：`npm install -g @hithink-tech/hithink-finance-cli` 后执行 `hithink-finance auth login`；未安装或未登录时自动降级（龙虎榜回退 AkShare，盘面补充只剩连板网）
- `scripts/yanbao/` 三源研报专项模式所需的 Node.js 运行时
- **必配其一**：通用 OpenAI-compatible ASR、SiliconFlow / Groq / OpenAI 音频 Key（抖音无字幕视频的唯一转录通道；不提供本地模型兜底）
- IMA API凭证（知识库搜索）
- 淘股吧登录Cookie（`data/tgb_cookies.json`）
- 同花顺自选股JSON（`$THS_SELFSTOCK_PATH`，仅供专项新闻筛选）

---

## 环境变量配置

```bash
# 内容总结 — 博主观点AI提炼（必配，否则淘股吧有内容时会阻断编译）
# 凭证来源二选一，优先级从高到低：
#   1) 系统/终端环境变量（export DEEPSEEK_API_KEY=...）
#   2) 本机凭证文件 ~/.codex/daily-briefing.env（scripts/env_config.py 自动读取）
# 注意：凭证不写进 Skill 目录，因为 Skill 会同步到 OneDrive
export DEEPSEEK_API_KEY="sk-xxxxxxxx"
export DEEPSEEK_BASE_URL="https://api.deepseek.com/v1"
export DEEPSEEK_MODEL="deepseek-chat"

# 抖音转录（必配其一；原生字幕优先，无字幕时只调用云端 ASR）
# 通用 ASR 三项必须同时配置，文本 Relay 地址不能填这里
export DOUYIN_ASR_BASE_URL=""
export DOUYIN_ASR_API_KEY=""
export DOUYIN_ASR_MODEL=""
export SILICONFLOW_API_KEY="sk-xxxxxxxx"
export GROQ_API_KEY="gsk_xxxxxxxx"
export OPENAI_API_KEY="sk-xxxxxxxx"

# 追加抖音博主（可选，格式 name|url,name|url）
export DOUYIN_BLOGGERS_EXTRA=""

# 抖音并发转录数（可选，默认 1-2，云端 ASR 建议不超过 2）
export DOUYIN_MAX_CONCURRENT="1"

# IMA知识库（可选）
export IMA_OPENAPI_CLIENTID="xxxxxxxx"
export IMA_OPENAPI_APIKEY="xxxxxxxx"

# 同花顺自选股（可选，仅供专项新闻筛选）
export THS_SELFSTOCK_PATH="C:/应用/同花顺/mo_xxxxx/SelfStockInfo.json"

# 盘面补充是否启用连板网补充抓取（可选，默认 1）
#   1 = 同花顺官方事实 + 连板网补充（新高新低/融资余额/资金流/次日观察）
#   0 = 只跑同花顺官方，完全跳过 Playwright，约 10 秒出结果
export BRIEFING_LIANBAN_SUPPLEMENT="1"

# 同花顺官方数据 API Key（可选，通常不需要）
#   推荐直接用 `hithink-finance auth login` 存进系统凭据库；
#   只有在无凭据库的环境（容器/定时任务）才用这个变量兜底，且不得写入仓库
# export HITHINK_FINANCE_API_KEY="<按部署环境注入，不要写入仓库>"
```

---

## 快速开始

```bash
# 1. 安装依赖
pip install playwright httpx requests akshare
playwright install chromium

# 2. 在 Codex 中输入: "生成每日简报"
#    运行前确认两件事：
#    a) AI凭证可用：~/.codex/daily-briefing.env 或环境变量里的 DEEPSEEK_API_KEY
#    b) 淘股吧Cookie未过期：~/.codex/tgb_cookies.json（或 data/tgb_cookies.json）
#    两项缺任意一项，正式编译门禁会阻断并给出原因，不产出不完整简报
```

---

## 更新日志

### 未发布（2026-11-12）

- 抖音转录改为纯云端 ASR：移除 faster-whisper、openai-whisper、CTranslate2、torch、`av` 依赖、模型权重和镜像预下载；无字幕视频只调用通用 OpenAI-compatible ASR、Groq、OpenAI 或 SiliconFlow。
- 预检在没有任何云端 ASR Key 时直接报错并列出缺失变量；定时简报在启动前增加 ASR 凭证门禁，禁止标题/固定回放冒充转录。
- 语义总结彻底移除本机 Codex CLI：云端和桌面均只走 OpenAI-compatible API，无 API Key 直接失败。
- 转录缓存身份升级：旧本地 Whisper 缓存不再复用，必须由云端 ASR 重新生成带真实 `transcript_source` 的转录。

### v3.23.19 (2026-11-12)

- 可移植行情入口补齐 `sort`、`watchlist`、`sectors`、`subscribe` 和白名单 `call`；云端排行使用扶摇实时快照分页，支持市场范围、指数成分和排除板块，`prev_close` 不再返回空值。
- 云端 `subscribe --api SubscribeIntradayCandle` 默认周期改为 `5`，与桌面端日 K 默认一致；其余订阅仍是一次性首帧快照，不伪装持续推送。
- `parity` 只归一采集 JSON 中的确切 `fetch_time`，不再全局屏蔽 HTML 内所有日期时间，业务时间差异会正常报错。
- 修正云端报告的数据来源口径：问财提供实时行情、财务、估值、同业、股东、产品、筹码、壁垒和大单日汇总；扶摇提供证券检索、板块/成分/快照、新闻和行情补充。
- 完整性门禁新增最新营业收入、最新归母净利润和行业证券代码的源事实校验，防止财务值或标的代码错误通过。
- `codex-cloud-bootstrap.sh` 默认从 `main` 取数，并继续要求显式 `EXPECTED_SHA` 锁定提交，不再指向旧的临时分支。

### v3.23.18 (2026-11-12)

- 云端移植加固：`cloud_cli.py` 的所有子命令超时会终止完整进程树（POSIX 进程组、Windows `taskkill /T`），超时统一返回 `124`，避免容器里残留采集或浏览器子进程。
- 增加 `DAILY_BRIEFING_PREFLIGHT_TIMEOUT`、`DAILY_BRIEFING_COLLECT_TIMEOUT`、`DAILY_BRIEFING_BUILD_TIMEOUT`、`DAILY_BRIEFING_PROBE_TIMEOUT`、`DAILY_BRIEFING_RUN_TIMEOUT`，默认值与云端入口文档一致。
- 个股和行业采集统一规范化证券名称：去除厂商返回的空格并做 NFKC 全半角归一（如 `万  科Ａ` → `万科A`），避免报告门禁把真实标的误判为缺失。
- 个股报告在无机构研报样本时不再输出空表，改为明确的“本次采集未返回可核验的机构研报样本”边界说明；`stock-report 000002`、机器人行业报告已通过门禁。
- 扶摇云端 `sector` 增加指数快照字段（价格、涨跌幅、成交量/额、开高低收），并对快照缺失返回显式 `snapshot_error`；新增板块、名称规范化和报告空表回归测试。

### v3.23.17 (2026-11-05)

- 修复 Codex 语义总结超时后只结束启动壳、未结束子进程的问题：现在按进程树整体终止，继承的管道不会再让采集任务一直挂到外层 900 秒超时。
- 语义总结曾将默认推理档从 `max` 调整为 `low`；该本机 Codex CLI 路径已在后续版本整体移除。
- 语义批次改为默认 4 路受控并发（`DAILY_BRIEFING_SEMANTIC_WORKERS`，范围 1–6），并让编译阶段复用采集阶段已缓存的研报逻辑，避免 299 篇研报在采集和编译各算一遍。
- 新增进程树终止、推理档校验及命令行参数测试，确保超时失败快速收敛且不输出源代码或凭据。

### v3.23.16 (2026-11-05)

- 行业轮动行情新增同花顺官方指数接口兜底：当 AKShare 的同花顺行业指数尚未更新到目标交易日时，逐行业改用 `hithink-finance index history` 核验并补入官方日线；沪深300基准同样支持回退。只有目标交易日、收盘价和全部模型列都有效才合并，避免把上一交易日冒充当日。
- 修复云端模型输入缺口的真实原因：同花顺行业指数在收盘后一段时间仍停留在前一交易日，原逻辑直接报错；现在本地和云端都能使用同一官方来源补齐，且保留 AKShare 为首选源。
- Codex 语义总结子进程使用 `--ignore-user-config`，不再加载用户 MCP/插件和无关配置；仍保留 Codex 登录态，避免摘要任务被工具初始化拖慢或尝试调用工具。
- 新增行业/基准回退与载荷映射测试；全量测试 137 项通过。

### v3.23.15 (2026-11-05)

- 云端一致性：干净安装按“缺失才补”自动获得情绪面板、节点/轮动历史和 AI 缓存基线，已有云端数据优先保留；不再从空面板起步，也不把 `*_today.json`、Cookie 和登录态带进新环境。
- 随包行业轮动模型：新增 `data/cloud-baseline/models/sw_rotation_model.zip`，没有显式模型时自动解压到可写缓存；修复插件根 `models/sw_rotation_model` 的路径识别。原模型目录未随市场包分发且本地已丢失，本版按原始配置与 38 个特征重建，2026-10-19 快照回归为 T+5 前15 重合 8/15、共同名称分数 Spearman 0.50、近端 T+5 RankIC 0.0638；详见模型内 `RECONSTRUCTED.md`。
- 云端依赖补齐 `scikit-learn` 与 `scipy`，运行前预检同步检查；避免“模型目录有了但 import 失败”。
- 预检加固：面板必须包含 22 个 v3.2 模型列；轮动/节点历史 JSON 必须有效；Whisper 权重必须真实存在；Chromium 必须能启动；AI Key 通过服务端认证探测；模型必须包含 `src/` 源码和三份原始行情输入。坏文件、缺列或缺依赖在采集前阻断。
- 本地与云端现在使用同一份模型压缩包和同一份输入；干净安装验收中 2026-10-19 的 `all_scores` 与本地模型逐字节一致。

### v3.23.14 (2026-11-05)

- 保留已发布的 `market-query` 1.1.0 扶摇云行情与自选分组能力；本版只叠加每日简报的云端一致性修复，不覆盖行情技能更新。
- 新增运行前预检：模型、历史面板、AI、抖音转录路径（本地 Whisper 或 API Key）、平台 Cookie、同花顺 CLI、行情日期和可写目录一次性检查；普通运行缺必选项时在采集前阻断，`--preflight-only` 可单独查看结构化结果。
- `--resume` 在编译前复用逐模块完整性校验，缺日期数据、未完成转录或未核验来源时直接阻断，不再等到 HTML 编译阶段才发现。
- 行业轮动模型改为环境变量和插件内 `models/sw_rotation_model` 的确定性路径，不再扫描整个 `D:\Codex`；云端使用可写模型工作卷，缺少原始模型时明确失败而不是拿旧排行结果重画。
- 持久数据迁移和云端种子共用同一长期文件白名单，只同步面板、节点/轮动历史、AI缓存、转录缓存和行情缓存；`*_today.json`、Cookie、登录态和临时交付文件不再进入干净云端目录。
- 修正 Compose Cookie secret 的目标文件名，使 `/run/secrets/*.json` 与实际读取路径一致；新增 `seed-data.ps1`、模型卷和云端预检说明。

### v3.23.11 (2026-10-14)

- 完整简报必须完成抖音转录，移除跳过采集和跳过完整性检查的路径。
- 日报默认指定本机 Whisper（small、中文），串行处理并限制 CPU 线程，Luna/max 继续负责观点语义提炼。
- 每日23:00任务恢复完整转录；转录失败明确报错，不能交付缺失抖音观点的成功简报。

### v3.23.10 (2026-10-14)

- 语义总结历史版本曾支持已登录 Codex CLI；该本机方案已在后续版本移除，现仅支持 API。
- 行业轮动更新全部 90 行业及基准，补齐指数采集、逐模块完整性检查和来源核验。
- 抖音详情按视频 ID 解析，默认串行转录；完整批次转录仍须实际验收。
- 报刊版保留完整板块、数据行及图标，交付前验收桌面与手机版式。

### v3.23.7 (2026-09-24)
- 统一编排器与HTML编译器的交易日算法，凌晨 5 点前对当天目标日一致回退。
- 编译器缺失、执行失败或未产出有效HTML时明确返回失败，不再报成功。
- 运行数据迁至跨版本持久目录；淘股吧摘要缓存按目标日、来源和原文校验，旧版无日期缓存不再误用。
- 将“无明确观点”作为有效的中性AI结论；抖音AI失败时继续保留标题/话题线索兜底。

### v3.23.1 (2026-09-23)
- **龙虎榜与板块轮动改为左右并列**：这两个板块不再各自拆成左右两半，而是作为一对栏目左右并列（龙虎榜在左、板块轮动在右），各自保留一张整表；列宽由 `.tbl-lhb` / `.tbl-rot` 百分比固定，渲染器新增 `single_table()` 只加类名、不拆栏。机构研报仍按条目对半拆栏
- 两张新闻表（财经科技新闻 / 自选股新闻）的来源列改为不折行，避免字号加大后 4 字来源被折成两行
- 龙虎榜条目多，单独收紧行距与内边距（`line-height:1.45`、`td` 上下 2px、小标题与口径框同步收紧），整块高度约降 20%，板块轮动不改

### v3.23 (2026-09-23)
- **报刊风模板固化进 Skill**：把"纸感报刊版"从一次性样板变成 Skill 内的固定模板，不再每天重画
  - 新增 `scripts/build_broadsheet.py`：把当日简报 HTML 重排为报刊版（报头 → 金句 → 四指数条 → 头版导读 + 阶段柱状图 → 节点票时间轴 → 长表两栏 → 报脚），支持 `--src/--out/--date/--dir`，默认自动取输出目录里日期最新的简报，输出 `YYYY-MM-DD简报-报刊版.html`
  - 新增 `templates/broadsheet.css`：报刊版全部样式外置为资产（配色、字体、纸张纹理占位符），改纸感/配色只动这一个文件
  - 新增 `scripts/verify_broadsheet.py`：期望值从源简报自动推导（板块数、数据行数），核对图标渲染与横向溢出，输出 1440/390 截图与 4 段切片；未通过不得交付
  - 纸张质感：细颗粒 + 纸浆斑纹 + 淡帘纹三层内嵌 data URI 纹理 + 光感渐变 + 纸边阴影，整页乘算叠印，打印自动去纹理
  - 通栏长表固定按行对半拆左右两栏（表头每栏重复、列宽百分比对齐）：龙虎榜买入侧/卖出侧+游资、板块轮动按名次、机构研报按条目；榜末口径与信号行保持通栏
  - 板式规则、图标映射（`ICONS`）、顺序与移动端单栏规则写入 SKILL.md 固定口径；frontmatter 增补 `beautifulsoup4` 依赖
  - 验收：skill 版渲染结果与原样板逐行比对仅剩标题/页眉/页脚文案差异；1440 与 390 两档截图复检 11 板块、125 数据行、12 图标全渲染、零横向溢出

### v3.22 (2026-09-22)
- **报刊质感精修层（用户反馈"整体质感不够好"）**：在报刊主题末尾追加纯纸墨语言精修层（`templates/briefing.html`），不改 DOM 结构、不改数据口径
  - 纸面去杂：去掉 1px/4px 条纹叠印与红蓝双色晕染，只保留顶部一点暖光晕
  - 卡片改细墨线：去掉全部卡片的 2px 黑顶边与硬边框，统一 1px 墨线 + 4px 圆角，悬停才出现轻投影（印刷语言：线承重，不堆阴影）
  - 指数卡按涨跌方向给 2px 顶线（涨红/跌绿，有含义的方向编码），字阶与内边距收紧填满卡面
  - 小徽章从全饱和描边铅字章改为低饱和色底 + 同色细边；表格行距统一 9px、末行去线、悬停更轻
  - 信号/共识框去 3px 侧条，改印章色浅底；策略三卡按方向染纸；多空圆环去霓虹光晕；金句报眼保留双线、细化字阶
  - 补浏览器自带面：`::selection` 与 `:focus-visible` 归入纸墨体系
  - 页脚版本号同步 v3.22；验收：1440/390 两档横向溢出均为 0，首屏/节点票/策略卡/金句截图核对通过（`报告\_验收截图\2026-09-21\`）

### v3.21.3 (2026-09-22)
- **交付链接改为 Markdown 绝对路径**：Codex 桌面端不渲染裸 HTML，`<a href="file:///...">` 金色按钮会原样显示成标签源码、用户点不动（用户 09-22 截图反馈）。交付规则改为输出 `[📄 打开 M 月 D 日简报](D:/MyProjects/股票分析/报告/每日简报/YYYY-MM-DD简报.html)`，不得再用 `file:///` URL 编码或内联 `<a>` 标签
- **已有报告也要给链接**：非交易日、抓取窗口不合适而主动跳过、门禁失败等未生成新报告的情况下，仍必须把输出目录里最近一份报告的可点击链接发出来

### v3.21.2 (2026-09-21)
- **节点时间轴行序＝周期跨度降序（用户口径）**：连板段（实心）＋断板后二波延续段（虚线）总长度最长的票地位最高，必须出现在最上面一行
  - `node_cycle_model.py` 给每个节点挂 `board_span_days` / `total_span_days`，输出顺序改成跨度降序（跨度并列再比连板高度、启动日），`evidence_note` 写明行序口径
  - `build_node_cycle.py` 第一趟探测改用 `build_node_model(..., keep_all_smalls=True)`，让每个候选都拿到日线核验跨度；`cycle_spans` 增加名称兜底键，避免第二趟换人时 `total_span_days` 退回纯连板天数（此前 新赛股份 出现 2 vs 3 的口径分裂）
  - `build_briefing.py` 渲染层改为「按跨度从长到短依次占位、落在第一行不与已有条形重叠的位置」，取代原来的"按 lane 分组、层内按左边界"排法；父节点未落位时子节点顺延，保证小节点永远在大节点下方。同日实测由 9 行压到 8 行，行首跨度 15→13→8→6→5→5→5→3 单调递减
  - 悬停标题补 `周期跨度 N 个交易日（连板 X＋二波延续 Y）`，行序依据可直接核对
  - 新增 4 项回归测试（跨度最长者置顶且为大节点、无日线时退回连板口径、渲染层最长条形在第一行、子节点不越过父节点），共 9 项通过

### v3.21.1 (2026-09-21)
- 节点模块固定展示最近1个月，并在每日编译前回补缺失交易日连板历史。

### v3.21.0 (2026-09-21)
- 新增“大小周期节点票”模块与节点模型 V1.0：滚动保留近1个月关键连板快照，按真实交易日期定位条形，同日票共享横坐标并纵向堆叠。
- 固化大/小节点筛选、穿越/观察排除、周期归属和证据等级；接入 `run_all.py` 正常生成流程。
- 沿用简报卡片、字体、颜色、表格和间距体系，增加示例渲染脚本与回归测试。

### v3.20.2 (2026-09-16)
- **阶段配色改为同一色系的深浅（用户要求：不要五颜六色）**：六阶段不再各占一个色相，统一用**报刊主色红**的六级明度阶梯，只靠深浅区分
  - 冰点 `#f0d0c2`（明度 85%）→ 退潮 `#e3a68f`（73%）→ 降温 `#d47a5f`（60%）→ 修复 `#bf4a32`（47%）→ 升温 `#9d2318`（36%）→ 高潮 `#76140d`（26%），色相 4°～18° 保持同一红系
  - 柱子加 1px 墨色细边，避免最浅的「冰点」柱在纸面上边界发虚
  - 新增断言 `test_phase_palette_is_single_hue_ramp`：色相极差 < 0.05 且明度必须「冰点最浅 → 高潮最深」，防止以后又改回多色相

### v3.20.1 (2026-09-16)
- **温度图折线改柱状（用户要求）**：头版「市场温度 · S」图由折线改成**阶段柱状图**，每根柱子按当日情绪阶段上色，标题改为「市场温度 · 阶段柱状（近N个交易日）」
  - 阶段配色（初版为六色相：冰点蓝/退潮青/降温橄榄/修复琥珀/升温朱红/高潮深红；**v3.20.2 已按用户要求改为同一红色系的深浅**）
  - 图表下方新增 `.chart-legend` 图例，**只列出当期真实出现过的阶段**（阶段来自 `cycle_label`，不猜、不补），按六阶段固定顺序排列
  - 柱子从 0 基线起画，y 轴 0/50/100 全部可见（旧折线实现的 `yS(0)` 落到画布外，0 刻度其实一直没显示出来）；悬停改成高亮该柱并提示「日期 · 数值 · 阶段」，tooltip 定位补上 canvas 偏移量，不再偏 20px
  - 窄屏（step < 26px）自动隔一显示日期标签，避免 14 个日期挤成一团
- **修阶段判定 bug**：`cycle_label` 形如「降温｜退潮加速」「退潮｜下跌收敛/退潮衰竭」，动能词里也含「退潮」，原先整串匹配会把「降温」误判成「退潮」。现在只取分隔符（`｜`/`|`/`（`）前的片段再匹配
- **新增测试**（`work/test_daily_briefing_integrity.py`）：阶段解析（含动能词干扰）、六阶段配色唯一性、柱状绘制断言（有 `fillRect`、无折线节点 `arc`），并把模板字面量↔编译器替换的一致性检查更新到新标题；共 41 项通过
- **像素级验证**：逐柱采样渲染结果，14 根柱子颜色与数据源 `cycle_label` 阶段**逐条一致**

### v3.20.0 (2026-09-16)
- **整站改为报刊风格（用户要求）**：暗黑主题 → 纸面米白（`--paper:#f5f1e8`）+ 油墨黑（`--ink:#1b1915`），正文/标题统一宋体系衬线栈（Noto Serif SC → 思源宋体 → 宋体），西文数字回落 Georgia；去掉玻璃拟态与发光效果，改为细线分隔、单线方框徽标（「铅字章」）、引语横幅上下粗线
  - 实现方式：`templates/briefing.html` 末尾追加「报刊风格主题」覆盖层，**不删除、不改名任何既有类名**（`.sec/.sh/table/.tb/.t2/.t3/徽标/survey-*/strat/quote-*` 全部沿用），所有板块自动继承同一套报纸语言
  - 新增报头 `.np-mast*`（英文刊头 + 报名「每日简报」+ 日期/数据日/板块数/模型版本信息行），由 `build_briefing.py` 注入，板块数为真实渲染数量而非写死
- **正文改左右两栏**：`.g` 由 `auto-fill` 自适应改为固定两列（1440px 下 675px × 2），中缝 26px 加一条竖细线（`.g::before`），`align-items:start` 保留各板块自然高度；`fw` 段（机构研报、抖音）横跨两栏；≤960px 降为单栏
  - 板块轮动从整宽改为落入右栏（与龙虎榜同排），消除「右栏空白」的排版空洞；移动端仍为单栏
- **折线图配色随主题调整**：网格 `rgba(255,255,255,.04)` → `rgba(27,25,21,.09)`、轴标签 → `rgba(27,25,21,.45)`、主线 `#E74C3C` → `#b3261e`、悬停竖线/光晕同步改深红、tooltip 改纸色底 + 细边框；页脚与 `<title>` 由 DailyPulse 改为「每日简报」，并补一行「数据仅为信息整理，不构成投资建议」
- **验证**：10 个板块、各板块条数（15/15/57/15/20/41/4/6）与改版前一致；桌面 1440px 两列 675px×2、无横向溢出；390px 单栏无溢出；39 项测试通过

### v3.20.0 (2026-09-16)
- **龙虎榜换主源：同花顺官方（hithink-finance），AkShare 降级兜底**。`fetch_longhubang.py` 的 `main()` 先走 `collect_hithink()`，失败或未装 CLI 时回退原来的 `collect_akshare()`，输出结构（`lhb_today.json`）完全不变，简报模板零改动
  - 同花顺 `special dragon-tiger` 一次给全个股榜、机构榜（含买卖机构家数）、游资派系榜（派系名/净额/涉及个股），不再需要逐股抓 15 次营业部席位
  - **实测对齐**：2026-09-16 净买入 TOP5（10.15 / 9.14 / 7.06 / 4.57 / 3.33 亿）与机构净买 TOP5（2.53 / 2.06 / 1.15 / 0.92 / 0.81 亿）与东方财富（AkShare）**完全一致**；耗时从约 14 秒降到约 5 秒
  - `source` 字段写明实际来源，"游资席位"组件名改为"游资派系"，缺数据时 `note` 照实说明
- **盘面补充改双源：同花顺官方给事实，连板网补它独有的字段**。`fetch_lianban.py` 拆成 `collect_hithink()` + `collect_lianban()` + `merge_sources()`，产物仍是 `data/lianban_today.json`
  - 同花顺负责：涨停/跌停/炸板家数、封板率、炸板率、最高板与次高板、连板家数、涨跌家数、两市成交、当日主线（按涨停原因归并）、总龙头。**支持历史交易日回填**（`--date` 任意在过去一年内的交易日）
  - 连板网负责：63 日新高新低、融资余额、主力资金流、AI 复盘、次日观察名单。Playwright 失败时这些字段降级留空，同花顺那部分照常出，不再"整块停用"
  - **⛔ 温度只有一个来源**：连板网自带的"情绪温度/情绪周期"在合并阶段直接丢弃，不再进入结果 JSON
  - 温度卡标签从写死的"盘面补充（连板网）"改为按 `source` 渲染（同花顺官方／同花顺官方+连板网／连板网）
  - **实测对齐**（2026-09-16）：涨停 89、跌停 4、炸板 11、封板率 89%、炸板率 11%、连板 12 家、最高板 6、涨 4170 / 跌 1189 家、两市成交 1.84 万亿，与连板网逐项一致；09-15 涨停 32 / 跌停 27 与本 Skill v3.17.0 记录的当日值一致
  - **停牌股必须剔除**：全市场快照 5573 只含 23 只停牌，停牌股 `last_price=0` 且 `price_change` 为负，不剔除会被计入下跌家数（1212 → 1189，正好差这 23 只）
  - 新增环境变量 `BRIEFING_LIANBAN_SUPPLEMENT=0` 可只跑同花顺、跳过 Playwright（约 10 秒）
- 新增 `scripts/_hithink.py`：同花顺 CLI 的统一封装（交易日历、池子分页、梯队统计、全市场广度、两市成交），供上面两个脚本共用

### v3.19.1 (2026-09-16)
- **修「板块轮动」窄屏排版**：≤600px 时该表启用 `.rot-tbl` 专属压缩（列宽自适应、字号/内边距收紧、徽标不再撑宽），6 列（排名/板块/T+5分数/T+3排名/周期/变动）在 360～430px 宽度下全部可见，不再依赖卡片横向滚动；桌面端排版未变（表宽仍 1374px）
- **修指数卡片坏值**：`fetch_index_data` 的取数增加有效性校验，剔除数据源里 close ≤ 0 / 非数字的行（KOSPI 曾把最新一行写成 0，被渲染成「0 ▼100.00%」）。校验后 KOSPI 取到真实收盘价与日期；若整段序列都无效，则按取数失败处理，卡片显示「数据获取失败」而不是编造行情

### v3.19.0 (2026-09-15)
- **新增板块「板块轮动」**：接入用户的**行业轮动模型 v2.0.0**（`Industry Rotation Core`，横截面排序模型，默认标的池为同花顺行业指数 90 板块，主周期 T+5、取前 15），渲染在龙虎榜之后、机构研报之前的整宽版面
  - 新增 `scripts/fetch_rotation.py`：调模型的 `run.py predict --asof {date}` → 读 `outputs/all_scores_{date}.csv` 与 `predict_manifest_{date}.json` → 转成 `data/rotation_today.json`。**不改模型代码、不改模型参数、不覆盖模型产物**
  - 模型目录按 `ROTATION_MODEL_DIR` 环境变量查找，未设置时使用内置候选路径并在 `D:\Codex\*\*\outputs\sw_rotation_model` 兜底扫描；找不到时该板块如实显示“数据获取失败”，不编造排行
  - 版面内容：表头（15个板块 · T+5 · 数据日）、KPI 条（短周期共振 n/15、本期新进、本期跌出）、排行表（排名/板块/T+5分数/T+3排名/周期共振/变动）、口径说明
  - 「短周期共振」= 该板块同时进入 T+3 与 T+5 的前 K，说明短周期与主周期同向；「新进/跌出」由 `data/rotation_history.json` 的上一期快照对比得出，首次运行标注「首次」而不是编造变化
  - **口径诚实**：模型只给行业相对排序，分数不是上涨概率；T+1 换手成本过高不可用，按 T+3/T+5 周期调仓。这些都写在板块的口径行里
- **前端风格统一**：板块沿用简报既有的暗色设计系统（`.sec` / `.sh` / `table` / `.tb/.t2/.t3/.tr` / 徽标类），只新增 `.rot-head/.rot-kpi/.rot-note` 组用于报刊式排行刊头，未引入任何外部样式或独立主题

### v3.18.0 (2026-09-15)
- **接入连板网（lianban.net）作为现有板块的补充数据源**，新增 `scripts/fetch_lianban.py`，取的是公开无需登录的几类数据：
  - 概况：涨停/跌停（含昨日对比）、连板家数、最高板、封板率、炸板率、昨涨停今表现（均值+中位+翻红比例）、情绪周期、涨跌家数、63日新高/新低、两市成交、融资余额及其日变动
  - 当日主线：主线板块 + 涨停家数 + 板块龙头 + 驱动逻辑，以及总龙头
  - 资金：板块/概念/个股的主力净额（`live/zjflow.json`）
  - 次日观察名单与 AI 复盘正文（`summary/{date}.json`）
- **补充位置**：顶部温度卡新增一行「盘面补充（连板网）」（最高板/连板/封板率/炸板率/涨跌家数/两市成交/新高新低/融资余额）；策略卡「做多」加入当日主线与总龙头，「观察等待」加入次日观察名单
- **⛔ 温度只有一个来源（用户明确要求）**：市场温度始终由用户自己的「A股超短情绪温度模型 3.2」计算，连板网自带的“情绪温度/情绪周期”**既不参与计算、也不在简报中展示**，避免一个页面出现两个“温度”。卡片上只保留可核对的盘面事实统计
- **采集方式**：Playwright 无头渲染 `days/{date}.html` 后解析页面文本（概况与主线），再用同一页面的 request 上下文取 `live/zjflow.json` 与 `summary/{date}.json`；日期不匹配时整块停用，不混入其它交易日盘面
- 编排接入：`run_all.py` / `inline_runner.py` 的 Group A 增加 `fetch_lianban.py`（超时 180s，实测约 10s），产物 `data/lianban_today.json`

### v3.17.0 (2026-09-15)
- **市场温度补齐当天数据**：开盘啦对当日的日度聚合要收盘后很久才发布，原来只能回退到上一交易日。新增实时回退口径 `fetch_day_realtime()`，与开盘啦逐项对齐后才使用：
  - 涨停/跌停/炸板池（东方财富，经 AkShare）：09-14 涨停 55、跌停 16、炸板 30、首板 44、连板 11、空间 4、次高 3、炸板率 0.3529 与开盘啦**全等**；09-15 涨停 32、跌停 27 与开盘啦实时接口一致
  - 涨跌家数/成交额：`sina_snapshot()` 用本地全量代码表分批取新浪行情（5,205 只约 3.6 秒），广度比值与开盘啦同为 20.4%，成交额 16,027 亿 vs 开盘啦 16,127 亿（差 0.6%）
  - 昨涨停/昨连板今表现：前一日涨停池的今日收益**均值**（09-15 算得 +0.667%，开盘啦实时字段 0.5495%，口径一致）
  - 面板新增 `source` 列，实时补齐的行标 `realtime`，顶部卡片同步写明“当日用实时口径补齐（已与开盘啦逐项对齐）”
- **雪球多空统计真正打通**：原来裸 HTTP 与外部浏览器指纹都会被阿里云 WAF 拦成滑动验证页。新增 `scripts/fetch_xueqiu.py`：用 Playwright 打开 `xueqiu.com` 后，**复用同一页面的 request 上下文**请求 `/statuses/user_timeline.json`（注意 `/v4/...` 仍被拦）即可拿到真实 JSON。实测查询 50 位博主、28 位当日活跃、0 失败，多空统计从“仅淘股吧 14 位”变成两平台 41 位
- **研报核心逻辑不再拿标题充数**：新增 `ai_summarize_yanbao()` / `ai_summarize_yanbao_parallel()`，把研报标题+评级改写成「驱动因素→受益方向」的逻辑句，提示词硬约束“只能用给定字段、不得补充任何新事实”，无法生成时如实回到标题并标注「（原始报告标题）」。本次 20/20 篇均生成
- **停更账号给出确切日期**：淘股吧记录 `last_seen_date`（页面最新跟帖日），抖音新增 `probe_latest_video_date()`（桌面UA读主页最新发布时间）。九尾北极猫显示“账号最后跟帖 2026-07-21”，福总显示“账号最后发布 2026-08-07”，不再只是笼统的“目标日无可核验”

### v3.16.0 (2026-09-15)
- **市场温度改用用户的「A股超短情绪温度模型 3.2」**（`A-SHORT-SENTIMENT-3.2`），顶替原来的 11 参数线性公式：
  - 新增 `scripts/sentiment_model_v32.py`：模型本体，与用户提供的 `reference_impl.py` 逐行一致（F/L/R/A/B/V → Q → J → S → 六阶段），不改权重、不改阈值
  - 新增 `scripts/market_temperature_v32.py`：把开盘啦收盘数据整理成模型输入面板，逐日增量写入 `data/sentiment_panel_v32.csv`，输出仍写 `data/panic_today.json`
  - `scripts/panic_greed_index_enhanced.py` 改为薄转发入口，`run_all.py` / `inline_runner.py` 的调度与文件映射保持不变
  - 面板首次构建回补 400 个交易日（2025-01 起）；`run_all.py` 中该脚本超时从 60s 提到 1200s，避免首次回补被误杀
  - 旧版 11 因子模块 `market_temperature.py` 保留在磁盘但已停用
- **顶部卡片改为模型驱动**：`render_sentiment_summary()` 支持 `factor_display`，显示 赚钱反馈F/连板生态L/风险质量R/进攻扩散A/市场广度B/量能确认V/基础强度Q/接缝J 与牛熊环境；无 `factor_display` 时回退旧 11 因子渲染
- **晋级率按定义推算**：1进2=当日2板/昨日首板，2进3=当日3板/昨日2板，3板以上=当日4板以上/昨日3板及以上；分母<3 沿用前值（README 17.9），避免小样本放大噪声
- **折线图数据源同步**：`sentiment_history.json` 现在写模型 3.2 的 S 序列，与顶部卡片同源
- **依赖补齐**：`requirements.txt` 补 akshare / pandas / numpy / openai-whisper

### v3.15.0 (2026-09-15)
- **自选股新闻换成个股口径**：原实现只在东方财富通用快讯里匹配股票代码，实测 22 只自选股常年 0 条。现改为逐只调用 `ak.stock_news_em`（东方财富个股新闻/公告），保留目标日前 3 天窗口，表格补回 `时间` 列；单只接口失败会在 `note` 里列出失败代码，不再静默算作“无新闻”
- **未来大事件改用真正的财经日历接口**：原实现从会滚动的快讯流里正则抽取日期，晚上运行时条目已滚走、板块长期只显示“暂无”。现直接调用东方财富财经日历报表接口 `RPT_CPH_FECALENDAR`（`data.eastmoney.com/cjrl/` 的数据源），窗口 14 天，**单日最多取 3 条、总量 20 条**，同一天优先保留带利率/CPI/LPR/美联储等关键词的重要事件，避免整表被同一天的数据发布填满
- **策略卡不再贴博主口语原文**：`build_strategy_items()` 的“风险提示”改为只引用已经过 AI 语义总结的淘股吧结论句子，无可用摘要时给出明确空状态；“做多”不再要求新闻必须带股票代码，利好新闻标题可直接入选
- **数据完整性测试扩充**：`work/test_daily_briefing_integrity.py` 新增未来事件窗口过滤、日历查询区间、自选股单只失败留痕、AkShare 列规范化等用例，共 19 项

### v3.14.0 (2026-09-15)
- **移除 Serenity 板块**（按用户要求）：`serenitysaid.com` 长期返回 HTTP 521，板块每天只能显示"数据获取失败"，已从 `run_all.py` 的 Group A 和 `build_briefing.py` 的渲染层整块摘除，板块总数 12 → 11
  - `scripts/fetch_serenity.py` 与 `serenity_crawler.py` 文件保留在磁盘上，需要恢复时重新挂回 Group A 与渲染层即可
  - `templates/briefing.html` 的 Serenity 示例块同步删除

### v3.13.0 (2026-09-14)
- **凭证移出 Skill 目录**：删除 `run_all.py`/`inline_runner.py`/`win_launcher.py` 中写死的讯飞MaaS密钥（Skill 会同步到 OneDrive，源码存密钥等于外泄），改由 `scripts/env_config.py` 读取 `~/.codex/daily-briefing.env`；系统环境变量优先，文件只作兜底
- **所有入口统一加载凭证**：`run_all.py`、`build_briefing.py`、`fetch_douyin.py`、`fetch_serenity.py`、`analyze_douyin.py` 均显式导入 `env_config`，避免直接运行主脚本时"读不到凭证却静默降级"
- **编译门禁收紧**（取代 v3.12 的"淘股吧和抖音至少一个有数据即可编译"）：淘股吧与抖音都必须有目标日可核验内容；淘股吧内容还必须拿到 AI 语义摘要，否则阻断编译，不输出把原始口语当结论的简报
- **名言数据失败状态**：`pick_quote.py` 失败只显示"每日金句数据获取失败"，不再回退默认名言
- **日期口径统一**：快讯、研报、未来大事件、自选股、Serenity 均按目标日期过滤，越界或缺失一律标注失败原因，禁止用其它日期内容补齐
- **过期缓存不再被渲染**：列表类板块（新闻/自选股/龙虎榜/Serenity/多空统计/淘股吧/抖音/大事件/研报）只有数据日期对得上时才渲染条目，否则整段降级为"数据获取失败"，不再出现"标题写失败、下面列旧条目"的画面
- **修复 KOSPI 长期取不到数**：新浪环球指数里韩国指数登记名是「首尔综合指数」，原代码用的 `KOSPI` 不存在且异常被 `except: pass` 吞掉；现在改为按名称回退并记录失败原因
- **指数口径统一**：四家指数都取"最近一个已收盘交易日"，盘中不会把未完成的当日行情当收盘价展示；各指数数据日期不同时逐项标注
- **AI 凭证失效快速失败**：401/403 不再逐个博主/视频重试 3 次（一次编译从 23 秒降到 4 秒），并把修复路径直接写进报错

### v3.11.0 (2026-07-29)
- **内置讯飞MaaS API默认配置**：`run_all.py` 启动时自动注入 `DEEPSEEK_API_KEY`/`DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL`，AI总结开箱即用无需手动配置
  - `DEEPSEEK_API_KEY` 从必配项降级为可选（用户可通过环境变量覆盖为自己的API）
- **修复抖音0条视频核心bug**（3处修复）：
  - 修复 `iesdouyin.com` 域名判断拼写错误（原写 `iedsdouyin.com` 少了个`o`），导致口罩哥sec_uid解析失败
  - 修复 `fill_create_times()` 使用httpx直接请求抖音详情页被反爬拦截返回空页（2492字节），改用Playwright浏览器渲染提取create_time
  - 修复 `fill_create_times()` 签名变更后调用处未传入 `browser` 参数导致TypeError
- **抖音博主配置改为sec_uid直传**：`DEFAULT_BLOGGERS` 从短链URL改为直接使用sec_uid，避免短链解析失败
- **`fetch_douyin.py` AI总结支持自定义API**：`summarize_with_deepseek()` 从硬编码 `api.deepseek.com` 改为读取 `DEEPSEEK_BASE_URL`/`DEEPSEEK_MODEL` 环境变量
- **`build_briefing.py` 默认API改为讯飞MaaS**：`DEEPSEEK_BASE_URL` 默认值从 `api.deepseek.com` 改为讯飞MaaS

### v3.12.0 (2026-09-13)
- **顶部情绪指数统一为市场温度公式**：使用空间、次高、涨停、跌停、首板、连板、炸板率、成交量、红盘数、昨连板、昨涨停 11 个参数，并计算 Δ1/Δ2 与完整周期。
- **数据完整性门禁**：所有板块写入来源、数据日期、状态和失败原因；淘股吧与抖音任一核心源无可核验数据时阻断正式HTML交付。
- **去除虚构兜底**：指数、每日金句、未来事件、空结果日期和博主原始转录不再以样例、默认值或推算文本冒充真实数据。

### v3.13.0 (2026-09-14)
- **修复抖音当前页面解析**：旧 `iesdouyin.com` HTTP 结构缺少 `videoInfoRes` 时，改用 Playwright 解析当前 SSR/媒体页面，并支持移动验证码页回退到桌面公开页。
- **修复抖音下载与时间核验**：Windows curl 增加 Schannel 吊销检查兼容；详情页可从 SSR `create_time` 或可见“发布时间”核验日期；列表接口若提供 `create_time` 也直接复用。
- **修复转录状态与兜底**：本地 Whisper 参数统一为 `local`；转录失败保持 `partial` 而不是被覆盖为 success；无 AI 时 HTML 展示明确来源的真实转录摘录，避免空白或伪造摘要。

### v3.10.0 (2026-07-26)
- **修复抖音周末回退0条bug**（3个严重bug）：
  - 移除错误的预检早退逻辑（`min_cursor` 是API分页游标而非视频发布时间，周末运行时误判"非今日"直接返回空列表）
  - 移除错误的 `create_time` 赋值（用 `min_cursor_ms` 当视频发布时间完全错误）
  - 在主流程中调用 `fill_create_times()` 通过详情页并发获取每个视频的真实 `create_time`
  - 调整早退逻辑：`min_cursor` 日期早于目标日期时才早退（说明已翻过目标日期的视频）
- **新增抖音日期回退机制**：指定日期无视频时，自动向前搜索1天（周末/节假日场景）
- **新增淘股吧日期回退机制**：指定日期0条时，自动向前搜索1天，确保周末不空
- **放宽必选校验**：淘股吧和抖音至少一个有数据即可继续编译，两者都为空才报错
- **博主观点总结规则强化**：
  - AI总结成为唯一输出路径，删除正则提取和原文截断兜底
  - AI失败时重试最多3次，仍失败则标记 `[AI总结失败-xxx]` 而非输出原文
  - `DEEPSEEK_API_KEY` 从可选升级为必配项
- **SKILL.md规则6放宽**：从"不可能没有数据→必须报错"改为"自动回退1天+回退后仍空才报错"

### v3.8.0 (2026-07-14)
- **博主多空统计板块**：新增 ⑤½ 板块，自动统计雪球+淘股吧各50个核验账号样本的当日观点
  - 新增 `scripts/fetch_sentiment_survey.py`：爬取50个TGB博主帖子 + 读取雪球数据 + 关键词规则分析观点方向
  - 输出JSON写入 `data/sentiment_survey_today.json`
  - HTML板块包含：大盘观点表、板块观点表、平台对比表、核心结论
  - Group B新增第3个并行脚本，max_workers=3

### v3.7.0 (2026-07-13)
- **一体化编排脚本**：新增 `scripts/run_all.py`，替换原来的手动5步编排
  - 自动检测最近交易日（凌晨/周末自动回退）
  - Group A（6快速脚本）并行 → Group B（淘股吧+抖音+多空统计）并行 → 编译HTML
  - 所有子脚本输出写入 `data/` 目录JSON文件，避免stdout解析问题
  - 必选模块校验（淘股吧回复>0，抖音有视频）
- **通用编译器**：改造 `scripts/build_briefing.py`
  - 接受 `--date` 参数
  - 从 `data/` 目录读取所有JSON数据
  - 实时获取指数数据（上证/科创50/纳斯达克/KOSPI）
  - 自动生成情绪折线图数据
  - 自动生成策略板块内容
- **抖音浏览器复用**：`fetch_douyin.py` 优化
  - 所有博主共享1个Playwright浏览器实例（节省~30s/博主）
  - 早退机制：滚动时检测到非今日数据立即停止（节省~15s/博主）
  - 支持 `--date` 参数
- **统一日期参数**：所有6个脚本新增 `--date YYYY-MM-DD` 支持
  - `panic_greed_index_enhanced.py`、`fetch_news.py`、`fetch_selfstock_news.py`
  - `fetch_future_events.py`、`serenity_crawler.py`、`pick_quote.py`
	- **SKILL.md执行流程简化**：从5步手动编排 → 2步自动执行（环境检查 + `run_all.py`）
- **删除微信公众号板块**：脚本`fetch_wechat_article.py`已不存在，`run_all.py`/`build_briefing.py`无集成代码，板块实际已废弃，正式从文档和数据中清理
	- 删除数据源表格中⑧微信公众号行，板块编号重排（⑨→⑧，⑩→⑨，⑪→⑩）
	- 删除`data/wechat_articles.json`和`data/wechat_mp_cache.json`缓存文件
	- 板块总数从11个减至10个
- **预估总耗时**：从5-8分钟降至3-4分钟（提速40-50%）

### v3.6.0 (2026-07-13)
- **新增每日一句板块**：每日简报加入投资名言横幅
  - 新增 `scripts/pick_quote.py`：从72条名言库随机选取，自动去重，用完重置
  - 新增 `data/investment_quotes.json`：72条经典投资格言（巴菲特、芒格、格雷厄姆、段永平等）
  - 新增 `data/used_quotes.json`：已用ID追踪（自动维护）
  - HTML模板新增 `.quote-banner` 样式区块，Hero下方金色渐变横幅设计
	  - 板块总数从9个增至10个（⑩ 每日一句）
  - 执行流程：Step 1 Group A 并行执行 `<1秒`

### v3.5.4 (2026-07-08)
- **抖音只取今日 + 并发转录**：`fetch_douyin.py` 升级为 v3.5.4
  - **只抓取今日发布的视频**，按北京时间（UTC+8）过滤 `create_time`
  - **并发转录**：默认最多 3 条视频同时转录，避免本地 Whisper 资源耗尽；支持 `DOUYIN_MAX_CONCURRENT` 调整
  - 抓取全部今日视频，不再做 topN 截断
  - 转录失败/为空时，自动使用视频标题+话题标签兜底
  - 标的/板块关键词库大幅扩展（半导体、AI、机器人、港股、美股科技等）
  - 新增 `warning` 字段标注哪些视频使用了兜底摘要
  - 支持环境变量 `DOUYIN_BLOGGERS_EXTRA` 追加抖音博主

### v3.5.3 (2026-07-08)
- **抖音不限制视频数量**：`fetch_douyin.py` 升级为 v3.5.3
  - 抓取博主主页全部视频，不再做 topN 截断
  - 转录失败/为空时，自动使用视频标题+话题标签兜底

### v3.5.2 (2026-07-08)
- **修复抖音信息遗漏**：`fetch_douyin.py` 升级为 v3.5.2
  - 每位博主默认抓取前3条最热视频（原2条），单入口候选数提升至2条
  - 转录失败/为空时，自动使用视频标题+话题标签兜底
  - 转录流程改为：`auto` 失败后自动尝试 `whisper` 本地兜底
  - 标的/板块关键词库大幅扩展

### v3.5.1 (2026-07-08)
- **⛔ 淘股吧和抖音改为必选板块**：获取不到数据必须报错停止，禁止跳过、禁止填"无数据"、禁止提前输出简报后再补数据
- **删除快速模式**：不再支持跳过淘股吧/抖音的快速模式，所有板块统一完整模式
- **淘股吧爬虫重写**：`tgb_crawl.py` 从Playwright改为urllib HTTP+Cookie方式
  - 根因：Playwright `add_cookies()` 注入的Cookie与淘股吧认证不兼容，导致moreTopic/moreReplyMod页面跳转登录页
  - 新方案：用 `Cookie: name=value; ...` HTTP header直接传递，绕过浏览器Cookie注入问题
  - 解析moreReplyMod的 `<div class="blogReply">` HTML结构提取跟帖内容/赞数/来源帖子
  - 三源融合：moreReplyMod（主数据）+ moreTopic（主帖补充）+ 博客主页（公开精华帖）
  - 无需启动浏览器，速度更快更稳定
- **执行流程更新**：Group B（淘股吧+抖音+多空统计）必须成功后才能编译输出简报

### v3.5.0 (2026-07-08)
- **淘股吧和抖音改为必选板块**（详见v3.5.1）
- **执行流程更新**：Group B（淘股吧+抖音+多空统计）必须成功后才能编译输出简报

### v3.4.6 (2026-07-07)
- **抖音转录兜底方案**：`analyze_douyin.py` 默认 provider 从 `groq` 改为 `auto`
  - 未配置 SiliconFlow/Groq/OpenAI API Key 时自动降级到本地Whisper（`openai-whisper`）
  - SKILL.md 移除"缺少 SILICONFLOW_API_KEY 则跳过抖音"的逻辑，改为必须尝试本地转录
  - frontmatter 增加 `openai-whisper` 依赖，API Key 环境变量标记为可选

### v3.4.5 (2026-07-06)
- **全面禁用前端浏览器**：新增"前端浏览器零容忍"常规规则
  - 禁止 `mcp__plugin_playwright`、`present_files`、`powershell Start-Process`、`Bash start`
  - 所有数据源优先后台HTTP或headless脚本（无可见界面）
  - 淘股吧/抖音Playwright爬虫使用 `headless=True` 模式（可接受，无可见窗口）

### v3.4.4 (2026-07-06)
- **淘股吧板块优化**：去掉"更新"列，表格简化为`博主 | 核心观点 + 标的`两列
- 移除"只核大学生"博主，淘股吧关注博主精简为4位（东北玄、太阳的微笑、九尾北极猫、狼王行千里）
- 新增主帖/跟帖处理规则：无主帖时只总结跟帖内容，标注"当日无主帖，仅跟帖动态"
- 明确狼王行千里主页链接：`https://www.tgb.cn/blog/2747572`

### v3.4.3 (2026-07-06)
- **机构研报逻辑化**：每条研报观点必须包含看多/看空的核心逻辑（驱动因素→传导路径→受益标的），禁止只写结论不写逻辑
- 新增机构研报表格格式规范（正例/反例），新增常见错误检查项

### v3.4.2 (2026-07-06)
- **新增自选股新闻后台脚本** `scripts/fetch_selfstock_news.py`：读取同花顺自选股，后台请求东方财富快讯API筛选相关新闻，纯HTTP无浏览器
- **新增未来大事件后台脚本** `scripts/fetch_future_events.py`：后台请求东方财富财经日历API，获取未来14日重要宏观/经济事件，纯HTTP无浏览器
- **更新HTML生成器** `scripts/generate_briefing.py`：整合自选股新闻、未来大事件等板块，输出到 `D:\OneDrive\Codex\股票分析\Codex
eports\每日简报/每日简报_YYYY-MM-DD.html`
- **新增执行规则**：自选股新闻与未来大事件必须使用后台脚本获取，严禁打开浏览器或弹出窗口

### v3.4.1 (2026-07-06)
- **交付规则简化**：报告生成后只输出一个URL编码的Markdown文件链接到对话中，不再输出原始中文路径链接和绝对路径文本兜底
- **深色主题色板统一**：简报模板 CSS 变量调整为与行业分析/财报深色主题一致的配色（--bg #0b0f19 / --bg3 #0f172a / --t1 #f3f4f6 / 红涨绿跌等）

### v3.4.1b (2026-07-11)
- **交付方式升级为HTML内联按钮**：报告生成后输出一个金色渐变按钮（`<a>` 标签 + 内联CSS），用户点击即在浏览器中打开简报，替代原来的Markdown文本链接

### v3.4.0 (2026-07-06)
- **性能优化：脚本并行执行**
  - 5个快速脚本（恐慌指数/新闻/自选股/Serenity/研报）并行执行
  - 抖音/淘股吧作为可选板块，支持快速模式跳过
  - 新增"快速模式"（2-3分钟）vs "完整模式"（5-8分钟）
  - 预估整体提速50-70%

### v3.3.1 (2026-07-06)
- **自选股新闻周末处理规则**：周末/节假日时，自选股新闻板块必须保留完整表格结构，显示最近交易日的数据，在表头meta标注数据日期
- **交付规则更新**：报告生成后只输出一个URL编码的Markdown文件链接到对话中，不再输出原始中文路径链接和绝对路径文本兜底

### v3.3.0 (2026-07-05)
- **布局强制一行优化**（3项改动）：
  - 情绪指标+折线图：`flex-wrap:nowrap` 强制同行，折线图 `min-width:0` 自适应
  - 指数栏精简为4个：上证、科创50、纳斯达克、KOSPI，`flex-wrap:nowrap` 强制一行
  - 策略三卡：`display:flex` + `flex:1;min-width:0` 强制等宽一行，≤600px纵向堆叠
- 更新模板布局图和SKILL.md规则说明

### v3.2.0 (2026-07-05)
- 策略三卡从grid改为flex强制一行布局

### v3.1.0 (2026-07-05)
- **重要修复**：新增"执行前必读"章节，明确禁止以下常见错误
- 禁止硬编码日期，必须使用 `datetime.now()` 动态获取
- 禁止使用模板样例数据，必须获取当日实际数据
- 明确 `fw` class 使用规则：仅机构研报、抖音博主使用
- 明确文件命名规范：`每日简报_YYYY-MM-DD.html`
- 周末/节假日处理：标注"周末无更新"而非保留旧数据

### v3.0.0 (2026-07-05)
- 新增恐慌贪婪指数计算器（参照CNN标准）
- 数据源从WebSearch改为开盘啦API + Akshare
- 新增北向资金、融资余额、板块强度等维度
- HTML模板优化：策略改为flex一行布局，来源列自适应

### v2.0.0
- 初始版本，使用WebSearch作为数据源

---

## 常见错误与修正

| 错误现象 | 原因 | 正确做法 |
|---------|------|---------|
| 文件名为 `daily_pulse_xxx.html` | 使用英文命名 | 使用 `YYYY-MM-DD简报.html`（如 `2026-07-06简报.html`） |
| 日期固定为某个历史日期 | 脚本中硬编码日期 | 使用 `datetime.now().strftime("%Y-%m-%d")` |
| 内容与模板样例完全相同 | 未获取实际数据 | 调用各数据源API获取当日数据 |
| 某些板块消失 | 误删section | 保留所有11个板块，无数据时标注原因 |
| 财经新闻独占一行 | 错误添加 `fw` class | 仅机构研报、抖音博主使用 `fw` |
| 周末显示旧数据 | 未判断周末 | 标注"周末无更新"并保留空表格结构 |
| **凭空捏造指数数值** | API失败后随意填写 | 标注数据来源日期，如"(7/3数据)" |
| **编造新闻/观点** | 懒于获取真实数据 | 如实标注"数据获取失败"或使用最近可用数据 |
| **机构研报只有结论没有逻辑** | 只写了"XX看多YY" | 必须写出逻辑链：驱动因素→传导路径→受益标的，如"存储涨价：三星提价+美光扩产→NAND供给偏紧→利好存储模组厂" |
| **淘股吧4位博主全部0条** | Cookie过期或脚本故障 | 检查 `~/.codex/tgb_cookies.json` 是否过期；用urllib直接测试moreReplyMod页面是否返回登录页；**必须报错修复后重试，禁止填"今日无动态"** |
| **抖音板块跳过或填"处理超时"** | ffmpeg缺失/云端 ASR 未配置/网络问题 | 检查 ffmpeg、原生字幕、`GROQ_API_KEY`/`SILICONFLOW_API_KEY`/`OPENAI_API_KEY` 或完整 `DOUYIN_ASR_*`；延长超时到5分钟；**必须报错修复后重试，禁止跳过** |
| **先输出简报再补数据** | 没等Group B完成就编译 | 必须等淘股吧和抖音都成功获取后，再统一编译输出；获取失败则报错停止，不输出简报 |
| **链接不可点击** | 用了裸 HTML `<a>` 标签，或把链接写进 ``` 代码块 | 用 `[📄 打开 M 月 D 日简报](D:/.../YYYY-MM-DD简报.html)` 的 Markdown 绝对路径链接，放在代码块外；Codex 桌面端不渲染 HTML |

### 完整简报逐模块门禁

使用 `scripts/briefing_integrity.py` 核验行情、盘面、新闻、龙虎榜、90行业轮动、研报、两平台调查、淘股吧、抖音、事件、节点、四指数和名言出处。实际日期优先于请求日期；partial/error、旧行情、未转录视频、未核验研报或观点均不能报告成功。`run_all.py --resume` 可复用已核验的本次数据继续编译，仍执行完整门禁。新闻关键词不直接决定A股利好/利空；方向判断优先读取日期、来源URL和正文哈希绑定的语义判读。
