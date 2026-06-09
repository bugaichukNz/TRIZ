"""Нейтральная минималистичная тема Streamlit (ChatGPT / Notion)."""



CUSTOM_CSS = """

<style>

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');



:root {

    --bg-page: #F9F9F9;

    --bg-white: #FFFFFF;

    --bg-muted: #F0F0F0;

    --bg-status-ok: #F0FBF7;

    --border: #E5E5E5;

    --border-muted: #D0D0D0;

    --text-primary: #1A1A1A;

    --text-secondary: #6B6B6B;

    --text-label: #8A8A8A;

    --accent: #10A37F;

    --accent-hover: rgba(16, 163, 127, 0.85);

    --icon: #404040;

    --radius: 6px;

    --radius-lg: 8px;

    --shadow: 0 1px 3px rgba(0, 0, 0, 0.08);

}



html, body, [class*="css"] {

    font-family: 'Inter', system-ui, -apple-system, sans-serif;

}



.stApp {

    background-color: var(--bg-page) !important;

}



#MainMenu, footer {

    visibility: hidden;

    height: 0;

}



/* Кнопка «☰» для раскрытия левого меню (в шапке Streamlit) */

header[data-testid="stHeader"] {

    visibility: visible !important;

    height: auto !important;

    background: transparent !important;

}



[data-testid="stSidebarCollapseButton"],

[data-testid="collapsedControl"],

button[data-testid="stBaseButton-headerNoPadding"] {

    visibility: visible !important;

    display: flex !important;

    opacity: 1 !important;

    pointer-events: auto !important;

    z-index: 999999 !important;

}



section[data-testid="stSidebar"] {

    min-width: 280px;

    z-index: 999990;

}



.block-container {

    padding-top: 1.5rem;

    max-width: 920px;

}



/* Hero */

.triz-hero {

    background: var(--bg-white);

    border: 1px solid var(--border);

    border-radius: var(--radius-lg);

    padding: 1.75rem 2rem;

    margin-bottom: 1.5rem;

    box-shadow: var(--shadow);

    color: var(--text-primary);

}

.triz-hero h1 {

    margin: 0 0 0.35rem 0;

    font-size: 1.75rem;

    font-weight: 600;

    letter-spacing: -0.02em;

    color: var(--text-primary) !important;

}

.triz-hero p {

    margin: 0;

    font-size: 0.95rem;

    line-height: 1.5;

    color: var(--text-secondary) !important;

}

.triz-badge {

    display: inline-block;

    background: var(--bg-muted);

    border: 1px solid var(--border);

    border-radius: 999px;

    padding: 0.2rem 0.65rem;

    font-size: 11px;

    font-weight: 500;

    text-transform: uppercase;

    letter-spacing: 0.05em;

    margin-bottom: 0.75rem;

    color: var(--text-label);

}



/* Cards */

.triz-card {

    background: var(--bg-white);

    border: 1px solid var(--border);

    border-left: 3px solid var(--border-muted);

    border-radius: var(--radius-lg);

    padding: 1rem 1.15rem;

    margin-bottom: 0.75rem;

    box-shadow: var(--shadow);

}

.triz-card-label {

    font-size: 11px;

    font-weight: 500;

    text-transform: uppercase;

    letter-spacing: 0.05em;

    color: var(--text-label);

    margin-bottom: 0.35rem;

}

.triz-card-body {

    font-size: 0.95rem;

    line-height: 1.55;

    color: var(--text-primary);

}



/* Section titles */

.triz-section {

    font-size: 1.05rem;

    font-weight: 500;

    color: var(--text-primary);

    margin: 1.25rem 0 0.65rem 0;

    display: flex;

    align-items: center;

    gap: 0.4rem;

}



/* Principle list */

.triz-principle {

    background: var(--bg-muted);

    border-radius: var(--radius);

    padding: 0.55rem 0.85rem;

    margin-bottom: 0.45rem;

    border: 1px solid var(--border);

    font-size: 0.9rem;

    color: var(--text-primary);

}

.triz-principle-num {

    display: inline-flex;

    align-items: center;

    justify-content: center;

    min-width: 1.5rem;

    height: 1.5rem;

    background: var(--bg-white);

    color: var(--icon);

    border: 1px solid var(--border);

    border-radius: var(--radius);

    font-size: 0.75rem;

    font-weight: 500;

    margin-right: 0.5rem;

}



/* Metrics */

.triz-metric {

    background: var(--bg-white);

    border: 1px solid var(--border);

    border-radius: var(--radius-lg);

    padding: 0.75rem 1rem;

    text-align: center;

    box-shadow: var(--shadow);

}

.triz-metric-value {

    font-size: 1.5rem;

    font-weight: 600;

    color: var(--text-primary);

}

.triz-metric-label {

    font-size: 0.75rem;

    color: var(--text-secondary);

    margin-top: 0.15rem;

}



/* ========== Sidebar ========== */

section[data-testid="stSidebar"] {

    background-color: var(--bg-white) !important;

    border-right: 1px solid var(--border);

}

section[data-testid="stSidebar"] > div {

    background: var(--bg-white) !important;

}

section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {

    padding-top: 1rem;

}



.sidebar-brand {

    margin-bottom: 1.1rem;

}

.sidebar-brand-title {

    font-size: 1.2rem;

    font-weight: 600;

    color: var(--text-primary);

    letter-spacing: -0.02em;

    line-height: 1.3;

}

.sidebar-brand-sub {

    margin-top: 0.25rem;

    font-size: 0.82rem;

    color: var(--text-secondary);

    line-height: 1.4;

}



section[data-testid="stSidebar"] label[data-testid="stWidgetLabel"] p {

    color: var(--text-primary) !important;

    font-size: 0.85rem !important;

    font-weight: 500 !important;

}

section[data-testid="stSidebar"] .stTextInput > div > div {

    background: var(--bg-white) !important;

    border: 1px solid var(--border) !important;

    border-radius: var(--radius) !important;

}

section[data-testid="stSidebar"] .stTextInput input {

    background: transparent !important;

    color: var(--text-primary) !important;

    -webkit-text-fill-color: var(--text-primary) !important;

    caret-color: var(--text-primary) !important;

    font-size: 0.85rem !important;

}

section[data-testid="stSidebar"] .stTextInput input::placeholder {

    color: var(--text-secondary) !important;

    opacity: 1 !important;

}



.sidebar-status {

    display: flex;

    gap: 0.55rem;

    align-items: flex-start;

    padding: 0.65rem 0.75rem;

    border-radius: var(--radius);

    margin: 0.5rem 0 0.75rem;

    font-size: 0.8rem;

    line-height: 1.45;

    border: 1px solid var(--border);

}

.sidebar-status-icon {

    flex-shrink: 0;

    width: 0.5rem;

    height: 0.5rem;

    border-radius: 50%;

    display: inline-block;

    margin-top: 0.35rem;

}

.sidebar-status-text {

    color: inherit;

    word-break: break-word;

}

.sidebar-status--ok {

    background: var(--bg-status-ok);

    border-color: var(--border);

    color: var(--accent);

}

.sidebar-status--ok .sidebar-status-icon {

    background: var(--accent);

}

.sidebar-status--warn {

    background: var(--bg-muted);

    border-color: var(--border);

    color: var(--text-secondary);

}

.sidebar-status--warn .sidebar-status-icon {

    background: var(--text-secondary);

}



.sidebar-divider {

    border: none;

    border-top: 1px solid var(--border);

    margin: 0.85rem 0 1rem;

}



section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) {

    align-items: center !important;

    flex-wrap: nowrap !important;

    gap: 0.35rem !important;

    margin-bottom: 0.35rem !important;

}

section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) > div[data-testid="column"]:first-child {

    flex: 1 1 auto !important;

    min-width: 0 !important;

}

section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) > div[data-testid="column"]:not(:first-child) {

    flex: 0 0 2.25rem !important;

    width: 2.25rem !important;

    min-width: 2.25rem !important;

    max-width: 2.25rem !important;

}



section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) > div[data-testid="column"] .stPopover > button {

    min-height: 1.75rem !important;

    padding: 0.2rem 0.35rem !important;

    font-size: 0.85rem !important;

    width: 100% !important;

}

.sidebar-history-title {

    font-weight: 500;

    font-size: 0.95rem;

    color: var(--text-primary);

    white-space: nowrap;

}

.sidebar-empty {

    margin: 0.35rem 0 0;

    font-size: 0.8rem;

    color: var(--text-secondary);

    line-height: 1.45;

}



section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) .stButton > button {

    color: var(--text-secondary) !important;

    background: var(--bg-white) !important;

    border: 1px solid var(--border) !important;

    font-size: 0.72rem !important;

    padding: 0.28rem 0.35rem !important;

    white-space: nowrap !important;

    min-height: 1.75rem !important;

    line-height: 1.2 !important;

    width: 100% !important;

    border-radius: var(--radius) !important;

}

section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) .stButton > button:hover:not(:disabled) {

    background: var(--bg-muted) !important;

    border-color: var(--border) !important;

    opacity: 0.85;

}

section[data-testid="stSidebar"] [data-testid="stHorizontalBlock"]:has(.sidebar-history-title) .stButton > button:disabled {

    opacity: 0.35 !important;

    color: var(--text-label) !important;

}



section[data-testid="stSidebar"] [data-testid="stExpander"] {

    background: var(--bg-white);

    border: 1px solid var(--border);

    border-radius: var(--radius);

}

section[data-testid="stSidebar"] [data-testid="stExpander"] summary,

section[data-testid="stSidebar"] [data-testid="stExpander"] summary p,

section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] p,

section[data-testid="stSidebar"] [data-testid="stExpander"] [data-testid="stMarkdownContainer"] strong {

    color: var(--text-primary) !important;

}

section[data-testid="stSidebar"] [data-testid="stExpander"][open],

section[data-testid="stSidebar"] [data-testid="stExpander"] details[open] {

    background: var(--bg-muted);

}

section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button {

    color: var(--text-primary) !important;

    background: var(--bg-white) !important;

    border: 1px solid var(--border) !important;

    font-size: 0.78rem !important;

    border-radius: var(--radius) !important;

}

section[data-testid="stSidebar"] [data-testid="stExpander"] .stButton > button:hover:not(:disabled) {

    background: var(--bg-muted) !important;

    opacity: 0.85;

}



/* Основная область */

.main .stMarkdown p,

.main .stMarkdown li,

.main .stCaption,

.main label p {

    color: var(--text-primary) !important;

}

.main h1, .main h2, .main h3 {

    color: var(--text-primary) !important;

    font-weight: 600 !important;

}

.stTextArea textarea {

    color: var(--text-primary) !important;

    background: var(--bg-white) !important;

}

.stTextArea textarea::placeholder {

    color: var(--text-secondary) !important;

}



/* Primary button */

.stButton > button[kind="primary"],

.stDownloadButton > button[kind="primary"] {

    background: var(--accent) !important;

    color: #FFFFFF !important;

    border: none !important;

    border-radius: var(--radius) !important;

    font-weight: 500 !important;

    padding: 0.65rem 1.25rem !important;

    box-shadow: none !important;

    transition: opacity 0.15s ease !important;

}

.stButton > button[kind="primary"]:hover:not(:disabled),

.stDownloadButton > button[kind="primary"]:hover:not(:disabled) {

    opacity: 0.85 !important;

    transform: none !important;

    box-shadow: none !important;

}

.stButton > button[kind="secondary"],

.stDownloadButton > button {

    border-color: var(--border) !important;

    color: var(--text-primary) !important;

    background: var(--bg-white) !important;

    border-radius: var(--radius) !important;

    font-weight: 500 !important;

    box-shadow: none !important;

    transition: opacity 0.15s ease !important;

}

.stButton > button[kind="secondary"]:hover:not(:disabled),

.stDownloadButton > button:hover:not(:disabled) {

    opacity: 0.85 !important;

    background: var(--bg-muted) !important;

    border-color: var(--border) !important;

}



/* Text area */

.stTextArea textarea {

    border-radius: var(--radius-lg) !important;

    border: 1px solid var(--border) !important;

    font-size: 0.95rem !important;

    line-height: 1.5 !important;

    box-shadow: var(--shadow);

}

.stTextArea textarea:focus {

    border-color: var(--border-muted) !important;

    box-shadow: 0 0 0 2px rgba(0, 0, 0, 0.04) !important;

}



/* Expanders in main area */

.main [data-testid="stExpander"] {

    border: 1px solid var(--border);

    border-radius: var(--radius-lg);

    background: var(--bg-white);

    box-shadow: var(--shadow);

}

.main [data-testid="stExpander"] summary {

    font-weight: 500;

    color: var(--text-primary);

}



/* Metrics widget */

[data-testid="stMetric"] {

    background: var(--bg-white);

    border: 1px solid var(--border);

    border-radius: var(--radius-lg);

    padding: 0.75rem 1rem;

    box-shadow: var(--shadow);

}

[data-testid="stMetricLabel"] {

    color: var(--text-label) !important;

    font-size: 11px !important;

    font-weight: 500 !important;

    text-transform: uppercase;

    letter-spacing: 0.05em;

}

[data-testid="stMetricValue"] {

    color: var(--text-primary) !important;

    font-weight: 600 !important;

}



/* Divider */

hr {

    border-color: var(--border) !important;

}



/* Alerts */

div[data-testid="stAlert"] {

    border-radius: var(--radius-lg);

    border: 1px solid var(--border);

}

</style>

"""





def inject_theme() -> None:

    import streamlit as st



    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

