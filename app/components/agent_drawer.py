"""AI second-opinion card: renders stored VLM enrichment for an incident with modern styling."""

from __future__ import annotations

import streamlit as st

from app.components.cards import render_panel_head
from app.core.backend import EnrichmentView

_VERDICTS: dict[str | None, tuple[str, str, str]] = {
    "fall": ("AI agrees: looks like a fall", "red", ":material/emergency:"),
    "no_fall": ("AI disagrees: looks like normal activity", "orange", ":material/help:"),
    "unclear": ("AI is unsure: view blocked or unclear", "orange", ":material/help:"),
    None: ("No AI answer", "gray", ":material/remove:"),
}

_POSTURES = {
    "lying_floor": "Lying on the floor",
    "sitting_floor": "Sitting on the floor",
    "slumped_furniture": "Slumped on furniture",
    "kneeling_floor": "Kneeling on the floor",
    "upright": "Upright posture",
    "unclear": "Unclear or hidden",
}


def render_ai_second_opinion(enrichment: EnrichmentView | None, vlm_enabled: bool) -> None:
    """Render the advisory vision-language model opinion in a modern minimalist container."""
    with st.container(border=True):
        render_panel_head("AI second opinion", "Advice only")
        st.caption(
            "A vision-language model looked at the snapshots. It can be wrong: "
            "your review is the final answer."
        )

        if enrichment is None:
            if vlm_enabled:
                st.info(
                    "The AI is still looking at the snapshots. Press **Refresh** in a moment.",
                    icon=":material/hourglass_top:",
                )
            else:
                st.info(
                    "The AI second opinion is turned off. To turn it on, start the demo with "
                    "`VLM_PROVIDER=openai_compat`.",
                    icon=":material/info:",
                )
            return

        if enrichment.status != "completed" or not enrichment.output:
            st.warning(
                "The AI could not give an opinion this time "
                f"({enrichment.status}, {enrichment.error_code or 'no details'}). "
                "The fall alert itself is still valid.",
                icon=":material/warning:",
            )
            return

        out = enrichment.output
        label, color, icon = _VERDICTS.get(out.get("fall_assessment"), _VERDICTS[None])
        st.badge(label, color=color, icon=icon)

        if out.get("scene_summary"):
            st.markdown(f"**What it sees:** {out['scene_summary']}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown(
                f"**Posture:** {_POSTURES.get(out.get('postural_state') or '', 'Not stated')}"
            )
        with c2:
            st.markdown(
                f"**AI confidence:** {str(out.get('confidence_assessment', 'not stated')).capitalize()}"
            )

        if out.get("environmental_context"):
            st.caption(f"**Surroundings:** {out['environmental_context']}")
        if out.get("potential_hazards"):
            st.caption("**Possible hazards:** " + ", ".join(out["potential_hazards"]))
        if out.get("uncertainty_factors"):
            st.caption("**Why it may be unsure:** " + ", ".join(out["uncertainty_factors"]))

        took = f", took {enrichment.duration_ms / 1000:.1f} s" if enrichment.duration_ms else ""
        st.caption(
            f"Model: `{enrichment.model}` via `{enrichment.provider}` (prompt `{enrichment.prompt_version}`){took}"
        )
