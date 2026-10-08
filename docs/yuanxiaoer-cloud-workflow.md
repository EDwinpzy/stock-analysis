# 圆小二云端增量蒸馏

## 云端执行顺序

1. GitHub Actions 每天北京时间 21:00 执行 `.github/workflows/yuanxiaoer-collect.yml`，遍历圆小二作者列表全部分页，更新原帖/本人回复归档和 `pending_distillation.json`。工作流也支持手动运行；首次推送工作流后，应在 Actions 页面验证一轮。
2. 目标是在 ChatGPT 网页端创建北京时间 22:30 的云端定时任务，读取 GitHub `main`，根据本文件和仓库 `AGENTS.md` 蒸馏待处理项并回写项目。网页端任务不依赖本机目录。只有该任务已在 ChatGPT 的定时任务列表中出现，并成功完成一次手动测试后，才可将蒸馏阶段标记为云端启用。

## 启用状态

GitHub Actions 负责采集，ChatGPT 云端任务负责蒸馏，两者是独立阶段。仓库中的工作流文件只会创建采集阶段；它不会创建 ChatGPT 定时任务。ChatGPT 云端任务尚未确认前，仍须保留现有本地 Codex 定时任务作为回退，不得把本地执行称为云端执行。

## 蒸馏规则

- 只处理 `data/yuanxiaoer/pending_distillation.json` 中的项目。逐项读取对应的 `data/yuanxiaoer/posts/<id>.json`，只使用作者 ID `12089754` 的主贴正文和本人回复，不混入读者观点。
- 仅当 `data/yuanxiaoer/latest_run.json` 的 `status` 为 `success`、`feed_complete` 为 `true` 且 `errors` 为空时，才可推进整体蒸馏成功边界。失败或部分采集时，保留待处理状态并报告错误，不得清空队列或前移成功时间。
- 检查主贴和本人回复的图片链接。`pending_distillation.json` 的 `unreviewed_images` 提供待核验位置、图片 URL 与 URL 列表哈希；既有图片被移除时，`status: removed` 也会重新入队。能读取图片时，逐张注明核验结论并把对应哈希记入状态；图片无法访问或交易含义不确定时保留待处理，不得声称完整覆盖。
- 已处理帖子以存档状态为范围底账：比较已处理主贴的正文/图片哈希，以及已处理本人回复的正文/图片哈希。旧帖修订或旧回复修订必须重新入队；基线之前从未处理的旧回复不因全量列表扫描而自动加入。
- 每项都要蒸馏，或记录明确的非交易内容跳过理由。记录主贴/回复 ID、原文时间、来源链接、正文/回复哈希；区分观察、条件式买卖、作者自述实操和通用规则。新增规则标为“仅语料”，记录与既有规则的冲突及适用背景，不改历史回测标签。
- 将完整结果写入 `data/yuanxiaoer/distillations/YYYY-MM-DD.md`，再更新 `data/yuanxiaoer/latest.md`。只有采集完整且每个队列项目都有已核验的蒸馏或明确审查结论时，才更新 `distillation_state.json` 的成功时间、已处理 ID 和哈希，并重算/清空已完成的待处理项。
- 更新后通过 GitHub 连接重新读取受影响文件，核验状态、哈希、来源 ID 与待处理队列。遇到写入冲突时先重新读取 `main`，再合并，禁止覆盖并发更新。
- 若当日 `pending_distillation.json` 为空且采集成功，报告无新增即可，不必为无内容的运行创建蒸馏文件。抓取失败或尚有未核验项目时，明确报告问题并保留队列。

## 日常检查

- 先确认当天 GitHub Actions 的 collection run 已成功；核验 `checked_at`、`feed_pages`、`feed_topics`、`feed_complete` 和 `errors`。
- 采集工作流用仓库级 `GITHUB_TOKEN` 写回新增的帖子归档、版本和运行状态；原始 HTML 保持在忽略目录中，不提交。
- GitHub Actions 手动重跑入口：仓库 **Actions → Yuanxiaoer post collection → Run workflow**。
