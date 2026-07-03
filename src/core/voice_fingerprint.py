# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (c) 2026 徐俊瑞 (Junrui Xu). Commercial licensing rights reserved.

"""Character voice fingerprint — extract per-character dialogue style from chapters.

Analyzes each character's dialogue corpus to build a "voice fingerprint"
covering vocabulary, sentence patterns, catchphrases, and emotional tendency.
The fingerprint is injected into writing prompts to ensure consistent
character voice across chapters.

Pure-function statistics, no LLM calls. Relies on graph_store for character
roster and json_store for chapter content.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from data.json_store import json_store

# Minimal Chinese stop words for vocabulary analysis
_STOP_WORDS: frozenset[str] = frozenset({
    "的", "了", "是", "在", "我", "你", "他", "她", "它", "们", "这", "那",
    "一个", "什么", "怎么", "为什么", "不", "没", "有", "就", "都", "也",
    "还", "又", "只", "才", "却", "但", "而", "及", "与", "或", "把", "被",
    "对", "给", "向", "从", "到", "于", "为", "以", "其", "之", "者", "所",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
})

# Emotional lexicon (subset of pacing_analyzer's lexicon)
_EMOTION_POSITIVE = frozenset({"高兴", "快乐", "开心", "兴奋", "笑", "爱", "喜欢", "希望", "美好", "温暖"})
_EMOTION_NEGATIVE = frozenset({"悲伤", "愤怒", "恐惧", "绝望", "恨", "哭", "死", "杀", "痛", "怒"})
_EMOTION_NEUTRAL = frozenset({"说", "想", "看", "知道", "明白", "嗯", "哦", "啊", "吧", "呢"})


@dataclass
class VoiceFingerprint:
    """Statistical voice profile for a single character."""

    character_id: str = ""
    character_name: str = ""
    dialogue_count: int = 0         # total dialogue lines
    total_dialogue_chars: int = 0   # total characters in dialogues
    top_words: list[dict] = field(default_factory=list)  # [{word, count}]
    avg_sentence_length: float = 0.0
    sentence_pattern_ratio: dict = field(default_factory=dict)
    # {"declarative": 0.x, "interrogative": 0.x, "exclamatory": 0.x, "rhetorical": 0.x}
    catchphrases: list[str] = field(default_factory=list)  # repeated n-grams
    emotional_tendency: str = "neutral"  # passionate / cold / irritable / gloomy / neutral

    def to_dict(self) -> dict[str, Any]:
        return {
            "character_id": self.character_id,
            "character_name": self.character_name,
            "dialogue_count": self.dialogue_count,
            "total_dialogue_chars": self.total_dialogue_chars,
            "top_words": self.top_words,
            "avg_sentence_length": round(self.avg_sentence_length, 1),
            "sentence_pattern_ratio": {k: round(v, 3) for k, v in self.sentence_pattern_ratio.items()},
            "catchphrases": self.catchphrases,
            "emotional_tendency": self.emotional_tendency,
        }


# ── Dialogue extraction ──

_DIALOGUE_PATTERN = re.compile(r'\u201c([^\u201d]+)\u201d')
_CORNER_BRACKET_PATTERN = re.compile(r'\u300c([^\u300d]+)\u300d')


def _extract_all_dialogues(content: str) -> list[str]:
    """Extract all dialogue lines from chapter content."""
    lines: list[str] = []
    for m in _DIALOGUE_PATTERN.finditer(content):
        lines.append(m.group(1))
    for m in _CORNER_BRACKET_PATTERN.finditer(content):
        lines.append(m.group(1))
    return lines


def _find_speaker(dialogue: str, content: str, char_names: list[str]) -> str | None:
    """Find which character said a given dialogue by looking at context.

    Looks at the text preceding the dialogue for character name mentions.
    """
    # Find the dialogue position in content
    pos = content.find(f"\u201c{dialogue}\u201d")
    if pos < 0:
        pos = content.find(dialogue)
    if pos < 0:
        return None

    # Look at the 50 characters before the dialogue
    context = content[max(0, pos - 50):pos]

    # Find the closest character name mention
    best_match: str | None = None
    best_pos = -1
    for name in char_names:
        idx = context.rfind(name)
        if idx >= 0 and idx > best_pos:
            best_pos = idx
            best_match = name
    return best_match


def extract_dialogues(
    chapters: list[dict],
    char_names: list[str],
) -> dict[str, list[str]]:
    """Extract dialogue lines per character from all chapters.

    Args:
        chapters: List of chapter dicts (with versions).
        char_names: List of character names (including aliases).

    Returns:
        Dict mapping character name → list of dialogue strings.
    """
    result: dict[str, list[str]] = {name: [] for name in char_names}

    for ch in chapters:
        cur = json_store._get_current_version(ch)
        content = cur.get("content", "")
        dialogues = _extract_all_dialogues(content)

        for d in dialogues:
            speaker = _find_speaker(d, content, char_names)
            if speaker and speaker in result:
                result[speaker].append(d)

    return result


# ── Voice analysis ──


def _compute_top_words(dialogues: list[str], top_n: int = 20) -> list[dict]:
    """Compute top-N frequent words (2-4 char tokens) in dialogues."""
    counter: Counter[str] = Counter()
    for d in dialogues:
        # Simple 2-char sliding window for Chinese
        clean = d.replace(" ", "").replace("\n", "")
        for i in range(len(clean) - 1):
            token = clean[i : i + 2]
            if token not in _STOP_WORDS and len(token) >= 2:
                counter[token] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]


def _compute_sentence_patterns(dialogues: list[str]) -> dict[str, float]:
    """Compute sentence pattern ratios (declarative/interrogative/exclamatory)."""
    total = len(dialogues) or 1
    declarative = 0
    interrogative = 0
    exclamatory = 0

    for d in dialogues:
        if d.endswith("？") or d.endswith("?"):
            interrogative += 1
        elif d.endswith("！") or d.endswith("!"):
            exclamatory += 1
        else:
            declarative += 1

    return {
        "declarative": declarative / total,
        "interrogative": interrogative / total,
        "exclamatory": exclamatory / total,
    }


def _find_catchphrases(dialogues: list[str], min_repeats: int = 3) -> list[str]:
    """Find repeated short phrases across dialogues (catchphrases).

    Uses 4-gram frequency analysis. Returns phrases that appear in at least
    min_repeats different dialogue lines.
    """
    ngram_sources: list[str] = []
    for d in dialogues:
        clean = d.replace(" ", "").replace("\n", "")
        if len(clean) >= 4:
            for i in range(len(clean) - 3):
                ngram_sources.append(clean[i : i + 4])

    counter = Counter(ngram_sources)
    catchphrases: list[str] = []
    for phrase, count in counter.most_common(20):
        if count >= min_repeats:
            catchphrases.append(phrase)
    return catchphrases[:10]


def _compute_emotional_tendency(dialogues: list[str]) -> str:
    """Classify emotional tendency from dialogue content."""
    if not dialogues:
        return "neutral"

    pos_count = 0
    neg_count = 0
    for d in dialogues:
        pos_count += sum(1 for w in _EMOTION_POSITIVE if w in d)
        neg_count += sum(1 for w in _EMOTION_NEGATIVE if w in d)

    total = pos_count + neg_count
    if total == 0:
        return "neutral"
    ratio = neg_count / total

    if ratio > 0.65:
        return "gloomy"    # 阴沉
    elif ratio > 0.45:
        return "irritable"  # 暴躁
    elif ratio < 0.2:
        return "passionate"  # 热情
    elif ratio < 0.35:
        return "cold"       # 冷淡
    return "neutral"


def analyze_voice(dialogues: list[str], character_name: str = "", character_id: str = "") -> VoiceFingerprint:
    """Analyze a character's dialogue corpus and build a voice fingerprint.

    Pure function — no side effects.
    """
    if not dialogues:
        return VoiceFingerprint(
            character_id=character_id,
            character_name=character_name,
            emotional_tendency="neutral",
        )

    total_chars = sum(len(d) for d in dialogues)

    # Sentence lengths
    sentence_lengths = [len(d.replace(" ", "")) for d in dialogues]
    avg_len = statistics.mean(sentence_lengths) if sentence_lengths else 0.0

    return VoiceFingerprint(
        character_id=character_id,
        character_name=character_name,
        dialogue_count=len(dialogues),
        total_dialogue_chars=total_chars,
        top_words=_compute_top_words(dialogues),
        avg_sentence_length=avg_len,
        sentence_pattern_ratio=_compute_sentence_patterns(dialogues),
        catchphrases=_find_catchphrases(dialogues),
        emotional_tendency=_compute_emotional_tendency(dialogues),
    )


def build_voice_prompt(fingerprint: VoiceFingerprint) -> str:
    """Generate a prompt fragment for injecting character voice constraints.

    This text is designed to be appended to the character's setting block
    in the writing system prompt, ensuring dialogue consistency.
    """
    if fingerprint.dialogue_count < 3:
        return ""  # Not enough data for a meaningful fingerprint

    parts: list[str] = [f"【{fingerprint.character_name}的语言风格】"]

    if fingerprint.emotional_tendency != "neutral":
        tendency_map = {
            "passionate": "热情奔放",
            "cold": "冷淡简洁",
            "irritable": "急躁易怒",
            "gloomy": "阴沉压抑",
            "neutral": "平稳中性",
        }
        parts.append(f"语气倾向：{tendency_map.get(fingerprint.emotional_tendency, '中性')}")

    if fingerprint.avg_sentence_length > 0:
        if fingerprint.avg_sentence_length < 10:
            parts.append("句式简短有力，多用短句")
        elif fingerprint.avg_sentence_length > 25:
            parts.append("说话冗长，常长篇大论")
        else:
            parts.append("句式长短适中")

    patterns = fingerprint.sentence_pattern_ratio
    if patterns:
        if patterns.get("interrogative", 0) > 0.3:
            parts.append("爱提问，常反问")
        if patterns.get("exclamatory", 0) > 0.25:
            parts.append("情感外露，多用感叹")

    if fingerprint.catchphrases:
        parts.append(f"口头禅/高频用语：{'、'.join(fingerprint.catchphrases[:5])}")

    if fingerprint.top_words:
        top5 = "、".join(w["word"] for w in fingerprint.top_words[:5])
        parts.append(f"高频用词：{top5}")

    return "\n".join(parts)


def get_character_voice(book_id: str, character_name: str) -> VoiceFingerprint:
    """Get voice fingerprint for a specific character by name.

    Loads chapters and extracts dialogues attributed to the character.
    """
    from core.graph_store import GraphStore

    chapters = json_store.load_chapters(book_id)

    # Get character list from graph store
    store = GraphStore()
    entities = store.get_entities(book_id)
    char_names: list[str] = []
    char_id = ""

    for ent in entities:
        if ent.get("type") == "character":
            name = ent.get("name", "")
            if name:
                char_names.append(name)
                if name == character_name:
                    char_id = ent.get("id", "")
            # Also check aliases
            aliases = ent.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if alias and alias not in char_names:
                        char_names.append(alias)

    if character_name not in char_names:
        char_names.append(character_name)

    dialogues_map = extract_dialogues(chapters, char_names)
    char_dialogues = dialogues_map.get(character_name, [])

    return analyze_voice(
        dialogues=char_dialogues,
        character_name=character_name,
        character_id=char_id,
    )


def get_all_voice_fingerprints(book_id: str) -> list[VoiceFingerprint]:
    """Get voice fingerprints for all characters in a book."""
    from core.graph_store import GraphStore

    chapters = json_store.load_chapters(book_id)
    store = GraphStore()
    entities = store.get_entities(book_id)

    char_names: list[str] = []
    char_ids: dict[str, str] = {}

    for ent in entities:
        if ent.get("type") == "character":
            name = ent.get("name", "")
            if name and name not in char_names:
                char_names.append(name)
                char_ids[name] = ent.get("id", "")
            aliases = ent.get("aliases", [])
            if isinstance(aliases, list):
                for alias in aliases:
                    if alias and alias not in char_names:
                        char_names.append(alias)

    dialogues_map = extract_dialogues(chapters, char_names)

    results: list[VoiceFingerprint] = []
    for name in char_names:
        if name in char_ids:  # Only primary names, not aliases
            dialogues = dialogues_map.get(name, [])
            results.append(analyze_voice(
                dialogues=dialogues,
                character_name=name,
                character_id=char_ids.get(name, ""),
            ))

    return results
