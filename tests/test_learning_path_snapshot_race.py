"""回归：并发刷新学习路径不能因快照版本冲突把接口打成 500。"""

from __future__ import annotations

import sqlite3
import threading

from backend.learning import path_data


def _snapshot_payload(index: int) -> dict:
    return {
        "user_id": 59,
        "path_id": f"path-{index}",
        "version": 1,  # 故意模拟并发请求都算出了同一个版本号
        "strategy": "rule_based_with_ai_explanation",
        "data_quality": {},
        "diagnosis": {},
        "stages": [],
        "ai_notes": {},
        "generated_at": "2026-09-14T00:00:00+00:00",
    }


def test_concurrent_persist_snapshot_keeps_unique_versions(tmp_path):
    database_path = str(tmp_path / "learning.db")
    path_data.init_database(database_path)
    connection = sqlite3.connect(database_path)
    connection.execute(
        "INSERT INTO users (id, username, name, role) VALUES (59, 'u59', 'u59', 'student')"
    )
    connection.commit()
    connection.close()

    errors: list[Exception] = []

    def worker(index: int) -> None:
        try:
            path_data.persist_snapshot(_snapshot_payload(index), {"index": index}, database_path)
        except Exception as exc:  # pragma: no cover - 失败时用于断言
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []

    connection = sqlite3.connect(database_path)
    versions = [row[0] for row in connection.execute(
        "SELECT version FROM learning_path_snapshots WHERE user_id = 59 ORDER BY version"
    )]
    connection.close()

    assert len(versions) == 8
    assert len(set(versions)) == 8
    assert versions == list(range(1, 9))