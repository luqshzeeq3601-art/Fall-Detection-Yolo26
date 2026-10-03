"""Modern minimalist CSS layer for ElderCare Vision Streamlit application.

Complements the theme tokens in .streamlit/config.toml with refined typographic
rhythm, tabular numeric alignment, and subtle status indicators.
"""

from __future__ import annotations

import streamlit as st


def apply_custom_theme() -> None:
    """Inject minimalist global style rules that elevate the UI aesthetic."""
    st.markdown(
        """
        <style>
        /* 1. Tabular figures for precision numeric alignment */
        [data-testid="stMetricValue"],
        .stDataFrame,
        code,
        kbd {
            font-variant-numeric: tabular-nums;
        }

        /* 2. Modern eyebrow and page intro typography */
        .page-eyebrow {
            font-size: 0.72rem;
            letter-spacing: 0.08em;
            font-weight: 600;
            text-transform: uppercase;
            opacity: 0.75;
            margin: 0 0 0.25rem 0;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
        }

        .page-intro {
            max-width: 68ch;
            font-size: 0.98rem;
            line-height: 1.6;
            opacity: 0.82;
            margin: 0.25rem 0 1.25rem 0;
        }

        /* 3. Refined metric cards with high-clarity typography */
        [data-testid="stMetric"] {
            padding: 0.35rem 0.25rem;
        }

        [data-testid="stMetricLabel"] {
            font-size: 0.78rem;
            font-weight: 500;
            opacity: 0.75;
            letter-spacing: 0.01em;
        }

        [data-testid="stMetricValue"] {
            font-weight: 600;
            letter-spacing: -0.02em;
        }

        [data-testid="stMetricDelta"] {
            font-size: 0.75rem;
            font-weight: 500;
        }

        /* 4. Subtle card container transitions */
        [data-testid="stVerticalBlockBorderWrapper"] > div {
            transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        /* 5. Minimal live pulse dot */
        .live-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: #16a34a;
            box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.7);
            animation: live-pulse-anim 2s infinite;
        }

        @keyframes live-pulse-anim {
            0% {
                box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.6);
            }
            70% {
                box-shadow: 0 0 0 6px rgba(22, 163, 74, 0);
            }
            100% {
                box-shadow: 0 0 0 0 rgba(22, 163, 74, 0);
            }
        }

        /* 6. Streamlined sidebar header */
        .sidebar-brand-box {
            padding: 0.2rem 0 0.6rem 0;
            border-bottom: 1px solid rgba(140, 149, 159, 0.15);
            margin-bottom: 0.8rem;
        }

        .sidebar-brand-title {
            font-size: 1.05rem;
            font-weight: 700;
            letter-spacing: -0.02em;
            margin: 0;
            line-height: 1.25;
        }

        .sidebar-brand-sub {
            font-size: 0.72rem;
            opacity: 0.7;
            margin: 0.15rem 0 0 0;
            letter-spacing: 0.02em;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
