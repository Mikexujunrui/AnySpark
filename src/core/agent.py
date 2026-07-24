# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Agent Core — classify content for long-input hinting.

NOTE: The autonomous while-loop in ``agent_loop.py`` now does its own
planning via tool_calls, so the legacy ``plan_actions`` / ``suggest_skill``
helpers have been removed. ``classify_content`` remains in use by
``routes/chat.py`` to inject a content-type hint when the user submits very
long text.
"""

import json

from .llm_client import chat

CLASSIFY_SYSTEM = """You are a content classifier for a novel writing assistant. Analyze the user's input and determine what type of content it is.

# Content Types
- setting_document: Pure worldbuilding, character profiles, cultivation systems, location descriptions. No narrative prose.
- novel_chapter: Complete or near-complete narrative prose with scenes, dialogue, plot progression. Looks like a book chapter.
- story_fragment: Partial narrative — an unfinished scene, a snippet of dialogue, a half-written paragraph.
- inspiration_note: A brief idea, brainstorm, "what if" question, or creative musing. Not structured.
- instruction: User is giving a command like "write chapter 5", "extract from this", "validate this". Not creative content.
- mixed: Contains multiple types — e.g. some setting text followed by a chapter draft.

# Rules
1. Output ONLY a JSON object with: type, confidence (0.0-1.0), reasoning (brief).
2. If the user clearly wants to WRITE (e.g. "/w ..."), classify as instruction.
3. If text is long (2000+ chars) and reads like prose, it's likely a chapter or fragment.
4. If text is short and asks "should I..." or "what if...", it's inspiration_note.

# Output format
{"type": "setting_document", "confidence": 0.9, "reasoning": "..."}"""


def classify_content(text: str) -> dict:
    """Determine what type of content the user submitted."""
    prompt = f"Classify this content:\n\n{text[:3000]}\n\nOutput JSON:"
    response = chat(prompt, system=CLASSIFY_SYSTEM, temperature=0.1, task="extraction")
    try:
        j = response.strip()
        if j.startswith("```"):
            j = j.split("\n", 1)[1]
        if j.endswith("```"):
            j = j.rsplit("\n", 1)[0]
        return json.loads(j.strip())
    except json.JSONDecodeError:
        return {"type": "setting_document", "confidence": 0.5, "reasoning": "classification failed"}
