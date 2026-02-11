import streamlit as st
import pandas as pd
import math
import numpy as np
import matplotlib.pyplot as plt
import io
from pathlib import Path

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='Army Readiness Dashboard',
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
    """Grab GDP data from a CSV file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Instead of a CSV on disk, you could read from an HTTP endpoint here too.
    DATA_FILENAME = Path(__file__).parent/'data/gdp_data.csv'
    raw_gdp_df = pd.read_csv(DATA_FILENAME)

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

    return gdp_df

gdp_df = get_gdp_data()

# Sidebar: choose units for GDP display
unit_choice = st.sidebar.selectbox(
    'Select Unit',
    ('One', 'Two', 'Three', 'Four'),
    index=1,
)
_unit_map = {'One': 1e12, 'Two': 1e9, 'Three': 1e6, 'Four': 1}
unit_scale = _unit_map[unit_choice]
_suffix_map = {'One': 'T', 'Two': 'B', 'Three': 'M', 'Four': ''}

unit_suffix = _suffix_map[unit_choice]

# ----------------- Readiness Excel loader (no caching) -----------------
def load_readiness_from_excel(excel_path):
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
        overall_val = overall_df.iat[0, 0]

    # Parse key factors - expects columns: name, score, [trend], [color]
    kf_list = []
    if isinstance(kf_df, pd.DataFrame) and not kf_df.empty:
        for idx, (_, r) in enumerate(kf_df.iterrows()):
            try:
                name = str(r.iat[0])
                score = float(r.iat[1])
                trend = str(r.iat[2]) if len(r) > 2 else 'UNKNOWN'
                color = str(r.iat[3]) if len(r) > 3 else '#1f8f3f'
                kf_list.append((name, score, trend, color))
            except (ValueError, IndexError):
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
    loaded_overall, loaded_kf = load_readiness_from_excel(excel_path)

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
st.header(f'Overall Readiness: {readiness_score}/100')
st.progress(readiness_score / 100)

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
