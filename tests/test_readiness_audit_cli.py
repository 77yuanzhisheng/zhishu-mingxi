from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_readiness_audit_cli_outputs_json():
    root = Path(__file__).parents[1]
    script = root / "scripts" / "audit_project_readiness.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--format", "json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["curriculum"]["chapters"] == 19
    assert report["question_bank"]["total"] == 112
    assert report["finetune"]["records"] == 3630
    assert "SPARK_API_KEY" not in result.stdout
