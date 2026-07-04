"""
candidate_search.py

Takes the structured output of vibe_interpreter.py (genres, era, reference
artists, target descriptors) and turns it into real Spotify Web API search
queries, collecting a pool of candidate tracks for scorer.py to evaluate.

Spotify's /recommendations endpoint is deprecated for new apps, so this file
is the manual stand-in: it builds its own search queries instead of asking
Spotify for recommendations directly.
"""

import os
import re
import json

from spotify_client import get_client, search_tracks

# How many candidates to gather relative to the final target playlist length.
# A bigger pool gives scorer.py more to filter from.
POOL_MULTIPLIER = 5

# Max results to pull per individual search query (Spotify caps at 50).
RESULTS_PER_QUERY = 10


def _parse_year_range(era: str | None) -> str | None:
    """
    Convert a loose era string (e.g. "2010s - 2020s", "1990s", null) into a
    Spotify search year filter like "2010-2029". Returns None if no years
    can be found.
    """
    if not era:
        return None

    years = [int(y) for y in re.findall(r"\d{4}", era)]
    if not years:
        return None

    start = min(years)
    end = max(years) if len(years) > 1 else start + 9
    return f"{start}-{end}"


def build_search_queries(vibe_params: dict) -> list[str]:
    """
    Build a list of Spotify search query strings from vibe_params.
    Combines genre tags and reference artists, each optionally scoped to
    an era, so multiple angles are covered.
    """
    genres = vibe_params.get("genres", [])
    reference_artists = vibe_params.get("reference_artists", [])
    year_range = _parse_year_range(vibe_params.get("era"))

    queries = []

    for genre in genres:
        # Note: Spotify's genre: field filter reliably returns empty results
        # for standard developer apps (likely tied to the same genre-taxonomy
        # systems deprecated alongside /recommendations in Nov 2024). Use the
        # genre tag as a plain keyword instead of a strict field filter.
        query = genre
        if year_range:
            query += f" year:{year_range}"
        queries.append(query)

    for artist in reference_artists:
        query = f'artist:"{artist}"'
        if year_range:
            query += f" year:{year_range}"
        queries.append(query)

    return queries


def find_candidates(sp, vibe_params: dict, target_length: int = 20) -> list[dict]:
    """
    Run all search queries derived from vibe_params, dedupe results by
    track id, and return a candidate pool sized around
    target_length * POOL_MULTIPLIER (fewer if searches don't turn up enough).
    """
    queries = build_search_queries(vibe_params)
    pool_target = target_length * POOL_MULTIPLIER

    seen_ids = set()
    candidates = []

    for query in queries:
        if len(candidates) >= pool_target:
            break

        results = search_tracks(sp, query, limit=RESULTS_PER_QUERY)
        for track in results:
            if track["id"] not in seen_ids:
                seen_ids.add(track["id"])
                candidates.append(track)

    return candidates[:pool_target]


def save_candidates(candidates: list[dict], run_dir: str) -> str:
    """Write candidates to <run_dir>/candidates.json and return the file path."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "candidates.json")
    with open(path, "w") as f:
        json.dump(candidates, f, indent=2)
    return path


if __name__ == "__main__":
    # Quick manual smoke test using the vibe_params shape interpreter.py
    # produces for "upbeat road trip through the desert"
    test_vibe_params = {
        "genres": ["desert rock", "indie rock"],
        "era": "2010s - 2020s",
        "reference_artists": ["Queens of the Stone Age", "Khruangbin"],
        "target_descriptors": "high energy, warm and sunny valence, driving tempo",
    }

    sp = get_client()
    candidates = find_candidates(sp, test_vibe_params, target_length=20)

    print(f"Found {len(candidates)} candidates:\n")
    for c in candidates[:10]:
        print(f"  - {c['name']} — {', '.join(c['artists'])}")