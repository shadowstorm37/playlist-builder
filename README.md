# playlist-builder

Type a vibe, get a Spotify playlist.

## Why this exists

Spotify's own app can turn a mood into a playlist (AI DJ, Discover Weekly, Blend) using
internal recommendation models — but that logic was never exposed to outside developers.
In November 2024, Spotify restricted the public Web API endpoints
(`/audio-features`, `/audio-analysis`, `/recommendations`, `/related-artists`) that
third-party apps used to rely on for that kind of curation, citing concerns about the
data being used to train competing AI models.

This project rebuilds that missing piece from the outside: instead of pulling Spotify's
audio-feature numbers, it uses an LLM (Gemini) as the taste model. You describe a vibe
in plain English, the LLM turns that into search parameters and scores candidate tracks
against the vibe, and the result gets assembled into a real Spotify playlist in your
account.

## How it works

1. **Vibe → search params** — Gemini turns a free-text description ("upbeat road trip
   through the desert") into genres, era, adjacent artists, and target energy/valence
   descriptors.
2. **Catalog search** — those params drive Spotify Web API search queries to gather
   candidate tracks.
3. **Scoring** — each candidate gets scored against the original vibe by Gemini.
4. **Curation** — top-scoring tracks are deduped by song and by artist, then trimmed to
   your target length.
5. **Playlist creation** — the final list gets written to a new playlist on your Spotify
   account, after you confirm.

---

## Setup

### 1. Prerequisites

- Python 3.11 or newer — check with `python3 --version`
- A Spotify account (free or Premium both work)
- A Google account (for a free Gemini API key)

### 2. Clone the repo and install dependencies

```bash
git clone <your-repo-url>
cd playlist-builder
pip install -r requirements.txt --break-system-packages
```

The `--break-system-packages` flag is needed on newer Debian/Ubuntu systems where pip
refuses to install outside a virtual environment. If you'd rather use a virtual
environment instead, that works too:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Get a Spotify Developer app (free, ~2 minutes)

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and
   log in with your normal Spotify account.
2. Click **Create app**.
3. Fill in any name/description. For **Redirect URI**, enter exactly:
   ```
   http://127.0.0.1:8888/callback
   ```
   (Spotify requires `127.0.0.1`, not `localhost`, for this kind of redirect.)
4. Check the box for **Web API**, then **Save**.
5. On the app's **Settings** page, copy the **Client ID**, and click **View client
   secret** to reveal and copy the **Client Secret**.

### 4. Get a free Gemini API key

1. Go to [aistudio.google.com](https://aistudio.google.com) (or
   [ai.google.dev](https://ai.google.dev)) and log in.
2. Find **Get API key** / **API keys** in the menu and create a new key.
3. Copy it — this project uses Gemini's free tier, so this shouldn't cost anything for
   normal personal use. (Free-tier quotas do exist and can run out — see
   [Troubleshooting](#troubleshooting) below.)

### 5. Create your `.env` file

Copy the example file and fill in the four values you just collected:

```bash
cp .env.example .env
```

Then edit `.env` so it looks like:

```
SPOTIPY_CLIENT_ID=your_spotify_client_id
SPOTIPY_CLIENT_SECRET=your_spotify_client_secret
SPOTIPY_REDIRECT_URI=http://127.0.0.1:8888/callback
GEMINI_API_KEY=your_gemini_api_key
```

`.env` is git-ignored — it stays on your machine only.

---

## Running it

There are two ways to use this: a command-line version, or a browser-based GUI.

### Option A: Command line

```bash
python3 src/main.py --vibe "upbeat road trip through the desert" --length 15
```

- `--vibe` (required): a plain-English description of the mood/style you want.
- `--length` (optional, default 20): how many tracks to aim for.
- `--reference-tracks` (optional): comma-separated `Artist - Title` examples. Useful for
  niche or emerging genres the LLM might not recognize from the genre name alone, e.g.:
  ```bash
  python3 src/main.py --vibe "botanica" --reference-tracks "phritz - It's OK I'm Here, Eli Bishop - Afternoon Bike Ride"
  ```

The first time you run it, it'll print a Spotify login URL. Open it in any browser, log
in, approve access, and you'll land on a page that looks broken (e.g. "site can't be
reached") — that's expected. Copy the full URL from your browser's address bar and paste
it back into the terminal when prompted.

The script will show you the generated tracklist and ask for confirmation before
creating anything on your actual Spotify account.

### Option B: Browser GUI (Streamlit)

```bash
pip install streamlit --break-system-packages
cd src
streamlit run app.py
```

This opens a form in your browser: log in to Spotify (same paste-the-redirect-URL flow
as above, just via a text box instead of the terminal), type a vibe, adjust the length
slider, and click through to generate and create the playlist.

---

## Project structure

```
playlist-builder/
├── .env                  # your real credentials (git-ignored)
├── .env.example          # template showing which variables are needed
├── requirements.txt
├── spec.md               # design doc / planning notes
├── data/
│   └── runs/             # each run's saved JSON (vibe params, candidates, scores, final list)
└── src/
    ├── main.py           # CLI entry point
    ├── app.py            # Streamlit GUI entry point
    ├── interpreter.py    # vibe text -> structured search params (Gemini)
    ├── candidate_search.py  # search params -> real Spotify candidate tracks
    ├── scorer.py          # scores candidates against the vibe (Gemini)
    ├── curator.py          # sorts, dedupes, trims to final track list
    └── spotify_client.py   # Spotify auth, search, playlist creation
```

---

## Troubleshooting

**"Invalid limit" error from Spotify search** — Spotify's search API has been
inconsistent about enforcing a lower request limit than its documented max of 50 for
standard developer apps since their February 2026 API migration. This is already
accounted for in `candidate_search.py` (requests are capped conservatively), but if you
still hit it, try lowering `RESULTS_PER_QUERY` in that file further.

**403 Forbidden when creating a playlist or adding tracks** — Spotify's February 2026 Web
API migration moved playlist creation to `/me/playlists` and track-adding to
`/playlists/{id}/items`. This is already handled in `spotify_client.py`; if you see 403s
here, double check you're on the latest version of that file.

**Gemini "you do not have enough quota" error** — this means your free-tier quota is
exhausted, not just rate-limited per minute — waiting a few seconds won't fix it. Check
your usage and reset time at [ai.dev/usage](https://ai.dev/usage?tab=rate-limit).
Free-tier quotas are commonly daily. If you need to keep testing sooner, either wait for
the reset, or create a new API key under a *separate* Google Cloud project (a new key on
the same project shares the same exhausted quota).

**`ModuleNotFoundError` when running a script** — most files in `src/` import each other
as plain siblings (e.g. `from spotify_client import ...`), so they need to be run from
inside the `src/` folder, not the project root:
```bash
cd src
python3 main.py --vibe "..."
```

**No browser available / "site can't be reached" after Spotify login** — expected
behavior on headless or remote setups. The auth flow doesn't rely on the redirect
actually loading anything; just copy the URL your browser lands on (even though it
looks broken) and paste it back when prompted.

---

## Notes on cost

- **Spotify's Web API** is free for personal-scale use like this.
- **Gemini** is used on the free tier by default — normal usage for generating a handful
  of playlists should stay well within free limits, but very heavy use (many long runs
  back-to-back) can hit daily quota caps.
