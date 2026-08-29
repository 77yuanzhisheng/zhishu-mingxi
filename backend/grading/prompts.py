'''Versioned prompts for the three-stage grading pipeline.'''

from __future__ import annotations

import json


PROMPT_VERSION = 'grading-v1.1-fast'

RUBRIC = {
    'conclusion_correctness': 20,
    'key_reasoning_steps': 35,
    'logical_rigor': 25,
    'definition_theorem_usage': 10,
    'expression_notation': 10,
}


def _context_block(context) -> str:
    return json.dumps(
        {
            'question': context.question,
            'reference_answer': context.reference_answer,
            'knowledge_points': context.knowledge_points,
            'grading guide': context.grading_guides,
        },
        ensure_ascii=False,
    )


def grading_messages(context, student_answer: str) -> list[dict[str, str]]:
    """Request all auditable grading artifacts in one concise model response."""
    return [
        {
            'role': 'system',
            'content': (
                'You are a rigorous discrete mathematics grader. Return one valid JSON object only, '
                'with no markdown. Be concise: at most 3 items in each analysis list and evidence list; '
                'feedback must be Chinese and no more than 120 Chinese characters.'
            ),
        },
        {
            'role': 'user',
            'content': (
                f'{_context_block(context)}\nstudent_answer: {student_answer}\n'
                f'rubric maximums: {json.dumps(RUBRIC)}\n'
                'Allowed error_types: circular_reasoning, jump_step, theorem_misuse, notation_error, conclusion_error. '
                'Return {analysis:{key_steps:[string],missing_steps:[string],error_candidates:[string]},'
                'approved:true,dimension_scores:{all five keys},error_types:[allowed values],'
                'evidence:[{dimension:key,student_excerpt:string,reason:string}],feedback:string,review_notes:string}. '
                'Grade only reasoning that the student explicitly wrote.'
            ),
        },
    ]


def analysis_messages(context, student_answer: str) -> list[dict[str, str]]:
    return [
        {
            'role': 'system',
            'content': 'You are a rigorous discrete mathematics grading analyst. Return JSON only.',
        },
        {
            'role': 'user',
            'content': f'{_context_block(context)}\nstudent_answer: {student_answer}\nReturn {{key_steps:[string],missing_steps:[string],error_candidates:[string]}}.',
        },
    ]


def scoring_messages(context, student_answer: str, analysis: dict) -> list[dict[str, str]]:
    return [
        {
            'role': 'system',
            'content': 'Grade only from evidence. Return JSON only; do not award points for unstated reasoning.',
        },
        {
            'role': 'user',
            'content': f'{_context_block(context)}\nstudent_answer: {student_answer}\nanalysis: {json.dumps(analysis, ensure_ascii=False)}\nrubric maximums: {json.dumps(RUBRIC)}\nAllowed error_types: circular_reasoning, jump_step, theorem_misuse, notation_error, conclusion_error. Return {{dimension_scores:{{all five keys}},error_types:[allowed values],evidence:[{{dimension:key,student_excerpt:string,reason:string}}],feedback:string}}.',
        },
    ]


def review_messages(context, student_answer: str, scoring: dict) -> list[dict[str, str]]:
    return [
        {
            'role': 'system',
            'content': 'Act as an independent grading reviewer. Return JSON only and preserve the constrained rubric.',
        },
        {
            'role': 'user',
            'content': f'{_context_block(context)}\nstudent_answer: {student_answer}\nproposed scoring: {json.dumps(scoring, ensure_ascii=False)}\nRecheck every score against the answer and reference. Return {{approved:true,dimension_scores:{{all five keys}},error_types:[allowed values],evidence:[{{dimension:key,student_excerpt:string,reason:string}}],feedback:string,review_notes:string}}. The evidence must support the final scores and error types; use an empty list only when no concrete issue is present. Correct unsupported scores before approving.',
        },
    ]


def repair_messages(stage: str, invalid_output: str, error: str) -> list[dict[str, str]]:
    contracts = {
        'analysis': 'Return {key_steps:[string],missing_steps:[string],error_candidates:[string]}.',
        'scoring': 'Return a valid scoring JSON object with all five dimension scores, allowed error_types, evidence, and feedback.',
        'review': 'Return {approved:true,dimension_scores:{all five keys},error_types:[allowed values],evidence:[objects],feedback:string,review_notes:string}. approved must be the JSON boolean true.',
    }
    return [
        {
            'role': 'system',
            'content': 'Repair the following output into valid JSON only. Do not add markdown or explanations.',
        },
        {
            'role': 'user',
            'content': 'stage: {}\nvalidation error: {}\n{}\ninvalid output:\n{}'.format(
                stage, error, contracts.get(stage, 'Return a valid JSON object.'), invalid_output
            ),
        },
    ]

