'''Local integration with the structured question bank maintained by team two.'''

from __future__ import annotations

from dataclasses import dataclass

from backend.kb.structured import get_structured_questions


@dataclass(frozen=True)
class GradingContext:
    question_id: str | None
    question_type: str
    question: str
    reference_answer: str
    knowledge_points: list[str]
    grading_guides: dict[str, dict]


def resolve_grading_context(
    *,
    question_id: str | None,
    question: str | None,
    reference_answer: str | None,
    knowledge_points: list[str],
) -> GradingContext:
    '''Resolve a request without making an HTTP call back into this service.'''

    if question_id:
        found = next(
            (
                item
                for item in get_structured_questions(limit=1000)['questions']
                if item['id'] == question_id
            ),
            None,
        )
        if found is None:
            raise LookupError(f'question_id not found: {question_id}')
        resolved_kps = list(dict.fromkeys([*knowledge_points, found['kp']]))
        from backend.kb.structured import GRADING_GUIDE

        guides = {}
        for kp in resolved_kps:
            guide = found['grading_guide'] if kp == found['kp'] else GRADING_GUIDE.get(kp)
            if guide:
                guides[kp] = guide
        return GradingContext(
            question_type=found.get('type', 'direct'),
            question_id=question_id,
            question=found['question'],
            reference_answer=found['answer'],
            knowledge_points=resolved_kps,
            grading_guides=guides,
        )

    from backend.kb.structured import GRADING_GUIDE

    guides = {kp: GRADING_GUIDE[kp] for kp in knowledge_points if kp in GRADING_GUIDE}
    return GradingContext(
        question_id=None,
        question_type='direct',
        question=question or '',
        reference_answer=reference_answer or '',
        knowledge_points=knowledge_points,
        grading_guides=guides,
    )
