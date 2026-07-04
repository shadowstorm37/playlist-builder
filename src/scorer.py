"""
scorer.py
 
Scores each candidate track (from candidate_search.py) against the original
vibe description, using Gemini as the taste model. This replaces the
numeric audio-feature scoring Spotify no longer exposes publicly.
"""
 
import os
import json
from dotenv import load_dotenv
from google import genai
 
load_dotenv()
 
MODEL = "gemini-3.5-flash"
 
# Batch size for candidates sent per API call, keeps prompts small
# and makes it easier to isolate a bad response to a specific batch.
BATCH_SIZE = 15
 
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
any order."""
 
 
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
 
 
def _score_batch(client: genai.Client, vibe: str, batch: list[dict]) -> list[dict]:
    prompt = PROMPT_TEMPLATE.format(vibe=vibe, track_list=_format_track_list(batch))
    interaction = client.interactions.create(model=MODEL, input=prompt)
    raw_text = interaction.output_text
    cleaned = _clean_json_text(raw_text)
 
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini did not return valid JSON for a batch.\nRaw response:\n{raw_text}"
        ) from e
 
    if not isinstance(result, list):
        raise ValueError(f"Expected a JSON array, got: {type(result)}")
 
    return result
 
 
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