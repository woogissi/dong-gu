import os
from pathlib import Path

import pytest

from crawler.ops.live_deu_integration_smoke import run_smoke


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("CRAWLER_RUN_LIVE_INTEGRATION") != "1",
        reason="set CRAWLER_RUN_LIVE_INTEGRATION=1 to fetch real DEU pages",
    ),
]


def test_live_deu_integration_smoke(tmp_path: Path) -> None:
    report = run_smoke(report_path=tmp_path / "live_deu_integration_smoke.json")

    assert report["ok"], [
        {
            "sample": sample["sample"]["name"],
            "failed_steps": [
                step
                for step in sample.get("steps", [])
                if not step["ok"]
            ],
            "failed_attachment_steps": [
                step
                for attachment in sample.get("attachments", [])
                for step in attachment.get("steps", [])
                if not step["ok"]
            ],
        }
        for sample in report["samples"]
        if not sample["ok"]
    ]
