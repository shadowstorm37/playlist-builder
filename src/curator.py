"""
curator.py

Takes the scored candidates from scorer.py and candidates.json's metadata,
merges them, and produces the final track list for the playlist:
sorted by fit score, capped per artist so no single artist dominates,
trimmed to the target playlist length.
"""

import os
import json

# Max tracks any single artist can contribute to the final playlist,
# even if several of their tracks scored well.
MAX_TRACKS_PER_ARTIST = 2


def merge_candidates_and_scores(candidates: list[dict], scores: list[dict]) -> list[dict]:
    """
    Join candidate metadata (id, uri, name, artists) with their fit scores
    (track_id, fit_score, reason) on the shared track id.
    Tracks with no matching score are dropped (shouldn't normally happen).
    """
    score_by_id = {s["track_id"]: s for s in scores}

    merged = []
    for track in candidates:
        score_entry = score_by_id.get(track["id"])
        if score_entry is None:
            continue  # no score found for this track, skip it
        merged.append(
            {
                **track,
                "fit_score": score_entry["fit_score"],
                "reason": score_entry["reason"],
            }
        )
    return merged


def curate(
    merged: list[dict],
    target_length: int = 20,
    max_per_artist: int = MAX_TRACKS_PER_ARTIST,
) -> list[dict]:
    """
    Sort by fit_score descending, cap per-artist contributions, and trim
    to target_length.
    """
    sorted_tracks = sorted(merged, key=lambda t: t["fit_score"], reverse=True)

    artist_counts: dict[str, int] = {}
    seen_songs: set[tuple[str, tuple[str, ...]]] = set()
    final_list = []

    for track in sorted_tracks:
        if len(final_list) >= target_length:
            break

        # Spotify sometimes lists the same song under multiple track IDs
        # (single vs. album version, remaster, etc.) — dedupe by normalized
        # name + artist so the same song can't be picked twice.
        song_key = (track["name"].strip().lower(), tuple(sorted(track["artists"])))
        if song_key in seen_songs:
            continue

        # A track can have multiple artists (features/collabs); check all of them
        # against the cap before including it.
        over_cap = any(
            artist_counts.get(artist, 0) >= max_per_artist for artist in track["artists"]
        )
        if over_cap:
            continue

        final_list.append(track)
        seen_songs.add(song_key)
        for artist in track["artists"]:
            artist_counts[artist] = artist_counts.get(artist, 0) + 1

    return final_list


def save_final_playlist(final_list: list[dict], run_dir: str) -> str:
    """Write the final track list to <run_dir>/final_playlist.json."""
    os.makedirs(run_dir, exist_ok=True)
    path = os.path.join(run_dir, "final_playlist.json")
    with open(path, "w") as f:
        json.dump(final_list, f, indent=2)
    return path


if __name__ == "__main__":
    # Quick manual smoke test with fake data, no API calls needed
    fake_candidates = [
        {"id": "abc123", "uri": "spotify:track:abc123", "name": "Sunset Drive", "artists": ["Test Artist"]},
        {"id": "def456", "uri": "spotify:track:def456", "name": "Rainy Sunday Blues", "artists": ["Another Artist"]},
        {"id": "ghi789", "uri": "spotify:track:ghi789", "name": "Highway Static", "artists": ["Test Artist"]},
        {"id": "jkl012", "uri": "spotify:track:jkl012", "name": "Dust and Chrome", "artists": ["Test Artist"]},
    ]
    fake_scores = [
        {"track_id": "abc123", "fit_score": 9, "reason": "Great driving energy"},
        {"track_id": "def456", "fit_score": 1, "reason": "Wrong mood entirely"},
        {"track_id": "ghi789", "fit_score": 8, "reason": "Also fits well"},
        {"track_id": "jkl012", "fit_score": 7, "reason": "Fits, but same artist as two above"},
    ]

    merged = merge_candidates_and_scores(fake_candidates, fake_scores)
    final = curate(merged, target_length=20, max_per_artist=2)

    print(f"Final playlist ({len(final)} tracks):\n")
    for t in final:
        print(f"  - {t['name']} — {', '.join(t['artists'])} (score: {t['fit_score']})")