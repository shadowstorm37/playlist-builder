"""
app.py

A simple browser-based GUI for the playlist pipeline, built with Streamlit.
Wraps the exact same functions used by main.py — no pipeline logic lives
here, just widgets and session state to drive it step by step.

Run with:
    streamlit run src/app.py
"""

import os
from datetime import date
import re

import streamlit as st

from interpreter import interpret_vibe, save_vibe_params
from candidate_search import find_candidates, save_candidates
from scorer import score_candidates, save_scores
from curator import merge_candidates_and_scores, curate, save_final_playlist
from spotify_client import (
    build_auth_manager,
    get_auth_url,
    complete_auth,
    get_current_user_id,
    create_playlist,
    add_tracks_to_playlist,
)


def _slugify(vibe: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", vibe.lower()).strip("-")
    return slug[:40]


st.set_page_config(page_title="Playlist Builder", page_icon="🎵", layout="centered")

SPOTIFY_GREEN = "#1DB954"
SPOTIFY_BLACK = "#121212"
SPOTIFY_DARK_GRAY = "#181818"
SPOTIFY_LIGHT_GRAY = "#B3B3B3"

st.markdown(
    f"""
    <style>
    .stApp {{
        background-color: {SPOTIFY_BLACK};
        color: white;
    }}
    h1, h2, h3, p, label, .stMarkdown {{
        color: white !important;
    }}
    .stCaption, .stCaption p {{
        color: {SPOTIFY_LIGHT_GRAY} !important;
    }}
    /* Buttons: Spotify green pill */
    .stButton > button {{
        background-color: {SPOTIFY_GREEN};
        color: black;
        border-radius: 500px;
        border: none;
        font-weight: 700;
        padding: 0.6rem 1.5rem;
        transition: transform 0.1s ease, background-color 0.1s ease;
    }}
    .stButton > button:hover {{
        background-color: #1ed760;
        transform: scale(1.02);
        color: black;
    }}
    /* Text inputs, text areas, sliders */
    .stTextInput > div > div > input,
    .stTextArea textarea {{
        background-color: {SPOTIFY_DARK_GRAY};
        color: white;
        border: 1px solid #2a2a2a;
        border-radius: 6px;
    }}
    .stSlider [data-baseweb="slider"] div div {{
        background-color: {SPOTIFY_GREEN} !important;
    }}
    /* Track cards in the review step */
    .track-card {{
        background-color: {SPOTIFY_DARK_GRAY};
        border-radius: 8px;
        padding: 10px 16px;
        margin-bottom: 6px;
        border-left: 3px solid {SPOTIFY_GREEN};
    }}
    .track-name {{
        font-weight: 700;
        color: white;
    }}
    .track-artist {{
        color: {SPOTIFY_LIGHT_GRAY};
        font-size: 0.9rem;
    }}
    .track-score {{
        color: {SPOTIFY_GREEN};
        font-weight: 700;
        float: right;
    }}
    a {{
        color: {SPOTIFY_GREEN} !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(f"<h1 style='color:{SPOTIFY_GREEN};'>🎵 Playlist Builder</h1>", unsafe_allow_html=True)
st.caption("Type a vibe, get a Spotify playlist.")

# ---- Step 1: Spotify login ----
if "sp" not in st.session_state:
    st.subheader("Step 1: Log in to Spotify")

    if "auth_manager" not in st.session_state:
        st.session_state.auth_manager = build_auth_manager()
        st.session_state.auth_url = get_auth_url(st.session_state.auth_manager)

    st.markdown(f"[Click here to log in to Spotify]({st.session_state.auth_url})")
    st.write("After approving, your browser will land on a page that looks broken — that's expected.")
    redirected_url = st.text_input("Paste the full URL from your browser's address bar here:")

    if st.button("Confirm login") and redirected_url:
        try:
            st.session_state.sp = complete_auth(st.session_state.auth_manager, redirected_url)
            st.session_state.user_id = get_current_user_id(st.session_state.sp)
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

    st.stop()  # don't show the rest of the app until logged in

# ---- Logged in ----
st.success(f"Logged in as: {st.session_state.user_id}")

# ---- Step 2: Vibe input ----
st.subheader("Step 2: Describe your vibe")
vibe = st.text_input("What's the vibe?", placeholder="e.g. upbeat road trip through the desert")
length = st.slider("Playlist length", min_value=5, max_value=40, value=20)
reference_text = st.text_area(
    "Optional: reference tracks (one per line, 'Artist - Title')",
    placeholder="Useful for niche/emerging genres — e.g.\nphritz - It's OK, I'm Here\nEli Bishop - Afternoon Bike Ride",
    height=80,
)

if st.button("Generate playlist") and vibe:
    reference_tracks = [line.strip() for line in reference_text.splitlines() if line.strip()] or None
    run_dir = os.path.join("data", "runs", f"{date.today().isoformat()}-{_slugify(vibe)}")

    with st.spinner("Interpreting vibe..."):
        vibe_params = interpret_vibe(vibe, reference_tracks=reference_tracks)
        save_vibe_params(vibe_params, run_dir)

    with st.spinner("Searching Spotify..."):
        candidates = find_candidates(st.session_state.sp, vibe_params, target_length=length)
        save_candidates(candidates, run_dir)

    if not candidates:
        st.warning("No candidates found for that vibe — try describing it differently.")
        st.stop()

    with st.spinner(f"Scoring {len(candidates)} candidates..."):
        scores = score_candidates(vibe, candidates)
        save_scores(scores, run_dir)

    merged = merge_candidates_and_scores(candidates, scores)
    final_list = curate(merged, target_length=length)
    save_final_playlist(final_list, run_dir)

    st.session_state.final_list = final_list
    st.session_state.vibe = vibe
    st.session_state.run_dir = run_dir

# ---- Step 3: Review and confirm ----
if "final_list" in st.session_state:
    st.subheader("Step 3: Review your playlist")
    for t in st.session_state.final_list:
        st.markdown(
            f"""
            <div class="track-card">
                <span class="track-score">{t['fit_score']}/10</span>
                <div class="track-name">{t['name']}</div>
                <div class="track-artist">{', '.join(t['artists'])}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if st.button("Create this playlist on Spotify"):
        playlist_name = f"{st.session_state.vibe.title()} (generated)"
        playlist = create_playlist(
            st.session_state.sp,
            st.session_state.user_id,
            name=playlist_name,
            description=f'Auto-generated from the vibe: "{st.session_state.vibe}"',
        )
        track_uris = [t["uri"] for t in st.session_state.final_list]
        add_tracks_to_playlist(st.session_state.sp, playlist["id"], track_uris)

        st.success(f"Created: {playlist_name}")
        st.markdown(f"[Open in Spotify]({playlist['external_urls']['spotify']})")