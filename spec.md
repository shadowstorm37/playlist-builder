# spec.md
 
## What this is
 
A CLI tool that takes a plain-English "vibe" description and produces a Spotify playlist
matching it. An LLM stands in for the recommendation logic Spotify no longer exposes to
outside developers (see README for the API-access background).
 
## Input / output
 
**Input:** a vibe string and a target length.
```
python src/main.py --vibe "upbeat road trip through the desert" --length 20
```
 
**Output:** a new playlist created in the user's Spotify account, plus a saved run
folder under `data/runs/<date>-<slug>/` containing the intermediate JSON at each stage,
so a run can be inspected or reproduced.
 
## Pipeline
 
### 1. Vibe → search params (`vibe_interpreter.py`)
Send the vibe string to Claude with a fixed JSON schema. Output includes:
- `genres`: list of candidate genre tags
- `era`: optional decade/year range
- `reference_artists`: artists whose sound fits the vibe (used as search seeds, not
  copied verbatim)
- `target_descriptors`: qualitative energy/valence/tempo targets in plain language
  (e.g. "high energy, upbeat, driving tempo") — since Spotify no longer exposes numeric
  audio features, these stay descriptive rather than numeric.
Output written to `vibe_params.json`.
 
### 2. Candidate search (`candidate_search.py`)
Use `vibe_params.json` to run Spotify Web API search queries (genre + keyword + artist-
adjacent search). Collect a candidate pool larger than the target length (e.g. 4-5x) so
the scoring step has enough to filter from.
Output written to `candidates.json`.
 
### 3. Scoring (`scorer.py`)
Send candidate tracks (artist + title, batched) back to Claude along with the original
vibe description. Ask it to score each candidate's fit and return structured JSON:
```json
{"track_id": "...", "fit_score": 0-10, "reason": "short justification"}
```
Output written to `scores.json`.
 
### 4. Curation (`curator.py`)
- Sort candidates by fit score.
- Dedupe so no single artist dominates (cap per artist, e.g. max 2 tracks).
- Trim to target length.
Output written to `final_playlist.json`.
### 5. Write-back (`spotify_client.py`)
Create a new playlist in the user's account and populate it with the final track list.
This step requires explicit confirmation before writing (print the final tracklist,
prompt y/n) since it's the one side-effectful step against the user's real account.
 
## Out of scope (v1)
 
- No numeric audio-feature scoring (Spotify no longer provides this publicly; not
  reimplementing audio analysis from raw files in v1).
- No playlist editing/updating — each run creates a new playlist rather than modifying
  an existing one.
- No UI — CLI only.
- No multi-user support — single Spotify account via personal OAuth app.
## Open questions
 
- How many candidates to pull per search (affects Claude API cost/latency)?
- Whether to cache vibe→params results for identical vibe strings to save API calls
  during testing.