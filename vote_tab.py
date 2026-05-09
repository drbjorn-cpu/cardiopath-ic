"""Vote tab — collect IC votes; render_results displays the tally."""

import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

VOTES_FILE = Path(__file__).parent / "votes.json"

# Pitch defaults — the bid being voted on
PROPOSED_PRICE = 8.5  # × EBITDA (anchor)
PROPOSED_EV = 607  # $m
EBITDA = 71.4  # $m
REVISIT_THRESHOLD_PCT = 15  # ≥ 15% below proposed
REVISIT_MAX_PRICE = PROPOSED_PRICE * (1 - REVISIT_THRESHOLD_PCT / 100)  # 7.225×


def _load_votes():
    if not VOTES_FILE.exists():
        return []
    try:
        with open(VOTES_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def _save_vote(entry):
    votes = _load_votes()
    votes.append(entry)
    with open(VOTES_FILE, "w") as f:
        json.dump(votes, f, indent=2)


def render_vote():
    st.markdown("""
<div style='background: linear-gradient(90deg, #1F4E78 0%, #2E75B6 100%);
            color: white; padding: 18px 24px; border-radius: 8px; margin-bottom: 16px;'>
  <h1 style='color: white; font-size: 22px; font-weight: 700; margin: 0;'>🗳️ Cast Your IC Vote — CardioPath Diagnostics</h1>
  <div style='color: #D6E4F0; font-size: 13px; margin-top: 4px;'>
    Proposed price: <strong>8.5× EBITDA = $607m EV</strong> (anchor) · Stretch: 9.0× / $643m
  </div>
</div>
""", unsafe_allow_html=True)

    # One vote per session
    if st.session_state.get("has_voted", False):
        st.success("✅ You've already voted from this session. Thank you.")
        st.caption("One vote per session. To cast a new test vote (admin only), an admin can clear all votes from the Vote Results tab.")
        return

    st.markdown("""
### The Three Options

Per the IC voting protocol:

- **APPROVE** — Proceed at the proposed price ($607m / 8.5×).
- **REJECT** — Walk away from the deal.
- **REVISIT** — Offer a price at least **15% below proposed** (i.e., ≤ **7.23× EBITDA / ~$516m EV**).

> **Tie defaults to REVISIT.**
> Your professor reserves veto on any vote that ignores a fatal flaw.
""")

    st.divider()

    with st.form("vote_form", clear_on_submit=True):
        st.subheader("Your vote")
        st.caption("Votes are anonymous.")

        vote = st.radio(
            "Your vote",
            options=["APPROVE", "REJECT", "REVISIT"],
            horizontal=True,
            index=None,
        )

        revisit_price = None
        if vote == "REVISIT":
            st.markdown(f"**REVISIT requires a price ≤ 7.23× EBITDA (~$516m EV).**")
            revisit_price = st.number_input(
                "Your revisit price (× EBITDA)",
                min_value=4.0,
                max_value=REVISIT_MAX_PRICE,
                value=7.0,
                step=0.05,
                format="%.2f",
                help=f"Must be ≤ {REVISIT_MAX_PRICE:.2f}× (15% below proposed 8.5×).",
            )
            implied_ev = revisit_price * EBITDA
            st.caption(f"Implied EV at your revisit price: **${implied_ev:.0f}m**")

        comment = st.text_area(
            "Optional comment (1–2 sentences on why)",
            placeholder="e.g. Concerned about CMS rate cuts; would revisit at 6.5× to build margin of safety.",
            max_chars=400,
            height=80,
        )

        submitted = st.form_submit_button("📥 Submit my vote", type="primary",
                                           use_container_width=True)

        if submitted:
            errors = []
            if vote is None:
                errors.append("Please select APPROVE, REJECT, or REVISIT.")
            if vote == "REVISIT" and revisit_price is None:
                errors.append("Please enter a revisit price.")
            if vote == "REVISIT" and revisit_price is not None and revisit_price > REVISIT_MAX_PRICE + 0.001:
                errors.append(f"Revisit price must be ≤ {REVISIT_MAX_PRICE:.2f}×.")

            if errors:
                for e in errors:
                    st.error(e)
            else:
                entry = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "vote": vote,
                    "revisit_price": float(revisit_price) if revisit_price is not None else None,
                    "comment": comment.strip() or None,
                }
                _save_vote(entry)
                st.session_state["has_voted"] = True
                st.success("✅ Vote recorded — see Vote Results tab for the live tally.")
                st.balloons()
                st.rerun()


