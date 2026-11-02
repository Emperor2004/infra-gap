from pathlib import Path
import html
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import pydeck as pdk
import streamlit as st


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path("/data/out")
VIZ_DIR = OUTPUT_DIR / "viz"

SEVERITY_FILE = VIZ_DIR / "severity_hex.csv"
TALUKA_FILE = VIZ_DIR / "taluka_ranking.csv"
SUMMARY_FILE = OUTPUT_DIR / "summary_base.csv"
SENSITIVITY_FILE = OUTPUT_DIR / "sensitivity.csv"
VALIDATION_FILE = OUTPUT_DIR / "validation_summary.csv"
DISTRICT_VALIDATION_FILE = OUTPUT_DIR / "validation_by_district.csv"

st.set_page_config(
    page_title="INFRA-GAP | Maharashtra",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# CUSTOM CSS
# ============================================================

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background: #f4f7fb;
        color: #1e293b;
    }
    [data-testid="stHeader"] {
        background: rgba(244, 247, 251, 0.95);
    }
    .main .block-container {
        padding-top: 1.8rem;
        padding-bottom: 2rem;
        max-width: 1550px;
    }
    [data-testid="stSidebar"] {
        background: #142238;
    }
    [data-testid="stSidebar"] * {
        color: #e8eef7 !important;
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: #aebed2 !important;
    }
    [data-testid="stSidebar"] button {
        border-radius: 8px;
    }
    h1 {
        color: #142238 !important;
        font-weight: 800 !important;
        letter-spacing: -1px;
    }
    h2, h3, h4 {
        color: #1e3a5f !important;
        font-weight: 700 !important;
    }
    [data-testid="stMarkdownContainer"] p {
        color: #475569;
    }
    .metric-card {
        background: #ffffff;
        padding: 20px;
        border-radius: 14px;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #0d9488;
        box-shadow: 0 3px 12px rgba(15, 23, 42, 0.045);
        min-height: 120px;
        margin-bottom: 12px;
    }
    .metric-label {
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.7px;
        color: #64748b;
        text-transform: uppercase;
    }
    .metric-value {
        font-size: 27px;
        font-weight: 800;
        color: #142238;
        margin-top: 9px;
        line-height: 1.2;
        overflow-wrap: anywhere;
    }
    .metric-description {
        font-size: 12px;
        color: #64748b;
        margin-top: 7px;
    }
    .section-title {
        font-size: 21px;
        font-weight: 750;
        color: #142238;
        margin-top: 26px;
        margin-bottom: 8px;
    }
    [data-testid="stPlotlyChart"] {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 8px;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.035);
    }
    [data-testid="stDataFrame"] {
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        overflow: hidden;
    }
    [data-testid="stAlert"] {
        border-radius: 10px;
    }
    .stDownloadButton button, .stButton button {
        border-radius: 8px;
        font-weight: 600;
    }
    hr {
        border-color: #e2e8f0;
    }
    .dashboard-footer {
        text-align: center;
        color: #64748b;
        padding: 20px;
        font-size: 12px;
        line-height: 1.8;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(show_spinner="Loading infrastructure data...")
def load_data():
    severity = pd.read_csv(
        SEVERITY_FILE,
        low_memory=False,
        dtype={"hex_id": "str"},
    )
    taluka = pd.read_csv(TALUKA_FILE)
    summary = pd.read_csv(SUMMARY_FILE)
    sensitivity = pd.read_csv(SENSITIVITY_FILE)
    validation = pd.read_csv(VALIDATION_FILE)
    district_validation = pd.read_csv(DISTRICT_VALIDATION_FILE)

    return severity, taluka, summary, sensitivity, validation, district_validation


# ============================================================
# VALIDATE INPUT FILES AND LOAD
# ============================================================

required_files = [
    SEVERITY_FILE,
    TALUKA_FILE,
    SUMMARY_FILE,
    SENSITIVITY_FILE,
    VALIDATION_FILE,
    DISTRICT_VALIDATION_FILE,
]

missing_files = [str(file_path) for file_path in required_files if not file_path.exists()]

if missing_files:
    st.error("Required project output files are missing:")
    for file_path in missing_files:
        st.code(file_path)
    st.stop()

try:
    (
        severity,
        taluka,
        summary,
        sensitivity,
        validation,
        district_validation,
    ) = load_data()
except Exception as error:
    st.error(f"Unable to load project data: {error}")
    st.stop()

if severity.empty:
    st.error("The severity_hex.csv file contains no records.")
    st.stop()


# ============================================================
# DATA PREPARATION
# ============================================================

required_severity_columns = [
    "hex_id", "pop", "n_buildings", "d_hosp", "d_school",
    "d_water", "severity", "lon", "lat",
]
missing_columns = [c for c in required_severity_columns if c not in severity.columns]

if missing_columns:
    st.error(f"Missing columns in severity_hex.csv: {', '.join(missing_columns)}")
    st.stop()

numeric_columns = [
    "pop", "n_buildings", "d_hosp", "d_school",
    "d_water", "severity", "lon", "lat",
]

for column in numeric_columns:
    severity[column] = pd.to_numeric(severity[column], errors="coerce")

severity = severity.dropna(subset=["hex_id", "severity", "lon", "lat"]).copy()
severity = severity[
    severity["lon"].between(68, 98)
    & severity["lat"].between(6, 38)
].copy()

for column in ["pop", "n_buildings", "severity", "d_hosp", "d_school", "d_water"]:
    severity[column] = severity[column].replace([np.inf, -np.inf], np.nan)

severity["pop"] = severity["pop"].fillna(0).clip(lower=0)
severity["n_buildings"] = severity["n_buildings"].fillna(0).clip(lower=0)
severity["severity"] = severity["severity"].fillna(0).clip(lower=0)

for column in ["d_hosp", "d_school", "d_water"]:
    severity[column] = severity[column].clip(lower=0)

severity["severity_per_person"] = np.where(
    severity["pop"] > 0,
    severity["severity"] / severity["pop"],
    0,
)

# Relative quartile groups for display only; these are not official risk classes.
try:
    severity["risk_group"] = pd.qcut(
        severity["severity"].rank(method="first"),
        q=4,
        labels=["Q1 - Lowest", "Q2 - Moderate", "Q3 - High", "Q4 - Highest"],
    )
except ValueError:
    severity["risk_group"] = "Unclassified"

if "district" not in taluka.columns:
    taluka["district"] = "Unknown"

for col in ["severity_per_person", "total_severity", "population"]:
    if col in taluka.columns:
        taluka[col] = pd.to_numeric(taluka[col], errors="coerce")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def metric_card(title, value, description=""):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-label">{html.escape(str(title))}</div>
            <div class="metric-value">{html.escape(str(value))}</div>
            <div class="metric-description">{html.escape(str(description))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def format_number(value):
    return f"{value:,.0f}"


def apply_chart_style(fig, height=430):
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font=dict(family="Arial, sans-serif", size=12, color="#334155"),
        title=dict(font=dict(size=17, color="#142238"), x=0.02),
        height=height,
        margin=dict(l=45, r=30, t=65, b=50),
        legend=dict(
            bgcolor="rgba(255,255,255,0.9)",
            bordercolor="#e2e8f0",
            borderwidth=1,
            font=dict(color="#334155"),
        ),
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#edf1f6",
        zerolinecolor="#cbd5e1",
        automargin=True,
    )
    fig.update_yaxes(
        showgrid=False,
        gridcolor="#edf1f6",
        zerolinecolor="#cbd5e1",
        automargin=True,
    )
    return fig


def section_title(title, subtitle=None):
    st.markdown(
        f'<div class="section-title">{html.escape(str(title))}</div>',
        unsafe_allow_html=True,
    )
    if subtitle:
        st.caption(subtitle)


def make_bar_chart(data, x, y, title, color=None, height=450):
    fig = px.bar(
        data,
        x=x,
        y=y,
        color=color,
        title=title,
        orientation="h",
        color_discrete_sequence=[
            "#0d9488", "#2563eb", "#f59e0b", "#dc6b45", "#7c3aed"
        ],
    )
    fig.update_traces(marker_line_width=0, opacity=0.92)
    fig.update_yaxes(categoryorder="total ascending")
    return apply_chart_style(fig, height=height)


def render_map_legend(title, description, low, high, unit):
    # Build compact HTML without indentation so Markdown cannot treat it as a code block.
    legend_html = f"""<div style="background:#ffffff;padding:18px 22px;border:1px solid #dbe3ed;border-radius:12px;margin:12px 0 16px 0;">
<div style="font-size:17px;font-weight:700;color:#142238;margin-bottom:5px;">{html.escape(title)}</div>
<div style="font-size:13px;color:#475569;margin-bottom:14px;">{html.escape(description)}</div>
<div style="height:16px;border-radius:10px;background:linear-gradient(to right,rgb(13,148,136),rgb(250,204,21),rgb(249,115,22),rgb(185,28,28));"></div>
<div style="display:flex;justify-content:space-between;gap:12px;margin-top:9px;font-size:12px;font-weight:600;color:#334155;">
<span>LOW: {low:,.2f} {html.escape(unit)}</span><span>HIGH: {high:,.2f} {html.escape(unit)}</span>
</div>
<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-top:12px;font-size:11px;color:#475569;">
<span>● Low</span><span>● Moderate</span><span>● High</span><span>● Very high</span>
</div>
<div style="font-size:11px;color:#64748b;margin-top:10px;">Colour scale uses the 2nd–98th percentile range of the displayed dataset. Values outside this range are clipped to the end colours. These are relative metric values, not official government risk categories.</div>
</div>"""
    st.markdown(legend_html, unsafe_allow_html=True)


def make_map_colors(values):
    values = np.asarray(values, dtype=float)
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)

    if len(values) == 0:
        return [], 0.0, 0.0

    low, high = np.percentile(values, [2, 98])

    if not np.isfinite(low):
        low = 0.0
    if not np.isfinite(high):
        high = low

    if high <= low:
        normalized = np.zeros(len(values), dtype=float)
    else:
        normalized = np.clip((values - low) / (high - low), 0, 1)

    # Teal -> yellow -> orange -> dark red.
    positions = np.array([0.00, 0.35, 0.70, 1.00])
    red = np.array([13, 250, 249, 185])
    green = np.array([148, 204, 115, 28])
    blue = np.array([136, 21, 22, 28])

    colors = np.column_stack(
        [
            np.interp(normalized, positions, red),
            np.interp(normalized, positions, green),
            np.interp(normalized, positions, blue),
            np.full(len(normalized), 220),
        ]
    ).round().astype(int).tolist()

    return colors, float(low), float(high)


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("⬡ INFRA-GAP")
st.sidebar.caption("Distributed Geospatial Infrastructure Analysis")
st.sidebar.divider()

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Overview",
        "Infrastructure Gap Map",
        "Taluka Analysis",
        "Accessibility Analysis",
        "Validation",
        "Sensitivity Analysis",
    ],
)

