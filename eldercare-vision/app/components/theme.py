"""Custom CSS Design System for ElderCare Vision (Light Theme).

Adheres to frontend-ui-engineering:
- Crisp, clinical enterprise aesthetic
- WCAG 2.1 AA compliant contrast
- Semantic status pills: Safe (green), Warning (amber), Fall Alarm (red), VLM Agent (blue)
- Clean card elevations and responsive typography
"""

import streamlit as st


def apply_custom_theme() -> None:
    """Inject scoped CSS for the clinical light theme."""
    st.markdown(
        """
        <style>
        /* Global typography & spacing */
        .stApp {
            background-color: #F8FAFC !important;
            color: #0F172A;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }

        /* Top header container */
        .header-container {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 1rem 1.25rem;
            background: #FFFFFF;
            border-bottom: 1px solid #E2E8F0;
            border-radius: 8px;
            margin-bottom: 1.25rem;
            box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.03);
        }
        .header-title {
            font-size: 1.35rem;
            font-weight: 700;
            color: #0F172A;
            margin: 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .header-subtitle {
            font-size: 0.85rem;
            color: #64748B;
            margin-top: 0.2rem;
        }

        /* Demo Tour Banner */
        .demo-guide-card {
            background-color: #EFF6FF;
            border: 1px solid #BFDBFE;
            border-left: 4px solid #2563EB;
            border-radius: 6px;
            padding: 0.85rem 1.15rem;
            margin-bottom: 1.25rem;
            color: #1E3A8A;
        }
        .demo-guide-title {
            font-weight: 700;
            font-size: 0.95rem;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            margin-bottom: 0.35rem;
        }
        .demo-guide-text {
            font-size: 0.85rem;
            line-height: 1.45;
            color: #1E40AF;
            margin: 0;
        }

        /* KPI Metric Cards */
        .metric-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 1rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
        }
        .metric-label {
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: #64748B;
        }
        .metric-value {
            font-size: 1.75rem;
            font-weight: 700;
            color: #0F172A;
            line-height: 1.2;
            font-feature-settings: "tnum";
            font-variant-numeric: tabular-nums;
        }
        .metric-sub {
            font-size: 0.8rem;
            color: #059669;
            font-weight: 500;
        }

        /* Semantic Status Badges */
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.3rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            text-transform: uppercase;
        }
        .badge-safe {
            background-color: #ECFDF5;
            color: #065F46;
            border: 1px solid #A7F3D0;
        }
        .badge-warning {
            background-color: #FFFBEB;
            color: #92400E;
            border: 1px solid #FDE68A;
        }
        .badge-alarm {
            background-color: #FEF2F2;
            color: #991B1B;
            border: 1px solid #FECACA;
            animation: pulse-border 1.5s infinite;
        }
        .badge-agent {
            background-color: #F0F9FF;
            color: #075985;
            border: 1px solid #BAE6FD;
        }

        @keyframes pulse-border {
            0% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(220, 38, 38, 0); }
            100% { box-shadow: 0 0 0 0 rgba(220, 38, 38, 0); }
        }

        /* Fall Alert Banner */
        .fall-alert-banner {
            background-color: #FEF2F2;
            border: 2px solid #EF4444;
            border-radius: 8px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .fall-alert-title {
            color: #991B1B;
            font-weight: 800;
            font-size: 1.15rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .fall-alert-detail {
            color: #B91C1C;
            font-size: 0.85rem;
            margin-top: 0.2rem;
        }

        /* VLM Agent Card */
        .agent-card {
            background: #FFFFFF;
            border: 1px solid #BAE6FD;
            border-left: 4px solid #0284C7;
            border-radius: 8px;
            padding: 1.1rem;
            box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.04);
            margin-top: 0.75rem;
        }
        .agent-header {
            font-size: 0.9rem;
            font-weight: 700;
            color: #0369A1;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            margin-bottom: 0.5rem;
        }
        .agent-text {
            font-size: 0.875rem;
            line-height: 1.5;
            color: #1E293B;
            margin-bottom: 0.75rem;
        }

        /* Streamlit native widget cleanups */
        div[data-testid="stMetricValue"] {
            font-size: 1.75rem !important;
            font-weight: 700 !important;
            color: #0F172A !important;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            color: #64748B !important;
            text-transform: uppercase !important;
        }
        .stButton>button {
            border-radius: 6px !important;
            font-weight: 600 !important;
            font-size: 0.875rem !important;
            transition: all 0.15s ease-in-out !important;
        }
        .stButton>button:hover {
            border-color: #2563EB !important;
            color: #2563EB !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
