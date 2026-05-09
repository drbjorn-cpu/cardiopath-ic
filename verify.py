"""Independently recompute base-case MOIC/IRR for all four sheets."""

def model(inp, basis="EBITDA"):
    rev0       = inp["Rev_Y0"]
    g          = inp["Growth"]
    m0         = inp["Margin_Y0"]
    mt         = inp["Margin_Target"]
    # Margin_Pricing = the margin underwritten at the bid (sets EV / debt / equity).
    # Decoupled from Margin_Y0 so post-close margin compression (CMS cut, etc.)
    # doesn't shrink the deal we actually closed at $607m / $258m equity.
    m_price    = inp.get("Margin_Pricing", m0)
    ramp       = inp["Ramp_Years"]
    capex_pct  = inp["Capex_Pct"]
    dnwc_pct   = inp["DNWC_Pct"]
    da_pct     = inp["DA_Pct"]
    tax        = inp["Tax_Rate"]
    hold       = inp["Hold"]
    em_in      = inp["Entry_Mult"]
    fee_pct    = inp["Fee_Pct"]
    debt_mult  = inp["Debt_Mult"]
    rate       = inp["Int_Rate"]
    amort_pct  = inp["Amort_Pct"]
    sweep      = inp["Sweep_Pct"]
    em_out     = inp["Exit_Mult"]

    ebitda_pricing = rev0 * m_price
    ebitda0        = rev0 * m0
    ev      = (rev0 * em_in) if basis == "ARR" else (ebitda_pricing * em_in)
    fees    = ev * fee_pct
    uses    = ev + fees
    debt0   = ebitda_pricing * debt_mult
    equity  = uses - debt0

    rev   = [rev0]
    marg  = [m0]
    ebitda_arr = [ebitda0]
    for t in range(1, 6):
        rev.append(rev[-1] * (1 + g))
        marg.append(m0 + min(t, ramp) / ramp * (mt - m0))
        ebitda_arr.append(rev[t] * marg[t])

    ufcf = []
    for t in range(0, 6):
        da    = rev[t] * da_pct
        ebit  = ebitda_arr[t] - da
        nopat = ebit - max(ebit, 0) * tax
        capex = rev[t] * capex_pct
        dnwc  = 0 if t == 0 else (rev[t] - rev[t-1]) * dnwc_pct
        ufcf.append(nopat + da - capex - dnwc)

    debt = debt0
    cash = 0.0
    for t in range(1, 6):
        beg_debt = debt
        interest = beg_debt * rate
        at_int   = interest * (1 - tax)
        lfcf     = ufcf[t] - at_int
        mand     = min(debt0 * amort_pct, beg_debt)
        avail    = lfcf - mand
        cash_sweep = min(max(avail, 0) * sweep, beg_debt - mand)
        end_debt = beg_debt - mand - cash_sweep
        cash    += avail - cash_sweep
        debt     = end_debt

    if basis == "ARR":
        exit_ev = rev[5] * em_out
    else:
        exit_ev = ebitda_arr[5] * em_out
    exit_equity = exit_ev - debt + cash
    moic = exit_equity / equity
    irr  = (exit_equity / equity) ** (1 / hold) - 1

    return dict(
        ebitda0=ebitda0, ev=ev, fees=fees, debt0=debt0, equity=equity,
        rev=rev, marg=marg, ebitda_arr=ebitda_arr, ufcf=ufcf,
        exit_ev=exit_ev, end_debt=debt, end_cash=cash,
        exit_equity=exit_equity, moic=moic, irr=irr,
    )


ARIA = dict(Rev_Y0=720, Growth=0.05, Margin_Y0=0.16, Margin_Target=0.19, Ramp_Years=3,
            Capex_Pct=0.035, DNWC_Pct=0.15, DA_Pct=0.035, Tax_Rate=0.30, Hold=5,
            Entry_Mult=9.5, Fee_Pct=0.025, Debt_Mult=5.5, Int_Rate=0.075,
            Amort_Pct=0.01, Sweep_Pct=0.75, Exit_Mult=9.5)

CARDIO = dict(Rev_Y0=340, Growth=0.04, Margin_Y0=0.21, Margin_Target=0.21, Margin_Pricing=0.21,
              Ramp_Years=3,
              Capex_Pct=0.05, DNWC_Pct=0.10, DA_Pct=0.06, Tax_Rate=0.25, Hold=5,
              Entry_Mult=8.5, Fee_Pct=0.025, Debt_Mult=5.1, Int_Rate=0.085,
              Amort_Pct=0.01, Sweep_Pct=0.50, Exit_Mult=9.5)
