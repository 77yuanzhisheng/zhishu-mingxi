from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.practice import router as practice_module
from backend.practice.router import router as practice_router


def test_get_calc_questions_returns_structured_teacher_questions(tmp_path, monkeypatch):
    quiz_file = tmp_path / "teacher_questions.json"
    quiz_file.write_text(
        json.dumps(
            {
                "exams": [
                    {
                        "id": 1,
                        "calc": [
                            {
                                "q": "计算题",
                                "a": "答案",
                                "kp": "graph-basic",
                                "fig": "figure.png",
                            }
                        ],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(practice_module, "TEACHER_QUIZ_FILE", str(quiz_file))

    app = FastAPI()
    app.include_router(practice_router)
    response = TestClient(app).get("/api/practice/calc-questions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["questions"] == [
        {
            "id": "e1_calc_1",
            "question": "计算题",
            "answer": "答案",
            "kp": "graph-basic",
            "module": "graph_theory",
            "moduleName": "图论",
            "nodeId": "gt_01_01",
            "fig": "figure.png",
        }
    ]
