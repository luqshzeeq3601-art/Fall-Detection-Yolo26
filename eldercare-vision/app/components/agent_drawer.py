"""Ultralytics VLM Agent & Multimodal Analysis Drawer for ElderCare Vision."""

from __future__ import annotations

import streamlit as st


def render_vlm_agent_drawer(
    vlm_summary: str,
    kinetic_score: float,
    floor_score: float,
    adl_score: float,
    confidence: float,
) -> None:
    """Render the AI agent reasoning card with confidence gate breakdowns."""
    with st.container(border=True):
        st.markdown(
            f"""
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 0.5rem;">
                <div style="font-weight: 700; color: #0369A1; font-size: 0.95rem; display: flex; align-items: center; gap: 0.4rem;">
                    🤖 Ultralytics VLM Agent — Scene Intelligence
                </div>
                <span class="status-badge badge-agent">
                    VLM VERIFIED (Confidence: {confidence * 100:.0f}%)
                </span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(
            f"""
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; padding: 0.85rem; font-size: 0.875rem; line-height: 1.5; color: #1E293B; margin-bottom: 0.85rem;">
                "{vlm_summary}"
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("**Rule & Confidence Gate Clearance**")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric(
                label="Kinetic Displacement",
                value=f"{kinetic_score * 100:.0f}%",
                help="Rate of downward displacement during onset",
                border=True,
            )
        with col2:
            st.metric(
                label="Floor Proximity",
                value=f"{floor_score * 100:.0f}%",
                help="Geometric distance of pelvis/torso to ground plane",
                border=True,
            )
        with col3:
            st.metric(
                label="ADL Suppression",
                value=f"{(1.0 - adl_score) * 100:.0f}% Clearance",
                help="Likelihood this is NOT everyday sitting or bending",
                border=True,
            )
