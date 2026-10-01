"""Small CSS layer on top of the Streamlit theme in .streamlit/config.toml.

Colors, fonts and radii come from the theme config; this file only adds what
config cannot express (numeric alignment and the page intro text width).
"""

import streamlit as st


def apply_custom_theme() -> None:
    """Inject the few global style rules the app needs."""
    st.markdown(
        """
        <style>
        /* Aligned digits in metrics and tables */
        [data-testid="stMetricValue"], .stDataFrame { font-variant-numeric: tabular-nums; }
        /* Keep explanatory paragraphs at a readable line length */
        .page-intro { max-width: 72ch; color: inherit; opacity: 0.85;
                      font-size: 1.05rem; line-height: 1.55; margin: -0.25rem 0 1rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )
