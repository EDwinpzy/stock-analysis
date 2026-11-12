import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[1]
    / "plugins"
    / "daily-briefing-pro"
    / "skills"
    / "daily-briefing-pro"
    / "scripts"
    / "verify_cloud_report.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location("verify_cloud_report", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_inspect_html_counts_sections_tables_and_rows(tmp_path):
    report = tmp_path / "report.html"
    report.write_text(
        """
        <html><head><title>测试报告</title></head><body>
          <div class="sec"><table><tr><th>一</th></tr><tr><td>1</td></tr></table></div>
          <div class="sec"><table><tr><td>2</td></tr></table></div>
        </body></html>
        """,
        encoding="utf-8",
    )

    result = _load_module().inspect_html(report)

    assert result == {
        "sections": 2,
        "tables": 2,
        "rows": 3,
        "title": "测试报告",
    }
