"""
spotify_client.py

Handles all direct interaction with the Spotify Web API:
- Authenticating as the user (OAuth)
- Searching the catalog for candidate tracks
- Creating a playlist and populating it with final track selections

Requires SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI
to be set in .env (see .env.example).
"""

import os
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

# Scopes needed:
# - playlist-modify-public / playlist-modify-private: to create + fill playlists
# - user-read-private: to fetch the current user's ID
SCOPES = "playlist-modify-public playlist-modify-private user-read-private"


def get_client() -> spotipy.Spotify:
    """
    Authenticate as the current user via OAuth and return a Spotipy client.

    First run will open a browser window for login/consent; spotipy caches
    the resulting token locally (.cache file) so subsequent runs won't
    re-prompt unless the token expires or scopes change.
    """
    client_id = os.getenv("SPOTIPY_CLIENT_ID")
    client_secret = os.getenv("SPOTIPY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIPY_REDIRECT_URI")

    if not all([client_id, client_secret, redirect_uri]):
        raise EnvironmentError(
            "Missing Spotify credentials. Check that SPOTIPY_CLIENT_ID, "
            "SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI are set in .env"
        )

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPES,
        open_browser=False,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_current_user_id(sp: spotipy.Spotify) -> str:
    """Return the Spotify user ID for the authenticated account."""
    return sp.current_user()["id"]


def search_tracks(sp: spotipy.Spotify, query: str, limit: int = 20) -> list[dict]:
    """
    Search the Spotify catalog for tracks matching a query string.

    query examples: "genre:emo", "artist:Origami Angel", "road trip"
    Returns a simplified list of track dicts: id, uri, name, artists, popularity.
    """
    limit = min(limit, 50)  # Spotify API max per request
    results = sp.search(q=query, type="track", limit=limit)
    tracks = results.get("tracks", {}).get("items", [])

    return [
        {
            "id": t["id"],
            "uri": t["uri"],
            "name": t["name"],
            "artists": [a["name"] for a in t["artists"]],
            "popularity": t.get("popularity"),
        }
        for t in tracks
    ]


def create_playlist(
    sp: spotipy.Spotify, user_id: str, name: str, description: str = "", public: bool = False
) -> dict:
    """
    Create a new (empty) playlist on the user's account.
    Returns the playlist object, including its id and external URL.
    """
    playlist = sp.user_playlist_create(
        user=user_id, name=name, public=public, description=description
    )
    return playlist


def add_tracks_to_playlist(sp: spotipy.Spotify, playlist_id: str, track_uris: list[str]) -> None:
    """
    Add tracks to an existing playlist. Spotify allows max 100 URIs per request,
    so this batches automatically.
    """
    batch_size = 100
    for i in range(0, len(track_uris), batch_size):
        batch = track_uris[i : i + batch_size]
        sp.playlist_add_items(playlist_id, batch)


if __name__ == "__main__":
    # Quick manual smoke test: confirms auth works and prints your user ID.
    sp = get_client()
    user_id = get_current_user_id(sp)
    print(f"Authenticated as: {user_id}")

    sample = search_tracks(sp, "genre:midwest emo", limit=5)
    print(f"\nSample search results ({len(sample)} tracks):")
    for track in sample:
        print(f"  - {track['name']} — {', '.join(track['artists'])}")