st.sidebar.divider()
st.sidebar.subheader("Study Area")
st.sidebar.info(
    "Maharashtra, India\n\n"
    "H3 Resolution: 8\n\n"
    "Approximate hexagon area: 0.74 km²"
)
st.sidebar.divider()
st.sidebar.caption(
    "Processing: Apache Spark + Apache Sedona\n"
    "Spatial indexing: Uber H3\n"
    "Visualization: Streamlit + PyDeck"
)

if st.sidebar.button("Refresh Dashboard Data"):
    st.cache_data.clear()
    st.rerun()


# ============================================================
# GLOBAL HEADER
# ============================================================

st.title("⬡ INFRA-GAP")
st.markdown("### Mapping Infrastructure Accessibility Gaps Across Maharashtra")
st.caption(
    "A distributed geospatial big data analytics platform "
    "for identifying underserved population clusters."
)
st.divider()


# ============================================================
# OVERVIEW
# ============================================================

if page == "Overview":
    total_hex = len(severity)
    total_population = severity["pop"].sum()
    avg_severity = severity["severity"].mean()
    critical_cells = (severity["risk_group"] == "Q4 - Highest").sum()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        metric_card("H3 HEXAGONS", format_number(total_hex), "Valid spatial analysis units")
    with col2:
        metric_card("MODELLED POPULATION", format_number(total_population), "Population estimate")
    with col3:
        metric_card("AVERAGE SEVERITY", f"{avg_severity:.2f}", "Mean cell severity score")
    with col4:
        metric_card("CRITICAL CELLS", format_number(critical_cells), "Highest severity quartile")

    section_title("Infrastructure Accessibility Overview")
    s = summary.iloc[0]

    col1, col2, col3 = st.columns(3)
    with col1:
        metric_card("HOSPITAL ACCESS GAP", f"{s['hosp_pct_pop_beyond']:.2f}%", "Population beyond 10 km")
    with col2:
        metric_card("SCHOOL ACCESS GAP", f"{s['school_pct_pop_beyond']:.2f}%", "Population beyond 3 km")
    with col3:
        metric_card("WATER ACCESS GAP", f"{s['water_pct_pop_beyond']:.2f}%", "Population beyond 2 km")

    section_title("Population Beyond Accessibility Thresholds")
    access_data = pd.DataFrame(
        {
            "Infrastructure": ["Hospitals", "Schools", "Water Points"],
            "Population (%)": [
                s["hosp_pct_pop_beyond"],
                s["school_pct_pop_beyond"],
                s["water_pct_pop_beyond"],
            ],
        }
    )

    fig = px.bar(
        access_data,
        x="Infrastructure",
        y="Population (%)",
        color="Infrastructure",
        text_auto=".2f",
        color_discrete_map={
            "Hospitals": "#2563eb",
            "Schools": "#0d9488",
            "Water Points": "#f59e0b",
        },
        title="Population Beyond Accessibility Thresholds",
    )
    fig.update_traces(textposition="outside", cliponaxis=False)
    fig = apply_chart_style(fig, height=420)
    fig.update_layout(margin=dict(l=35, r=25, t=65, b=55))
    st.plotly_chart(fig, width="stretch")

    section_title("Top 10 Infrastructure Gap Talukas")
    if "severity_per_person" in taluka.columns and "taluka" in taluka.columns:
        top10 = taluka.nlargest(10, "severity_per_person")
        fig = make_bar_chart(
            top10,
            x="severity_per_person",
            y="taluka",
            title="Top 10 Talukas by Severity Per Person",
        )
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("Taluka ranking file does not contain the required ranking columns.")

    st.caption(
        "Severity-per-person rankings are not the same as total infrastructure-gap burden."
    )


