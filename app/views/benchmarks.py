"""Model Benchmarks & Deployment Gate Scorecard for ElderCare Vision.

Every number shown here is read from committed evaluation artifacts:
the one-time sealed evaluation of the frozen model
(docs/reports/V6_3_FINAL_TESTB_EVALUATION.json) and the per-phase training reports.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.cards import render_page_header
from app.core.data_loader import get_benchmark_reports

GATES = {"recall": 0.90, "precision": 0.85, "p95_tta": 3.0, "fa_per_hour": 0.05}


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _ci(ci: list[float] | None) -> str:
    return "" if not ci else f"95% CI {ci[0] * 100:.1f}–{ci[1] * 100:.1f}%"


def render_benchmarks_view() -> None:
    """Render the final gate scorecard, phase progression and known limitations."""
    reports = get_benchmark_reports()
    final = reports.get("final_eval")
    passed = bool(final and final["gate_status"]["overall_gate_passed"])
    render_page_header(
        "Results",
        "How the frozen model performed on test videos it never saw during development, "
        "how each development phase improved it, and what is still unproven.",
    )
    if passed:
        st.badge(
            "Targets met on the sealed test set; false-alarm rate not yet proven",
            color="blue",
            icon=":material/verified:",
        )
    with st.expander("How to read these numbers", icon=":material/help:"):
        st.markdown(
            """
            - **Recall**: of all real falls, the share that raised an alert. Missed falls lower it.
            - **Precision**: of all alerts, the share that were real falls. False alarms lower it.
            - **Time to alert**: seconds from the fall starting to the alert. "p95" means 95% of
              alerts came at least this fast.
            - **False alerts per hour**: alerts during long, ordinary home videos with no falls.
            - **95% CI**: the range the true value probably lies in, given how few test videos
              there are. Narrower is more certain.
            - **Sealed test set**: videos locked away until the model was final, then used once.
            """
        )

    if final is None:
        st.warning(
            "Final evaluation report not found "
            "(docs/reports/V6_3_FINAL_TESTB_EVALUATION.json)."
        )
        return

    tb = final["splits"]["test_b"]
    m, t = tb["metrics"], tb["time_to_alert_seconds"]
    lf = final["splits"].get("longform_adl_heldout", {})

    # 1. Sealed Test-B scorecard
    st.markdown("### Sealed Test-B Scorecard (frozen V6.3)")
    st.caption(
        f"{tb['total_sequences']} UP-Fall clips (cameras 1 and 2), evaluated once after the "
        "freeze. Event-level matching, Wilson / exact Poisson 95% intervals."
    )
    g1, g2, g3, g4 = st.columns(4)
    with g1:
        st.metric(
            "Event-Level Recall",
            _pct(m["recall"]),
            delta=f"target ≥ {GATES['recall']:.0%}",
            delta_color="off",
        delta_arrow="off",
            help=_ci(m["recall_95_ci"]),
            border=True,
        )
    with g2:
        st.metric(
            "Event-Level Precision",
            _pct(m["precision"]),
            delta=f"target ≥ {GATES['precision']:.0%}",
            delta_color="off",
        delta_arrow="off",
            help=_ci(m["precision_95_ci"]),
            border=True,
        )
    with g3:
        st.metric(
            "p95 Time-to-Alert",
            f"{t['p95']:.2f} s",
            delta=f"target ≤ {GATES['p95_tta']:.0f} s · median {t['median']:.2f} s",
            delta_color="off",
        delta_arrow="off",
            border=True,
        )
    with g4:
        ci = lf.get("poisson_95_ci", [None, None])
        st.metric(
            "False Alerts / Hour (held-out)",
            f"{lf.get('false_alarm_rate_per_hour', 0.0):.2f} / h",
            delta=f"{lf.get('total_false_alarms', 0)} in {lf.get('total_hours', 0):.2f} h · "
            f"95% CI ≤ {ci[1]:.2f} / h",
            delta_color="off",
        delta_arrow="off",
            help="Point estimate meets ≤ 0.05/h, but 0.83 h of footage cannot prove it.",
            border=True,
        )

    cam_rows = [
        {
            "Camera": cam,
            "Falls": v["fall_sequences"],
            "Recall (%)": v["recall"] * 100,
            "Precision (%)": v["precision"] * 100,
            "False alerts": v["false_alerts_total"],
            "p95 TTA (s)": v["p95_tta_sec"],
        }
        for cam, v in tb["camera_breakdown"].items()
    ]
    st.dataframe(
        pd.DataFrame(cam_rows),
        column_config={
            "Recall (%)": st.column_config.ProgressColumn(min_value=0, max_value=100, format="%.1f%%"),
            "Precision (%)": st.column_config.ProgressColumn(
                min_value=0, max_value=100, format="%.1f%%"
            ),
        },
        hide_index=True,
        width="stretch",
    )

    st.divider()

    # 2. Phase progression (out-of-fold Dev)
    st.markdown("### Phase Progression (out-of-fold development data)")
    st.caption(
        "Per-camera event recall at each phase's calibrated operating point; "
        "dev_longform false alerts per hour from untrimmed home videos."
    )
    rows = []
    for name, rep in reports.get("phases", []):
        b = rep["event_level_dev_metrics"]
        cams = b["oof_per_camera"]
        rows.append(
            {
                "Phase": name,
                "Cam 1 recall (%)": cams["UP-Fall:cam1"]["recall"] * 100,
                "Cam 2 recall (%)": cams["UP-Fall:cam2"]["recall"] * 100,
                "URFD recall (%)": cams["URFD:cam0"]["recall"] * 100,
                "Precision (%)": b["oof_precision"] * 100,
                "FA / hour": b["dev_longform_fa_rate_per_hour"],
                "p95 TTA (s)": b["oof_p95_tta"],
            }
        )
    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch")
        st.bar_chart(
            df.set_index("Phase")[["Cam 1 recall (%)", "Cam 2 recall (%)", "URFD recall (%)"]],
            height=260,
        )

    st.divider()

    # 3. Findings and limitations
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("#### What moved the numbers")
        st.markdown(
            """
            - **Multi-person pose caches**: the old cache kept only the first detected person; on
              camera 2 that was usually a seated bystander, not the person falling.
            - **Online track stitching + handover fix**: falls that break the tracker ID now keep
              their kinetic evidence across the ID change.
            - **Body-normalised descent** as a low-posture signal recovers falls toward the camera.
            """
        )
    with c2, st.container(border=True):
        st.markdown("#### Limitations")
        st.markdown(
            """
            - False alerts/hour is **not proven** ≤ 0.05/h: 0 alerts in 0.83 h of held-out video.
            - Test-B shares subjects 12–17 with Test-A/X (different trials), which guided design.
            - One lab, two cameras, staged falls; URFD dev precision is only ~67%.
            - Full write-up: `docs/reports/V6_FINAL_RESULTS.md`.
            """
        )