# Note: Debt_Mult=5.1 is LTV-capped at 60% of EV at 8.5x entry
# (5.1 = 0.60 × 8.5; lender practice cap for HC services LBOs)
# Sweep_Pct=0.50: TLB / unitranche standard for HC services; preserves cash for M&A bolt-ons

MED_SAAS = dict(Rev_Y0=84, Growth=0.35, Margin_Y0=0.12, Margin_Target=0.28, Ramp_Years=5,
                Capex_Pct=0.025, DNWC_Pct=0.05, DA_Pct=0.04, Tax_Rate=0.25, Hold=5,
                Entry_Mult=9.0, Fee_Pct=0.025, Debt_Mult=5.0, Int_Rate=0.10,
                Amort_Pct=0.05, Sweep_Pct=0.50, Exit_Mult=6.0)

MED_LBO = dict(Rev_Y0=84, Growth=0.35, Margin_Y0=0.12, Margin_Target=0.28, Ramp_Years=5,
               Capex_Pct=0.025, DNWC_Pct=0.05, DA_Pct=0.04, Tax_Rate=0.25, Hold=5,
               Entry_Mult=75.0, Fee_Pct=0.025, Debt_Mult=5.0, Int_Rate=0.10,
               Amort_Pct=0.05, Sweep_Pct=0.75, Exit_Mult=20.0)


def report(name, r, currency="$"):
    print(f"\n=== {name} (BASE CASE) ===")
    print(f"  Entry EBITDA:      {currency}{r['ebitda0']:>8.1f}")
    print(f"  Enterprise Value:  {currency}{r['ev']:>8.1f}")
    print(f"  Fees:              {currency}{r['fees']:>8.1f}")
    print(f"  Debt:              {currency}{r['debt0']:>8.1f}")
    print(f"  Sponsor Equity:    {currency}{r['equity']:>8.1f}")
    print(f"  Y5 Revenue/ARR:    {currency}{r['rev'][5]:>8.1f}")
    print(f"  Y5 EBITDA:         {currency}{r['ebitda_arr'][5]:>8.1f}  (margin {r['marg'][5]*100:.1f}%)")
    print(f"  Exit EV:           {currency}{r['exit_ev']:>8.1f}")
    print(f"  Y5 Ending Debt:    {currency}{r['end_debt']:>8.1f}")
    print(f"  Y5 Ending Cash:    {currency}{r['end_cash']:>8.1f}")
    print(f"  Exit Equity:       {currency}{r['exit_equity']:>8.1f}")
    print(f"  MOIC:              {r['moic']:>8.2f}x")
    print(f"  IRR:               {r['irr']*100:>8.1f}%")


def scenarios(name, base, basis, cases):
    print(f"\n=== {name} — Scenario MOIC / IRR ===")
    for label, mt, em in cases:
        cfg = dict(base); cfg["Margin_Target"] = mt; cfg["Exit_Mult"] = em
        r = model(cfg, basis=basis)
        print(f"  {label:5s}  MarginT {mt*100:5.1f}%  Exit {em:5.1f}x  →  MOIC {r['moic']:.2f}x   IRR {r['irr']*100:.1f}%")


if __name__ == "__main__":
    report("MedScribe (SaaS view)", model(MED_SAAS, basis="ARR"), "$")
    report("MedScribe (Stretched LBO view)", model(MED_LBO, basis="EBITDA"), "$")
    report("Aria",        model(ARIA, basis="EBITDA"), "€")
    report("CardioPath",  model(CARDIO, basis="EBITDA"), "$")

    scenarios("MedScribe (SaaS)",      MED_SAAS, "ARR",
              [("Base", 0.28, 6.0), ("Bear", 0.20, 4.0), ("Bull", 0.32, 9.0)])
    scenarios("MedScribe (LBO)",       MED_LBO, "EBITDA",
              [("Base", 0.28, 20.0), ("Bear", 0.20, 10.0), ("Bull", 0.32, 30.0)])
    scenarios("Aria",                  ARIA, "EBITDA",
              [("Base", 0.19, 9.5), ("Bear", 0.16, 7.5), ("Bull", 0.20, 11.0)])
    scenarios("CardioPath",            CARDIO, "EBITDA",
              [("Base", 0.22, 10.0), ("Bear", 0.20, 8.0), ("Bull", 0.23, 11.5)])
