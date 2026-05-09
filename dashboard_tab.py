"""CardioPath — interactive IC dashboard.

Run with:    streamlit run cardio_dashboard.py --server.port 8502
Open:        http://localhost:8502

(Aria dashboard runs on 8501; this one on 8502 so both can be live at once.)

Slider semantics: same as aria_dashboard.py — percent inputs use display-units
(5.0 means 5%) and convert to decimals only at the model-call boundary.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.transforms import blended_transform_factory
import seaborn as sns
import streamlit as st
from verify import model, CARDIO

SWING_FLOOR = 0.05  # tornado: hide inputs that move MOIC by < 0.05×


def is_scenario_active(scenario_values):
    """Return True if current session state matches the scenario's preset values.
    Hoisted to module level so closures inside render() can access it regardless of
    definition order."""
    for k, v in scenario_values.items():
        if k not in st.session_state:
            return False
        try:
            cur = float(st.session_state[k])
            tgt = float(v)
            tol = 0.05 if abs(tgt) < 1.0 else 0.05
            if abs(cur - tgt) > tol:
                return False
        except (TypeError, ValueError):
            if st.session_state[k] != v:
                return False
    return True


# page_config moved to app.py
# ---------- Custom CSS for a more polished look ----------

def render():
    st.markdown("""
    <style>
    /* Section header styling */
    .section-h {
        font-size: 13px;
        font-weight: 600;
        color: #1F4E78;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-left: 3px solid #1F4E78;
        padding: 4px 10px;
        margin: 0 0 14px 0;
        background: #F5F7FA;
    }
    /* Branded header bar */
    .brand-header {
        background: linear-gradient(90deg, #1F4E78 0%, #2E75B6 100%);
        color: white;
        padding: 18px 24px;
        border-radius: 8px;
        margin-bottom: 16px;
    }
    .brand-header h1 {
        color: white !important;
        font-size: 22px;
        font-weight: 700;
        margin: 0;
    }
    .brand-header .meta {
        color: #D6E4F0;
        font-size: 13px;
        margin-top: 4px;
        letter-spacing: 0.02em;
    }
    /* Tighten metric cards */
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
        color: #666;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetricValue"] {
        font-size: 26px !important;
        font-weight: 700 !important;
        color: #1A1A1A !important;
    }
    [data-testid="stMetricDelta"] {
        font-size: 11px !important;
    }
    /* Scenario buttons — slightly smaller, denser */
    div[data-testid="stHorizontalBlock"] button[kind="secondary"] {
        font-size: 13px !important;
        padding: 8px 6px !important;
    }
    /* Tighter dividers */
    hr {
        margin: 14px 0 !important;
        border-color: #E5E7EB !important;
    }
    /* Caption styling under buttons */
    .stCaption {
        font-size: 11px !important;
        color: #666 !important;
        line-height: 1.35 !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # Unit conversion helpers
    # -------------------------------------------------------------------
    PERCENT_KEYS = {
        "Growth", "Margin_Y0", "Margin_Target",
        "Capex_Pct", "DNWC_Pct", "DA_Pct",
        "Tax_Rate", "Fee_Pct", "Int_Rate", "Amort_Pct", "Sweep_Pct",
    }

    def to_display(d):
        return {k: (v * 100 if k in PERCENT_KEYS else v) for k, v in d.items()}

    def to_decimal(d):
        return {k: (v / 100 if k in PERCENT_KEYS else v) for k, v in d.items()}

    CARDIO_DISPLAY = to_display(CARDIO)

    # -------------------------------------------------------------------
    # Bid postures — set Entry_Mult and Debt_Mult (LTV-correct) only
    # -------------------------------------------------------------------
    LTV_CAP = 0.60     # Standard HC services LBO LTV cap
    DEBT_MAX = 6.0     # Maximum Debt/EBITDA ratio regardless of LTV

    def ltv_capped_debt_mult(entry_mult, ltv_cap=LTV_CAP, debt_max=DEBT_MAX):
        """Return Debt/EBITDA mult capped at LTV × Entry_Mult, never above debt_max."""
        return min(debt_max, ltv_cap * entry_mult)

    BID_POSTURES = {
        "anchor": {
            "label": "⬇ ANCHOR · 8.5×",
            "Entry_Mult": 8.5,
            "blurb": "Where we want to win. **EV \\$607m · Debt \\$364m (5.1×) · Equity \\$258m**. ~10–20% probability of winning auction.",
        },
        "stretch": {
            "label": "➡ STRETCH · 9.0×",
            "Entry_Mult": 9.0,
            "blurb": "Where we'll go for conviction. **EV \\$643m · Debt \\$386m (5.4×) · Equity \\$273m**. ~30–45% probability of winning.",
        },
        "original": {
            "label": "⬆ AT FLOOR · 9.5×",
            "Entry_Mult": 9.5,
            "blurb": "Seller's range floor. Comparison only — we walk above 9.0×. **EV \\$678m · Debt \\$407m (5.7×) · Equity \\$288m**.",
        },
    }

    # -------------------------------------------------------------------
    # Operating presets (decoupled from bid posture — they don't change Entry_Mult)
    # -------------------------------------------------------------------
    PRESETS = {
        # ------------------- VALUE-CREATION -------------------
        "Base — organic only": {
            "kind": "value",
            "values": dict(Growth=4.0, Margin_Y0=21.0, Margin_Target=21.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "4% same-store, flat margin, 9.5× exit. **MOIC 2.25× / IRR 17.6%** — needs at least one operational lever to clear hurdle.",
            "details": """
    **Inputs changed:** Growth 4% (teaser same-store) · Margin_Target 21% (no improvement) · Exit_Mult 9.5×

    **Why this is the floor:** This is the "do nothing operationally" case — what we earn from just the price discipline (8.5× entry) and the demographic + CMS tailwind. It's the minimum viable return.

    **What has to be true:** US 65+ population continues growing ~3%/yr. CMS doesn't reverse the site-of-service migration. Same-store volume holds at 4%.

    **Why it's below hurdle:** Bid discipline alone gets us +5pp vs paying at the seller's floor. But it's not enough — we need at least one operational lever (centralized reading OR M&A) to clear 20%.
    """,
        },
        "+ Centralized reading": {
            "kind": "value",
            "values": dict(Growth=4.0, Margin_Y0=21.0, Margin_Target=24.0, Ramp_Years=4,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "Techs onsite, cardiologists central. +3pp margin. **MOIC 2.83× / IRR 23.1%** — clears hurdle.",
            "details": """
    **Inputs changed:** Margin_Target 21% → **24%** (+3pp) · Ramp_Years 3 → **4** (slower IT migration)

    **Why this works:** Cardiologists at regional reading centers (telecardiology), techs stay onsite. Replaces ~0.7 onsite cardio FTE per site with ~0.3 central-reader FTE. Cost savings flow directly to margin. Same playbook teleradiology proved in the 2010s.

    **What has to be true:**
    - IT migration succeeds: ~\$20–30m capex, 18–24 months
    - Commercial payers accept remote reading (validate top contracts pre-close)
    - State licensure manageable across 23 states (annual cost ~\$1k/state/cardiologist)
    - Cardiologists either accept the model or can be replaced

    **Failure mode:** Commercial payers force on-site reading → margin uplift halves to 1.5pp → IRR drops back to 19–20%.
    """,
        },
        "+ Bolt-on M&A": {
            "kind": "value",
            "values": dict(Growth=8.0, Margin_Y0=21.0, Margin_Target=21.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "10–15 bolt-ons → 8% blended growth. **MOIC 3.00× / IRR 24.5%** — clears hurdle.",
            "details": """
    **Inputs changed:** Growth 4% → **8%** (4% same-store + 4pp from acquisitions)

    **Why this works:** 10–15 small bolt-on acquisitions over 5 years (1–4 doctor practices, \$1–3m EBITDA each). Buy at 5–6× → fold into platform at 9.5× → ~\$15–20m equity value created per deal. Existing M&A engine (14 prior deals) is the proof point.

    **What has to be true:**
    - 50+ named targets in pipeline pre-close (diligence priority)
    - Buy-side multiples stay at 5–6× (not bid up by other PE platforms)
    - Integration capacity: IT, payer contracts, back-office
    - M&A capital: ~\$200m over 5 years (50% sweep preserves it on B/S)
    - 12–15 priority states are CPOM-friendly (avoid NY/NJ/CA scale-up issues)

    **Failure mode:** Pipeline dries up or prices rise → growth slows to 5–6% → IRR drops to ~21%.
    """,
        },
        "TOP-2 combined": {
            "kind": "value",
            "values": dict(Growth=8.0, Margin_Y0=21.0, Margin_Target=24.0, Ramp_Years=4,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "Centralized reading + M&A engine. **MOIC 3.69× / IRR 29.9%** — fund-returner. Pitch this.",
            "details": """
    **Inputs changed:** Both centralized reading AND bolt-on M&A active simultaneously.

    **Why this is the underwrite:** Both moves succeed together. The margin engine + growth engine compound: bigger EBITDA base × higher margin × growing revenue. Tax-shield uplift from higher EBITDA growth. Cash sweep accelerates debt paydown.

    **Built-in redundancy:** The deal clears hurdle even if **either** lever fails. Centralized alone = 23.1%. M&A alone = 24.5%. Both fail = 17.6% (base — below hurdle, but not catastrophic). **You only need 1 of 2 to hit hurdle; both for fund-returner.**

    **Diligence priority:** Validate that BOTH levers are executable. Approve only if at least one is high-conviction.
    """,
        },
        "⭐ FULL plan (aspirational)": {
            "kind": "value",
            "values": dict(Growth=9.0, Margin_Y0=21.0, Margin_Target=26.5, Ramp_Years=4,
                           Capex_Pct=5.5, Exit_Mult=11.5),
            "blurb": "⚠️ **NOT the underwrite — aspirational ceiling.** All moves + payer mix + IPO exit. **MOIC 5.56× / IRR 40.9%** if every lever hits. Top-decile PE returns are 30–40%; 41% requires perfect execution + cooperative public markets.",
            "details": """
    **Inputs changed:** Growth 9% · Margin_Target 26.5% · Capex_Pct 5.5% · Exit_Mult 11.5× (IPO premium)

    **What's stacked:** TOP-2 (centralized + M&A) + payer-mix shift to commercial + premium "Executive Cardiac" sub-brand + vertical add-ons (EP, vascular labs in top 30 markets) + hospital JVs + **IPO exit at 11.5× EBITDA**.

    **What has to be true:** Everything for TOP-2, PLUS:
    - Payer-mix shift achievable (1–2pp Medicare → Commercial)
    - Premium sub-brand finds enough cash-pay demand
    - Vertical add-ons execute cleanly with ~\$20–40m equipment capex
    - IPO market open in 5 years AND public HC-services comps trading at 12–15× EBITDA
    """,
        },
        # ------------------- RISK / BEAR -------------------
        "⚠ CMS rate cut (-2pp margin)": {
            "kind": "risk",
            "values": dict(Growth=4.0, Margin_Y0=19.0, Margin_Target=19.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "MPFS cuts margin -2pp. **MOIC 2.22× / IRR 17.3%** — needs operational lever to recover.",
            "details": """
    **Inputs changed:** Margin_Y0 21% → **19%** · Margin_Target 21% → **19%** (-2pp permanent)

    **The scenario:** CMS releases the annual MPFS with a 5–7% cut to top cardiac dx codes (CPT 78451 nuclear MPI, 93306 echocardiography, etc.). Margin compresses 2pp permanently.

    **Why so mild:** Our base already assumes flat margin. CMS rate cut just confirms the base. Net IRR delta is only -0.3pp from base 17.6%.

    **Mitigation:** Payer-mix shift toward commercial. Each 1pp Medicare → Commercial = ~30bps of margin recovery. 5pp shift over 3 years offsets one 10% MPFS cut.

    **Probability:** High (annual MPFS revisions). This is the headline risk but not the deal-killer.
    """,
        },
        "⚠ Multiple compression (7.0× exit)": {
            "kind": "risk",
            "values": dict(Growth=4.0, Margin_Y0=21.0, Margin_Target=21.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=7.0),
            "blurb": "Sector de-rate. **MOIC 1.41× / IRR 7.1%** — below hurdle, capital preserved.",
            "details": """
    **Inputs changed:** Exit_Mult 9.5× → **7.0×** (-2.5 turns)

    **The scenario:** At exit, FTC has issued enforcement action against another PE healthcare roll-up; public HC-services comps trade at 7× EBITDA; IPO market is closed; PE-to-PE multiples compress.

    **Why this is the #1 risk:** Operational performance is fine — we still hit 4% growth and 21% margin. But the multiple compression alone destroys 6.5pp of IRR (vs 17.6% base). At 9.5× entry it would have brought IRR to ~1% — at 8.5× entry, we still preserve capital.

    **Mitigation (structural, not operational):**
    - Multiple exit paths designed in: IPO, strategic, secondary buyout
    - Willingness to extend hold beyond 5 years
    - Deleverage so deal is financeable for next sponsor
    - **Bid discipline (8.5× anchor) is the primary structural mitigation**

    **Probability:** Medium (sector cycle + political backdrop).
    """,
        },
        "⚠ M&A pipeline misses": {
            "kind": "risk",
            "values": dict(Growth=2.0, Margin_Y0=21.0, Margin_Target=21.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=9.5),
            "blurb": "Growth slows to 2%. **MOIC 1.91× / IRR 13.9%** — below hurdle, modest return.",
            "details": """
    **Inputs changed:** Growth 4% → **2%** (no M&A; same-store also slows under cycle pressure)

    **The scenario:** Other PE platforms compete aggressively for the same bolt-on targets; sellers want 7×+; integration is harder than the data room suggested. Same-store growth slows from 4% → 2% under economic pressure.

    **Why it's a partial wipeout:** Without M&A, we don't even hit base case. The thesis was that M&A clears hurdle alone — without it we're below hurdle in every scenario.

    **Mitigation (mostly diligence-side):**
    - Pre-LOI: 50+ named targets with founder relationships
    - Walk if diligence reveals fewer than 30 actionable targets
    - Don't approve at 8.5× without high-conviction pipeline visibility

    **Probability:** Medium.
    """,
        },
        "💀 Triple hit": {
            "kind": "risk",
            "values": dict(Growth=2.0, Margin_Y0=19.0, Margin_Target=19.0, Ramp_Years=3,
                           Capex_Pct=5.0, Exit_Mult=7.0),
            "blurb": "All three failure modes. **MOIC 1.12× / IRR 2.3%** — capital preserved (vs −5% loss at 9.5× entry).",
            "details": """
    **Inputs changed:** All three bear scenarios combined — Growth 2% · Margin 19% · Exit 7.0×

    **The scenario:** CMS rate cut, M&A pipeline failure, AND multiple compression — all three at once. Most adversarial scenario in the simulation.

    **Why bid discipline matters here:** At 8.5× entry, even Triple Hit returns +2.3% — capital preserved. At 9.5× entry, the same scenario is **-4 to -5% IRR** = ~25% capital loss. **The 1-turn entry-multiple difference rescues ~\$50m of capital in the worst case.**

    **Probability:** ~5–15% (correlated events: regulatory pressure → multiple compression → M&A market cools → all happen together).

    **Why we accept this tail:**
    - Position sized within fund concentration limits
    - Capital is preserved, not destroyed
    - Single-axis bears all clear capital preservation
    - We sized the deal for THIS being possible

    **Walk if:** During diligence, any 2 of the 3 indicator metrics turn red (CMS rule changes pending, IPO market signals weak, M&A pipeline shrinking).
    """,
        },
    }

    if "_pending_preset" in st.session_state:
        # Operational-profile preset: changes everything EXCEPT Entry_Mult and Debt_Mult
        preset_key = st.session_state.pop("_pending_preset")
        for k, v in CARDIO_DISPLAY.items():
            if k not in ("Entry_Mult", "Debt_Mult"):
                st.session_state[k] = v
        for k, v in PRESETS[preset_key]["values"].items():
            st.session_state[k] = v

    # NOTE: pending-bid handler moved to app.py (shared across tabs)
    # so a single click updates both Dashboard AND MC state consistently.

    # Initialise on first load
    for k, v in CARDIO_DISPLAY.items():
        st.session_state.setdefault(k, v)
    st.session_state.setdefault("_active_bid", "anchor")
    st.session_state.setdefault("auto_ltv", True)

    # -------------------------------------------------------------------
    # Sidebar — only render when the user has selected "Dashboard" panel.
    # When on Monte Carlo, the dashboard sidebar is hidden to prevent
    # confusion (those inputs don't affect MC simulation).
    # -------------------------------------------------------------------
    if st.session_state.get("_active_panel", "dashboard") == "dashboard":
      with st.sidebar:
        st.markdown("## Inputs")
        st.caption("Every yellow cell from the workbook")

        if st.button("↺ Reset all to teaser-base", use_container_width=True):
            for k, v in CARDIO_DISPLAY.items():
                st.session_state[k] = v
            st.rerun()

        with st.expander("Operating", expanded=True):
            st.number_input("Revenue Y0 ($m)", min_value=100.0, max_value=1500.0,
                            step=10.0, key="Rev_Y0")
            st.slider("Revenue Growth (per year)", 0.0, 15.0, step=0.5,
                      format="%.1f%%", key="Growth")
            st.slider("EBITDA Margin Y0", 15.0, 28.0, step=0.5,
                      format="%.1f%%", key="Margin_Y0")
            st.slider("EBITDA Margin Target", 15.0, 28.0, step=0.5,
                      format="%.1f%%", key="Margin_Target")
            st.slider("Margin Ramp (years)", 1, 5, step=1, key="Ramp_Years")
            st.slider("Capex (% of revenue)", 2.0, 10.0, step=0.25,
                      format="%.2f%%", key="Capex_Pct")
            st.slider("ΔNWC (% of Δrevenue)", 0.0, 25.0, step=1.0,
                      format="%.0f%%", key="DNWC_Pct")
            st.slider("D&A (% of revenue)", 2.0, 10.0, step=0.25,
                      format="%.2f%%", key="DA_Pct")
            st.slider("Tax Rate", 18.0, 32.0, step=0.5,
                      format="%.1f%%", key="Tax_Rate")
            st.slider("Hold (years)", 3, 7, step=1, key="Hold")

        with st.expander("Entry — Sources & Uses", expanded=True):
            st.slider("Entry EV / EBITDA", 7.0, 13.0, step=0.25,
                      format="%.2f×", key="Entry_Mult")
            st.slider("Fees (% of EV)", 0.0, 4.0, step=0.25,
                      format="%.2f%%", key="Fee_Pct")

        with st.expander("Debt", expanded=True):
            st.toggle("Auto-cap debt at 60% LTV (lender practice)",
                      value=st.session_state.get("auto_ltv", True),
                      key="auto_ltv",
                      help="When ON, Debt/EBITDA is auto-computed = 60% × Entry_Mult, capped at 6.0×. Override OFF lets you set Debt/EBITDA manually.")

            if st.session_state["auto_ltv"]:
                # Auto-cap: compute and force the value, show as read-only
                auto_dm = ltv_capped_debt_mult(st.session_state["Entry_Mult"])
                st.session_state["Debt_Mult"] = auto_dm
                st.markdown(f"**Debt / EBITDA (auto)**: `{auto_dm:.2f}×`  "
                            f"<span style='color:#666;font-size:11px;'>(60% LTV × Entry {st.session_state['Entry_Mult']:.2f}×)</span>",
                            unsafe_allow_html=True)
            else:
                st.slider("Debt / EBITDA", 4.0, 8.0, step=0.25,
                          format="%.2f×", key="Debt_Mult")

            st.slider("Interest Rate", 5.0, 12.0, step=0.25,
                      format="%.2f%%", key="Int_Rate")
            st.slider("Mandatory Amort (% of orig)", 0.0, 5.0, step=0.5,
                      format="%.1f%%", key="Amort_Pct")
            st.slider("Cash Sweep %", 0.0, 100.0, step=5.0,
                      format="%.0f%%", key="Sweep_Pct")

        with st.expander("Exit", expanded=True):
            st.slider("Exit EV / EBITDA", 6.0, 13.0, step=0.25,
                      format="%.2f×", key="Exit_Mult")

    state_display = {k: st.session_state[k] for k in CARDIO_DISPLAY.keys()}
    inp = to_decimal(state_display)
    r = model(inp, basis="EBITDA")

    # Compute conservative-base output once for delta comparisons
    base_r = model(CARDIO, basis="EBITDA")

    # -------------------------------------------------------------------
    # Branded header
    # -------------------------------------------------------------------
    st.markdown("""
    <div class='brand-header'>
      <h1>🫀 CardioPath Diagnostics — IC Investment Dashboard</h1>
      <div class='meta'>US outpatient cardiac dx · 162 locations · Secondary buyout · <strong>Bid ladder: anchor 8.5× / stretch 9.0× / walk above 9.0×</strong></div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # Bid posture selector — three click-to-set buttons
    # -------------------------------------------------------------------
    active_bid = st.session_state.get("_active_bid", "anchor")
    st.markdown("<div class='section-h'>🎯 Bid Posture</div>", unsafe_allow_html=True)
    col_a, col_s, col_o = st.columns(3)
    buttons = [(col_a, "anchor"), (col_s, "stretch"), (col_o, "original")]

    # Compute live IRR for each bid posture using the CURRENT operational scenario
    def _bid_live_irr(em_in):
        cfg = dict(CARDIO)
        for k in CARDIO_DISPLAY.keys():
            if k in ("Entry_Mult", "Debt_Mult"):
                continue
            v = st.session_state.get(k, CARDIO_DISPLAY[k])
            cfg[k] = v / 100 if k in PERCENT_KEYS else v
        cfg["Entry_Mult"] = em_in
        cfg["Debt_Mult"] = ltv_capped_debt_mult(em_in)
        out = model(cfg, basis="EBITDA")
        return out["irr"] * 100, out["moic"]

    # Identify current operational scenario (if any preset is active)
    def _current_scenario_name():
        for label, info in PRESETS.items():
            if is_scenario_active(info["values"]):
                return label
        return "custom inputs"
    cur_scenario_name = _current_scenario_name()

    for col, key in buttons:
        info = BID_POSTURES[key]
        is_active = (key == active_bid)
        label = ("✅ " + info["label"]) if is_active else info["label"]
        live_irr, live_moic = _bid_live_irr(info["Entry_Mult"])
        with col:
            if st.button(label, use_container_width=True, key=f"bid_{key}",
                         type=("primary" if is_active else "secondary")):
                st.session_state["_pending_bid"] = key
                st.rerun()
            st.markdown(f"**At '{cur_scenario_name}': MOIC {live_moic:.2f}× · IRR {live_irr:.1f}%**")
            st.caption(info["blurb"])

    # -------------------------------------------------------------------
    # Live scoreboard with deltas vs conservative base
    # -------------------------------------------------------------------
    st.markdown("<div class='section-h'>Live Output</div>", unsafe_allow_html=True)

    c1, c2, c3, c4, c5 = st.columns(5)
    moic_delta = r['moic'] - base_r['moic']
    irr_delta  = (r['irr']  - base_r['irr']) * 100
    ebitda_delta = r['ebitda_arr'][5] - base_r['ebitda_arr'][5]
    debt_delta = r['end_debt'] - base_r['end_debt']
    equity_delta = r['equity'] - base_r['equity']

    c1.metric("MOIC", f"{r['moic']:.2f}×",
              delta=f"{moic_delta:+.2f}× vs base" if abs(moic_delta) > 0.01 else None)
    c2.metric("IRR", f"{r['irr']*100:.1f}%",
              delta=f"{irr_delta:+.1f}pp vs base" if abs(irr_delta) > 0.05 else None)
    c3.metric("Y5 EBITDA", f"${r['ebitda_arr'][5]:.0f}m",
              delta=f"${ebitda_delta:+.0f}m" if abs(ebitda_delta) > 0.5 else None)
    c4.metric("Y5 End Debt", f"${r['end_debt']:.0f}m",
              delta=f"${debt_delta:+.0f}m" if abs(debt_delta) > 0.5 else None,
              delta_color="inverse")
    c5.metric("Sponsor Equity (in)", f"${r['equity']:.0f}m")

    with st.expander("📋 Current input values (sanity check)", expanded=False):
        rows = []
        for k in CARDIO_DISPLAY.keys():
            disp_v = state_display[k]
            if k in PERCENT_KEYS:
                shown = f"{disp_v:.2f}%"
            elif k in ("Entry_Mult", "Exit_Mult", "Debt_Mult"):
                shown = f"{disp_v:.2f}×"
            elif k in ("Ramp_Years", "Hold"):
                shown = f"{int(disp_v)} yr"
            else:
                shown = f"{disp_v:.1f}"
            rows.append({"Input": k, "Value": shown})
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with st.expander("⚖️ Probability-weighted return — the honest IRR for the bid ladder", expanded=False):
        st.markdown("""
    **The deterministic IRRs (TOP-2 = 30%, etc.) are conditional on winning the auction.** When you factor in the probability of NOT winning at our disciplined bid, the expected IRR is materially lower:

    | Bid outcome | Probability* | Conditional IRR (TOP-2 case) | Contribution |
    |---|---:|---:|---:|
    | Win at anchor 8.5× | ~15% | 29.9% | +4.5 pp |
    | Win at stretch 9.0× | ~30% | 27.7% | +8.3 pp |
    | Lose auction; capital sits at fund-cash rate (~4%) | ~55% | 4.0% | +2.2 pp |
    | **Probability-weighted IRR** | | | **~15.0%** |

    > **\\*Win probabilities are illustrative PE-norm estimates, NOT from a published study.** They assume a standard auction with 4 PE bidders, our bid 11% below seller's floor.
    > **Real auction win-rate data is closely held by sell-side advisors and not publicly available.** Validation path:
    > - **M&A advisor pitch (pre-LOI)** — every sell-side bank shows historical hit-rate file by bid spread; that's the on-the-record source
    > - **Cambridge Associates / Bain Global PE Report** — track average bid-spread benchmarks (HC services 2024 auctions trade at 8–15% spread vs. ask) but don't publish win rate by spread
    > - **Pitchbook PE deal analytics** — historical bid-vs-clearing-price data
    > - **Diligence priority:** confirm with our M&A advisor what their hit rate has been at this spread for similar HC services secondary buyouts in 2023–25.

    **What this means:** The deal's *expected return weighted by win probability* is ~15% — below the 20% PE hurdle. This is honest, not damning:
    - We're explicitly trading off win-probability for risk-adjusted underwriting
    - The 55% auction-loss outcome means capital is preserved as dry powder; cardiac dx remains a fragmented sector with periodic auction availability
    - The opportunity cost is real (~4% on uninvested equity) but the alternative is overpaying for a secondary buyout with regulatory risk

    **Why we accept this:** It's better to lose 55% of high-discipline auctions than to win 80% of them at prices that don't earn capital cost. This is a position-sizing and risk-management argument, not a returns-maximisation argument.
    """)

    with st.expander("📍 Deal context (from teaser)", expanded=False):
        st.markdown("""
    | Field | Value |
    |---|---|
    | **Sector** | Outpatient cardiac diagnostics |
    | **HQ / Founded** | Atlanta, GA · 2008 (rolled up from 14 acquisitions) |
    | **Footprint** | 162 locations across 23 US states |
    | **Revenue / EBITDA (FY24)** | $340m / $72m (21% margin) |
    | **Growth (3-yr)** | 11% top-line; 4% same-store |
    | **Payer mix** | Medicare 56% · Commercial 31% · Medicaid 13% |
    | **Owners** | Mid-market PE (since 2019), CEO 8% |
    | **Indicative valuation** | $680m–$820m (9.4–11.4× EBITDA) |
    | **Process** | Standard auction · secondary buyout |
    """)

    st.divider()

    # -------------------------------------------------------------------
    # Scenarios — placed above the tabs so the live scoreboard is always
    # visible while clicking
    # -------------------------------------------------------------------
    def _scenario_live_metrics(scenario_values):
        """Compute MOIC/IRR for a scenario at the CURRENT bid posture (Entry_Mult)."""
        cfg = dict(CARDIO)
        cur_em = st.session_state.get("Entry_Mult", 8.5)
        # Apply scenario operating-profile inputs (in display units, convert to model units)
        for k, v in scenario_values.items():
            if k in PERCENT_KEYS:
                cfg[k] = v / 100
            else:
                cfg[k] = v
        # Override with current bid posture
        cfg["Entry_Mult"] = cur_em
        cfg["Debt_Mult"] = ltv_capped_debt_mult(cur_em) if st.session_state.get("auto_ltv", True) \
                           else st.session_state.get("Debt_Mult", 5.1)
        out = model(cfg, basis="EBITDA")
        return out["moic"], out["irr"] * 100

    def render_scenarios(scenario_dict, intro_caption=None):
        if intro_caption:
            st.caption(intro_caption)
        cols = st.columns(len(scenario_dict))
        cur_em = st.session_state.get("Entry_Mult", 8.5)
        for col, (label, info) in zip(cols, scenario_dict.items()):
            active = is_scenario_active(info["values"])
            btn_label = ("✅ " + label) if active else label
            live_moic, live_irr = _scenario_live_metrics(info["values"])
            with col:
                if st.button(btn_label, use_container_width=True,
                             type=("primary" if active else "secondary"),
                             key=f"btn_{label}"):
                    st.session_state["_pending_preset"] = label
                    st.rerun()
                # Live MOIC/IRR at current bid posture (replaces the static caption numbers)
                st.markdown(f"**At {cur_em:.2f}× entry: MOIC {live_moic:.2f}× · IRR {live_irr:.1f}%**")
                st.caption(info["blurb"])
                if "details" in info:
                    with st.expander("ℹ️ Details · what changes & why", expanded=False):
                        st.markdown(info["details"])

    st.markdown("<div class='section-h'>🟢 Value-Creation Scenarios — what to do with the asset</div>", unsafe_allow_html=True)
    value_presets = {k: v for k, v in PRESETS.items() if v["kind"] == "value"}
    render_scenarios(value_presets, "Click any button → sliders snap to preset · scoreboard updates · active scenario highlighted in green.")

    st.markdown("<div class='section-h'>🔴 Risk / Stress-Test Scenarios — what kills the deal</div>", unsafe_allow_html=True)
    risk_presets = {k: v for k, v in PRESETS.items() if v["kind"] == "risk"}
    render_scenarios(risk_presets)

    st.divider()

    # -------------------------------------------------------------------
    # Tabs
    # -------------------------------------------------------------------
    tab_snap, tab_tornado, tab_heat, tab_entry = st.tabs(
        ["📊 Snapshot", "📈 Tornado", "🗺️ Heatmap (Growth × Exit)", "💰 Entry-Multiple Sensitivity"]
    )

    # ---------- SNAPSHOT ----------
    with tab_snap:
        left, right = st.columns([1, 1])
        with left:
            st.subheader("Sources & Uses")
            st.markdown(
                f"""
    | Item | $ (m) |
    |---|---:|
    | Entry EBITDA | {r['ebitda0']:.1f} |
    | Enterprise Value | **{r['ev']:.1f}** |
    | Deal Fees | {r['fees']:.1f} |
    | Total Uses | **{r['ev']+r['fees']:.1f}** |
    | Debt | {r['debt0']:.1f} |
    | Sponsor Equity (plug) | {r['equity']:.1f} |
    | Total Sources | **{r['debt0']+r['equity']:.1f}** |
    """
            )
            ltv = r['debt0']/r['ev']
            ltv_warn = " ⚠ above 65% lender cap" if ltv > 0.65 else ""
            st.subheader("Capitalisation")
            st.markdown(
                f"""
    | Metric | Value |
    |---|---:|
    | Debt / EBITDA | {r['debt0']/r['ebitda0']:.2f}× |
    | Equity / EBITDA | {r['equity']/r['ebitda0']:.2f}× |
    | **LTV (Debt / EV)** | **{ltv*100:.1f}%**{ltv_warn} |
    | Equity % of EV | {r['equity']/r['ev']*100:.1f}% |
    """
            )
        with right:
            st.subheader("Operating model — Y0 to Y5")
            df = pd.DataFrame({
                "Year":     [f"Y{i}" for i in range(6)],
                "Revenue":  [round(x, 1) for x in r["rev"]],
                "Margin":   [f"{m*100:.1f}%" for m in r["marg"]],
                "EBITDA":   [round(x, 1) for x in r["ebitda_arr"]],
                "U-FCF":    [round(x, 1) for x in r["ufcf"]],
            })
            st.dataframe(df, hide_index=True, use_container_width=True)

            st.subheader("Returns")
            st.markdown(
                f"""
    | | |
    |---|---:|
    | Y5 EBITDA | ${r['ebitda_arr'][5]:.1f}m |
    | Exit Mult | {state_display['Exit_Mult']:.2f}× |
    | **Exit EV** | **${r['exit_ev']:.0f}m** |
    | (–) End Debt | (${r['end_debt']:.0f}m) |
    | (+) Cash | ${r['end_cash']:.0f}m |
    | **Exit Equity** | **${r['exit_equity']:.0f}m** |
    | Sponsor Equity (in) | ${r['equity']:.0f}m |
    | **MOIC** | **{r['moic']:.2f}×** |
    | **IRR** | **{r['irr']*100:.1f}%** |
    """
            )

    # ---------- TORNADO ----------
    with tab_tornado:
        st.subheader("MOIC sensitivity — every flex-able input, ranked")
        st.caption("Bars centered on current MOIC. Each row holds everything else at the current sidebar values.")

        FLEXES = [
            ("Exit EV / EBITDA",        "Exit_Mult",     7.5,    11.5,   "{:.1f}×"),
            ("Revenue Growth",          "Growth",        0.02,   0.11,   "{:.0%}"),
            ("EBITDA Margin Target",    "Margin_Target", 0.18,   0.23,   "{:.0%}"),
            ("Entry EV / EBITDA",       "Entry_Mult",    8.0,    9.5,    "{:.1f}×"),
            ("EBITDA Margin Y0",        "Margin_Y0",     0.19,   0.23,   "{:.0%}"),
            ("Interest Rate",           "Int_Rate",      0.07,   0.10,   "{:.1%}"),
            ("Margin Ramp (years)",     "Ramp_Years",    2,      5,      "{:.0f}y"),
            ("Tax Rate",                "Tax_Rate",      0.21,   0.30,   "{:.0%}"),
            ("Capex (% of revenue)",    "Capex_Pct",     0.04,   0.07,   "{:.1%}"),
            ("ΔNWC (% of Δrevenue)",    "DNWC_Pct",      0.05,   0.15,   "{:.0%}"),
            ("D&A (% of revenue)",      "DA_Pct",        0.04,   0.08,   "{:.1%}"),
            ("Cash Sweep %",            "Sweep_Pct",     0.30,   0.75,   "{:.0%}"),
        ]
        # When auto-LTV is on, Debt_Mult is not independently flex-able (it's derived from Entry_Mult)
        # so we exclude it from the tornado. When user has overridden auto-LTV, allow Debt_Mult flex.
        if not st.session_state.get("auto_ltv", True):
            FLEXES.append(("Debt / EBITDA", "Debt_Mult", 4.5, 6.0, "{:.1f}×"))

        base_moic = r["moic"]
        rows = []
        for label, key, lo, hi, fmt in FLEXES:
            cfg_lo = dict(inp); cfg_lo[key] = lo
            cfg_hi = dict(inp); cfg_hi[key] = hi
            m_lo = model(cfg_lo, basis="EBITDA")["moic"]
            m_hi = model(cfg_hi, basis="EBITDA")["moic"]
            rows.append((label, key, lo, hi, m_lo, m_hi, abs(m_hi - m_lo), fmt))
        rows.sort(key=lambda r_: -r_[6])
        visible_rows = [r_ for r_ in rows if r_[6] >= SWING_FLOOR]
        hidden       = [r_ for r_ in rows if r_[6] <  SWING_FLOOR]

        fig, ax = plt.subplots(figsize=(13, 7))
        fig.patch.set_facecolor("white")
        fig.subplots_adjust(left=0.28, right=0.65, top=0.88, bottom=0.10)
        trans = blended_transform_factory(ax.transAxes, ax.transData)

        y_positions = list(range(len(visible_rows)))[::-1]
        y_labels = [f"{r_[0]}\n({r_[7].format(r_[2])} → {r_[7].format(r_[3])})"
                    for r_ in visible_rows]

        for ypos, (label, key, lo, hi, m_lo, m_hi, swing, fmt) in zip(y_positions, visible_rows):
            if m_lo < base_moic:
                ax.barh(ypos, base_moic - m_lo, left=m_lo, color="#C0504D",
                        edgecolor="white", height=0.6)
            if m_hi > base_moic:
                ax.barh(ypos, m_hi - base_moic, left=base_moic, color="#4F81BD",
                        edgecolor="white", height=0.6)

        LOW_X, HIGH_X, DELTA_X = 1.05, 1.18, 1.32
        for ypos, (label, key, lo, hi, m_lo, m_hi, swing, fmt) in zip(y_positions, visible_rows):
            ax.text(LOW_X,   ypos, f"{m_lo:.2f}×", transform=trans,
                    ha="center", va="center", fontsize=10, color="#7F2A28", fontweight="bold")
            ax.text(HIGH_X,  ypos, f"{m_hi:.2f}×", transform=trans,
                    ha="center", va="center", fontsize=10, color="#1F3F6E", fontweight="bold")
            ax.text(DELTA_X, ypos, f"Δ {swing:.2f}×", transform=trans,
                    ha="center", va="center", fontsize=10, color="#404040")

        header_y = len(visible_rows) - 0.3
        ax.text(LOW_X,   header_y, "Low",   transform=trans, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#7F2A28")
        ax.text(HIGH_X,  header_y, "High",  transform=trans, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#1F3F6E")
        ax.text(DELTA_X, header_y, "Swing", transform=trans, ha="center", va="bottom",
                fontsize=10, fontweight="bold", color="#404040")

        ax.axvline(base_moic, color="black", lw=1.5, ls="--", alpha=0.7)
        ax.text(base_moic, header_y, f" base {base_moic:.2f}×",
                ha="left", va="bottom", fontsize=10, fontweight="bold")

        ax.set_yticks(y_positions)
        ax.set_yticklabels(y_labels, fontsize=9)
        ax.set_xlabel("Sponsor MOIC")
        ax.set_xlim(min(r_[4] for r_ in visible_rows) - 0.05,
                    max(r_[5] for r_ in visible_rows) + 0.05)
        ax.set_title(f"Tornado — current MOIC {base_moic:.2f}×",
                     fontweight="bold", pad=15)
        for s in ("top", "right", "left"):
            ax.spines[s].set_visible(False)
        ax.grid(axis="x", alpha=0.3)
        ax.set_axisbelow(True)
        ax.tick_params(left=False)

        if hidden:
            note = "Not shown (swing < {:.2f}×): {}".format(
                SWING_FLOOR,
                ", ".join(f"{h[0]} (Δ{h[6]:.2f}×)" for h in hidden),
            )
            fig.text(0.28, 0.02, note, fontsize=8, style="italic", color="#666666")

        st.pyplot(fig, use_container_width=True)

    # ---------- HEATMAP ----------
    with tab_heat:
        st.subheader("IRR by Growth × Exit Multiple (other inputs held at current values)")
        GROWTHS    = np.arange(0.02, 0.121, 0.01)
        EXIT_MULTS = np.arange(7.0, 12.01, 0.5)
        grid = np.zeros((len(EXIT_MULTS), len(GROWTHS)))
        for i, em in enumerate(EXIT_MULTS):
            for j, g in enumerate(GROWTHS):
                cfg = dict(inp); cfg["Growth"] = g; cfg["Exit_Mult"] = em
                grid[i, j] = model(cfg, basis="EBITDA")["irr"] * 100

        vmin, vcenter, vmax = grid.min(), 20.0, grid.max()
        if vcenter <= vmin: vcenter = vmin + 0.1
        if vcenter >= vmax: vcenter = vmax - 0.1
        norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=vcenter, vmax=vmax)

        fig2, ax2 = plt.subplots(figsize=(11, 6))
        fig2.patch.set_facecolor("white")
        sns.heatmap(
            grid,
            xticklabels=[f"{g*100:.0f}%" for g in GROWTHS],
            yticklabels=[f"{em:.1f}×" for em in EXIT_MULTS],
            annot=True, fmt=".1f", cmap="RdYlGn", norm=norm,
            cbar_kws={"label": "IRR %"}, linewidths=0.4, linecolor="white", ax=ax2,
        )
        cur_g_idx  = int(np.argmin(np.abs(GROWTHS - inp["Growth"])))
        cur_em_idx = int(np.argmin(np.abs(EXIT_MULTS - inp["Exit_Mult"])))
        ax2.add_patch(plt.Rectangle((cur_g_idx, cur_em_idx), 1, 1,
                                    fill=False, edgecolor="black", lw=2.5))
        ax2.invert_yaxis()
        ax2.set_xlabel("Revenue Growth")
        ax2.set_ylabel("Exit EV / EBITDA")
        ax2.set_title(
            f"IRR surface — current point ({inp['Growth']*100:.0f}%, {inp['Exit_Mult']:.1f}×) → {r['irr']*100:.1f}%",
            fontweight="bold", pad=12,
        )
        plt.tight_layout()
        st.pyplot(fig2, use_container_width=True)

    # ---------- ENTRY-MULTIPLE SENSITIVITY (cross-product) ----------
    with tab_entry:
        st.subheader("IRR by Entry Multiple × Scenario")
        st.caption(
            "Pick a value-creation or risk scenario and see how IRR moves across entry multiples 7.5× → 11.0×. "
            "**Bid discipline is the single biggest lever:** the column you pay determines the floor for every scenario. "
            "20% PE hurdle is the green/red color split."
        )

        # Define the operating profiles to overlay
        OPERATING_PROFILES = [
            ("Base — organic only",       dict(Growth=0.04, Margin_Y0=0.21, Margin_Target=0.21, Ramp_Years=3, Exit_Mult=9.5)),
            ("+ Centralized reading",     dict(Growth=0.04, Margin_Y0=0.21, Margin_Target=0.24, Ramp_Years=4, Exit_Mult=9.5)),
            ("+ Bolt-on M&A",             dict(Growth=0.08, Margin_Y0=0.21, Margin_Target=0.21, Ramp_Years=3, Exit_Mult=9.5)),
            ("TOP-2 combined",            dict(Growth=0.08, Margin_Y0=0.21, Margin_Target=0.24, Ramp_Years=4, Exit_Mult=9.5)),
            ("FULL plan + IPO",           dict(Growth=0.09, Margin_Y0=0.21, Margin_Target=0.265, Ramp_Years=4, Capex_Pct=0.055, Exit_Mult=11.5)),
            ("⚠ CMS rate cut",            dict(Growth=0.04, Margin_Y0=0.19, Margin_Target=0.19, Ramp_Years=3, Exit_Mult=9.5)),
            ("⚠ Multiple compression 7×", dict(Growth=0.04, Margin_Y0=0.21, Margin_Target=0.21, Ramp_Years=3, Exit_Mult=7.0)),
            ("⚠ M&A pipeline misses",     dict(Growth=0.02, Margin_Y0=0.21, Margin_Target=0.21, Ramp_Years=3, Exit_Mult=9.5)),
            ("💀 Triple hit",              dict(Growth=0.02, Margin_Y0=0.19, Margin_Target=0.19, Ramp_Years=3, Exit_Mult=7.0)),
        ]
        ENTRY_MULTS_GRID = [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 10.5, 11.0]

        # Build IRR matrix
        grid = np.zeros((len(OPERATING_PROFILES), len(ENTRY_MULTS_GRID)))
        for i, (_, override) in enumerate(OPERATING_PROFILES):
            for j, em_in in enumerate(ENTRY_MULTS_GRID):
                cfg = dict(CARDIO); cfg.update(override)
                cfg["Entry_Mult"] = em_in
                # Apply LTV cap per cell — debt scales with entry multiple
                cfg["Debt_Mult"] = ltv_capped_debt_mult(em_in)
                grid[i, j] = model(cfg, basis="EBITDA")["irr"] * 100

        vmin, vcenter, vmax = grid.min(), 20.0, grid.max()
        if vcenter <= vmin: vcenter = vmin + 0.1
        if vcenter >= vmax: vcenter = vmax - 0.1
        norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=vcenter, vmax=vmax)

        fig3, ax3 = plt.subplots(figsize=(13, 7))
        fig3.patch.set_facecolor("white")
        sns.heatmap(
            grid,
            xticklabels=[f"{em:.1f}×" for em in ENTRY_MULTS_GRID],
            yticklabels=[name for name, _ in OPERATING_PROFILES],
            annot=True, fmt=".1f", cmap="RdYlGn", norm=norm,
            cbar_kws={"label": "IRR %"}, linewidths=0.5, linecolor="white", ax=ax3,
        )
        # Mark current bid (8.5×) and walk-away (9.0×) thresholds
        bid_idx     = ENTRY_MULTS_GRID.index(8.5)
        walk_idx    = ENTRY_MULTS_GRID.index(9.0)
        teaser_idx  = ENTRY_MULTS_GRID.index(9.5)
        ax3.axvline(bid_idx + 1, color="black", lw=2.5, ls="-", label="Committed bid (8.5×)")
        ax3.axvline(walk_idx + 1, color="orange", lw=2, ls="--", label="Walk threshold (9.0×)")
        ax3.axvline(teaser_idx, color="red", lw=1.5, ls=":", label="Seller's floor (9.4×) ≈ 9.5×")
        ax3.legend(loc="upper right", fontsize=9, frameon=True, facecolor="white")

        ax3.set_xlabel("Entry EV / EBITDA")
        ax3.set_ylabel("Operating profile")
        ax3.set_title(
            "Bid discipline is the rescue lever — every column moves the deal economics by ~5pp of IRR",
            fontweight="bold", pad=12,
        )
        plt.tight_layout()
        st.pyplot(fig3, use_container_width=True)

        st.markdown("""
    **How to read this:**
    - Each **column** is an entry multiple (price we pay).
    - Each **row** is an operating profile (what we deliver post-close).
    - Each **cell** is the resulting IRR.
    - **Green = above 20% PE hurdle. Red = below.**
    - The thick black line is our **committed bid (8.5×)**. The dashed orange is our **walk threshold (9.0×)**.

    **Key takeaway:**

    > *Whether we hit our operational targets matters less than what we pay at entry.*
    > At 8.5× entry, **even Multiple Compression and M&A miss return positive capital**.
    > At 9.5× entry (seller's range), Multiple Compression and Triple Hit destroy capital.
    """)

    # -------------------------------------------------------------------
    # Reference: full preset table (collapsed by default)
    # -------------------------------------------------------------------
    st.divider()

    # -------------------------------------------------------------------
    # Addendum: methodology notes (collapsible)
    # -------------------------------------------------------------------
    with st.expander("📎 Addendum — Cash Sweep & LTV methodology notes", expanded=False):
        st.markdown("""
    ### Cash Sweep — why 50%, not 75% or 100%

    **Definition:** After paying mandatory debt amortization, "cash sweep" determines what fraction of remaining free cash flow goes to additional debt paydown vs. accumulating on the balance sheet.

    **Decision: 50% sweep at base.**

    | Sweep % | TOP-2 IRR | Triple Hit IRR | End Cash (TOP-2) | Implication |
    |---:|---:|---:|---:|---|
    | 50% (current) | 29.9% | +2.3% | $80m | M&A capital reserved on B/S |
    | 75% | 30.0% | +2.5% | $41m | Modest cash, prior default |
    | 100% | 30.1% | +2.7% | $0m | All FCF to debt; M&A via revolver |

    **Why this matters more than the IRR delta:**
    - IRR difference between 50% and 100% is only ~0.2 pp — **sweep barely moves returns** because cash that doesn't pay debt accumulates as exit equity.
    - The bigger impact is **operational flexibility**: with 50% sweep, ~$80m of cash builds up by Y5. That's exactly the firepower for the bolt-on M&A engine — no need to raise an incremental delayed-draw facility or revolver expansion.
    - **Market norm:** TLB / unitranche standard for HC services is 50% with leverage-based step-downs (drops to 25% as Debt/EBITDA falls below 4×). 75% is sponsor-friendly aggressive; 100% is rare and only on stressed credits.

    **The trade-off accepted:**
    - Give up ~0.2 pp IRR
    - Gain ~$40m of mid-hold M&A capital
    - Better story for IC: "we structure for execution flexibility, not maximum deleveraging"

    ### LTV-capped Debt — why 5.1× at 8.5× entry, not 6.0×

    **Definition:** Loan-to-Value (LTV) = Debt / Enterprise Value. Lenders cap LTV to ensure equity cushion above their debt position.

    **Standard HC services LBO LTV cap: ~60% of EV.**

    At 8.5× entry: 60% × $607m = $364m max debt = **5.1× EBITDA** (since EBITDA is $71.4m).
    At 9.0× entry: 60% × $643m = $386m max debt = **5.4× EBITDA**.
    At 9.5× entry: 60% × $678m = $407m max debt = **5.7× EBITDA**.

    A flat 6.0× EBITDA debt at 8.5× entry would be **71% LTV** — above standard cap. Lenders would either reduce debt to ~5.1× or charge ratings-penalty pricing. Modeling at 6.0× would overstate IRR by ~3 pp.

    **Implementation in this dashboard:**
    - "Auto-cap debt at 60% LTV" toggle in sidebar (default ON) auto-derives Debt/EBITDA from Entry Multiple
    - Toggle OFF to manually set Debt/EBITDA — the capital structure section warns if LTV >65%

    ### Sources / lender practice references

    These leverage and sweep norms come from typical TLB / unitranche term-sheets for $500m–$1B HC services LBOs in the 2024–25 vintage. Specific terms vary by lender, sponsor relationship, and credit profile — diligence priority is confirming exact terms in the financing process.
    """)

    with st.expander("Reference — all preset values (display units)", expanded=False):
        preset_df = pd.DataFrame([
            {"Scenario": label, "Group": info["kind"].title(), **{
                f"{k}": (f"{v:.1f}%" if k in PERCENT_KEYS else
                         f"{v:.2f}×" if k in ("Entry_Mult", "Exit_Mult", "Debt_Mult") else
                         f"{v}")
                for k, v in info["values"].items()
            }}
            for label, info in PRESETS.items()
        ])
        st.dataframe(preset_df, hide_index=True, use_container_width=True)

