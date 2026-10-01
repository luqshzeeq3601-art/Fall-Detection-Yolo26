"""AI second-opinion card: renders the stored VLM enrichment for one incident."""

from __future__ import annotations

import streamlit as st

from app.core.backend import EnrichmentView

_VERDICTS: dict[str | None, tuple[str, str, str]] = {
    "fall": ("Agrees: looks like a fall", "red", ":material/emergency:"),
    "no_fall": ("Disagrees: does not look like a fall", "orange", ":material/help:"),
    "unclear": ("Unsure from the image", "orange", ":material/help:"),
    None: ("No verdict given", "gray", ":material/remove:"),
}

_POSTURES = {
    "lying_floor": "Lying on the floor",
    "sitting_floor": "Sitting on the floor",
    "slumped_furniture": "Slumped on furniture",
    "kneeling_floor": "Kneeling on the floor",
    "upright": "Upright",
    "unclear": "Unclear",
}


def render_ai_second_opinion(enrichment: EnrichmentView | None, vlm_enabled: bool) -> None:
    """Explain what the vision-language model said, or why there is nothing yet."""
    with st.container(border=True):
        st.markdown("#### :material/smart_toy: AI second opinion")
        st.caption(
            "A vision-language model looks at the alert snapshot and describes the scene. "
            "It is advisory: the alert was already raised, and a person makes the final call."
        )

        if enrichment is None:
            if vlm_enabled:
                st.info("The model is still looking at this incident. Refresh in a few seconds.")
            else:
                st.info(
                    "The AI second opinion is switched off for this demo, so the alert relies "
                    "on the fall detector and the caregiver review. To enable it, run a local "
                    "vision model and start the app with `VLM_PROVIDER=openai_compat`."
                )
            return

        if enrichment.status != "completed" or not enrichment.output:
            st.warning(
                f"The model could not give an opinion ({enrichment.status}, "
                f"{enrichment.error_code or 'no detail'}). The alert itself is unaffected."
            )
            return

        out = enrichment.output
        label, color, icon = _VERDICTS.get(out.get("fall_assessment"), _VERDICTS[None])
        st.badge(label, color=color, icon=icon)
        st.markdown(out.get("scene_summary", ""))

        c1, c2 = st.columns(2)
        c1.markdown(f"**Posture:** {_POSTURES.get(out.get('postural_state') or '', 'Not given')}")
        c2.markdown(f"**Model confidence:** {str(out.get('confidence_assessment', 'n/a')).title()}")
        if out.get("environmental_context"):
            st.markdown(f"**Surroundings:** {out['environmental_context']}")
        if out.get("potential_hazards"):
            st.markdown("**Possible hazards:** " + ", ".join(out["potential_hazards"]))
        if out.get("uncertainty_factors"):
            st.markdown("**What made it unsure:** " + ", ".join(out["uncertainty_factors"]))

        took = f" · {enrichment.duration_ms / 1000:.1f} s" if enrichment.duration_ms else ""
        st.caption(
            f"{enrichment.model} via {enrichment.provider} · prompt {enrichment.prompt_version}{took}"
        )
