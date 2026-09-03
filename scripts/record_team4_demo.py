"""Capture the three Team 4 demo flows with deterministic API fixtures.

Run the frontend first, then execute:
  python scripts/record_team4_demo.py --base-url http://127.0.0.1:5500

Add --video after installing Playwright ffmpeg to record WebM clips as well.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import Route, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "artifacts" / "team4-demo"


GRAPH = {
    "modules": [
        {
            "node_id": "propositional_logic",
            "name": "命题逻辑",
            "children": [
                {
                    "node_id": "pl_01",
                    "name": "命题与联结词",
                    "children": [
                        {"node_id": "pl_01_01", "name": "命题", "type": "definition", "text": "能够判断真假的陈述句。"},
                        {"node_id": "pl_01_02", "name": "联结词", "type": "rule", "text": "使用否定、合取、析取和蕴含构造复合命题。"},
                    ],
                }
            ],
        }
    ]
}

TEACHER_GRAPH = {
    "chapters": [
        {
            "id": "C01",
            "title": "第一章 命题逻辑",
            "sections": [
                {
                    "id": "S0101",
                    "title": "1.1 命题与联结词",
                    "kps": [
                        {"id": "K010101", "title": "命题", "platform_node_id": "pl_01_01", "mapping_kind": "exact", "points": [{"title": "命题的定义"}, {"title": "真值判断"}]},
                        {"id": "K010102", "title": "五种基本联结词", "platform_node_id": "pl_01_02", "mapping_kind": "exact", "points": [{"title": "否定"}, {"title": "合取与析取"}]},
                    ],
                },
                {
                    "id": "S0102",
                    "title": "1.2 等值演算",
                    "kps": [{"id": "K010201", "title": "德摩根律", "platform_node_id": "pl_02_02", "mapping_kind": "exact", "points": [{"title": "等价变换"}]}],
                },
            ],
        },
        {
            "id": "C02",
            "title": "第二章 谓词逻辑",
            "sections": [{"id": "S0201", "title": "2.1 量词", "kps": [{"id": "K020101", "title": "全称量词与存在量词", "platform_node_id": "fl_01_01", "mapping_kind": "exact", "points": [{"title": "量词辖域"}]}]}],
        },
    ]
}

REPORT = {
    "mastered": [{"node_id": "pl_01_01", "name": "命题", "level": 4, "correct_count": 5, "total_count": 5}],
    "weak": [{"node_id": "pl_01_02", "name": "联结词", "level": 1, "correct_count": 1, "total_count": 4}],
    "unlearned": [{"node_id": "pl_02_02", "name": "德摩根律", "level": 0}],
    "radar": [],
}


def api_fixture(route: Route) -> None:
    url = route.request.url
    if "/api/health" in url:
        route.fulfill(json={"status": "ok"})
    elif "/kb/teacher-graph" in url:
        route.fulfill(json=TEACHER_GRAPH)
    elif "/kb/knowledge-graph" in url:
        route.fulfill(json=GRAPH)
    elif "/api/learning/" in url or "/api/learning-report" in url:
        route.fulfill(json=REPORT)
    elif "/api/kb/structured-questions" in url:
        route.fulfill(json={"questions": [{
            "id": "proof-demo-1", "question": "证明：若 n 是偶数，则 n² 也是偶数。",
            "answer": "1. 已知 n 是偶数，所以存在整数 k，使 n=2k。\n2. 两边平方得 n²=(2k)²=4k²。\n3. 因为 n²=2(2k²)，且 2k² 是整数，所以 n² 是偶数。证毕。",
            "kp": "pl_01_02", "node_id": "pl_01_02",
        }]})
    elif "/api/grading/grade" in url:
        route.fulfill(json={
            "score": 9, "max_score": 10,
            "dimensions": [
                {"name": "结论正确性", "score": 2, "max_score": 2},
                {"name": "步骤完整性", "score": 1.8, "max_score": 2},
                {"name": "逻辑严密性", "score": 1.8, "max_score": 2},
                {"name": "定理使用", "score": 1.7, "max_score": 2},
                {"name": "符号规范", "score": 1.7, "max_score": 2},
            ],
            "comment": "推导完整，偶数定义与代数变形使用正确。",
            "errors": [],
        })
    elif "/api/agent/chat" in url:
        payload = json.loads(route.request.post_data or "{}")
        if "降级测试" in payload.get("message", ""):
            route.fulfill(status=503, json={"detail": "Agent deployment warming up"})
            return
        if "备课助手" in payload.get("message", ""):
            answer = "## 教学目标\n理解命题与联结词的定义，能够完成真值判断。\n\n## 课堂安排\n1. 5分钟情境导入。\n2. 15分钟讲解五种联结词。\n3. 15分钟分组完成真值表。\n4. 10分钟反馈与练习。\n\n## 检查理解\n判断“如果2是奇数，那么3是偶数”的真值。"
        elif "等价关系" in payload.get("message", ""):
            answer = "等价关系同时满足自反性、对称性和传递性。判断时应依次核对三条性质，其中任意一条不成立，就不是等价关系。"
        else:
            answer = "## 现在做什么\n复习联结词的真值定义。\n\n## 练几题\n完成3道等值判断题，其中至少1道写出真值表。\n\n## 完成标准\n连续答对2题，并能解释一次错误原因。"
        route.fulfill(json={"answer": answer, "session_id": "demo-session", "channel": "agent", "provider": "xfyun-agent"})
    elif url.endswith("/chat"):
        route.fulfill(json={"answer": "基础模型降级回答。", "session_id": "demo-session"})
    elif "/kb/learning-path" in url or "/api/learning/path" in url:
        route.fulfill(json={"path": []})
    elif "/kb/recommend" in url:
        route.fulfill(json={"questions": [{"type": "选择题", "content": "下列哪一个是合取命题？", "difficulty": 2}]})
    elif "/api/practice/questions" in url:
        route.fulfill(json={"questions": []})
    else:
        route.fulfill(status=404, json={"detail": "demo fixture not configured"})


def new_context(browser, video: bool, name: str):
    kwargs = {"viewport": {"width": 1440, "height": 960}, "device_scale_factor": 1}
    if video:
        kwargs.update(record_video_dir=str(OUTPUT / "videos"), record_video_size={"width": 1440, "height": 960})
    context = browser.new_context(**kwargs)
    context.route("http://127.0.0.1:8000/**", api_fixture)
    return context


def close_context(context, page, video: bool, name: str) -> None:
    recording = page.video if video else None
    context.close()
    if recording:
        destination = OUTPUT / "videos" / f"{name}.webm"
        destination.parent.mkdir(parents=True, exist_ok=True)
        recording.save_as(str(destination))
        recording.delete()


def capture_proof(browser, base_url: str, video: bool) -> None:
    context = new_context(browser, video, "proof")
    page = context.new_page()
    page.goto(f"{base_url}/practice?demo=1003", wait_until="networkidle")
    assert page.locator("[data-tab='lessonPrep']").is_hidden()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="大题", exact=True).click()
    page.locator("#proofStepInput").fill("已知 n 是偶数，因此存在整数 k，使得 n=2k。")
    page.locator("#addProofStepButton").click()
    page.locator("#proofStepInput").fill("所以 n²=(2k)²=4k²=2(2k²)。")
    page.locator("#addProofStepButton").click()
    page.locator("#proofStepInput").fill("2k² 是整数，因此 n² 是偶数。证毕。")
    page.locator("#finishProofButton").click()
    page.locator("#nextProofExplanationButton").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUTPUT / "01-proof-steps.png"), full_page=True)
    close_context(context, page, video, "01-proof-steps")


def capture_companion(browser, base_url: str) -> None:
    context = new_context(browser, False, "companion")
    page = context.new_page()
    page.goto(f"{base_url}/companion?demo=1003", wait_until="networkidle")
    page.locator("#generateCompanionButton").click()
    page.get_by_text("现在做什么", exact=True).wait_for()
    page.screenshot(path=str(OUTPUT / "04-learning-companion.png"), full_page=True)
    close_context(context, page, False, "companion")


def capture_fusion(browser, base_url: str, video: bool) -> None:
    context = new_context(browser, video, "fusion")
    page = context.new_page()
    page.goto(f"{base_url}/knowledge-graph?demo=1003", wait_until="networkidle")
    page.wait_for_timeout(500)
    page.get_by_role("button", name="融合导航").click()
    page.wait_for_timeout(600)
    page.locator("[data-fusion-kp='K010102']").click()
    page.wait_for_timeout(1200)
    page.screenshot(path=str(OUTPUT / "02-fusion-graph.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    metrics = page.evaluate("""() => ({
      body: document.body.scrollWidth,
      document: document.documentElement.scrollWidth,
      panel: document.querySelector('#graph .work-panel').getBoundingClientRect().toJSON(),
      toolbar: document.querySelector('.graph-toolbar').getBoundingClientRect().toJSON(),
      switcher: document.querySelector('.graph-view-switch').getBoundingClientRect().toJSON(),
      offenders: Array.from(document.querySelectorAll('*')).map(el => {
        const r = el.getBoundingClientRect();
        return {tag: el.tagName, id: el.id, cls: el.className, width: r.width, right: r.right};
      }).filter(x => x.width > 390 || x.right > 392).slice(0, 12)
    })""")
    if metrics["document"] > 392:
        raise AssertionError(f"mobile horizontal overflow: {metrics}")
    page.screenshot(path=str(OUTPUT / "02-fusion-graph-mobile.png"), full_page=False)
    close_context(context, page, video, "02-fusion-graph")


def capture_prep(browser, base_url: str, video: bool) -> None:
    context = new_context(browser, video, "prep")
    page = context.new_page()
    page.goto(f"{base_url}/lesson-prep?demo=2001&demoRole=teacher", wait_until="networkidle")
    assert page.locator("[data-tab='companion']").is_hidden()
    page.wait_for_timeout(500)
    page.locator("#generateLessonPrepButton").click()
    page.locator("#copyLessonPrepButton:not([disabled])").wait_for()
    page.wait_for_timeout(1400)
    page.screenshot(path=str(OUTPUT / "03-lesson-prep.png"), full_page=True)
    close_context(context, page, video, "03-lesson-prep")


def capture_agent(browser, base_url: str) -> None:
    context = new_context(browser, False, "agent")
    page = context.new_page()
    page.goto(f"{base_url}/chat?demo=1003", wait_until="networkidle")
    page.locator("#questionInput").fill("什么是等价关系？")
    page.locator("#askButton").click()
    page.locator(".message-channel.agent").wait_for()
    page.get_by_text("自反性、对称性和传递性", exact=False).wait_for()
    page.screenshot(path=str(OUTPUT / "05-agent-channel.png"), full_page=True)
    page.locator("#questionInput").fill("降级测试")
    page.locator("#askButton").click()
    page.locator(".message-channel.fallback").wait_for()
    page.get_by_text("基础模型降级回答", exact=False).wait_for()
    page.screenshot(path=str(OUTPUT / "05b-qwen-fallback.png"), full_page=True)
    close_context(context, page, False, "agent")


def capture_compliance(browser, base_url: str) -> None:
    context = new_context(browser, False, "compliance")
    page = context.new_page()
    page.goto(f"{base_url}/compliance?demo=1003", wait_until="networkidle")
    screenshots = [
        OUTPUT / "01-proof-steps.png",
        OUTPUT / "02-fusion-graph.png",
        OUTPUT / "05-agent-channel.png",
    ]
    for selector, screenshot in zip(
        ("#evidenceMaas", "#evidenceAgent", "#evidenceApplication"), screenshots
    ):
        page.locator(selector).set_input_files(str(screenshot))
    page.get_by_text("3 / 6", exact=True).wait_for()
    page.screenshot(path=str(OUTPUT / "06-compliance-evidence.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    page.evaluate("window.scrollTo(0, 0)")
    if page.evaluate("document.documentElement.scrollWidth") > 392:
        raise AssertionError("compliance page has mobile horizontal overflow")
    page.screenshot(path=str(OUTPUT / "06-compliance-mobile.png"), full_page=False)
    close_context(context, page, False, "compliance")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:5500")
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        capture_proof(browser, args.base_url.rstrip("/"), args.video)
        capture_fusion(browser, args.base_url.rstrip("/"), args.video)
        capture_prep(browser, args.base_url.rstrip("/"), args.video)
        capture_companion(browser, args.base_url.rstrip("/"))
        capture_agent(browser, args.base_url.rstrip("/"))
        capture_compliance(browser, args.base_url.rstrip("/"))
        browser.close()
    print(f"Team 4 demo artifacts: {OUTPUT}")


if __name__ == "__main__":
    main()
