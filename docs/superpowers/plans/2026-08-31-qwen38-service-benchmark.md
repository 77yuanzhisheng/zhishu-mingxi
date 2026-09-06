# Qwen3.8-27B Service Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a standalone, repeatable benchmark for the Qwen3.8-27B OpenAI-compatible service without changing application behavior.

**Architecture:** `scripts/benchmark_qwen38_service.py` sends fixed discrete-mathematics prompts directly to a configurable OpenAI-compatible `/chat/completions` endpoint. It streams responses to measure first-content-token latency, parses reported usage, checks structured JSON cases, and writes JSON details plus a Markdown summary under `outputs/`. Pure parsing and aggregation helpers are tested independently.

**Tech Stack:** Python 3.11, httpx, pytest, OpenAI-compatible SSE API.

---

### Task 1: Define measurable helper behavior

**Files:** `tests/test_benchmark_qwen38_service.py`

- [ ] Write failing tests for SSE usage extraction, fenced JSON extraction, and aggregate metrics.
- [ ] Run the focused test file and verify it fails because the module does not exist.

### Task 2: Implement the standalone benchmark

**Files:** `scripts/benchmark_qwen38_service.py`, `tests/test_benchmark_qwen38_service.py`

- [ ] Implement helpers for SSE event parsing, JSON-object extraction, and metric aggregation.
- [ ] Implement direct streaming client calls with configurable endpoint, model, token limit, concurrency, timeout, and output location.
- [ ] Include fixed short-chat, calculation-judgement, grading-JSON, and structured-JSON workloads.
- [ ] Run focused tests and verify they pass.

### Task 3: Verify locally and on the server

**Files:** generated `outputs/benchmark_qwen38_service.json`, `outputs/benchmark_qwen38_service.md`

- [ ] Compile the new script and run focused tests.
- [ ] Run existing LLM/chat/grading/practice regression tests.
- [ ] Execute against private vLLM at concurrencies 1, 4, and 8 with a small round count.
- [ ] Report direct-vLLM metrics separately from end-to-end grading and historical baselines.