"""CardioPath — Monte Carlo simulation.

Run on a separate port so it doesn't disturb the main dashboard:
    streamlit run cardio_montecarlo.py --server.port 8503
Open: http://localhost:8503

Methodology:
  - Triangular distributions for each randomized input (low / mode / high)
  - Optional Gaussian copula for correlation between Growth × Margin × Exit Multiple
  - 10,000 iterations by default
  - Outputs: distribution of MOIC and IRR, joint scatter, summary stats
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st
from scipy import stats
from verify import model, CARDIO


# -------------------------------------------------------------------
# MODULE-LEVEL: run_simulation — must be at module level so st.cache_data
# can correctly hash inputs across reruns. Defining inside render() breaks
# caching because the function object is re-created on every rerun.
# Params are passed as a *frozen* tuple of tuples so they're hashable for cache key.
# -------------------------------------------------------------------
@st.cache_data(show_spinner="Running Monte Carlo simulation…")
def run_simulation(n, params_tuple, use_corr):
    """Run n Monte Carlo iterations.

    params_tuple: tuple of (key, (low, mode, high)) tuples — hashable for cache.
    use_corr: if True, apply correlation matrix via Gaussian copula.
    Returns DataFrame of (Growth, Margin_Y0, Margin_Target, Entry_Mult, Exit_Mult, MOIC, IRR).
    """
    params = dict(params_tuple)
    keys = list(params.keys())
    n_vars = len(keys)

    if use_corr:
        corr_mat = np.array([
            [1.00, 0.10, 0.20, 0.10, 0.50],
            [0.10, 1.00, 0.30, 0.05, 0.10],
            [0.20, 0.30, 1.00, 0.05, 0.30],
            [0.10, 0.05, 0.05, 1.00, 0.40],
            [0.50, 0.10, 0.30, 0.40, 1.00],
        ])
        L = np.linalg.cholesky(corr_mat)
        z = np.random.standard_normal((n, n_vars))
        u = stats.norm.cdf(z @ L.T)
    else:
        u = np.random.uniform(0, 1, size=(n, n_vars))

    samples = np.zeros_like(u)
    for i, key in enumerate(keys):
        lo, mode, hi = params[key]
        c = (mode - lo) / (hi - lo)
        below = u[:, i] < c
        samples[below, i] = lo + np.sqrt(u[below, i] * (hi - lo) * (mode - lo))
        samples[~below, i] = hi - np.sqrt((1 - u[~below, i]) * (hi - lo) * (hi - mode))

    moics = np.zeros(n)
    irrs  = np.zeros(n)
    for i in range(n):
        cfg = dict(CARDIO)
        cfg["Growth"]        = samples[i, 0] / 100
        cfg["Margin_Y0"]     = samples[i, 1] / 100
        cfg["Margin_Target"] = samples[i, 2] / 100
        cfg["Entry_Mult"]    = samples[i, 3]
        cfg["Exit_Mult"]     = samples[i, 4]
        cfg["Debt_Mult"]     = min(6.0, 0.60 * samples[i, 3])
        out = model(cfg, basis="EBITDA")
        moics[i] = out["moic"]
        irrs[i]  = out["irr"]

    df = pd.DataFrame(samples, columns=keys)
    df["MOIC"] = moics
    df["IRR"]  = irrs * 100
    return df

# page_config moved to app.py
# ---------- Styling ----------

def render():
    st.markdown("""
    <style>
    .brand-header {
        background: linear-gradient(90deg, #4A148C 0%, #7B1FA2 100%);
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
        color: #E1BEE7;
        font-size: 13px;
        margin-top: 4px;
    }
    .section-h {
        font-size: 13px;
        font-weight: 600;
        color: #4A148C;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        border-left: 3px solid #4A148C;
        padding: 4px 10px;
        margin: 0 0 14px 0;
        background: #F3E5F5;
    }
    [data-testid="stMetricValue"] {
        font-size: 24px !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 12px !important;
        color: #666;
        text-transform: uppercase;
    }
    </style>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # Default values (used by Reset button)
    # -------------------------------------------------------------------
    DEFAULTS = {
        "n_iter": 5000,
        "use_correlation": True,
        "g_lo": 2.0, "g_mod": 6.0, "g_hi": 11.0,
        "my0_lo": 19.0, "my0_mod": 21.0, "my0_hi": 22.0,
        "mt_lo": 21.0, "mt_mod": 23.0, "mt_hi": 25.0,
        "em_in_lo": 8.0, "em_in_mod": 8.5, "em_in_hi": 9.0,
        "em_out_lo": 7.0, "em_out_mod": 9.5, "em_out_hi": 11.5,
    }

    # Bid postures — set the entry-multiple triangular distribution
    # (Each posture's range reflects the realistic spread of winning prices around that bid)
    MC_BID_POSTURES = {
        "anchor": {
            "label": "⬇ ANCHOR · 8.5×",
            "em_in_lo": 8.0, "em_in_mod": 8.5, "em_in_hi": 9.0,
            "blurb": "Win prices distribute around 8.5×. Tight discipline; ~10–20% probability of winning auction.",
        },
        "stretch": {
            "label": "➡ STRETCH · 9.0×",
            "em_in_lo": 8.5, "em_in_mod": 9.0, "em_in_hi": 9.5,
            "blurb": "Willing to push to 9.0× for conviction. ~30–45% probability of winning auction.",
        },
        "original": {
            "label": "⬆ AT FLOOR · 9.5×",
            "em_in_lo": 9.0, "em_in_mod": 9.5, "em_in_hi": 10.0,
            "blurb": "Accept seller's range floor. Comparison only — we walk above 9.0×.",
        },
    }

    # NOTE: pending-bid handler moved to app.py (shared across tabs)
    # so a single click updates both Dashboard AND MC state consistently.

    # Initialise session state on first load
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = v
    st.session_state.setdefault("_active_bid", "anchor")

    # -------------------------------------------------------------------
    # Header
    # -------------------------------------------------------------------
    st.markdown("""
    <div class='brand-header'>
      <h1>🎲 CardioPath — Probability Simulation</h1>
      <div class='meta'>Run the deal 10,000 times under different conditions to see how often we hit our return targets — and how often we don't</div>
    </div>
    """, unsafe_allow_html=True)

    # -------------------------------------------------------------------
    # Bid posture selector (matches main dashboard layout)
    # -------------------------------------------------------------------
    active_bid = st.session_state.get("_active_bid", "anchor")
    st.markdown("<div class='section-h'>🎯 Bid Posture · sets the entry-multiple distribution</div>", unsafe_allow_html=True)
    col_a, col_s, col_o = st.columns(3)
    mc_buttons = [(col_a, "anchor"), (col_s, "stretch"), (col_o, "original")]
    for col, key in mc_buttons:
        info = MC_BID_POSTURES[key]
        is_active = (key == active_bid)
        label = ("✅ " + info["label"]) if is_active else info["label"]
        with col:
            if st.button(label, use_container_width=True, key=f"mc_bid_{key}",
                         type=("primary" if is_active else "secondary")):
                st.session_state["_pending_bid"] = key
                st.rerun()
            st.caption(info["blurb"])

    # -------------------------------------------------------------------
    # Sidebar — input ranges (plain language)
    # -------------------------------------------------------------------
    with st.sidebar:
        st.markdown("## Set the input ranges")
        st.caption("For each input, set the **worst case (Low)**, **most likely (Mode)**, and **best case (High)**. The simulation samples randomly within each range.")

        if st.button("↺ Reset to defaults", use_container_width=True):
            for k, v in DEFAULTS.items():
                st.session_state[k] = v
            st.rerun()

        st.divider()

        st.slider("How many simulations to run", 1000, 50000, step=1000, key="n_iter")
        st.toggle(
            "Tie cycles together (recommended)",
            key="use_correlation",
            help="In real life, when the economy is strong, growth AND exit prices tend to be high together. When it's weak, both fall. Turning this OFF lets them move independently — overstates how often you get lucky in one but unlucky in the other.",
        )

        st.divider()
        st.markdown("**🔵 Revenue Growth** *(% per year)*")
        st.number_input("Worst case",  0.0, 15.0, step=0.5, format="%.1f", key="g_lo")
        st.number_input("Most likely", 0.0, 15.0, step=0.5, format="%.1f", key="g_mod")
        st.number_input("Best case",   0.0, 15.0, step=0.5, format="%.1f", key="g_hi")

        st.markdown("**🔵 Starting EBITDA Margin** *(Y0 %)*")
        st.number_input("Worst case",  10.0, 28.0, step=0.5, format="%.1f", key="my0_lo")
        st.number_input("Most likely", 10.0, 28.0, step=0.5, format="%.1f", key="my0_mod")
        st.number_input("Best case",   10.0, 28.0, step=0.5, format="%.1f", key="my0_hi")

        st.markdown("**🔵 Target EBITDA Margin** *(Y3+ %)*")
        st.number_input("Worst case",  10.0, 28.0, step=0.5, format="%.1f", key="mt_lo")
        st.number_input("Most likely", 10.0, 28.0, step=0.5, format="%.1f", key="mt_mod")
        st.number_input("Best case",   10.0, 28.0, step=0.5, format="%.1f", key="mt_hi")

        st.markdown("**🔵 Entry Multiple** *(EV ÷ EBITDA at purchase)*")
        st.number_input("Worst case",  6.0, 14.0, step=0.1, format="%.1f", key="em_in_lo")
        st.number_input("Most likely", 6.0, 14.0, step=0.1, format="%.1f", key="em_in_mod")
        st.number_input("Best case",   6.0, 14.0, step=0.1, format="%.1f", key="em_in_hi")

        st.markdown("**🔵 Exit Multiple** *(EV ÷ EBITDA at sale)*")
        st.number_input("Worst case",  6.0, 14.0, step=0.1, format="%.1f", key="em_out_lo")
        st.number_input("Most likely", 6.0, 14.0, step=0.1, format="%.1f", key="em_out_mod")
        st.number_input("Best case",   6.0, 14.0, step=0.1, format="%.1f", key="em_out_hi")

        st.divider()
        st.caption("All other inputs (Capex, Tax, Debt level, Interest rate) held at the base case.")

    # Read current values from session_state
    n_iter = st.session_state["n_iter"]
    use_correlation = st.session_state["use_correlation"]
    g_lo, g_mod, g_hi = st.session_state["g_lo"], st.session_state["g_mod"], st.session_state["g_hi"]
    my0_lo, my0_mod, my0_hi = st.session_state["my0_lo"], st.session_state["my0_mod"], st.session_state["my0_hi"]
    mt_lo, mt_mod, mt_hi = st.session_state["mt_lo"], st.session_state["mt_mod"], st.session_state["mt_hi"]
    em_in_lo, em_in_mod, em_in_hi = st.session_state["em_in_lo"], st.session_state["em_in_mod"], st.session_state["em_in_hi"]
    em_out_lo, em_out_mod, em_out_hi = st.session_state["em_out_lo"], st.session_state["em_out_mod"], st.session_state["em_out_hi"]


    # run_simulation is now defined at MODULE level (above this function)
    # so st.cache_data works correctly across reruns.


    # Build params dict
    params = {
        "Growth":        (g_lo, g_mod, g_hi),
        "Margin_Y0":     (my0_lo, my0_mod, my0_hi),
        "Margin_Target": (mt_lo, mt_mod, mt_hi),
        "Entry_Mult":    (em_in_lo, em_in_mod, em_in_hi),
        "Exit_Mult":     (em_out_lo, em_out_mod, em_out_hi),
    }

    # Validate distributions (low <= mode <= high)
    for k, (lo, mode, hi) in params.items():
        if not (lo <= mode <= hi):
            st.error(f"{k}: low ({lo}) ≤ mode ({mode}) ≤ high ({hi}) required.")
            st.stop()

    # Run simulation — pass params as a frozen tuple so st.cache_data hashes correctly
    params_tuple = tuple((k, tuple(v)) for k, v in params.items())
    df = run_simulation(n_iter, params_tuple, use_correlation)

    # -------------------------------------------------------------------
    # Headline stats — written for a layperson
    # -------------------------------------------------------------------
    st.markdown("<div class='section-h'>The Headline — Out of all simulations, here's what we got</div>", unsafe_allow_html=True)
    st.caption(f"Ran the deal **{n_iter:,} times** with random combinations of growth, margin, and exit prices. Below: how the {n_iter:,} outcomes break down.")

    c1, c2, c3, c4, c5 = st.columns(5)
    with st.expander("⚖️ Probability-weighted IRR across the bid ladder (the honest expected return)", expanded=False):
        st.markdown("""
    The deterministic IRRs (Median, P(IRR≥20%), etc.) below are **conditional on winning the auction**.
    Factoring in the probability of NOT winning at our disciplined bid:

    | Bid outcome | Probability* | Conditional IRR (TOP-2) | Contribution |
    |---|---:|---:|---:|
    | Win at anchor 8.5× | ~15% | 29.9% | +4.5 pp |
    | Win at stretch 9.0× | ~30% | 27.7% | +8.3 pp |
    | Lose; capital sits at fund-cash rate (~4%) | ~55% | 4.0% | +2.2 pp |
    | **Probability-weighted IRR** | | | **~15.0%** |

    > **\\*Win probabilities are illustrative PE-norm estimates — NOT from a published study.**
    > Validation path: M&A advisor pitch (banks share their hit-rate file by bid spread); Cambridge Associates / Bain Global PE Report bid-spread benchmarks; Pitchbook deal analytics. These are diligence priorities, not IC-decision facts.

    **Below hurdle on a weighted basis** — explicitly traded for risk-adjusted underwriting and capital preservation.
    """)

    c1.metric("Typical IRR (middle outcome)", f"{df['IRR'].median():.1f}%",
              help="Half the simulations beat this, half don't. The 'middle' result if you ranked all 10k outcomes.")
    c2.metric("Average MOIC", f"{df['MOIC'].mean():.2f}×",
              help="On average, sponsor equity grows by this multiple over the 5-year hold.")
    c3.metric("Chance of beating 20% IRR", f"{(df['IRR'] >= 20).mean()*100:.0f}%",
              help="The PE 'hurdle' — the minimum return LPs expect.")
    c4.metric("Chance of beating 30% IRR", f"{(df['IRR'] >= 30).mean()*100:.0f}%",
              help="A 'fund-returner-class' result — what makes a PE fund's overall performance.")
    c5.metric("Chance of capital loss (MOIC < 1)", f"{(df['MOIC'] < 1.0).mean()*100:.0f}%",
              help="Probability of getting back less than we invested.")

    # Quantiles table — friendlier headers
    st.markdown("##### If we ran this deal 100 times, here's what we'd see:")
    qdf = pd.DataFrame({
        "Outcome rank": [
            "Worst 5 out of 100",
            "Worst 10 out of 100",
            "Bottom quarter",
            "Middle (typical)",
            "Top quarter",
            "Top 10 out of 100",
            "Top 5 out of 100",
        ],
        "Sponsor MOIC":  [f"{df['MOIC'].quantile(q):.2f}×" for q in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)],
        "Annualised return (IRR)": [f"{df['IRR'].quantile(q):.1f}%"  for q in (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)],
    })
    st.dataframe(qdf, hide_index=True, use_container_width=True)

    st.divider()

    # -------------------------------------------------------------------
    # Scenario probabilities — connects MC to the named scenarios on
    # the main dashboard
    # -------------------------------------------------------------------
    st.markdown("<div class='section-h'>How likely is each named scenario?</div>", unsafe_allow_html=True)
    st.caption(
        "These are the same scenarios on the main dashboard. For each one, we look at the simulation and ask: "
        "**how often did the random run come out at least this good (for value-creation) or at least this bad (for risk)?**"
    )
    st.caption(
        "⚠️ **Caveat on probabilities:** The MC uses Gaussian-copula correlation between Growth, Margin, and Exit Multiple. "
        "Real-world tails are fatter than the model assumes (regulatory shocks are binary; cycle correlations spike during stress). "
        "Actual P(capital loss) is likely 2–5%, not <1% as the simulation may suggest."
    )

    # Named scenarios — IRRs recomputed dynamically at the CURRENT bid posture mode.
    # Each scenario is defined by its operating profile overrides; IRR is computed
    # at the entry-multiple mode currently set in the sidebar.
    SCENARIO_DEFS_VALUE = [
        # (name, blurb, override_dict)
        ("Base — organic only",          "Do nothing operationally — needs an operational lever to clear hurdle",
         {}),
        ("+ Centralized reading",         "Cardiologists central, techs onsite (+3pp margin)",
         dict(Margin_Target=0.24, Ramp_Years=4)),
        ("+ Bolt-on M&A",                 "10–15 acquisitions over 5 years",
         dict(Growth=0.08)),
        ("TOP-2 combined",                "Centralized reading + M&A engine — pitch this",
         dict(Growth=0.08, Margin_Target=0.24, Ramp_Years=4)),
        ("⭐ FULL plan (aspirational)",    "Everything + 11.5× IPO exit. NOT the underwrite — top-decile ceiling.",
         dict(Growth=0.09, Margin_Target=0.265, Ramp_Years=4, Capex_Pct=0.055, Exit_Mult=11.5)),
    ]
    SCENARIO_DEFS_RISK = [
        ("⚠ CMS rate cut",                "Medicare cuts margin -2pp; absorbed by bid discipline",
         dict(Margin_Y0=0.19, Margin_Target=0.19)),
        ("⚠ Multiple compression 7.0×",    "Sector de-rate / FTC; below hurdle, no capital loss",
         dict(Exit_Mult=7.0)),
        ("⚠ M&A pipeline misses",         "Growth slows to 2%; positive but below hurdle",
         dict(Growth=0.02)),
        ("💀 Triple hit",                  "All three failure modes simultaneously",
         dict(Growth=0.02, Margin_Y0=0.19, Margin_Target=0.19, Exit_Mult=7.0)),
    ]

    # Compute scenario IRRs at the CURRENT bid mode's entry multiple
    def compute_scenario_irr(override):
        cfg = dict(CARDIO)
        cfg.update(override)
        cfg["Entry_Mult"] = st.session_state["em_in_mod"]
        cfg["Debt_Mult"] = min(6.0, 0.60 * cfg["Entry_Mult"])
        cfg["Sweep_Pct"] = 0.50
        return model(cfg, basis="EBITDA")

    DASHBOARD_SCENARIOS_VALUE = [
        (name, *((r := compute_scenario_irr(ov))["irr"]*100, r["moic"]), blurb)
        for name, blurb, ov in SCENARIO_DEFS_VALUE
    ]
    DASHBOARD_SCENARIOS_RISK = [
        (name, *((r := compute_scenario_irr(ov))["irr"]*100, r["moic"]), blurb)
        for name, blurb, ov in SCENARIO_DEFS_RISK
    ]
    # Reorder: (name, target_irr, target_moic, blurb) — match the loop below
    DASHBOARD_SCENARIOS_VALUE = [(n, irr, moic, b) for n, irr, moic, b in DASHBOARD_SCENARIOS_VALUE]
    DASHBOARD_SCENARIOS_RISK  = [(n, irr, moic, b) for n, irr, moic, b in DASHBOARD_SCENARIOS_RISK]

    st.caption(
        f"💡 IRR targets below are recomputed live at the **{st.session_state['em_in_mod']:.1f}×** mode "
        f"of your current bid-posture distribution. Click a different bid posture above to see how the targets shift."
    )

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("##### 🟢 Value-creation scenarios — *chance of hitting this or better*")
        rows = []
        for name, target_irr, target_moic, blurb in DASHBOARD_SCENARIOS_VALUE:
            prob = (df['IRR'] >= target_irr).mean() * 100
            rows.append({
                "Scenario": name,
                "Target IRR": f"{target_irr:.1f}%",
                "Chance ≥ target": f"{prob:.0f}%",
                "What this means": blurb,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    with col_right:
        st.markdown("##### 🔴 Risk scenarios — *chance of falling to this or worse*")
        rows = []
        for name, target_irr, target_moic, blurb in DASHBOARD_SCENARIOS_RISK:
            prob = (df['IRR'] <= target_irr).mean() * 100
            rows.append({
                "Scenario": name,
                "IRR floor": f"{target_irr:.1f}%",
                "Chance ≤ floor": f"{prob:.0f}%",
                "What this means": blurb,
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    st.caption(
        "**Reading these:** A 30% chance of hitting the 'TOP-2 combined' outcome (26.7% IRR or better) "
        "means the deal lands at fund-returner level in roughly 30 out of 100 simulations. "
        "A 5% chance of the 'Triple hit' (or worse) means catastrophic loss is rare but not zero — size the deal accordingly."
    )

    st.divider()

    # -------------------------------------------------------------------
    # Tabs: distributions / joint plots / variance contribution
    # -------------------------------------------------------------------
    tab_dist, tab_joint, tab_var = st.tabs(
        ["📊 Distribution of outcomes", "🔀 Two-input maps", "🌪 What matters most"]
    )

    # ---------- DISTRIBUTIONS ----------
    with tab_dist:
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        fig.patch.set_facecolor("white")

        # MOIC histogram
        axes[0].hist(df["MOIC"], bins=60, color="#7B1FA2", alpha=0.75, edgecolor="white")
        axes[0].axvline(1.0, color="red", lw=1.5, ls="--", alpha=0.7, label="MOIC = 1× (break-even)")
        axes[0].axvline(df["MOIC"].median(), color="black", lw=1.5, ls="-", label=f"Median {df['MOIC'].median():.2f}×")
        axes[0].set_xlabel("MOIC")
        axes[0].set_ylabel("Frequency")
        axes[0].set_title("MOIC distribution", fontweight="bold")
        axes[0].legend(fontsize=9)
        axes[0].grid(axis="y", alpha=0.3)
        for s in ("top", "right"):
            axes[0].spines[s].set_visible(False)

        # IRR cumulative distribution
        sorted_irr = np.sort(df["IRR"])
        cdf = np.arange(1, len(sorted_irr) + 1) / len(sorted_irr)
        axes[1].plot(sorted_irr, 1 - cdf, color="#1F4E78", lw=2)
        axes[1].fill_between(sorted_irr, 0, 1 - cdf, alpha=0.2, color="#1F4E78")
        axes[1].axvline(20, color="red", lw=1.5, ls="--", alpha=0.7, label="20% hurdle")
        axes[1].axvline(30, color="green", lw=1.5, ls="--", alpha=0.5, label="30% target")
        axes[1].axvline(0,  color="black", lw=1.0, ls="-",  alpha=0.4, label="0% (capital preservation)")
        axes[1].set_xlabel("IRR (%)")
        axes[1].set_ylabel("P(IRR ≥ x)")
        axes[1].set_title("IRR — exceedance probability", fontweight="bold")
        axes[1].legend(fontsize=9, loc="upper right")
        axes[1].grid(alpha=0.3)
        for s in ("top", "right"):
            axes[1].spines[s].set_visible(False)
        axes[1].set_xlim(min(sorted_irr) - 2, max(sorted_irr) + 2)
        axes[1].set_ylim(0, 1)

        plt.tight_layout()
        st.pyplot(fig, use_container_width=True)

    # ---------- JOINT PLOTS ----------
    with tab_joint:
        st.caption("Each dot is one simulation iteration. Color shows IRR.")

        fig2, axes2 = plt.subplots(1, 2, figsize=(14, 6))
        fig2.patch.set_facecolor("white")

        norm = mcolors.TwoSlopeNorm(vmin=df["IRR"].min(), vcenter=20, vmax=df["IRR"].max())

        # Growth × Exit Mult
        sc1 = axes2[0].scatter(df["Growth"], df["Exit_Mult"], c=df["IRR"],
                               cmap="RdYlGn", norm=norm, s=4, alpha=0.5)
        axes2[0].set_xlabel("Revenue Growth (%)")
        axes2[0].set_ylabel("Exit EV / EBITDA")
        axes2[0].set_title("Growth × Exit Mult → IRR", fontweight="bold")
        plt.colorbar(sc1, ax=axes2[0], label="IRR %")
        for s in ("top", "right"):
            axes2[0].spines[s].set_visible(False)
        axes2[0].grid(alpha=0.3)

        # Margin_Target × Exit Mult
        sc2 = axes2[1].scatter(df["Margin_Target"], df["Exit_Mult"], c=df["IRR"],
                               cmap="RdYlGn", norm=norm, s=4, alpha=0.5)
        axes2[1].set_xlabel("EBITDA Margin Target (%)")
        axes2[1].set_ylabel("Exit EV / EBITDA")
        axes2[1].set_title("Margin Target × Exit Mult → IRR", fontweight="bold")
        plt.colorbar(sc2, ax=axes2[1], label="IRR %")
        for s in ("top", "right"):
            axes2[1].spines[s].set_visible(False)
        axes2[1].grid(alpha=0.3)

        plt.tight_layout()
        st.pyplot(fig2, use_container_width=True)

    # ---------- VARIANCE CONTRIBUTION ----------
    with tab_var:
        st.caption(
            "Of all the uncertainty in the outcome (MOIC), how much is **explained by each input**? "
            "Tells you where to focus diligence and management attention."
        )

        inputs_to_check = ["Growth", "Margin_Y0", "Margin_Target", "Entry_Mult", "Exit_Mult"]
        contributions = {}
        for inp_name in inputs_to_check:
            contributions[inp_name] = df[inp_name].corr(df["MOIC"]) ** 2
        total = sum(contributions.values())
        contrib_pct = {k: v / total * 100 for k, v in contributions.items()}
        sorted_contrib = sorted(contrib_pct.items(), key=lambda x: -x[1])

        fig3, ax3 = plt.subplots(figsize=(10, 5))
        fig3.patch.set_facecolor("white")
        names = [k for k, _ in sorted_contrib]
        vals  = [v for _, v in sorted_contrib]
        bars  = ax3.barh(range(len(names)), vals, color="#7B1FA2", edgecolor="white")
        ax3.set_yticks(range(len(names)))
        ax3.set_yticklabels(names, fontsize=11)
        ax3.invert_yaxis()
        ax3.set_xlabel("Variance contribution (%)")
        ax3.set_title("Which input drives most of the MOIC uncertainty?",
                      fontweight="bold", pad=12)
        for s in ("top", "right", "left"):
            ax3.spines[s].set_visible(False)
        ax3.grid(axis="x", alpha=0.3)
        ax3.tick_params(left=False)
        for bar, val in zip(bars, vals):
            ax3.text(val + 1, bar.get_y() + bar.get_height()/2, f"{val:.0f}%",
                     va="center", fontsize=10, fontweight="bold")
        plt.tight_layout()
        st.pyplot(fig3, use_container_width=True)

    st.divider()

    # -------------------------------------------------------------------
    # How to read this
    # -------------------------------------------------------------------
    with st.expander("📚 What is this and how do I read it?", expanded=False):
        st.markdown("""
    ### In plain English

    Instead of saying *"if growth is 8% and the exit multiple is 9.5×, MOIC will be 2.58×,"*
    this page asks *"if growth could realistically be anywhere from 2% to 11% and exit anywhere from 7× to 11.5×, **how often** does the deal succeed across all those combinations?"*

    **We run the deal 10,000 times** with random combinations of inputs (within the ranges you set in the sidebar), then count how often each outcome happens.

    ### What each number means

    - **Typical IRR** — if you ranked all 10,000 outcomes from worst to best, this is the middle one
    - **Chance of beating 20% IRR** — how often did the random run produce an IRR ≥ 20%? That's the PE return target
    - **Chance of capital loss** — how often did MOIC come out below 1.0× (we get back less than we invested)
    - **Chance of named scenario** — for each of the scenarios on the main dashboard, how often did the sim land at that outcome or better/worse

    ### What the toggle does

    **Tie cycles together** = realistic. In real life, when the economy is good, growth is high AND exit prices are high (both winning together). When it's bad, both fall (both losing together). Without this, the simulation lets growth go up while exit multiples go down, which is mostly fictional.

    ### Important caveats — the limits of this analysis

    1. **The ranges you set are still assumptions.** If you say "Growth is between 2% and 11%," the simulation believes you. If reality is wider, the answer is too narrow.
    2. **Some risks aren't smooth.** A CMS rule change or FTC action is a yes/no event, not a number on a dial. Monte Carlo doesn't capture binary regime changes well.
    3. **This complements, not replaces, the named scenarios.** The scenarios tell the **story** ("if we execute centralized reading…"). The simulation tells the **probability** ("…and that delivers about 30% of the time").
    """)

