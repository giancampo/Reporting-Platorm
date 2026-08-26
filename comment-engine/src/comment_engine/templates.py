"""Layer 3 of the comment engine (action-plan.md §11): "Templates with
variants — 3-5 phrasings per sentence type, rotated, so monthly reports do
not read like photocopies."

Variant selection is deterministic (hashed from rule_key + a caller-supplied
seed, typically the period string) rather than random, so the snapshot tests
required by §13 ("given a fixed dataset, the generated text must be stable")
hold: the same period always renders the same variant, while different
periods get different phrasing.

Locale fallback follows §5: `en` is mandatory in every rule's `templates`
dict; `it` falls back to `en` when missing, never machine-translated.
"""

from __future__ import annotations

import hashlib

from .rules import CommentRule


class MissingEnglishTemplateError(ValueError):
    pass


def _variant_index(rule_key: str, seed: str, variant_count: int) -> int:
    digest = hashlib.sha256(f"{rule_key}:{seed}".encode("utf-8")).hexdigest()
    return int(digest, 16) % variant_count


def render_template(rule: CommentRule, locale: str, seed: str, tokens: dict[str, str]) -> str:
    # 'en' is mandatory on every rule regardless of which locale is being
    # rendered right now — checked upfront so a config gap surfaces at
    # authoring time, not only when an Italian-language report happens to
    # request a locale that has no fallback.
    if not rule.templates.get("en"):
        raise MissingEnglishTemplateError(
            f"Rule '{rule.rule_key}' has no 'en' templates — every rule must define at least English."
        )

    variants = rule.templates.get(locale)
    used_locale = locale
    if not variants:
        variants = rule.templates["en"]
        used_locale = "en"

    index = _variant_index(rule.rule_key, seed, len(variants))
    template = variants[index]

    try:
        return template.format(**tokens)
    except KeyError as exc:
        raise ValueError(
            f"Template for rule '{rule.rule_key}' ({used_locale}) references unknown token {exc}."
        ) from exc
