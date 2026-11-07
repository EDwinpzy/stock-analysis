"""Render the local review artifact. No browser/network/state mutation."""
from pathlib import Path
import markdown

ROOT = Path(__file__).resolve().parent
name = "节点票筛选条件"
body = markdown.markdown((ROOT / f"{name}.md").read_text(encoding="utf-8"), extensions=["tables", "fenced_code", "toc"])
css = """
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f5f8;color:#202e42;font:16px/1.8 'Microsoft YaHei',sans-serif}main{max-width:1150px;margin:32px auto;background:white;padding:40px 46px;border:1px solid #dce3ec;border-radius:14px}h1{font-size:30px;line-height:1.45;color:#163756}h2{font-size:23px;margin-top:42px;padding-top:16px;border-top:2px solid #e0e7ef}a{color:#155d9c;text-decoration:none}a:hover{text-decoration:underline}p{margin:18px 0}table{width:100%;border-collapse:collapse;margin:24px 0;font-size:14px;line-height:1.65}th{background:#eaf1f8;color:#173958}th,td{padding:11px 10px;border:1px solid #dce3ec;vertical-align:top}tbody tr:nth-child(even){background:#f8fafc}strong{color:#163756}code{background:#edf2f7;padding:3px 5px;word-break:break-word}li{margin:7px 0}nav{display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid #dde5ee;padding-bottom:18px}footer{font-size:13px;color:#64748b;margin-top:30px}@media(max-width:800px){main{margin:0;padding:24px 16px;border:0;border-radius:0}h1{font-size:25px}table{font-size:12px}th,td{padding:7px 5px}}@media print{body{background:white}main{border:0;margin:0;max-width:none;padding:0}nav{display:none}h2{break-after:avoid}tr{break-inside:avoid}}
"""
html = f'<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{name}｜2026-10-19</title><style>{css}</style><main><nav><a href="#conditions">筛选条件</a><a href="#validation">完整候选池验证</a><a href="validation/validation_report.md">验证明细</a><a href="validation/candidate_outcomes.csv">下载候选CSV</a></nav>{body}<footer>公开语料与截至2026-10-19收盘的参考价格研究 · 生成于本地项目</footer></main></html>'
(ROOT / f"{name}.html").write_text(html, encoding="utf-8")
print(ROOT / f"{name}.html")
