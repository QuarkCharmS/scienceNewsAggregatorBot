"""Claude AI integration for ranking and summarizing science articles."""

import json
import logging
import re
import anthropic

logger = logging.getLogger(__name__)

CLIENT = anthropic.Anthropic()
MODEL = "claude-sonnet-4-5"


def build_prompt(articles: list[dict], top_n: int, topic: str, bilingual: bool = True) -> str:
    articles_text = ""
    for i, article in enumerate(articles):
        articles_text += (
            f"[{i}] Source: {article['source']}\n"
            f"    Title: {article['title']}\n"
            f"    Summary: {article['summary'] or '(no summary)'}\n"
            f"    Link: {article['link']}\n\n"
        )

    if bilingual:
        language_instructions = (
            "For each selected article you must write content in BOTH Spanish and English:\n"
            "- Spanish: everyday words only, answer \"why does this matter / why is this cool?\", no jargon without explanation.\n"
            "- English: same style and quality as the Spanish version — plain, engaging, no dry academic phrasing.\n"
            "- Both versions must avoid \"researchers found\" or \"the study shows\" — just tell the story directly."
        )
        task_step_2 = "For each, write a 2-3 sentence explanation in Spanish AND a 2-3 sentence explanation in English."
        task_step_3 = "Translate the title to Spanish as well (keep the English original too)."
        json_fields = (
            "- \"title_es\": the article title translated to Spanish\n"
            "- \"title_en\": the original article title in English\n"
            "- \"explanation_es\": your 2-3 sentence plain-language explanation in Spanish\n"
            "- \"explanation_en\": your 2-3 sentence plain-language explanation in English"
        )
    else:
        language_instructions = (
            "For each selected article write a plain-language explanation in English only:\n"
            "- Everyday words, answer \"why does this matter / why is this cool?\", no jargon without explanation.\n"
            "- Avoid \"researchers found\" or \"the study shows\" — just tell the story directly."
        )
        task_step_2 = "For each, write a 2-3 sentence plain-language explanation in English."
        task_step_3 = "Keep the title in English — do not translate."
        json_fields = (
            "- \"title_en\": the original article title in English\n"
            "- \"explanation_en\": your 2-3 sentence plain-language explanation in English"
        )

    return f"""You are a science communicator writing for a curious but non-technical audience — \
think curious teenagers or adults with no science background. Make science feel exciting and \
accessible, never intimidating.

This digest is strictly focused on: {topic}
IMPORTANT: If an article is not clearly and directly related to these topics, do NOT select it — \
skip it entirely, even if it seems interesting. Off-topic articles (legal news, politics, lifestyle, \
business, sports, food, entertainment) must never be included.

{language_instructions}

Below are {len(articles)} articles published today. Your task:
1. Select the {top_n} most important articles that are strictly on-topic ({topic}).
2. {task_step_2}
3. {task_step_3}
4. Assign one relevant emoji per article.
5. If there are not enough on-topic articles to fill {top_n} slots, return fewer — do not pad with off-topic content.

Return ONLY a JSON array with exactly {top_n} objects. Each object must have these fields:
- "id": the integer index from the list above (e.g. 0, 3, 12)
- "emoji": one emoji string
{json_fields}
- "link": the original article link (copy exactly)
- "source": the original source name (copy exactly)

Do not include any text outside the JSON array.

Articles:
{articles_text}"""


def rank_and_summarize(articles: list[dict], top_n: int = 5, topic: str = "general science and technology", bilingual: bool = True) -> list[dict]:
    """Send articles to Claude and get back the top top_n with explanations."""
    if not articles:
        raise ValueError("No articles provided to rank.")

    prompt = build_prompt(articles, top_n, topic, bilingual)

    try:
        message = CLIENT.messages.create(
            model=MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error: %s", exc)
        raise

    raw = message.content[0].text.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("Claude returned invalid JSON: %s\nRaw response:\n%s", exc, raw)
        raise

    if not isinstance(results, list) or len(results) == 0:
        raise ValueError(f"Unexpected Claude response structure: {results!r}")

    if len(results) < top_n:
        logger.warning("Claude returned %d articles (fewer than requested %d) — likely not enough on-topic content.", len(results), top_n)

    # Validate required fields
    required = {"emoji", "title_es", "title_en", "explanation_es", "explanation_en", "link", "source"} if bilingual else {"emoji", "title_en", "explanation_en", "link", "source"}
    for item in results:
        missing = required - set(item.keys())
        if missing:
            raise ValueError(f"Claude result missing fields {missing}: {item!r}")

    logger.info("Claude selected %d articles", len(results))
    return results[:top_n]


def translate_apod(apod: dict) -> dict:
    """Translate APOD title and explanation to Spanish for a non-technical audience.

    Returns a dict with keys: title_es, explanation_es.
    """
    prompt = f"""Eres un divulgador científico. Traduce al español el título y la explicación \
de la Imagen Astronómica del Día de la NASA para un público sin formación técnica.

Reglas:
- Usa palabras cotidianas. Si un término técnico es inevitable, explícalo brevemente en la misma oración.
- Mantén la maravilla y el asombro del texto original.
- La explicación traducida puede resumir o simplificar si el original es muy largo, pero debe tener \
al menos 3 oraciones.

Title: {apod['title']}
Explanation: {apod['explanation']}

Return ONLY a JSON object with exactly two fields:
- "title_es": the title translated to Spanish
- "explanation_es": the explanation translated and adapted to Spanish

Do not include any text outside the JSON object."""

    try:
        message = CLIENT.messages.create(
            model=MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error translating APOD: %s", exc)
        raise

    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    result = json.loads(raw)
    logger.info("APOD translated: '%s'", result.get("title_es"))
    return result
