"""CardioPath IC — consolidated investment committee site.

Single Streamlit app with:
  1. Login gate (any UN/PW works — confidential warning)
  2. After login, tabs:
     - 📊 IC Dashboard
     - 🎲 Monte Carlo
     - 🗳️ Vote
     - 📈 Vote Results

Run locally:
  streamlit run app.py

Deploy:
  - Streamlit Community Cloud (recommended): push to GitHub, link repo at share.streamlit.io
  - Vercel (via Docker): see README.md
"""

import streamlit as st

# ---------- Page config (must be first Streamlit call) ----------
st.set_page_config(
    page_title="CardioPath IC — Investment Committee",
    page_icon="🫀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Lazy imports — only loaded after auth (heavy modules)
from dashboard_tab import render as render_dashboard
from montecarlo_tab import render as render_montecarlo
from vote_tab import render_vote, render_results


# -------------------------------------------------------------------
# Shared pending-bid handler
# Both dashboard and MC tabs render every page interaction. The previous
# design had each tab handle "_pending_bid" independently, but whichever
# tab rendered first would consume the key, leaving the other tab stale.
# Centralising here so a single button click updates both pages' state.
# -------------------------------------------------------------------
_DASH_BID_VALUES = {
    "anchor":   {"Entry_Mult": 8.5, "Debt_Mult": 5.1},
    "stretch":  {"Entry_Mult": 9.0, "Debt_Mult": 5.4},
    "original": {"Entry_Mult": 9.5, "Debt_Mult": 5.7},
}
_MC_BID_VALUES = {
    "anchor":   {"em_in_lo": 8.0, "em_in_mod": 8.5, "em_in_hi": 9.0},
    "stretch":  {"em_in_lo": 8.5, "em_in_mod": 9.0, "em_in_hi": 9.5},
    "original": {"em_in_lo": 9.0, "em_in_mod": 9.5, "em_in_hi": 10.0},
}

if "_pending_bid" in st.session_state:
    bid_key = st.session_state.pop("_pending_bid")
    for k, v in _DASH_BID_VALUES.get(bid_key, {}).items():
        st.session_state[k] = v
    for k, v in _MC_BID_VALUES.get(bid_key, {}).items():
        st.session_state[k] = v
    st.session_state["_active_bid"] = bid_key

# ---------- Custom CSS for the login screen + tabs ----------
st.markdown("""
<style>
.confidential-bar {
    background: #C62828;
    color: white;
    padding: 8px 16px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    text-align: center;
    margin-bottom: 16px;
}
.login-container {
    max-width: 480px;
    margin: 60px auto;
    padding: 32px;
    background: #F5F7FA;
    border-radius: 12px;
    border: 1px solid #E5E7EB;
}
.login-title {
    color: #1F4E78;
    font-size: 26px;
    font-weight: 700;
    margin: 0 0 8px 0;
}
.login-sub {
    color: #666;
    font-size: 14px;
    margin: 0 0 24px 0;
}
[role="tablist"] [role="tab"] {
    font-size: 15px !important;
    font-weight: 600 !important;
}
[role="tablist"] [role="tab"][aria-selected="true"] {
    color: #1F4E78 !important;
    border-bottom-color: #1F4E78 !important;
}
</style>
""", unsafe_allow_html=True)


# ---------- Auth gate ----------
def _login_form():
    st.markdown(
        "<div class='confidential-bar'>⚠️ CONFIDENTIAL — INVESTMENT COMMITTEE MATERIALS</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        """
<div class='login-container'>
  <div class='login-title'>CardioPath IC Site</div>
  <div class='login-sub'>
    These materials contain confidential analysis prepared for the Investment Committee.
    Sign in to continue. <em>Class capstone exercise — use <strong>demo</strong> / <strong>demo</strong> or any credentials.</em>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )
    left, mid, right = st.columns([1, 2, 1])
    with mid:
        with st.form("login"):
            username = st.text_input("Username", placeholder="demo")
            password = st.text_input("Password", type="password",
                                     placeholder="demo")
            submitted = st.form_submit_button("Sign in →", type="primary",
                                               use_container_width=True)
            if submitted:
                if username.strip() and password.strip():
                    st.session_state["authed"] = True
                    st.session_state["username"] = username.strip()
                    st.rerun()
                else:
                    st.error("Please enter both a username and password.")


if not st.session_state.get("authed", False):
    _login_form()
    st.stop()


# ---------- Authed: tabbed UI ----------
# Top bar
top_left, top_right = st.columns([6, 1])
with top_left:
    st.markdown(
        f"<div style='font-size: 12px; color: #666; padding: 6px 0;'>"
        f"🔐 Signed in as <strong>{st.session_state.get('username', 'guest')}</strong> · "
        f"Confidential IC Materials"
        f"</div>",
        unsafe_allow_html=True,
    )
with top_right:
    if st.button("Sign out", use_container_width=True):
        for k in ("authed", "username"):
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()


# ---------- Tabs ----------
tab_dash, tab_mc, tab_vote, tab_results = st.tabs([
    "📊 IC Dashboard",
    "🎲 Monte Carlo",
    "🗳️ Cast Vote",
    "📈 Vote Results",
])

with tab_dash:
    render_dashboard()

with tab_mc:
    render_montecarlo()

with tab_vote:
    render_vote()

with tab_results:
    render_results()
