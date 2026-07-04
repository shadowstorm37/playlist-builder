"""
vibe_interpreter.py

Turns a plain-English vibe description into structured search parameters
that candidate_search.py can use to query the Spotify catalog.

Uses the Gemini API (free tier) instead of Claude, so this step costs nothing
to run. Swap out the client/model below if you'd rather use Claude later.
"""

import os
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = "gemini-3.5-flash"

PROMPT_TEMPLATE = """You are helping generate a Spotify playlist. Given a vibe
description, output ONLY a JSON object (no markdown fences, no commentary)
with this exact shape:

{{
  "genres": ["list", "of", "candidate", "spotify", "genre", "tags"],
  "era": "optional decade or year range, or null",
  "reference_artists": ["artists", "whose", "sound", "fits", "this", "vibe"],
  "target_descriptors": "a short plain-language description of the target energy,
    valence, and tempo, e.g. 'high energy, upbeat, driving tempo'"
}}

Vibe: "{vibe}"
{reference_section}
Return ONLY the JSON object, nothing else."""

REFERENCE_SECTION_TEMPLATE = """
This vibe may refer to a niche or emerging genre/scene that you may not have
strong knowledge of. Here are real example tracks the person considers a
perfect fit — use them as your primary signal for genres and reference
artists, rather than guessing from the vibe label alone:
{track_list}
"""


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


def interpret_vibe(vibe: str, reference_tracks: list[str] | None = None) -> dict:
    """
    Send a vibe description to Gemini and return the parsed search-params dict.

    reference_tracks: optional list of "Artist - Title" strings the user
    already knows fit the vibe. Useful for niche/emerging genres (e.g.
    microgenres from SoundCloud scenes) that a general-purpose LLM may not
    have strong knowledge of from the genre name alone — grounds the
    interpretation in real examples instead of a guessed label.

    Raises ValueError if the model's response isn't valid JSON.
    """
    client = _get_client()

    if reference_tracks:
        track_list = "\n".join(f"- {t}" for t in reference_tracks)
        reference_section = REFERENCE_SECTION_TEMPLATE.format(track_list=track_list)
    else:
        reference_section = ""

    prompt = PROMPT_TEMPLATE.format(vibe=vibe, reference_section=reference_section)

    interaction = client.interactions.create(model=MODEL, input=prompt)
    raw_text = interaction.output_text

    cleaned = _clean_json_text(raw_text)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Gemini did not return valid JSON.\nRaw response:\n{raw_text}"
        ) from e


def save_vibe_params(params: dict, run_dir: str) -> str:
    """Write params to <run_dir>/vibe_params.json and return the file path."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "vibe_params.json")
    with open(path, "w") as f:
        json.dump(params, f, indent=2)
    return path


if __name__ == "__main__":
    # Quick manual smoke test — grounding a niche genre with real examples
    test_vibe = "botanica"
    test_references = [
        "phritz - It's OK, I'm Here",
        "Eli Bishop - Afternoon Bike Ride",
    ]
    print(f"Vibe: {test_vibe}\n")
    params = interpret_vibe(test_vibe, reference_tracks=test_references)
    print(json.dumps(params, indent=2))