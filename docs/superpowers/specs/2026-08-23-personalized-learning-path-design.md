# Personalized Learning Path Design

## Objective

Build a backend-first personalized learning path engine for discrete mathematics. The engine combines QA history, practice results, mastery records, and long-answer grading evidence to produce an auditable staged path for each learner.

The product flow is diagnosis, foundation repair, reinforcement, and advancement. Diagnosis is returned as analysis metadata. The executable learning tasks are grouped into `foundation`, `reinforcement`, and `advancement` stages.

## Scope

This feature only targets discrete mathematics knowledge points already used by the project. It does not build a cross-course planner, calendar schedule, frontend UI, or teacher dashboard.

The first delivery is a stable backend API that teammate 4 can integrate later.

## API Contract

Add these endpoints under the learning API:

```http
GET /api/learning/path?user_id=1
POST /api/learning/path/refresh
```

`GET /api/learning/path` returns the latest stored path snapshot for the user. If no snapshot exists, it generates and stores one.

`POST /api/learning/path/refresh` forces a new generation when `force` is true or when new evidence makes the existing snapshot stale.

Request body:

```json
{
  "user_id": 1,
  "force": true
}
```

Response shape:

```json
{
  "user_id": 1,
  "path_id": "path-...",
  "version": 1,
  "strategy": "rule_based_with_ai_explanation",
  "data_quality": {},
  "diagnosis": {},
  "stages": [],
  "ai_notes": {},
  "generated_at": "2026-08-23T00:00:00Z"
}
```

Each path node includes:

```text
node_id
module
stage
priority
title
reason
evidence
tasks
mastery_gate
status
confidence
```

## Data Sources

The path engine reads these existing sources:

- `messages`: QA history. Existing `node_ids` are the highest-confidence knowledge tags.
- `answer_events`: objective practice, exam, and proof activity records.
- `node_mastery`: current mastery estimates.
- `grading_results`: long-answer scores, dimensions, and error types from teammate 1's grading engine.
- `backend/kb/recommender.py`: knowledge modules, dependency order, and recommendation utilities.
- Teammate 2 KB APIs: structured questions and grading guides can enrich task generation and explanations.

Knowledge-point extraction priority for QA history is:

1. Use existing `node_ids`.
2. Use a local discrete-math keyword and node dictionary.
3. Use AI classification only as a low-confidence supplement.
4. If still uncertain, mark the evidence as unidentified and avoid letting it strongly influence the path.

## Path Generation Strategy

The engine uses a rule-first design with constrained AI assistance.

Rules are authoritative for dependency correctness, stage assignment, scoring, fallback behavior, and nonexistent-node protection. AI may only produce readable diagnosis text, learning advice, and small explanation-level adjustments. If AI fails or returns invalid data, the API returns the rule-generated path with `ai_status = "fallback"`.

AI output must be JSON-validated. It cannot introduce unknown node IDs, reorder prerequisites behind dependent modules, remove mastery gates, or create tasks outside the known discrete-math scope.

## Priority Scoring

Each candidate knowledge point receives a priority score:

```text
40% mastery weakness
25% practice error severity
20% QA confusion frequency
10% dependency importance
5% recency and activity
```

The default response includes at most 8 learning nodes. Started nodes are kept stable unless the new score changes enough to justify reordering.

## Stage Rules

`foundation` is used when mastery is low, recent accuracy is below 0.6, prerequisites are weak, or the evidence shows definition and theorem confusion. Gate: at least 5 related questions, accuracy at least 0.8, and no two consecutive same-type errors.

`reinforcement` is used when the learner has a base but performance is unstable, repeated errors appear, or QA history repeatedly asks about the same point. Gate: at least 6 related questions, accuracy at least 0.8, and at least 2 of the latest 3 performances pass. For proof-heavy points, long-answer grading should have total score at least 70 and no severe key-reasoning or logical-rigor weakness.

`advancement` is used only when foundation and reinforcement evidence are stable and prerequisites are healthy. If new consecutive errors appear, the point falls back to reinforcement.

## Persistence

Add a learning path snapshot table that stores:

- user ID
- path ID
- version
- generated time
- source data summary
- rule path JSON
- AI notes JSON
- status and fallback reason

Snapshots make the feature auditable for demos and defense. They also allow future comparison between old and new learning paths after additional QA or practice events.

## Files

Add:

- `backend/learning/path_models.py`
- `backend/learning/path_data.py`
- `backend/learning/path_scoring.py`
- `backend/learning/path_engine.py`
- `backend/learning/path_ai.py`
- `backend/learning/path_router.py`
- `tests/test_learning_path.py`

Modify:

- `backend/api.py`
- `backend/learning/database.py`

Reuse:

- `backend/chat/llm.py`
- `backend/kb/recommender.py`
- `backend/learning/service.py`

## Validation Requirements

The implementation must verify these cases:

- Practice-only data generates a path.
- QA-only data generates a low-confidence path.
- No data returns a default discrete-math path and marks `insufficient_data`.
- Existing QA `node_ids` take priority over inferred labels.
- Dependencies are respected.
- AI failure still returns the rule path.
- Unknown nodes, unknown questions, and unknown tasks are rejected.
- Snapshots are persisted and versioned.
- New evidence can change the next generated path.

## Team Integration

This module consumes teammate 2's structured question and grading-guide outputs when available. It also uses teammate 1's grading results as high-value proof-performance evidence. Teammate 4 receives the learning path API for frontend integration. Teammate 3's learning records and ability-profile work can improve the same evidence layer without changing the API contract.
