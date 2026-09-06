from pathlib import Path

from backend.training.audit import audit_project_readiness


def test_project_readiness_matches_competition_data_contract():
    report = audit_project_readiness(Path(__file__).parents[1])

    assert report["curriculum"] == {
        "chapters": 19,
        "sections": 73,
        "knowledge_points": 150,
        "key_points": 376,
    }
    assert report["question_bank"]["total"] == 112
    assert report["question_bank"]["unmapped"] == 0
    assert report["question_bank"]["distinct_node_ids"] == 53
    assert report["finetune"]["records"] == 3630
    assert report["finetune"]["duplicates"] == 0
