from __future__ import annotations

from typing import Dict, List


def build_question_record(
    concept: Dict[str, object], concepts: List[Dict[str, object]], filename: str
) -> Dict[str, object]:
    del filename
    question = f"Which statement best explains {concept['name']}?"
    answer = str(concept["summary"]).strip()
    distractors = [
        str(other["summary"]).strip()
        for other in concepts
        if other["name"] != concept["name"] and str(other["summary"]).strip() != answer
    ][:3]
    explanation = f"The correct answer captures the core meaning of {concept['name']} without relying on a heading or source label."
    return {
        "question": question,
        "answer": answer,
        "distractors": distractors,
        "explanation": explanation,
        "difficulty_value": 0.45,
    }