# ============================================================
# INFRASTRUCTURE GAP MAP
# ============================================================

elif page == "Infrastructure Gap Map":
    section_title(
        "Geospatial Infrastructure Gap Map",
        "Each polygon represents one H3 resolution-8 spatial cell.",
    )

    metric_labels = {
        "Infrastructure Gap Severity": "severity",
        "Population": "pop",
        "Distance to Hospital": "d_hosp",
        "Distance to School": "d_school",
        "Distance to Water Facility": "d_water",
    }
    selected_label = st.selectbox("Select Map Metric", list(metric_labels.keys()))
    map_mode = metric_labels[selected_label]

    # Full dataset is the default. Smaller options are available for slower machines.
    render_options = {
        "All valid cells": len(severity),
        "150,000 cells": min(150000, len(severity)),
        "75,000 cells": min(75000, len(severity)),
        "25,000 cells": min(25000, len(severity)),
    }
    render_choice = st.selectbox(
        "Number of H3 cells to render",
        list(render_options.keys()),
        index=0,
        help="Rendering all 321,165 cells may take longer. Smaller options improve responsiveness.",
    )
    map_limit = render_options[render_choice]

    if map_limit < len(severity):
        # Keep the highest metric values so the subset emphasizes larger values.
        map_data_full = severity.nlargest(map_limit, map_mode).copy()
        st.warning(
            f"Showing {len(map_data_full):,} of {len(severity):,} valid H3 cells. "
            "This is a filtered subset, not the complete statewide map."
        )
    else:
        map_data_full = severity.copy()
        st.success(f"Showing all {len(map_data_full):,} valid H3 cells.")

    values = pd.to_numeric(
        map_data_full[map_mode], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan).fillna(0).to_numpy(dtype=float)

    colors, low, high = make_map_colors(values)

    # Preserve a one-to-one relationship between H3 IDs and RGBA colours.
    map_data = map_data_full[["hex_id"]].copy()
    map_data["fill_color"] = colors

    if len(map_data) != len(colors):
        st.error("Map rendering error: H3 cell and colour counts do not match.")
        st.stop()

    info = {
        "severity": (
            "Infrastructure Gap Severity",
            "Higher values indicate greater infrastructure gap severity.",
            "Severity score",
        ),
        "pop": (
            "Population Distribution",
            "Higher values indicate more modelled population in a hexagon.",
            "People per hexagon",
        ),
        "d_hosp": (
            "Distance to Nearest Hospital",
            "Higher values indicate poorer hospital proximity.",
            "km",
        ),
        "d_school": (
            "Distance to Nearest School",
            "Higher values indicate poorer school proximity.",
            "km",
        ),
        "d_water": (
            "Distance to Nearest Water Facility",
            "Higher values indicate poorer water-facility proximity.",
            "km",
        ),
    }[map_mode]

    render_map_legend(
        title=info[0],
        description=info[1],
        low=low,
        high=high,
        unit=info[2],
    )

    if map_mode == "severity":
        st.markdown(
            """
            <div style="background:#ffffff;border:1px solid #dbe3ed;border-radius:10px;padding:14px 18px;margin-bottom:15px;">
            <div style="font-size:16px;font-weight:700;color:#142238;margin-bottom:12px;">Severity Classification</div>
            <div style="display:flex;gap:22px;flex-wrap:wrap;font-size:13px;font-weight:600;">
            <span style="color:#0d9488;">● Q1 – Lowest</span>
            <span style="color:#60a5fa;">● Q2 – Moderate</span>
            <span style="color:#d97706;">● Q3 – High</span>
            <span style="color:#dc2626;">● Q4 – Highest</span>
            </div>
            <p style="color:#64748b;font-size:11px;margin-top:10px;margin-bottom:0;">
            Quartiles are relative severity-score groups, not official government risk categories.
            </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    layer = pdk.Layer(
        "H3HexagonLayer",
        data=map_data,
        get_hexagon="hex_id",
        get_fill_color="fill_color",
        pickable=True,
        auto_highlight=True,
        extruded=False,
        coverage=0.95,
        opacity=0.92,
    )

    view = pdk.ViewState(
        latitude=19.5,
        longitude=76.5,
        zoom=5.8,
        pitch=0,
    )

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view,
        tooltip={
            "html": (
                "<b>H3 Cell:</b> {hex_id}<br/>"
                "<b>Selected metric:</b> " + html.escape(selected_label)
            ),
            "style": {
                "backgroundColor": "#142238",
                "color": "white",
            },
        },
        map_style="https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    )

    st.pydeck_chart(deck, width="stretch", height=680)

    st.caption(
        "The map displays H3 cells from the exported dataset. "
        "Colour is relative to the selected metric and displayed subset. "
        "Distances are not road-network travel times."
    )

    download_columns = [
        c for c in [
            "hex_id", "pop", "n_buildings", "d_hosp",
            "d_school", "d_water", "severity", "lon", "lat",
        ]
        if c in map_data_full.columns
    ]
    st.download_button(
        "Download Displayed Map Data",
        map_data_full[download_columns].to_csv(index=False),
        file_name="infra_gap_map_data.csv",
        mime="text/csv",
    )


# ============================================================
# TALUKA ANALYSIS
# ============================================================

elif page == "Taluka Analysis":
    section_title("Taluka-Level Infrastructure Analysis")

    available_metrics = {
        "Severity Per Person": "severity_per_person",
        "Total Severity": "total_severity",
        "Population": "population",
    }
    available_metrics = {
        label: column for label, column in available_metrics.items()
        if column in taluka.columns
    }

    if not available_metrics or "taluka" not in taluka.columns:
        st.error("The taluka ranking file is missing required columns.")
    else:
        ranking_type = st.radio(
            "Ranking Metric",
            list(available_metrics.keys()),
            horizontal=True,
        )
        metric = available_metrics[ranking_type]
        top_n = st.slider(
            "Number of talukas",
            min_value=5,
            max_value=min(30, max(5, len(taluka))),
            value=min(10, max(5, len(taluka))),
        )
        ranked = taluka.nlargest(top_n, metric)
        fig = make_bar_chart(
            ranked,
            x=metric,
            y="taluka",
            title=f"Top {top_n} Talukas — {ranking_type}",
        )
        st.plotly_chart(fig, width="stretch")

        section_title("District Filter")
        districts = ["All"] + sorted(taluka["district"].dropna().astype(str).unique().tolist())
        selected_district = st.selectbox("Select District", districts)
        filtered = taluka.copy()

        if selected_district != "All":
            filtered = filtered[filtered["district"].astype(str) == selected_district]

        st.dataframe(
            filtered.sort_values(metric, ascending=False),
            width="stretch",
            hide_index=True,
        )
        st.download_button(
            "Download Taluka Rankings",
            filtered.to_csv(index=False),
            file_name="taluka_rankings.csv",
            mime="text/csv",
        )


# ============================================================
# ACCESSIBILITY ANALYSIS
# ============================================================

elif page == "Accessibility Analysis":
    section_title("Infrastructure Accessibility Analysis")

    infrastructure = st.selectbox(
        "Choose Infrastructure",
        ["Hospital", "School", "Drinking Water"],
    )
    column_map = {
        "Hospital": "d_hosp",
        "School": "d_school",
        "Drinking Water": "d_water",
    }
    distance_column = column_map[infrastructure]
    data = severity[distance_column].dropna() / 1000

    if data.empty:
        st.warning("No distance observations are available for this infrastructure type.")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            metric_card("MEDIAN DISTANCE", f"{data.median():.2f} km")
        with col2:
            metric_card("90TH PERCENTILE", f"{data.quantile(0.90):.2f} km")
        with col3:
            metric_card("MAXIMUM OBSERVED", f"{data.max():.2f} km")

        fig = px.histogram(
            x=data,
            nbins=50,
            title=f"Distance Distribution: {infrastructure}",
            labels={"x": "Distance (km)", "y": "H3 Cells"},
        )
        fig = apply_chart_style(fig, height=450)
        st.plotly_chart(fig, width="stretch")

    section_title("Population vs Infrastructure Gap")
    scatter_data = severity.copy()

    fig = px.scatter(
        scatter_data,
        x="pop",
        y="severity",
        color="risk_group",
        opacity=0.5,
        title="Population vs Gap Severity",
        labels={
            "pop": "Modelled Population per H3 Cell",
            "severity": "Gap Severity Score",
            "risk_group": "Severity Quartile",
        },
        color_discrete_map={
            "Q1 - Lowest": "#0d9488",
            "Q2 - Moderate": "#60a5fa",
            "Q3 - High": "#f59e0b",
            "Q4 - Highest": "#dc2626",
            "Unclassified": "#64748b",
        },
    )
    fig.update_traces(marker=dict(size=5))
    fig = apply_chart_style(fig, height=500)
    st.plotly_chart(fig, width="stretch")


# ============================================================
# VALIDATION
# ============================================================

elif page == "Validation":
    section_title(
        "Hospital Data Validation",
        "Comparison between official hospital records and OpenStreetMap.",
    )

    if validation.empty:
        st.warning("Validation summary contains no records.")
    else:
        v = validation.iloc[0]
        official_total = float(v["official_total"])
        matched = float(v["matched_in_osm"])
        unmatched = max(official_total - matched, 0)

        col1, col2, col3 = st.columns(3)
        with col1:
            metric_card("OFFICIAL HOSPITALS", format_number(official_total))
        with col2:
            metric_card("OSM MATCHED", format_number(matched))
        with col3:
            metric_card("MATCH RATE", f"{float(v['osm_match_pct']):.2f}%")

        section_title("Validation Interpretation")
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=["Matched", "Unmatched"],
                    values=[matched, unmatched],
                    hole=0.55,
                    marker=dict(colors=["#0d9488", "#f59e0b"]),
                    textinfo="label+percent",
                )
            ]
        )
        fig.update_layout(
            title="Official Hospitals: OSM Matching",
            template="plotly_white",
            paper_bgcolor="#ffffff",
            plot_bgcolor="#ffffff",
            font=dict(color="#334155"),
            height=400,
            margin=dict(l=30, r=30, t=65, b=35),
        )
        st.plotly_chart(fig, width="stretch")

    section_title("District-Level Validation")
    if not district_validation.empty:
        district_data = district_validation.copy()
        district_data["official_total"] = pd.to_numeric(
            district_data["official_total"], errors="coerce"
        )
        district_data["matched_in_osm"] = pd.to_numeric(
            district_data["matched_in_osm"], errors="coerce"
        )
        district_data["match_percentage"] = (
            district_data["matched_in_osm"]
            / district_data["official_total"].replace(0, np.nan)
            * 100
        )
        district_data = district_data.sort_values("match_percentage", ascending=True)

        fig = px.bar(
            district_data,
            x="match_percentage",
            y="district",
            orientation="h",
            title="Hospital Matching Percentage by District",
            labels={"match_percentage": "Match rate (%)", "district": "District"},
            color="match_percentage",
            color_continuous_scale=["#f59e0b", "#0d9488"],
        )
        fig = apply_chart_style(fig, height=650)
        st.plotly_chart(fig, width="stretch")
        st.dataframe(district_data, width="stretch", hide_index=True)
    else:
        st.warning("District validation file contains no records.")

    st.warning(
        "An unmatched official hospital does not necessarily mean that the "
        "hospital is absent from OSM at its real location. Matching depends "
        "on the project's spatial matching criteria."
    )


# ============================================================
# SENSITIVITY ANALYSIS
# ============================================================

elif page == "Sensitivity Analysis":
    section_title(
        "Sensitivity Analysis",
        "Testing the stability of infrastructure-gap rankings.",
    )

    st.dataframe(sensitivity, width="stretch", hide_index=True)

    if {"scenario", "spearman_rho"}.issubset(sensitivity.columns):
        fig = px.bar(
            sensitivity,
            x="scenario",
            y="spearman_rho",
            color="spearman_rho",
            range_y=[0, 1.05],
            text_auto=".3f",
            title="Ranking Stability: Spearman Correlation",
            color_continuous_scale=["#f59e0b", "#0d9488"],
        )
        fig = apply_chart_style(fig, height=450)
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("Sensitivity file needs 'scenario' and 'spearman_rho' columns.")

    if {"scenario", "top10_overlap"}.issubset(sensitivity.columns):
        fig = px.bar(
            sensitivity,
            x="scenario",
            y="top10_overlap",
            title="Top 10 Taluka Ranking Overlap",
            color_discrete_sequence=["#2563eb"],
        )
        fig = apply_chart_style(fig, height=400)
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("Sensitivity file needs 'scenario' and 'top10_overlap' columns.")

    st.info(
        "A Spearman correlation close to 1 indicates that relative rankings "
        "remain similar under the tested parameter changes. It does not prove "
        "that the underlying accessibility model is accurate."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.markdown(
    """
    <div class="dashboard-footer">
        INFRA-GAP | Maharashtra Infrastructure Accessibility Analysis
        <br>
        Apache Spark · Apache Sedona · Uber H3 · Streamlit
        <br>
        © OpenStreetMap contributors
    </div>
    """,
    unsafe_allow_html=True,
)
