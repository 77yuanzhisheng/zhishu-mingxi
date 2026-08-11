"""
RAG 演示脚本 — 知识库 + Qwen 模型串联测试
==========================================

用法：
    python scripts/test_rag.py "什么是德摩根律？"
    python scripts/test_rag.py                     # 交互模式

前提：
    1. 队员2知识库服务已启动: python main.py --api  (端口8001)
    2. 队员1 SSH隧道已建立: ssh -L 8000:localhost:8000 -p 40174 root@connect.nmb2.seetacloud.com
"""

import sys
import os
import re
import requests
import json

KB_API = "http://127.0.0.1:8001"
LLM_API = "https://api.siliconflow.cn/v1/chat/completions"
LLM_MODEL = "Qwen/Qwen3-8B"
LLM_KEY = "sk-nutahzvbrebohdcnylkexacxkkcxnwfehxpnvotwvnzrudas"


def search_knowledge(query: str, top_k: int = 5):
    """调用知识库检索（队员2）"""
    resp = requests.get(
        f"{KB_API}/kb/search",
        params={"q": query, "top_k": top_k, "min_score": 0.2},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def ask_llm(messages: list, max_tokens: int = 800):
    """调用 Qwen 模型（队员1 提供：硅基流动 API）"""
    resp = requests.post(
        LLM_API,
        headers={"Authorization": f"Bearer {LLM_KEY}"},
        json={
            "model": LLM_MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3,
            "enable_thinking": False,
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def rag_query(question: str) -> dict:
    """完整 RAG 流程"""
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"{'='*60}")

    # Step 1: 知识库检索
    print("\n[Step 1] 检索知识库...")
    kb = search_knowledge(question)

    if not kb["results"]:
        print("  未找到相关知识")
        contexts = ""
    else:
        print(f"  找到 {kb['total_hits']} 条结果")
        for i, item in enumerate(kb["results"]):
            src = item["metadata"]["source_document"]
            ch = item["metadata"].get("chapter", "")
            pg = item["metadata"].get("page_start", "?")
            score = item["score"]
            print(f"  [{i+1}] score={score:.3f} | {src[:25]} | {ch} (p.{pg})")

        # 拼接上下文
        context_parts = []
        for item in kb["results"]:
            meta = item["metadata"]
            src = meta["source_document"]
            ch = meta.get("chapter", "")
            pg = meta.get("page_start", "?")
            context_parts.append(
                f"【来源：{src}，{ch}，第{pg}页】\n{item['content']}"
            )
        contexts = "\n\n---\n\n".join(context_parts)

    # Step 2: 构建 Prompt 发送给 LLM
    print("\n[Step 2] 调用 Qwen 模型...")

    system_prompt = """你是一位离散数学智能助教，名为"知数·明析"。你的职责是帮助学生学习离散数学。

请严格遵循以下规则：
1. 仅根据提供的参考资料回答问题
2. 如果资料中没有相关信息，请明确告知学生
3. 回答时标注信息来源（章节和页码）
4. 数学公式使用 LaTeX 格式，如 $A \\cup B$、$$P \\rightarrow Q$$
5. 对复杂概念进行分步讲解，引导思考"""

    if contexts:
        user_prompt = f"""## 参考资料
{contexts}

## 学生问题
{question}

请根据以上参考资料回答学生的问题。"""
    else:
        user_prompt = f"""## 学生问题
{question}

注意：知识库中未找到相关资料，请根据你的知识回答，并提醒学生这只是通用解答。"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    answer = ask_llm(messages)
    print(f"  回复长度: {len(answer)} 字符")

    # Step 3: 输出结果
    print(f"\n[回答]")
    print(f"{'─'*60}")
    print(answer)
    print(f"{'─'*60}")

    return {
        "question": question,
        "kb_results": kb,
        "answer": answer,
    }


def interactive():
    """交互模式"""
    print("=" * 60)
    print("  知数·明析 — RAG 问答测试")
    print("=" * 60)
    print("  输入 quit 退出")
    print("-" * 60)

    # 检查服务
    print("\n检查服务状态...")
    try:
        r = requests.get(f"{KB_API}/api/health", timeout=5)
        print(f"  知识库: ✓ ({KB_API})")
    except Exception:
        print(f"  知识库: ✗ 请先启动 python main.py --api")
        return

    try:
        r = requests.post(LLM_API, headers={"Authorization": f"Bearer {LLM_KEY}"}, json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 10,
        }, timeout=10)
        print(f"  Qwen模型: ✓ ({LLM_MODEL})")
    except Exception as e:
        print(f"  Qwen模型: ✗ 无法连接硅基流动API")
        print(f"    错误: {e}")
        return

    print()
    while True:
        try:
            q = input("你: ").strip()
            if q.lower() in ("quit", "exit", "q"):
                break
            if not q:
                continue
            rag_query(q)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"出错: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        rag_query(sys.argv[1])
    else:
        interactive()
