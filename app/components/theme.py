"""Global CSS layer for the ElderCare Vision Streamlit application.

Complements the theme tokens in .streamlit/config.toml (font, colors, radii)
with typographic rhythm, sidebar structure, and responsive rules for tablet
and phone widths. Streamlit stacks columns below 640px on its own; the rules
here cover the 640-1100px range where 4-up rows get too narrow, and enlarge
touch targets on small screens.
"""

from __future__ import annotations

import streamlit as st

_CSS = """
<style>
/* Numbers line up in metrics, tables and code */
[data-testid="stMetricValue"],
.stDataFrame,
code,
kbd {
    font-variant-numeric: tabular-nums;
}

/* Secondary text. Streamlit draws captions at 60% opacity and ~13px, which
   reads as faint grey on white. Keep them visibly secondary but readable
   (about 9:1 on white, and the same in dark mode since it follows text color). */
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p {
    font-size: 0.9rem;
    line-height: 1.5;
}
[data-testid="stCaptionContainer"] {
    opacity: 1;
    color: inherit;
}
[data-testid="stCaptionContainer"] p {
    opacity: 0.8;
}
[data-testid="stWidgetLabel"] p {
    font-size: 0.95rem;
    font-weight: 500;
}
input::placeholder,
textarea::placeholder {
    color: inherit !important;
    opacity: 0.65 !important;
}

/* Page header */
.page-intro {
    max-width: 70ch;
    font-size: 1.0625rem;
    line-height: 1.6;
    opacity: 0.9;
    margin: 0.25rem 0 1.25rem 0;
}

/* Metrics */
[data-testid="stMetric"] {
    padding: 0.35rem 0.25rem;
}
[data-testid="stMetricLabel"] p {
    font-size: 0.9rem;
    font-weight: 500;
    opacity: 0.9;
}
[data-testid="stMetricValue"] {
    font-weight: 600;
    letter-spacing: -0.02em;
}
[data-testid="stMetricDelta"],
[data-testid="stMetricDelta"] div {
    font-size: 0.85rem;
    font-weight: 500;
}

/* Small inline label used on cards (e.g. pipeline stage component) */
.chip {
    display: inline-block;
    font-size: 0.8rem;
    font-weight: 600;
    padding: 0.125rem 0.5rem;
    border-radius: 6px;
    background: rgba(140, 149, 159, 0.14);
    white-space: nowrap;
}

/* Card header: title left, small context label right */
.panel-head {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    flex-wrap: wrap;
    gap: 0.25rem 0.75rem;
    margin-bottom: 0.25rem;
}
.panel-head__title {
    font-weight: 600;
    font-size: 1.0625rem;
}
.panel-head__meta {
    font-size: 0.85rem;
    opacity: 0.8;
}

/* Live indicator: the dot carries real pipeline state, the text repeats it */
.live-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.95rem;
    font-weight: 500;
}
.live-indicator__dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background-color: #71717a;
    flex: none;
}
.live-indicator--on .live-indicator__dot {
    background-color: #16a34a;
}
@media (prefers-reduced-motion: no-preference) {
    .live-indicator--on .live-indicator__dot {
        animation: live-pulse 2s ease-out infinite;
    }
}
@keyframes live-pulse {
    0% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0.55); }
    70% { box-shadow: 0 0 0 6px rgba(22, 163, 74, 0); }
    100% { box-shadow: 0 0 0 0 rgba(22, 163, 74, 0); }
}

/* Sidebar */
.sidebar-brand {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    margin: 0 0 0.25rem 0;
}
.sidebar-brand__title {
    font-size: 1.1875rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    line-height: 1.3;
}
.sidebar-brand__sub {
    font-size: 0.875rem;
    opacity: 0.8;
}
.sidebar-group {
    font-size: 0.85rem;
    font-weight: 600;
    opacity: 0.8;
    margin: 0.75rem 0 0.125rem 0.25rem;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] a {
    min-height: 2.5rem;
}
[data-testid="stSidebar"] [data-testid="stPageLink"] p {
    font-size: 1rem;
}

/* Tablet and small laptop: rows of 3+ columns wrap to two per line */
@media (min-width: 640px) and (max-width: 1100px) {
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3)) {
        flex-wrap: wrap;
        row-gap: 1rem;
    }
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"]:nth-child(3))
        > [data-testid="stColumn"] {
        flex: 1 1 calc(50% - 1rem) !important;
        min-width: calc(50% - 1rem) !important;
    }
}

/* Phone */
@media (max-width: 640px) {
    .block-container,
    [data-testid="stMainBlockContainer"] {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 3.5rem;
    }
    h1 {
        font-size: 1.75rem !important;
        line-height: 1.25 !important;
    }
    h3 {
        font-size: 1.1875rem !important;
    }
    .page-intro {
        font-size: 1rem;
        margin-bottom: 1rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.75rem;
    }
    /* Comfortable touch targets */
    .stButton button,
    .stDownloadButton button,
    [data-testid="stFormSubmitButton"] button,
    [data-testid="stPageLink"] a {
        min-height: 44px;
    }
    .stButton,
    .stDownloadButton {
        width: 100%;
    }
    .stButton button,
    .stDownloadButton button {
        width: 100%;
    }
}
</style>
"""


def apply_custom_theme() -> None:
    """Inject the global style rules once per script run."""
    st.html(_CSS)
