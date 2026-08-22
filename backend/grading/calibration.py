from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Mapping, Sequence

from backend.grading.evaluation import HumanLabel, evaluate_against_human_labels
from backend.learning.database import connection_scope, init_database

RUBRIC_VERSION = "v1"
MAX_SCORE_MAE_FOR_RELEASE = 10.0
MIN_SCORE_BAND_COHEN_KAPPA_FOR_RELEASE = 0.7


@dataclass(frozen=True)
class HumanLabelInput:
    result_id: int
    rater_id: str
    rubric_version: str
    total_score: float
    dimension_scores: Mapping[str, float]
    error_types: Sequence[str]
    reason: str

    def to_label(self) -> HumanLabel:
        return HumanLabel(
            self.result_id,
            self.total_score,
            self.dimension_scores,
            self.error_types,
        )


def _validate_input(label: HumanLabelInput) -> None:
    if not label.rater_id.strip() or not label.reason.strip():
        raise ValueError("rater_id and reason are required")
    if label.rubric_version != RUBRIC_VERSION:
        raise ValueError("unsupported rubric version")
    label.to_label()


def _ensure_tables(connection: sqlite3.Connection) -> None:
    connection.executescript("""
    CREATE TABLE IF NOT EXISTS grading_human_labels (
      id INTEGER PRIMARY KEY AUTOINCREMENT, result_id INTEGER NOT NULL, rater_id TEXT NOT NULL,
      rubric_version TEXT NOT NULL, total_score REAL NOT NULL, dimension_scores TEXT NOT NULL CHECK(json_valid(dimension_scores)),
      error_types TEXT NOT NULL CHECK(json_valid(error_types)), reason TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(result_id, rater_id, rubric_version), FOREIGN KEY(result_id) REFERENCES grading_results(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS grading_adjudications (
      id INTEGER PRIMARY KEY AUTOINCREMENT, result_id INTEGER NOT NULL, adjudicator_id TEXT NOT NULL,
      rubric_version TEXT NOT NULL, total_score REAL NOT NULL, dimension_scores TEXT NOT NULL CHECK(json_valid(dimension_scores)),
      error_types TEXT NOT NULL CHECK(json_valid(error_types)), reason TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'adjudicated', created_at TEXT NOT NULL DEFAULT (datetime('now')),
      UNIQUE(result_id, rubric_version), FOREIGN KEY(result_id) REFERENCES grading_results(id) ON DELETE CASCADE
    );
    """)


