"""AI second-opinion card: renders stored VLM enrichment for an incident with modern styling."""

from __future__ import annotations

import streamlit as st

from app.core.backend import EnrichmentView

_VERDICTS: dict[str | None, tuple[str, str, str]] = {
    "fall": ("Consensus: Confirmed Fall Posture", "red", ":material/emergency:"),
    "no_fall": ("Divergence: Normal Activity Detected", "orange", ":material/help:"),
    "unclear": ("Indeterminate: Occluded or Ambiguous", "orange", ":material/help:"),
    None: ("No Inference Verdict", "gray", ":material/remove:"),
}

_POSTURES = {
    "lying_floor": "Lying on the floor",
    "sitting_floor": "Sitting on the floor",
    "slumped_furniture": "Slumped on furniture",
    "kneeling_floor": "Kneeling on the floor",
    "upright": "Upright posture",
    "unclear": "Ambiguous / occluded",
}


def render_ai_second_opinion(enrichment: EnrichmentView | None, vlm_enabled: bool) -> None:
    """Render the advisory vision-language model opinion in a modern minimalist container."""
    with st.container(border=True):
        st.markdown(
            """
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.3rem;">
                <span style="font-weight: 600; font-size: 0.95rem;">AI Second Opinion (Advisory)</span>
                <span style="font-size: 0.72rem; opacity: 0.7;">VLM Engine</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(
            "Advisory multimodal model analysis evaluated against keyframe snapshots. "
            "Human caregiver retains final decision authority."
        )

        if enrichment is None:
            if vlm_enabled:
                st.info("Vision reasoning in progress. Awaiting asynchronous result...", icon=":material/hourglass_top:")
            else:
                st.info(
                    "Multimodal VLM engine is currently disabled in local configuration. "
                    "Start demo with `VLM_PROVIDER=openai_compat` to enable local vision analysis.",
                    icon=":material/info:",
                )
            return

        if enrichment.status != "completed" or not enrichment.output:
            st.warning(
                f"Advisory reasoning unavailable ({enrichment.status}, "
                f"{enrichment.error_code or 'no error details'}). Core alert remains valid.",
                icon=":material/warning:",
            )
            return

        out = enrichment.output
        label, color, icon = _VERDICTS.get(out.get("fall_assessment"), _VERDICTS[None])
        st.badge(label, color=color, icon=icon)

        if out.get("scene_summary"):
            st.markdown(f"**Scene Analysis:** {out['scene_summary']}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Observed Posture:** `{_POSTURES.get(out.get('postural_state') or '', 'Unspecified')}`")
        with c2:
            st.markdown(f"**Certainty:** `{str(out.get('confidence_assessment', 'n/a')).upper()}`")

        if out.get("environmental_context"):
            st.caption(f"**Surrounding Context:** {out['environmental_context']}")
        if out.get("potential_hazards"):
            st.caption("**Environmental Hazards:** " + ", ".join(out["potential_hazards"]))
        if out.get("uncertainty_factors"):
            st.caption("**Ambiguity Factors:** " + ", ".join(out["uncertainty_factors"]))

        took = f" · {enrichment.duration_ms / 1000:.1f}s latency" if enrichment.duration_ms else ""
        st.caption(
            f"Model: `{enrichment.model}` via `{enrichment.provider}` (prompt `{enrichment.prompt_version}`){took}"
        )
