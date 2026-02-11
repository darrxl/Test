import streamlit as st
import pandas as pd
import math
import matplotlib.pyplot as plt
import io
from pathlib import Path
import streamlit.components.v1 as components

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='Army Readiness Dashboard',
    layout='wide',
)

# Page styling to approximate desired layout (dark background, banner, cards)
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

# Big page title
st.markdown('<div class="big-title">Army Readiness Dashboard</div>', unsafe_allow_html=True)


# Add some spacing
''
''

def _make_sparkline(values, color="#1f8f3f"):
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
# Declare some useful functions.

@st.cache_data
def get_gdp_data():
    """Grab GDP data from an Excel file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Try to read from Excel file first, fall back to CSV if not available
    DATA_FILENAME_EXCEL = Path(__file__).parent/'data/gdp_data.xlsx'
    DATA_FILENAME_CSV = Path(__file__).parent/'data/gdp_data.csv'
    
    try:
        if DATA_FILENAME_EXCEL.exists():
            raw_gdp_df = pd.read_excel(DATA_FILENAME_EXCEL, engine='openpyxl')
        else:
            raw_gdp_df = pd.read_csv(DATA_FILENAME_CSV)
    except Exception:
        # Fallback to CSV if Excel reading fails
        raw_gdp_df = pd.read_csv(DATA_FILENAME_CSV)

    MIN_YEAR = 1960
    MAX_YEAR = 2022

    # The data above has columns like:
    # - Country Name
    # - Country Code
    # - [Stuff I don't care about]
    # - GDP for 1960
    # - GDP for 1961
    # - GDP for 1962
    # - ...
    # - GDP for 2022
    #
    # ...but I want this instead:
    # - Country Name
    # - Country Code
    # - Year
    # - GDP
    #
    # So let's pivot all those year-columns into two: Year and GDP
    gdp_df = raw_gdp_df.melt(
        ['Country Code'],
        [str(x) for x in range(MIN_YEAR, MAX_YEAR + 1)],
        'Year',
        'GDP',
    )

    # Convert years from string to integers
    gdp_df['Year'] = pd.to_numeric(gdp_df['Year'])
    # Convert GDP values to numeric, handling any non-numeric entries
    gdp_df['GDP'] = pd.to_numeric(gdp_df['GDP'], errors='coerce')

    return gdp_df

gdp_df = get_gdp_data()

# Sidebar: choose units for GDP display
unit_choice = st.sidebar.selectbox(
    'Select Unit',
    ('1 SIR', '2 SIR', '3 SIR', '5 SIR'),
    index=0,
)
_unit_map = {'1 SIR': 1e12, '2 SIR': 1e9, '3 SIR': 1e6, '5 SIR': 1}
unit_scale = _unit_map[unit_choice]
_suffix_map = {'1 SIR': 'T', '2 SIR': 'B', '3 SIR': 'M', '5 SIR': ''}

unit_suffix = _suffix_map[unit_choice]

# ----------------- Readiness Excel loader -----------------
def load_readiness_from_excel(excel_path, unit_choice=None):
    """Load readiness data from Excel file without caching."""
    try:
        # Sheet 0: Overall readiness
        overall_df = pd.read_excel(excel_path, sheet_name=0, engine='openpyxl')
        # Sheet 1: Key factors
        kf_df = pd.read_excel(excel_path, sheet_name=1, engine='openpyxl')
    except Exception:
        return None, None

    # Parse overall readiness
    overall_val = None
    if isinstance(overall_df, pd.DataFrame) and not overall_df.empty:
        cols_map = {c.lower(): c for c in overall_df.columns}

        # Common candidate names for the overall numeric value
        value_candidates = ['readiness', 'readiness_score', 'score', 'value', 'overall', 'overall_readiness']

        unit_col = cols_map.get('unit')

        # If a unit column exists and a unit_choice is provided, try to pick that row
        row = None
        if unit_col is not None and unit_choice is not None:
            matched = overall_df[overall_df[unit_col].astype(str) == str(unit_choice)]
            if not matched.empty:
                row = matched.iloc[0]

        # If we didn't find a matching row, take the first row
        if row is None:
            row = overall_df.iloc[0]

        # Try to find a named column for the numeric overall value
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

        # Fallback: use the first non-unit column's value
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

    # Parse key factors - expects columns: name, score, [trend], [color]
    kf_list = []
    if isinstance(kf_df, pd.DataFrame) and not kf_df.empty:
        cols_map = {c.lower(): c for c in kf_df.columns}

        unit_col = cols_map.get('unit')
        name_col = cols_map.get('name') or cols_map.get('factor') or list(kf_df.columns)[0]
        score_col = cols_map.get('score') or cols_map.get('value') or (list(kf_df.columns)[1] if len(kf_df.columns) > 1 else name_col)
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


# Sidebar: allow users to upload an Excel file to override readiness values
uploaded_file = st.sidebar.file_uploader(
    'Upload Data File',
    type=['xlsx', 'xls'],
)

if uploaded_file is not None:
    # Save the uploaded file to disk immediately
    try:
        data_dir = Path(__file__).parent / 'data'
        data_dir.mkdir(parents=True, exist_ok=True)
        save_path = data_dir / 'readiness.xlsx'
        # Read file bytes and save
        file_bytes = uploaded_file.read()
        with open(save_path, 'wb') as f:
            f.write(file_bytes)
        st.sidebar.success('File saved to readiness.xlsx!')
    except Exception as e:
        st.sidebar.error(f'Failed to save file: {e}')

# Load from saved readiness.xlsx file (whether just uploaded or from previous session)
excel_path = Path(__file__).parent / 'data' / 'readiness.xlsx'
if excel_path.exists():
    loaded_overall, loaded_kf = load_readiness_from_excel(excel_path, unit_choice=unit_choice)

    # Update values if Excel data is available
    if loaded_overall is not None:
        try:
            readiness_score = int(float(loaded_overall))
        except Exception:
            pass

    if loaded_kf:
        try:
            key_factors = loaded_kf
        except Exception:
            pass

# Render Overall Readiness (now that Excel has been loaded)
score = int(readiness_score) if 'readiness_score' in locals() else 0
st.header(f"{unit_choice}'s: {score}/100")

# Color-code the progress: Red 0-49, Orange 50-79, Green 81-100
if score <= 49:
        bar_color = '#c33'
elif score <= 79:
        bar_color = '#f39c12'
else:
        bar_color = '#1f8f3f'

# Animate width between previous and current score using a small component + session_state
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

# Add some spacing
''
''

# Render Key Factors (use key_factors, possibly overridden by Excel)
st.header('Key Factors', divider='gray')
for row_start in range(0, len(key_factors), 3):
    cols = st.columns(3)
    for i, (name, score, trend, color) in enumerate(key_factors[row_start:row_start+3]):
        col = cols[i]
        with col:
            st.markdown(
                f'<div style="margin:12px;"><div class="card"><div class="muted">{name}</div><div class="score">{score}/100</div><div class="muted">4-Report trend: <b style="color:{color if trend=="IMPROVING" else "#c33"}">{trend}</b></div></div></div>',
                unsafe_allow_html=True,
            )


# -----------------------------------------------------------------------------
# Draw the actual page

# Add some spacing
''
''


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
    ['DEU', 'FRA', 'GBR', 'BRA', 'MEX', 'JPN'])

''
''
''

# Filter the data
filtered_gdp_df = gdp_df[
    (gdp_df['Country Code'].isin(selected_countries))
    & (gdp_df['Year'] <= to_year)
    & (from_year <= gdp_df['Year'])
]

# Create a scaled GDP column according to the sidebar units selection
filtered_gdp_df = filtered_gdp_df.copy()
filtered_gdp_df['GDP_SCALED'] = filtered_gdp_df['GDP'] / unit_scale

st.header('GDP over time', divider='gray')

''

st.line_chart(
    filtered_gdp_df,
    x='Year',
    y='GDP_SCALED',
    color='Country Code',
)

''
''


first_year = gdp_df[gdp_df['Year'] == from_year]
last_year = gdp_df[gdp_df['Year'] == to_year]

st.header(f'GDP in {to_year}', divider='gray')

''

cols = st.columns(4)

for i, country in enumerate(selected_countries):
    col = cols[i % len(cols)]

    with col:
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
            delta_color=delta_color
        )