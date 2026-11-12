# 圆小二每日更新

## 项目 Quick Card

- 仓库：`EDwinpzy/stock-analysis`（`git@github.com:EDwinpzy/stock-analysis.git`）。
- 官方插件源码入口：`plugins/daily-briefing-pro/`；不要把安装缓存或 `deploy/cloud/runtime/` 当作源码。
- 行情/个股/行业/简报统一入口：`python plugins/daily-briefing-pro/cloud_cli.py ...`；完整命令见根 `README.md` 和插件 `SKILL.md`。
- 测试：`python -m pytest tests -q`。云端/取数冒烟：`python plugins/daily-briefing-pro/cloud_cli.py doctor --probe`。
- 凭证/外部服务：机器清单位于 `config/credentials.manifest.json`，替换流程见 `docs/credentials.md`；真实值只放在 `~/.codex/daily-briefing.env` 和 Cookie JSON，不写入仓库。审计命令：`python tools\credential_manifest.py check --github --all --strict`。
- 报告交付门禁：个股/行业报告必须同时校验 HTML 和采集 JSON，未通过不得交付。
- 生成/忽略目录：`work/`、`plugins/daily-briefing-pro/deploy/cloud/runtime/`、`secrets/`、`*.tmp.html`、采集器旁的 `_fetch_result_*.json` / `_industry_*.json`。
- 发布/签名：本仓库当前无 APK/HAP/商店发布门禁；插件版本、标签和 Release 未获明确指令不执行。
- 禁止直接修改：`reference/` 口径基准、`C:\Users\63054\.codex\plugins\cache\` 安装缓存、`deploy/cloud/runtime/` 运行快照。
- 任务隔离：写入前按 `$git-workflow` 使用独立 worktree 和 `codex/<topic>` 分支；主工作区保持 `main`。

在本项目使用圆小二体系分析时，先读取 `data/yuanxiaoer/latest_run.json`、`data/yuanxiaoer/latest.md` 与最近的蒸馏记录，再读取安装插件的体系规则。明确报告最新原文日期、核验时间及缺失范围。

每日增量采集命令：`python tools/fetch_yuanxiaoer_posts.py`。首次补齐安装包截至日期之后的帖子可用 `--since 2026-09-25`。

“新增”覆盖安装包基线之后的所有新主帖，以及任何旧帖中的本人新回复；扫描整个作者列表的所有分页，不限制当天或最近10篇。读取 `pending_distillation.json`，逐项蒸馏或记录明确的非交易内容跳过理由。待处理项只按成功蒸馏状态去重，不能根据本次采集的 `changes` 列表清空。正文/回复修订使用哈希核对。

仅把圆小二本人原文和本人回复作为语料；保留帖子、回复 ID、时间和来源。区分观察、条件式买卖、实际操作与通用规则；新增规则默认标记“仅语料”，不得继承旧规则的回测标签。记录与旧规则的冲突和适用背景，保留历史版本。

采集失败、分页不完整或图片未核验必须明确记录，不能当成没有新帖。蒸馏完成后才更新 `latest.md`，不覆盖已验证的历史回测结论。

只有全文列表与目标回复分页采集成功、待处理内容全部蒸馏或有明确审查结论之后，才能更新 `distillation_state.json` 的成功时间和已处理ID/哈希；部分失败不得向前移动整体成功边界。更新状态后重跑，核验待处理队列清空。图片独有的交易内容未核验时保留待处理项，不宣称覆盖完成。

安装缓存不是源码，不直接修改缓存或自动发布共享插件。本项目增量库用于补充已安装插件；找到原始源码并按其发布流程更新后，才能宣称插件发布包已更新。

## Muse 云端统一产物模式（2026-10-25）

用户明确选择 A股行情与圆小二在 Muse 云端统一生成，Muse 与 Codex 接收同一份产物。日常交付以此模式优先，以上本机采集命令保留为维护和离线核验入口，不默认重复运行来交付另一份结果。

本模式下，本机 `data/yuanxiaoer/` 仅作为迁移前历史参考。新的语料、队列与成功状态以云端 `active-data/yuanxiaoer/` 为准，回答前读取相应已交付产物，不用本机旧状态推断云端最新覆盖范围。云端 `runtime/` 保留为不可变迁移基线。

- 云端运行根目录为 `/home/hatch/workspace/migrations/codex-plugins-20261025`，使用其中 `.venv/bin/python`、`run_workflow.py` 和原始插件工作流。不得省略原有来源核验、完整性门禁、图片审查及成功状态边界。
- 云端生成后用 `artifact_delivery.py publish` 打包实际产物，并将 ZIP 和其 SHA256 文件交付到现有 OneDrive 私有目录 `MusePluginArtifacts`。不要改变共享权限，不把凭证放入交付包。
- Codex 接收入口为 `python -X utf8 work/muse-migration/receive_inbox.py`，从 `D:\OneDrive\MusePluginArtifacts` 校验 ZIP、清单与每个文件的 SHA256，再保存到 `报告/Muse产物/<artifact_id>/`。接收端不得重新进行 AI 分析、重排 HTML、转码 PNG 或覆盖历史产物。
- 用户要求的日期或主题没有对应产物时，向 Muse 提交该请求或明确报告尚未生成，不能把历史重放结果当成当日结果。云端数据源连接或授权失败时如实报告，不自动放宽数据门禁。
- 本机固定输入重建和测试是迁移验证，不代表云端实时数据全部可用。当前迁移证据与未完成项以 `work/muse-migration/progress.json` 和实际验证产物为准。

## Muse 验收补充（2026-10-26）

用户最新要求：内容可以不同，但格式、样式、板块名称与顺序、必填字段和桌面/手机布局遵循原插件。抖音真实转录与观点提炼的实现由 Muse 自选，不限定本地模型、固定 API 或具体流程；保留真实原文、作者来源核验和完整性要求，不能用标题代替转录。跨端哈希仅用于同一份交付文件的传输校验，不要求不同次生成逐字或像素一致。
