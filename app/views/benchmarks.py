"""Model Benchmarks & Deployment Gate Scorecard for ElderCare Vision.

Every number shown here is read from committed evaluation artifacts:
the one-time sealed evaluation of the frozen model
(docs/reports/V6_3_FINAL_TESTB_EVALUATION.json) and the per-phase training reports.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.cards import render_page_header, render_section_header
from app.core.data_loader import get_benchmark_reports

GATES = {"recall": 0.90, "precision": 0.85, "p95_tta": 3.0, "fa_per_hour": 0.05}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _ci(ci: list[float] | None) -> str:
    return "" if not ci else f"95% CI {ci[0] * 100:.1f}-{ci[1] * 100:.1f}%"


def render_benchmarks_view() -> None:
    """Render the final gate scorecard, phase progression, and empirical limitations."""
    reports = get_benchmark_reports()
    final = reports.get("final_eval")
    passed = bool(final and final["gate_status"]["overall_gate_passed"])

    render_page_header(
        title="Benchmarks & Gate",
        intro=(
            "How the final model scored on test videos it never saw during development. "
            "Each number is shown next to the target it had to reach before release."
        ),
        badge_text="Gate target met" if passed else "Gate incomplete",
        badge_color="green" if passed else "orange",
        badge_icon=":material/check_circle:" if passed else ":material/pending:",
    )

    with st.expander("What do these numbers mean?", icon=":material/help:"):
        st.markdown(
            """
            - **Falls caught (recall):** out of all real falls, how many raised an alert.
            - **Correct alerts (precision):** out of all alerts, how many were real falls.
            - **Time to alert:** seconds from the start of a fall to the alert. "95%" means
              95 out of 100 alerts were at least this fast.
            - **False alarms per hour:** alerts raised during normal daily activity at home.
            - **95% CI (in the ? tooltips):** the likely range of the true value, given
              the limited number of test videos.
            - **Test-B:** a set of videos locked away until the model was final, so the
              results could not be tuned to it.
            """
        )

    if final is None:
        st.warning(
            "The final test report is missing (`docs/reports/V6_3_FINAL_TESTB_EVALUATION.json`).",
            icon=":material/warning:",
        )
        return

    tb = final["splits"]["test_b"]
    m, t = tb["metrics"], tb["time_to_alert_seconds"]
    lf = final["splits"].get("longform_adl_heldout", {})

    st.divider()

    # 1. Sealed Test-B Scorecard
    render_section_header(
        title="Final test results (model v6.3)",
        subtitle=f"{tb['total_sequences']} UP-Fall test videos, filmed from 2 camera angles.",
        icon=":material/fact_check:",
    )

    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.metric(
            "Falls caught",
            _pct(m["recall"]),
            delta=f"Target: at least {GATES['recall']:.0%}",
            delta_color="off",
            delta_arrow="off",
            help=_ci(m["recall_95_ci"]),
            border=True,
        )
    with g2:
        st.metric(
            "Correct alerts",
            _pct(m["precision"]),
            delta=f"Target: at least {GATES['precision']:.0%}",
            delta_color="off",
            delta_arrow="off",
            help=_ci(m["precision_95_ci"]),
            border=True,
        )
    with g3:
        st.metric(
            "Time to alert (95%)",
            f"{t['p95']:.2f} s",
            delta=f"Target: under {GATES['p95_tta']:.0f} s",
            delta_color="off",
            delta_arrow="off",
            help=f"95% of alerts arrived within this time. Typical (median): {t['median']:.2f} s.",
            border=True,
        )
    with g4:
        ci = lf.get("poisson_95_ci", [None, None])
        ci_str = f" 95% CI: up to {ci[1]:.2f} per hour." if ci and ci[1] is not None else ""
        st.metric(
            "False alarms per hour",
            f"{lf.get('false_alarm_rate_per_hour', 0.0):.2f}",
            delta=f"{lf.get('total_false_alarms', 0)} in {lf.get('total_hours', 0):.2f} h of home video",
            delta_color="off",
            delta_arrow="off",
            help="Measured on everyday home video. Meets the target, but more hours of "
            f"testing are needed to be sure.{ci_str}",
            border=True,
        )

    # Per-Camera Breakdown Table
    st.markdown("**:material/table_chart: Results by camera angle**")
    cam_rows = [
        {
            "Camera": f"Camera {str(cam).removeprefix('cam')}",
            "Falls tested": v["fall_sequences"],
            "Falls caught (%)": v["recall"] * 100,
            "Correct alerts (%)": v["precision"] * 100,
            "False alarms": v["false_alerts_total"],
            "Time to alert, 95% (s)": v["p95_tta_sec"],
        }
        for cam, v in tb["camera_breakdown"].items()
    ]
    st.dataframe(
        pd.DataFrame(cam_rows),
        column_config={
            "Falls caught (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.1f%%"
            ),
            "Correct alerts (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.1f%%"
            ),
        },
        hide_index=True,
        width="stretch",
    )

    st.divider()

    # 2. Phase progression
    render_section_header(
        title="Progress during development",
        subtitle="Earlier versions, measured on development data before the final model was locked.",
        icon=":material/trending_up:",
    )

    rows = []
    for name, rep in reports.get("phases", []):
        b = rep["event_level_dev_metrics"]
        cams = b["oof_per_camera"]
        rows.append(
            {
                "Phase": name,
                "Camera 1 falls caught (%)": cams["UP-Fall:cam1"]["recall"] * 100,
                "Camera 2 falls caught (%)": cams["UP-Fall:cam2"]["recall"] * 100,
                "URFD falls caught (%)": cams["URFD:cam0"]["recall"] * 100,
                "Correct alerts (%)": b["oof_precision"] * 100,
                "False alarms per hour": b["dev_longform_fa_rate_per_hour"],
                "Time to alert, 95% (s)": b["oof_p95_tta"],
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch")
        st.caption("Falls caught per phase, by camera (higher is better)")
        st.bar_chart(
            df.set_index("Phase")[
                [
                    "Camera 1 falls caught (%)",
                    "Camera 2 falls caught (%)",
                    "URFD falls caught (%)",
                ]
            ],
            height=260,
        )

    st.divider()

    # 3. Findings and limitations bento
    render_section_header(
        title="What helped, and known limits",
        subtitle="The changes that improved results most, and what the tests cannot yet show.",
        icon=":material/lightbulb:",
    )
    c1, c2 = st.columns(2)
    with c1, st.container(border=True, height="stretch"):
        st.markdown("**:material/auto_fix_high: What helped most**")
        st.markdown(
            """
            - **Following each person separately:** the model no longer mixes up the person
              who falls with someone standing nearby (a problem on camera 2).
            - **Keeping track during the fall:** the tracker used to lose the person mid-fall;
              their movement is now carried across the gap.
            - **Measuring drop speed relative to body size:** catches falls straight toward
              or away from the camera, which look small on screen.
            """
        )
    with c2, st.container(border=True, height="stretch"):
        st.markdown("**:material/policy: Known limits**")
        st.markdown(
            """
            - **Small test set:** the final test has a limited number of falls, so the true
              scores could be somewhat higher or lower.
            - **Actors, not patients:** falls were acted out by healthy volunteers. Real falls
              by frail older adults may look different.
            - **Short home test:** no false alarms in 50 minutes of home video is encouraging,
              but weeks of real use are needed to be sure.
            """
        )
