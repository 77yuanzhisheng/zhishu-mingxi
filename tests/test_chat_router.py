import importlib


chat_router = importlib.import_module("backend.chat.router")


PROOF_QUESTION = "\u8bc1\u660e\u547d\u9898\u903b\u8f91\u4e2d\u7684\u5fb7\u6469\u6839\u5f8b\uff1a\u00ac(P\u2227Q) \u21d4 \u00acP\u2228\u00acQ"
GENERAL_QUESTION = "\u4ec0\u4e48\u662f\u96c6\u5408\uff1f"


def test_build_messages_enables_symbolic_reasoning_for_proof():
    contexts = [
        {
            "content": "\u5fb7\u6469\u6839\u5f8b\u53ef\u4ee5\u901a\u8fc7\u771f\u503c\u8868\u8bc1\u660e\u3002",
            "metadata": {"source_document": "\u547d\u9898\u903b\u8f91.md", "chapter": "\u547d\u9898\u903b\u8f91", "page_start": 1},
            "score": 0.9,
        }
    ]

    payload = chat_router.build_chat_payload(PROOF_QUESTION, contexts)

    assert payload.reasoning_enabled is True
    assert payload.symbolic_check.checked is True
    assert "\u5df2\u77e5" in payload.messages[0]["content"]
    assert "\u63a8\u5bfc" in payload.messages[0]["content"]
    assert "\u7a0b\u5e8f\u4fa7\u7b26\u53f7\u6821\u9a8c\u7ed3\u679c" in payload.messages[1]["content"]
    assert "T" in payload.symbolic_check.evidence


def test_build_messages_keeps_general_question_unforced():
    payload = chat_router.build_chat_payload(GENERAL_QUESTION, [])

    assert payload.reasoning_enabled is False
    assert payload.symbolic_check.checked is False
    assert "\u5df2\u77e5" not in payload.messages[0]["content"]
    assert "\u8bc1\u6bd5" not in payload.messages[0]["content"]


def test_chat_endpoint_returns_reasoning_metadata():
    async def fake_search_knowledge(question, top_k, min_score):
        return [
            {
                "content": "\u5fb7\u6469\u6839\u5f8b\uff1a\u00ac(P\u2227Q) \u21d4 \u00acP\u2228\u00acQ\u3002",
                "metadata": {"source_document": "\u547d\u9898\u903b\u8f91.md", "chapter": "\u547d\u9898\u903b\u8f91", "page_start": 1},
                "score": 0.88,
            }
        ]

    async def fake_call_llm(messages, max_tokens):
        assert "\u7a0b\u5e8f\u4fa7\u7b26\u53f7\u6821\u9a8c\u7ed3\u679c" in messages[1]["content"]
        return """### 1. \u5df2\u77e5
\u76ee\u6807\uff1a\u8bc1\u660e \u00ac(P\u2227Q) \u21d4 \u00acP\u2228\u00acQ\u3002
### 2. \u5206\u6790
\u4f7f\u7528\u771f\u503c\u8868\u6cd5\u3002
### 3. \u63a8\u5bfc
\u6b65\u9aa41\uff1a\u5217\u51fa P,Q \u7684\u771f\u503c\u7ec4\u5408\uff1b\u4f9d\u636e\uff1a\u771f\u503c\u8868\u5b9a\u4e49\u3002
\u6b65\u9aa42\uff1a\u6bd4\u8f83\u4e24\u4fa7\u771f\u503c\u76f8\u540c\uff1b\u4f9d\u636e\uff1a\u7b49\u4ef7\u547d\u9898\u5b9a\u4e49\u3002
### 4. \u81ea\u68c0
\u6bcf\u4e00\u884c\u5747\u4e00\u81f4\u3002
### 5. \u7ed3\u8bba
\u00ac(P\u2227Q) \u21d4 \u00acP\u2228\u00acQ \u6210\u7acb\u3002
### 6. \u8bc1\u6bd5"""

    original_search = chat_router.search_knowledge
    original_call = chat_router.call_llm
    chat_router.search_knowledge = fake_search_knowledge
    chat_router.call_llm = fake_call_llm
    try:
        import anyio

        response = anyio.run(chat_router.chat, chat_router.ChatRequest(message=PROOF_QUESTION))
    finally:
        chat_router.search_knowledge = original_search
        chat_router.call_llm = original_call

    assert response.answer.endswith("\u8bc1\u6bd5")
    assert response.reasoning["enabled"] is True
    assert response.reasoning["symbolic_check"]["checked"] is True
    assert response.reasoning["evaluation"]["passed"] is True
    assert response.reasoning["proof_plan"]["enabled"] is True
    assert response.sources[0]["source_document"] == "\u547d\u9898\u903b\u8f91.md"



def test_chat_payload_injects_proof_plan():
    payload = chat_router.build_chat_payload("\u8bc1\u660e\u96c6\u5408\u6052\u7b49\u5f0f\uff1a(A\u222aB)^c = A^c\u2229B^c", [])

    assert payload.proof_plan.enabled is True
    assert payload.proof_plan.method == "element_chasing"
    assert "\u7b26\u53f7\u8bc1\u660e\u8ba1\u5212" in payload.messages[1]["content"]
    assert "element_chasing" in payload.messages[1]["content"]

def test_chat_payload_injects_quantifier_proof_plan():
    payload = chat_router.build_chat_payload("证明量词否定律：¬∀xP(x) ⇔ ∃x¬P(x)", [])

    assert payload.proof_plan.enabled is True
    assert payload.proof_plan.method == "quantifier_transformation"
    assert "量词" in payload.messages[1]["content"]
    assert "quantifier negation" in payload.messages[1]["content"]
