import streamlit as st
import pandas as pd
import numpy as np
import math
import matplotlib.pyplot as plt
import io
from pathlib import Path
import streamlit.components.v1 as components

# Configure page title and favicon
st.set_page_config(
    page_title='Army Readiness Dashboard',
    layout='wide',
)

# Page styling
st.markdown(
    """
    <style>
    .stApp {
        background-color: #0b0f12;
        color: #ffffff;
        margin-bottom: 6px;
        line-height: 1.1;
    }
    .big-title {
        font-size: 40px;
        font-weight: 800;
        color: #ffffff;
        margin-bottom: 20px;
    }
    .overall-number {
        margin-top: 10px;
        margin-bottom: 10px;
        font-size: 28px;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.05;
    }
    .overall-block { margin-bottom: 18px; }
    .banner {
        background: #f6a21b;
        color: #ffffff;
        padding: 18px 22px;
        border-radius: 10px;
        font-weight: 700;
        margin-bottom: 6px;
    }
    .section-title {
        color: #ffffff;
        font-size: 22px;
        margin-top: 22px;
        margin-bottom: 10px;
    }
    .card {
        background: #ffffff;
        color: #222222;
        border-radius: 12px;
        padding: 18px;
        height: 160px;
        box-shadow: none;
    }
    .card .muted { color: #9aa0a6; font-size: 12px; }
    .card .score { font-size: 28px; font-weight: 700; color: #111; }
    .spark { height: 48px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# Function definitions
# =============================================================================

def _make_sparkline(values, color="#1f8f3f"):
    """Create a small sparkline PNG in-memory and return as BytesIO.

    The sparkline is used for compact trend visualizations in the UI.
    """
    buf = io.BytesIO()
    fig = plt.figure(figsize=(2.6, 0.6), dpi=96)
    ax = fig.add_subplot(111)
    ax.plot(values, color=color, linewidth=2)
    ax.fill_between(range(len(values)), values, color=color, alpha=0.05)
    ax.set_axis_off()
    plt.margins(x=0)
    fig.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    plt.close(fig)
    buf.seek(0)
    return buf


# -----------------------------------------------------------------------------
# Helper functions

def get_gdp_data():
    """Load GDP data from an Excel file if present, otherwise CSV.

    Returns a long-form DataFrame with columns: `Country Code`, `Year`, `GDP`.
    The result is cached by Streamlit to avoid repeated file reads.
    """

    # Prefer an Excel file if present; fall back to CSV.
    DATA_FILENAME_EXCEL = Path(__file__).parent / 'data' / 'gdp_data.xlsx'
    DATA_FILENAME_CSV = Path(__file__).parent / 'data' / 'gdp_data.csv'

    try:
        if DATA_FILENAME_EXCEL.exists():
            raw_gdp_df = pd.read_excel(DATA_FILENAME_EXCEL, engine='openpyxl')
        else:
            raw_gdp_df = pd.read_csv(DATA_FILENAME_CSV)
    except Exception:
        # Fallback to CSV if Excel fails
        raw_gdp_df = pd.read_csv(DATA_FILENAME_CSV)

    # Dataset year range
    MIN_YEAR = 1960
    MAX_YEAR = 2022

    # Transpose year columns to long format
    gdp_df = raw_gdp_df.melt(
        ['Country Code'],
        [str(x) for x in range(MIN_YEAR, MAX_YEAR + 1)],
        'Year',
        'GDP',
    )

    # Ensure correct dtypes
    gdp_df['Year'] = pd.to_numeric(gdp_df['Year'])
    gdp_df['GDP'] = pd.to_numeric(gdp_df['GDP'], errors='coerce')

    return gdp_df


def load_readiness_from_excel(excel_path, unit_choice=None):
    """Load readiness values from an Excel workbook.

    Expected workbook format:
    - Sheet 0: overall readiness table (contains a numeric score and optional unit column)
    - Sheet 1: key factors with columns such as `name`, `score`, `trend`, `color`

    If parsing fails the function returns `(None, None)`.
    """
    try:
        overall_df = pd.read_excel(excel_path, sheet_name=0, engine='openpyxl')
        kf_df = pd.read_excel(excel_path, sheet_name=1, engine='openpyxl')
    except Exception:
        return None, None

    # Filter sheets by unit if present
    if unit_choice is not None:
        overall_cols_map = {c.lower(): c for c in overall_df.columns}
        kf_cols_map = {c.lower(): c for c in kf_df.columns}

        overall_has_unit = 'unit' in overall_cols_map
        kf_has_unit = 'unit' in kf_cols_map

        if overall_has_unit:
            overall_df = overall_df[overall_df[overall_cols_map['unit']].astype(str) == str(unit_choice)]
        if kf_has_unit:
            kf_df = kf_df[kf_df[kf_cols_map['unit']].astype(str) == str(unit_choice)]

        # Return no data if both sheets filtered to empty
        if (overall_has_unit or kf_has_unit) and overall_df.empty and kf_df.empty:
            return None, None

    # Parse overall readiness
    overall_val = None
    if isinstance(overall_df, pd.DataFrame) and not overall_df.empty:
        cols_map = {c.lower(): c for c in overall_df.columns}
        value_candidates = ['readiness', 'readiness_score', 'score', 'value', 'overall', 'overall_readiness']

        unit_col = cols_map.get('unit')

        # Select row by unit or use first row
        row = None
        if unit_col is not None and unit_choice is not None:
            matched = overall_df[overall_df[unit_col].astype(str) == str(unit_choice)]
            if not matched.empty:
                row = matched.iloc[0]

        if row is None:
            row = overall_df.iloc[0]

        # Find named column or fall back to first non-unit column
        for cand in value_candidates:
            col_name = cols_map.get(cand)
            if col_name is not None:
                try:
                    v = row[col_name]
                    if pd.notna(v):
                        overall_val = float(v)
                        break
                except Exception:
                    continue

        if overall_val is None:
            for c in overall_df.columns:
                if c == unit_col:
                    continue
                try:
                    v = row[c]
                    if pd.notna(v):
                        overall_val = float(v)
                        break
                except Exception:
                    continue

    # Parse key factors
    kf_list = []
    if isinstance(kf_df, pd.DataFrame) and not kf_df.empty:
        cols_map = {c.lower(): c for c in kf_df.columns}

        unit_col = cols_map.get('unit')
        name_col = cols_map.get('name') or cols_map.get('factor') or list(kf_df.columns)[0]
        score_col = (
            cols_map.get('score')
            or cols_map.get('value')
            or (list(kf_df.columns)[1] if len(kf_df.columns) > 1 else name_col)
        )
        trend_col = cols_map.get('trend')
        color_col = cols_map.get('color') or cols_map.get('colour')

        df_kf = kf_df
        if unit_col is not None and unit_choice is not None:
            df_kf = df_kf[df_kf[unit_col].astype(str) == str(unit_choice)]

        for _, r in df_kf.iterrows():
            try:
                name = str(r[name_col]) if name_col in r.index else str(r.iat[0])
                score = float(r[score_col]) if score_col in r.index else float(r.iat[1])
                trend = str(r[trend_col]) if (trend_col in r.index and pd.notna(r[trend_col])) else 'UNKNOWN'
                color = str(r[color_col]) if (color_col in r.index and pd.notna(r[color_col])) else '#1f8f3f'
                kf_list.append((name, score, trend, color))
            except Exception:
                continue

    return overall_val, kf_list


# =============================================================================
# Page setup and configuration
# =============================================================================

# Big page title
st.markdown('<div class="big-title">Army Readiness Dashboard</div>', unsafe_allow_html=True)

# Spacing
st.write("")
st.write("")

# Load GDP data
gdp_df = get_gdp_data()

# Unit selector
unit_choice = st.sidebar.selectbox(
    'Select Unit',
    ('1 SIR', '2 SIR', '3 SIR', '5 SIR'),
    index=0,
)
_unit_map = {'1 SIR': 1e12, '2 SIR': 1e9, '3 SIR': 1e6, '5 SIR': 1}
unit_scale = _unit_map[unit_choice]
_suffix_map = {'1 SIR': 'T', '2 SIR': 'B', '3 SIR': 'M', '5 SIR': ''}

unit_suffix = _suffix_map[unit_choice]

# File upload widget
uploaded_file = st.sidebar.file_uploader(
    'Upload Data File',
    type=['xlsx', 'xls'],
)

if uploaded_file is not None:
    # Save uploaded file
    try:
        data_dir = Path(__file__).parent / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)
        save_path = data_dir / 'readiness.xlsx'
        file_bytes = uploaded_file.read()
        with open(save_path, 'wb') as f:
            f.write(file_bytes)
        st.sidebar.success('File saved!')
    except Exception as e:
        st.sidebar.error(f'Failed to save file: {e}')

# Load readiness data
excel_path = Path(__file__).parent / 'data' / 'readiness.xlsx'
if excel_path.exists():
    loaded_overall, loaded_kf = load_readiness_from_excel(excel_path, unit_choice=unit_choice)

    # Override defaults with loaded data
    if loaded_overall is not None:
        try:
            # Parse overall score
            readiness_score = int(float(loaded_overall))
        except Exception:
            pass

    if loaded_kf:
        try:
            # Parse key factors
            key_factors = loaded_kf
        except Exception:
            pass

# Display readiness score
score = int(readiness_score) if 'readiness_score' in locals() else 0
st.header(f"{unit_choice}'s Readiness: {score} / 100")

# Color-code by score range
if score <= 49:
        bar_color = '#c33'
elif score <= 79:
        bar_color = '#f39c12'
else:
        bar_color = '#1f8f3f'

# Animate progress bar
prev_score = st.session_state.get('prev_readiness_score', 0)
html = f"""
<div style='background:#1b1f23;border-radius:10px;padding:6px;width:100%;max-width:720px'>
    <div id='readiness-bar' style='width:{prev_score}%;background:{bar_color};height:18px;border-radius:8px;transition:width 600ms ease, background-color 400ms linear;'></div>
</div>
<script>
    const bar = document.getElementById('readiness-bar');
    setTimeout(()=> {{
        bar.style.width = '{score}%';
        bar.style.background = '{bar_color}';
    }}, 50);
</script>
"""
components.html(html, height=40)
st.session_state['prev_readiness_score'] = score

# =========================
# GRID VIEW
# =========================
st.header('Key Factors', divider='gray') 
for row_start in range(0, len(key_factors), 3): 
    cols = st.columns(3) 
    for i, (name, score, trend, color) in enumerate(key_factors[row_start:row_start+3]): 
        col = cols[i] 
        with col: 
            # Render factor card 
            trend_color = color if trend == "IMPROVING" else "#c33" 
            # st.markdown(f'<div style="margin:12px;"><div class="card"><div class="muted">{name}</div><div class="score">{score}/100</div><div class="muted">Report trend: <b style="color:{trend_color}">{trend}</b></div></div></div>', unsafe_allow_html=True, )
            
            st.markdown(f"""
            <a href="?card={name}" style="text-decoration:none;">
            <div style="margin:12px; padding:12px; border-radius:8px; box-shadow:0 2px 5px rgba(0,0,0,0.1); background-color:#f9f9f9; color:black;">
                <div style="font-size:14px; color:#555;">{name}</div>
                <div style="font-size:20px; font-weight:bold;">{score}/100</div>
                <div style="font-size:12px; color:#777;">
                    Report trend: <b style="color:{trend_color};">{trend}</b>
                </div>
            </div>
            </a>
            """, unsafe_allow_html=True)

# GDP visualization section

# Spacing
st.write("")
st.write("")

min_value = gdp_df['Year'].min()
max_value = gdp_df['Year'].max()

from_year, to_year = st.slider(
    'Which years are you interested in?',
    min_value=min_value,
    max_value=max_value,
    value=[min_value, max_value])

countries = gdp_df['Country Code'].unique()

if not len(countries):
    st.warning("Select at least one country")

selected_countries = st.multiselect(
    'Which countries would you like to view?',
    countries,
    ['DEU', 'FRA', 'GBR', 'BRA', 'MEX', 'JPN'],
)

# Add vertical spacing
st.write("")
st.write("")
st.write("")

# Filter GDP data
filtered_gdp_df = gdp_df[
    (gdp_df['Country Code'].isin(selected_countries))
    & (gdp_df['Year'] <= to_year)
    & (from_year <= gdp_df['Year'])
]

# Scale GDP by unit
filtered_gdp_df = filtered_gdp_df.copy()
filtered_gdp_df['GDP_SCALED'] = filtered_gdp_df['GDP'] / unit_scale

st.header('GDP over time', divider='gray')

st.write("")

st.line_chart(
    filtered_gdp_df,
    x='Year',
    y='GDP_SCALED',
    color='Country Code',
)

st.write("")
st.write("")


first_year = gdp_df[gdp_df['Year'] == from_year]
last_year = gdp_df[gdp_df['Year'] == to_year]

st.header(f'GDP in {to_year}', divider='gray')

st.write("")

cols = st.columns(4)

for i, country in enumerate(selected_countries):
    col = cols[i % len(cols)]

    with col:
        # Get GDP for country/year (assumes row exists)
        first_gdp = first_year[first_year['Country Code'] == country]['GDP'].iat[0] / unit_scale
        last_gdp = last_year[last_year['Country Code'] == country]['GDP'].iat[0] / unit_scale

        if math.isnan(first_gdp):
            growth = 'n/a'
            delta_color = 'off'
        else:
            growth = f'{last_gdp / first_gdp:,.2f}x'
            delta_color = 'normal'

        st.metric(
            label=f'{country} GDP ({unit_choice})',
            value=f'{last_gdp:,.0f}{unit_suffix}',
            delta=growth,
            delta_color=delta_color,
        )