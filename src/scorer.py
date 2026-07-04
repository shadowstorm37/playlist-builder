"""
scorer.py

Scores each candidate track (from candidate_search.py) against the original
vibe description, using Gemini as the taste model. This replaces the
numeric audio-feature scoring Spotify no longer exposes publicly.
"""

import os
import json
import re
import time
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = "gemini-3.5-flash"

# Batch size for candidates sent per API call, keeps prompts small
# and makes it easier to isolate a bad response to a specific batch.
BATCH_SIZE = 15

# Free-tier pacing: stay comfortably under ~10 requests/minute by spacing
# calls at least this many seconds apart, rather than firing them back to
# back and relying on hitting the limit before backing off.
MIN_SECONDS_BETWEEN_CALLS = 7

# If a 429 does happen anyway, how long to wait before retrying, and how
# many times to retry before giving up.
RATE_LIMIT_COOLDOWN_SECONDS = 60
MAX_RATE_LIMIT_RETRIES = 3

_last_call_time = 0.0


def _pace_call() -> None:
    """Sleep if needed so calls stay at least MIN_SECONDS_BETWEEN_CALLS apart."""
    global _last_call_time
    elapsed = time.time() - _last_call_time
    if elapsed < MIN_SECONDS_BETWEEN_CALLS:
        time.sleep(MIN_SECONDS_BETWEEN_CALLS - elapsed)
    _last_call_time = time.time()


def _classify_error(e: Exception) -> str:
    """
    Classify an API error by inspecting its message rather than its exact
    class — the google-genai SDK's exception classes live under a private
    module path that can change between versions, so message-matching is
    more stable than importing from it directly.

    Returns "quota_exhausted", "rate_limited", or "other".
    """
    message = str(e).lower()
    if "not have enough quota" in message or "quota_exceeded" in message:
        return "quota_exhausted"
    if "429" in message or "too_many_requests" in message or "rate limit" in message:
        return "rate_limited"
    return "other"


def _call_gemini(client: genai.Client, prompt: str) -> str:
    """
    Call Gemini with proactive pacing and reactive backoff on transient
    rate limits. Raises immediately (no retry) on quota exhaustion, since
    that won't resolve by waiting a minute — see the message it surfaces.
    """
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        _pace_call()
        try:
            interaction = client.interactions.create(model=MODEL, input=prompt)
            return interaction.output_text
        except Exception as e:
            kind = _classify_error(e)

            if kind == "quota_exhausted":
                raise RuntimeError(
                    "Gemini quota is exhausted (not just rate-limited per minute). "
                    "Waiting won't fix this on its own — check your usage/reset time at "
                    "https://ai.dev/usage?tab=rate-limit, or wait for the daily quota "
                    "to reset, or add billing. Original error: " + str(e)
                ) from e

            if kind == "rate_limited" and attempt < MAX_RATE_LIMIT_RETRIES:
                print(
                    f"Hit Gemini rate limit (attempt {attempt + 1}/{MAX_RATE_LIMIT_RETRIES}). "
                    f"Cooling down for {RATE_LIMIT_COOLDOWN_SECONDS}s..."
                )
                time.sleep(RATE_LIMIT_COOLDOWN_SECONDS)
                continue

            raise

PROMPT_TEMPLATE = """You are scoring how well songs fit a specific vibe for a
playlist. For each track below, give a fit score from 0-10 (10 = perfect fit)
and a short one-sentence reason.

Vibe: "{vibe}"

Tracks:
{track_list}

Return ONLY a JSON array (no markdown fences, no commentary), one object per
track, in this exact shape:

[
  {{"track_id": "...", "fit_score": 0-10, "reason": "short justification"}}
]

Use the exact track_id values given above. Return one object per track, in
any order. IMPORTANT: never use double quote characters (") inside the
"reason" text, even to reference a song title — this breaks JSON parsing.
If you need to reference a title, write it without quotes or use single
quotes instead."""


def _get_client() -> genai.Client:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY in .env")
    return genai.Client(api_key=api_key)


def _clean_json_text(text: str) -> str:
    """Strip markdown code fences if the model adds them despite instructions."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
        if text.startswith("json"):
            text = text[len("json"):]
    return text.strip()


def _format_track_list(batch: list[dict]) -> str:
    lines = []
    for t in batch:
        artists = ", ".join(t["artists"])
        lines.append(f'- track_id: {t["id"]} | "{t["name"]}" by {artists}')
    return "\n".join(lines)


def _attempt_json_repair(text: str) -> str:
    """
    Best-effort fix for a common LLM mistake: unescaped double quotes inside
    a "reason" string (e.g. referencing a song title in quotes), which
    otherwise terminates the JSON string early and breaks parsing.

    Finds "reason": "..." spans and escapes any inner double quotes that
    aren't already escaped and aren't the span's own closing quote.
    """
    def fix_reason(match: re.Match) -> str:
        inner = match.group(1)
        # Escape any quote not already escaped
        fixed_inner = re.sub(r'(?<!\\)"', r'\\"', inner)
        return f'"reason": "{fixed_inner}"'

    # Matches "reason": "<anything, greedy up to the last quote before a
    # comma/brace>" — good enough for the common single-offender case.
    pattern = r'"reason":\s*"(.*?)"\s*(?=[,}])'
    return re.sub(pattern, fix_reason, text, flags=re.DOTALL)


def _score_batch(client: genai.Client, vibe: str, batch: list[dict], max_retries: int = 2) -> list[dict]:
    prompt = PROMPT_TEMPLATE.format(vibe=vibe, track_list=_format_track_list(batch))

    last_error = None
    for attempt in range(max_retries + 1):
        raw_text = _call_gemini(client, prompt)
        cleaned = _clean_json_text(raw_text)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try a best-effort repair before giving up on this attempt
            try:
                result = json.loads(_attempt_json_repair(cleaned))
            except json.JSONDecodeError as e:
                last_error = ValueError(
                    f"Gemini did not return valid JSON for a batch "
                    f"(attempt {attempt + 1}/{max_retries + 1}).\nRaw response:\n{raw_text}"
                )
                last_error.__cause__ = e
                continue  # retry

        if not isinstance(result, list):
            last_error = ValueError(f"Expected a JSON array, got: {type(result)}")
            continue

        return result

    raise last_error


def score_candidates(vibe: str, candidates: list[dict]) -> list[dict]:
    """
    Score every candidate track against the vibe. Batches requests to keep
    prompts manageable. Returns a flat list of
    {track_id, fit_score, reason} dicts across all batches.
    """
    client = _get_client()
    all_scores = []

    for i in range(0, len(candidates), BATCH_SIZE):
        batch = candidates[i : i + BATCH_SIZE]
        batch_scores = _score_batch(client, vibe, batch)
        all_scores.extend(batch_scores)

    return all_scores


def save_scores(scores: list[dict], run_dir: str) -> str:
    """Write scores to <run_dir>/scores.json and return the file path."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "scores.json")
    with open(path, "w") as f:
        json.dump(scores, f, indent=2)
    return path


if __name__ == "__main__":
    # Quick manual smoke test with a couple of fake candidates
    test_vibe = "upbeat road trip through the desert"
    fake_candidates = [
        {"id": "abc123", "name": "Sunset Drive", "artists": ["Test Artist"]},
        {"id": "def456", "name": "Rainy Sunday Blues", "artists": ["Another Artist"]},
    ]
    scores = score_candidates(test_vibe, fake_candidates)
    print(json.dumps(scores, indent=2))