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

    Uses the manual auth-code flow: prints a login URL, you log in in any
    browser (doesn't need to be the same machine), then paste back the
    full URL you were redirected to (even though that page shows an error
    like "site can't be reached" — that's expected, the code is in the URL).
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

    auth_url = auth_manager.get_authorize_url()
    print(f"\nGo to this URL and log in:\n{auth_url}\n")
    response_url = input(
        "After approving, paste the full URL you were redirected to "
        "(the page will look broken — that's fine, just copy the address bar): "
    ).strip()

    code = auth_manager.parse_response_code(response_url)
    token_info = auth_manager.get_access_token(code, as_dict=True)

    return spotipy.Spotify(auth=token_info["access_token"])


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
    Create a new (empty) playlist on the authenticated user's account.

    Note: this posts to /me/playlists rather than /users/{user_id}/playlists.
    Spotify's February 2026 Web API migration removed the latter endpoint for
    standard developer apps — it now returns 403 Forbidden regardless of
    scopes or user ID correctness. /me/playlists is the documented
    replacement and doesn't need the user ID in the URL at all.
    `user_id` is kept as a parameter for interface compatibility but isn't
    used in the request itself.
    """
    payload = {"name": name, "public": public, "description": description}
    playlist = sp._post("me/playlists", payload=payload)
    return playlist


def add_tracks_to_playlist(sp: spotipy.Spotify, playlist_id: str, track_uris: list[str]) -> None:
    """
    Add tracks to an existing playlist. Spotify allows max 100 URIs per request,
    so this batches automatically.

    Note: posts to /playlists/{playlist_id}/items rather than the older
    /playlists/{playlist_id}/tracks — Spotify's February 2026 migration moved
    this endpoint too, and the old path now returns 403 Forbidden.
    """
    batch_size = 100
    for i in range(0, len(track_uris), batch_size):
        batch = track_uris[i : i + batch_size]
        sp._post(f"playlists/{playlist_id}/items", payload={"uris": batch})


if __name__ == "__main__":
    # Quick manual smoke test: confirms auth works and prints your user ID.
    sp = get_client()
    user_id = get_current_user_id(sp)
    print(f"Authenticated as: {user_id}")

    sample = search_tracks(sp, "genre:midwest emo", limit=5)
    print(f"\nSample search results ({len(sample)} tracks):")
    for track in sample:
        print(f"  - {track['name']} — {', '.join(track['artists'])}")