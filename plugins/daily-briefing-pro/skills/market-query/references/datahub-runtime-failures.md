# DataHub 未通过验证的接口

本表区分账号权限、上游暂不可用和文档示例失效，不能仅凭一次失败判断接口永久失效。

## 业务失败

| 状态 | 业务码 | 接口 | 说明 | 尝试次数 |
|---|---:|---|---|---:|
| permission_denied | 2003 | `/api/a-share/high-frequency/intraday` | Permission denied | 2 |
| permission_denied | 2003 | `/api/a-share/high-frequency/historical` | Permission denied | 2 |
| upstream_unavailable | 5003 | `/api/futures/positions/contract-historical` | Futures finance upstream returned failure status | 3 |
| document_example_rejected | 3001 | `/api/news/notice/detail` | Target not found | 1 |
| upstream_unavailable | 5003 | `/api/news/anomaly/analysis` | Data source unavailable | 1 |
| document_example_rejected | 1002 | `/api/news/article/detail` | Invalid parameter format | 1 |

## 未请求

| 状态 | 接口 | 原因 |
|---|---|---|
| skipped_sensitive_dump | `/api/dump/market-dumps/daily-k/download-url` | 返回短时下载链接，未请求以避免敏感链接落盘。 |
| skipped_sensitive_dump | `/api/dump/market-dumps/adjustment-factors/download-url` | 返回短时下载链接，未请求以避免敏感链接落盘。 |
| skipped_sensitive_dump | `/api/dump/market-dumps/daily-k-10d/download-url` | 返回短时下载链接，未请求以避免敏感链接落盘。 |