def render_results():
    st.markdown("""
<div style='background: linear-gradient(90deg, #4A148C 0%, #7B1FA2 100%);
            color: white; padding: 18px 24px; border-radius: 8px; margin-bottom: 16px;'>
  <h1 style='color: white; font-size: 22px; font-weight: 700; margin: 0;'>📈 IC Vote Results — Live Tally</h1>
  <div style='color: #E1BEE7; font-size: 13px; margin-top: 4px;'>CardioPath Diagnostics · Proposed: 8.5× EBITDA / $607m</div>
</div>
""", unsafe_allow_html=True)

    # Admin gate
    if not st.session_state.get("admin_authed", False):
        st.warning("🔒 Admin access required to view live results.")
        left, mid, right = st.columns([1, 2, 1])
        with mid:
            with st.form("admin_login"):
                st.markdown("**Admin sign-in**")
                a_user = st.text_input("Username", key="admin_user")
                a_pass = st.text_input("Password", type="password", key="admin_pass")
                ok = st.form_submit_button("Sign in →", type="primary",
                                            use_container_width=True)
                if ok:
                    if a_user.strip().lower() == "admin" and a_pass == "admin":
                        st.session_state["admin_authed"] = True
                        st.rerun()
                    else:
                        st.error("Invalid admin credentials.")
        return

    # Admin signed in — show signout
    sign_out_col1, sign_out_col2 = st.columns([6, 1])
    with sign_out_col2:
        if st.button("Sign out admin", use_container_width=True):
            st.session_state["admin_authed"] = False
            st.rerun()

    votes = _load_votes()

    if not votes:
        st.info("📭 No votes cast yet. Head to the **Vote** tab to submit yours.")
        return

    df = pd.DataFrame(votes)

    # Tally
    counts = df["vote"].value_counts().to_dict()
    n_approve = counts.get("APPROVE", 0)
    n_reject = counts.get("REJECT", 0)
    n_revisit = counts.get("REVISIT", 0)
    total = len(df)

    # Decision: majority wins; tie → REVISIT
    sorted_counts = sorted(counts.items(), key=lambda x: -x[1])
    if len(sorted_counts) == 1:
        decision = sorted_counts[0][0]
    elif sorted_counts[0][1] > sorted_counts[1][1]:
        decision = sorted_counts[0][0]
    else:
        decision = "REVISIT"  # tie default

    # Headline metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total votes", f"{total}")
    c2.metric("APPROVE", f"{n_approve}", f"{n_approve/total*100:.0f}%")
    c3.metric("REJECT", f"{n_reject}", f"{n_reject/total*100:.0f}%")
    c4.metric("REVISIT", f"{n_revisit}", f"{n_revisit/total*100:.0f}%")

    # Decision banner
    decision_colors = {"APPROVE": "#2E7D32", "REJECT": "#C62828", "REVISIT": "#F57C00"}
    decision_meaning = {
        "APPROVE": "Deal proceeds at proposed price ($607m / 8.5× EBITDA).",
        "REJECT": "Deal rejected. We walk.",
        "REVISIT": "Deal revisited. New offer required at ≤ 7.23× EBITDA.",
    }
    st.markdown(f"""
<div style='background: {decision_colors[decision]}; color: white; padding: 16px 24px;
            border-radius: 8px; margin-top: 18px;'>
  <div style='font-size: 12px; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.85;'>IC Decision</div>
  <div style='font-size: 28px; font-weight: 700; margin-top: 4px;'>{decision}</div>
  <div style='font-size: 13px; margin-top: 4px;'>{decision_meaning[decision]}</div>
</div>
""", unsafe_allow_html=True)

    st.divider()

    # Bar chart of vote tally
    tally_df = pd.DataFrame({
        "Option": ["APPROVE", "REJECT", "REVISIT"],
        "Votes": [n_approve, n_reject, n_revisit],
    })
    st.subheader("Vote breakdown")
    st.bar_chart(tally_df.set_index("Option"), color="#1F4E78")

    # Revisit prices analysis (if any)
    revisit_rows = df[df["vote"] == "REVISIT"].copy()
    if len(revisit_rows) > 0:
        st.subheader("REVISIT price analysis")
        revisit_rows = revisit_rows[revisit_rows["revisit_price"].notna()]
        if len(revisit_rows) > 0:
            avg_price = revisit_rows["revisit_price"].mean()
            min_price = revisit_rows["revisit_price"].min()
            max_price = revisit_rows["revisit_price"].max()
            implied_avg_ev = avg_price * EBITDA
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("Avg REVISIT price", f"{avg_price:.2f}×")
            cc2.metric("Min", f"{min_price:.2f}×")
            cc3.metric("Max", f"{max_price:.2f}×")
            cc4.metric("Implied avg EV", f"${implied_avg_ev:.0f}m")

            # Histogram
            st.bar_chart(
                revisit_rows.assign(price_label=revisit_rows["revisit_price"].apply(lambda p: f"{p:.2f}×"))
                            .groupby("price_label").size().sort_index(),
                color="#F57C00",
            )

    st.divider()

    # Individual votes table (anonymous)
    st.subheader("All votes (anonymous)")
    display_df = df.copy()
    display_df["timestamp"] = pd.to_datetime(display_df["timestamp"]).dt.strftime("%Y-%m-%d %H:%M")
    display_df["revisit_price"] = display_df["revisit_price"].apply(
        lambda p: f"{p:.2f}×" if pd.notna(p) else ""
    )
    cols_to_show = ["timestamp", "vote", "revisit_price"]
    if "comment" in display_df.columns:
        cols_to_show.append("comment")
    display_df = display_df[cols_to_show]
    new_cols = ["Time (UTC)", "Vote", "Revisit Price"]
    if "comment" in cols_to_show:
        new_cols.append("Comment")
    display_df.columns = new_cols
    st.dataframe(display_df, hide_index=True, use_container_width=True)

    # Admin actions
    with st.expander("🛠 Admin"):
        st.caption("Use with care — these actions modify the votes file.")
        col_dl, col_clear = st.columns(2)
        with col_dl:
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇ Download votes CSV",
                csv,
                file_name=f"cardiopath_ic_votes_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_clear:
            if st.button("🗑 Clear all votes (admin only)", type="secondary",
                         use_container_width=True):
                if VOTES_FILE.exists():
                    VOTES_FILE.unlink()
                st.success("Votes cleared.")
                st.rerun()