def store_human_label(db, label: HumanLabelInput) -> int:
    _validate_input(label)
    init_database(db)
    with connection_scope(db) as connection:
        _ensure_tables(connection)
        try:
            cursor = connection.execute(
                """INSERT INTO grading_human_labels(
                    result_id, rater_id, rubric_version, total_score,
                    dimension_scores, error_types, reason
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    label.result_id,
                    label.rater_id,
                    label.rubric_version,
                    label.total_score,
                    json.dumps(dict(label.dimension_scores)),
                    json.dumps(list(label.error_types)),
                    label.reason,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("duplicate label or unknown result_id") from error
        return int(cursor.lastrowid)


def adjudicate_label(
    db, result_id: int, adjudicator_id: str, label: HumanLabelInput
) -> dict:
    if label.result_id != result_id:
        raise ValueError("result_id mismatch")
    if not adjudicator_id.strip():
        raise ValueError("adjudicator_id is required")

    _validate_input(label)
    init_database(db)
    with connection_scope(db) as connection:
        _ensure_tables(connection)
        raters = connection.execute(
            """SELECT DISTINCT rater_id FROM grading_human_labels
               WHERE result_id=? AND rubric_version=?""",
            (result_id, label.rubric_version),
        ).fetchall()
        if len(raters) < 2:
            raise ValueError("two independent raters are required before adjudication")
        try:
            connection.execute(
                """INSERT INTO grading_adjudications(
                    result_id, adjudicator_id, rubric_version, total_score,
                    dimension_scores, error_types, reason
                ) VALUES(?,?,?,?,?,?,?)""",
                (
                    result_id,
                    adjudicator_id,
                    label.rubric_version,
                    label.total_score,
                    json.dumps(dict(label.dimension_scores)),
                    json.dumps(list(label.error_types)),
                    label.reason,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("adjudication already exists") from error
        return dict(
            connection.execute(
                """SELECT * FROM grading_adjudications
                   WHERE result_id=? AND rubric_version=?""",
                (result_id, label.rubric_version),
            ).fetchone()
        )


def build_calibration_report(
    db, question_type: str = "overall", minimum_samples: int = 20
) -> dict:
    if minimum_samples < 1:
        raise ValueError("minimum_samples must be at least 1")

    init_database(db)
    with connection_scope(db) as connection:
        _ensure_tables(connection)
        question_filter = "" if question_type == "overall" else " AND g.question_type = ?"
        params = () if question_type == "overall" else (question_type,)
        counts = connection.execute(
            """
            SELECT
                COUNT(DISTINCT CASE WHEN label_counts.rater_count = 1 THEN g.id END) AS single_rater_count,
                COUNT(DISTINCT CASE
                    WHEN label_counts.rater_count >= 2 AND adjudication.id IS NULL THEN g.id
                END) AS dual_rater_pending_adjudication_count,
                COUNT(DISTINCT adjudication.result_id) AS adjudicated_gold_count
            FROM grading_results g
            LEFT JOIN (
                SELECT result_id, rubric_version, COUNT(DISTINCT rater_id) AS rater_count
                FROM grading_human_labels
                WHERE rubric_version = ?
                GROUP BY result_id, rubric_version
            ) AS label_counts ON label_counts.result_id = g.id
            LEFT JOIN grading_adjudications AS adjudication
                ON adjudication.result_id = g.id AND adjudication.rubric_version = ?
            WHERE 1 = 1
            """ + question_filter,
            (RUBRIC_VERSION, RUBRIC_VERSION, *params),
        ).fetchone()
        rows = connection.execute(
            """
            SELECT
                g.id, g.total_score, g.dimension_scores, g.error_types,
                adjudication.total_score AS human_score,
                adjudication.dimension_scores AS human_dims,
                adjudication.error_types AS human_errors
            FROM grading_results AS g
            JOIN grading_adjudications AS adjudication
                ON adjudication.result_id = g.id AND adjudication.rubric_version = ?
            WHERE 1 = 1
            """ + question_filter,
            (RUBRIC_VERSION, *params),
        ).fetchall()

    summary = {
        "question_type": question_type,
        "sample_size": int(counts["single_rater_count"] or 0)
        + int(counts["dual_rater_pending_adjudication_count"] or 0)
        + int(counts["adjudicated_gold_count"] or 0),
        "gold_standard_sample_size": len(rows),
        "gold_standard_source": "adjudicated",
        "single_rater_count": int(counts["single_rater_count"] or 0),
        "dual_rater_pending_adjudication_count": int(
            counts["dual_rater_pending_adjudication_count"] or 0
        ),
        "adjudicated_gold_count": int(counts["adjudicated_gold_count"] or 0),
        "minimum_samples": minimum_samples,
    }
    if len(rows) < minimum_samples:
        return {
            "status": "needs_calibration",
            "available": False,
            "reason": "fewer than the required adjudicated gold-standard samples are available",
            "release": _release_summary(False, "needs_calibration", None),
            **summary,
        }

    predictions = []
    labels = []
    for row in rows:
        predictions.append(
            {
                "result_id": row["id"],
                "total_score": row["total_score"],
                "dimension_scores": json.loads(row["dimension_scores"]),
                "error_types": json.loads(row["error_types"]),
            }
        )
        labels.append(
            HumanLabel(
                row["id"],
                row["human_score"],
                json.loads(row["human_dims"]),
                json.loads(row["human_errors"]),
            )
        )

    report = evaluate_against_human_labels(predictions, labels)
    release_eligible = (
        report["score_mae"] <= MAX_SCORE_MAE_FOR_RELEASE
        and report["score_band_cohen_kappa"] >= MIN_SCORE_BAND_COHEN_KAPPA_FOR_RELEASE
    )
    release_status = "calibrated" if release_eligible else "evaluated_not_accepted"
    report.update(
        {
            "status": release_status,
            "release": _release_summary(release_eligible, release_status, report),
            **summary,
        }
    )
    return report


def _release_summary(eligible: bool, status: str, report: Mapping | None) -> dict:
    actual = {} if report is None else {
        "score_mae": report["score_mae"],
        "score_band_cohen_kappa": report["score_band_cohen_kappa"],
    }
    return {
        "eligible": eligible,
        "status": status,
        "thresholds": {
            "max_score_mae": MAX_SCORE_MAE_FOR_RELEASE,
            "min_score_band_cohen_kappa": MIN_SCORE_BAND_COHEN_KAPPA_FOR_RELEASE,
        },
        "actual": actual,
    }
