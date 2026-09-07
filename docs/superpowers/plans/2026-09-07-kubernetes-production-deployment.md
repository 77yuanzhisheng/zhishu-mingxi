# Kubernetes Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Zhishu Mingxi platform as isolated, persistent Kubernetes workloads reachable through one NodePort.

**Architecture:** Build one Python API image and one Nginx static frontend image. Nginx proxies `/api`, `/chat`, `/kb`, `/tools`, and `/docs` to the internal API service so browser requests stay same-origin. Kubernetes configuration is entirely namespaced under `zhishu-mingxi`; credentials are supplied only through a runtime Secret and data is held in a namespace-local PVC.

**Tech Stack:** FastAPI, Uvicorn, Nginx, Docker, Kubernetes Deployment/Service/PVC/Secret.

---

### Task 1: Make the browser API endpoint deployment-safe

**Files:**
- Modify: `frontend/app.js:9-18`
- Create: `tests/test_frontend_api_base_url.py`

- [ ] Write static regression assertions for same-origin production API behavior.
- [ ] Run the test to verify the existing localhost default fails the production assertion.
- [ ] Implement same-origin default behavior while retaining explicitly local developer override support.
- [ ] Run the focused regression test.

### Task 2: Package the application

**Files:**
- Create: `Dockerfile.api`
- Create: `Dockerfile.web`
- Create: `deploy/nginx.conf`
- Create: `.dockerignore`

- [ ] Write static tests for non-root runtime users, API health command, and proxy paths.
- [ ] Build minimal production images with no secrets copied into the image.
- [ ] Run static tests and Docker builds.

### Task 3: Add isolated Kubernetes configuration

**Files:**
- Create: `deploy/kubernetes/namespace.yaml`
- Create: `deploy/kubernetes/storage.yaml`
- Create: `deploy/kubernetes/api.yaml`
- Create: `deploy/kubernetes/web.yaml`
- Create: `deploy/kubernetes/secret.example.yaml`
- Create: `deploy/kubernetes/kustomization.yaml`
- Create: `deploy/README.md`

- [ ] Write static manifest contract tests for namespace isolation, probes, resource bounds, one API replica, a PVC, and no secret values.
- [ ] Create manifests and deployment instructions including dry-run, rollout, verification, and scoped rollback commands.
- [ ] Run static tests and `kubectl kustomize` locally.

### Task 4: Publish and verify

**Files:**
- Modify: deployment documents only if runtime verification identifies an issue.

- [ ] Build and push versioned images to the existing Harbor registry from the shared server’s authenticated Docker context.
- [ ] Select unused NodePorts through a read-only cluster query.
- [ ] Apply only `zhishu-mingxi` resources and wait for rollouts.
- [ ] Verify public frontend, `/api/health`, and a real chat request; inspect only project namespace logs and events.
- [ ] Commit non-sensitive deployment configuration and push the deployment branch to GitHub.
