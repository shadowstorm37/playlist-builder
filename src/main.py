"""
main.py

CLI entry point. Wires together the whole pipeline:
  vibe string -> interpreter -> candidate_search -> scorer -> curator
  -> spotify_client (create + populate playlist)

This file contains no real logic of its own — it just calls the functions
already built and tested in the other src/ files, in order, and saves each
stage's output into a timestamped run folder under data/runs/.

Usage:
    python3 src/main.py --vibe "upbeat road trip through the desert" --length 20
"""

import argparse
import os
import re
from datetime import date

from interpreter import interpret_vibe, save_vibe_params
from candidate_search import find_candidates, save_candidates
from scorer import score_candidates, save_scores
from curator import merge_candidates_and_scores, curate, save_final_playlist
from spotify_client import (
    get_client,
    get_current_user_id,
    create_playlist,
    add_tracks_to_playlist,
)


def _slugify(vibe: str) -> str:
    """Turn a vibe string into a short filesystem-safe slug for the run folder name."""
    slug = re.sub(r"[^a-z0-9]+", "-", vibe.lower()).strip("-")
    return slug[:40]  # keep folder names reasonably short


def run(vibe: str, length: int) -> None:
    run_dir = os.path.join("data", "runs", f"{date.today().isoformat()}-{_slugify(vibe)}")
    print(f"Run folder: {run_dir}\n")

    # 1. Vibe -> search params
    print("Interpreting vibe...")
    vibe_params = interpret_vibe(vibe)
    save_vibe_params(vibe_params, run_dir)
    print(f"  genres: {vibe_params.get('genres')}")
    print(f"  reference artists: {vibe_params.get('reference_artists')}\n")

    # 2. Auth + candidate search
    print("Authenticating with Spotify...")
    sp = get_client()
    user_id = get_current_user_id(sp)
    print(f"  authenticated as: {user_id}\n")

    print("Searching for candidate tracks...")
    candidates = find_candidates(sp, vibe_params, target_length=length)
    save_candidates(candidates, run_dir)
    print(f"  found {len(candidates)} candidates\n")

    if not candidates:
        print("No candidates found — try a different vibe description. Stopping.")
        return

    # 3. Score candidates against the vibe
    print("Scoring candidates...")
    scores = score_candidates(vibe, candidates)
    save_scores(scores, run_dir)
    print(f"  scored {len(scores)} tracks\n")

    # 4. Curate final list
    merged = merge_candidates_and_scores(candidates, scores)
    final_list = curate(merged, target_length=length)
    save_final_playlist(final_list, run_dir)

    print(f"Final playlist ({len(final_list)} tracks):\n")
    for t in final_list:
        print(f"  - {t['name']} — {', '.join(t['artists'])} (score: {t['fit_score']})")

    # 5. Confirm before writing to the user's real Spotify account
    print()
    confirm = input("Create this playlist on your Spotify account? [y/N]: ").strip().lower()
    if confirm != "y":
        print("Not creating playlist. Run data saved locally under:", run_dir)
        return

    playlist_name = f"{vibe.title()} (generated)"
    playlist = create_playlist(
        sp,
        user_id,
        name=playlist_name,
        description=f'Auto-generated from the vibe: "{vibe}"',
    )
    track_uris = [t["uri"] for t in final_list]
    add_tracks_to_playlist(sp, playlist["id"], track_uris)

    print(f"\nCreated playlist: {playlist_name}")
    print(f"Link: {playlist['external_urls']['spotify']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a Spotify playlist from a vibe description.")
    parser.add_argument("--vibe", required=True, help="Plain-English description of the desired vibe.")
    parser.add_argument("--length", type=int, default=20, help="Target number of tracks (default: 20).")
    args = parser.parse_args()

    run(args.vibe, args.length)