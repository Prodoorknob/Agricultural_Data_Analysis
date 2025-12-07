"""
visuals.py - Plotly Visualization Functions for USDA Agricultural Dashboard

This module provides reusable Plotly figure generator functions for:
- Hex-tile map of US states
- State crop summary bar charts
- Time series / trend charts
- Diagnostic comparison charts

All functions return Plotly Figure objects that work both in Dash and Jupyter notebooks.
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import Dict, List, Optional, Tuple, Union

# ============================================================================
# HEX TILE MAP LAYOUT
# ============================================================================

# Hex tile layout for US states - positions each state in a grid
# Modeled after common tilegram layouts
HEX_LAYOUT = pd.DataFrame([
    # Row 0 (top)
    {'state_alpha': 'AK', 'state_name': 'Alaska', 'row': 0, 'col': 0},
    {'state_alpha': 'ME', 'state_name': 'Maine', 'row': 0, 'col': 10},
    
    # Row 1
    {'state_alpha': 'WA', 'state_name': 'Washington', 'row': 1, 'col': 1},
    {'state_alpha': 'MT', 'state_name': 'Montana', 'row': 1, 'col': 2},
    {'state_alpha': 'ND', 'state_name': 'North Dakota', 'row': 1, 'col': 3},
    {'state_alpha': 'MN', 'state_name': 'Minnesota', 'row': 1, 'col': 4},
    {'state_alpha': 'WI', 'state_name': 'Wisconsin', 'row': 1, 'col': 5},
    {'state_alpha': 'MI', 'state_name': 'Michigan', 'row': 1, 'col': 7},
    {'state_alpha': 'VT', 'state_name': 'Vermont', 'row': 1, 'col': 9},
    {'state_alpha': 'NH', 'state_name': 'New Hampshire', 'row': 1, 'col': 10},
    
    # Row 2
    {'state_alpha': 'OR', 'state_name': 'Oregon', 'row': 2, 'col': 1},
    {'state_alpha': 'ID', 'state_name': 'Idaho', 'row': 2, 'col': 2},
    {'state_alpha': 'WY', 'state_name': 'Wyoming', 'row': 2, 'col': 3},
    {'state_alpha': 'SD', 'state_name': 'South Dakota', 'row': 2, 'col': 4},
    {'state_alpha': 'IA', 'state_name': 'Iowa', 'row': 2, 'col': 5},
    {'state_alpha': 'IL', 'state_name': 'Illinois', 'row': 2, 'col': 6},
    {'state_alpha': 'IN', 'state_name': 'Indiana', 'row': 2, 'col': 7},
    {'state_alpha': 'OH', 'state_name': 'Ohio', 'row': 2, 'col': 8},
    {'state_alpha': 'NY', 'state_name': 'New York', 'row': 2, 'col': 9},
    {'state_alpha': 'MA', 'state_name': 'Massachusetts', 'row': 2, 'col': 10},
    
    # Row 3
    {'state_alpha': 'NV', 'state_name': 'Nevada', 'row': 3, 'col': 1},
    {'state_alpha': 'UT', 'state_name': 'Utah', 'row': 3, 'col': 2},
    {'state_alpha': 'CO', 'state_name': 'Colorado', 'row': 3, 'col': 3},
    {'state_alpha': 'NE', 'state_name': 'Nebraska', 'row': 3, 'col': 4},
    {'state_alpha': 'MO', 'state_name': 'Missouri', 'row': 3, 'col': 5},
    {'state_alpha': 'KY', 'state_name': 'Kentucky', 'row': 3, 'col': 6},
    {'state_alpha': 'WV', 'state_name': 'West Virginia', 'row': 3, 'col': 7},
    {'state_alpha': 'PA', 'state_name': 'Pennsylvania', 'row': 3, 'col': 8},
    {'state_alpha': 'NJ', 'state_name': 'New Jersey', 'row': 3, 'col': 9},
    {'state_alpha': 'CT', 'state_name': 'Connecticut', 'row': 3, 'col': 10},
    {'state_alpha': 'RI', 'state_name': 'Rhode Island', 'row': 3, 'col': 11},
    
    # Row 4
    {'state_alpha': 'CA', 'state_name': 'California', 'row': 4, 'col': 1},
    {'state_alpha': 'AZ', 'state_name': 'Arizona', 'row': 4, 'col': 2},
    {'state_alpha': 'NM', 'state_name': 'New Mexico', 'row': 4, 'col': 3},
    {'state_alpha': 'KS', 'state_name': 'Kansas', 'row': 4, 'col': 4},
    {'state_alpha': 'AR', 'state_name': 'Arkansas', 'row': 4, 'col': 5},
    {'state_alpha': 'TN', 'state_name': 'Tennessee', 'row': 4, 'col': 6},
    {'state_alpha': 'VA', 'state_name': 'Virginia', 'row': 4, 'col': 7},
    {'state_alpha': 'MD', 'state_name': 'Maryland', 'row': 4, 'col': 8},
    {'state_alpha': 'DE', 'state_name': 'Delaware', 'row': 4, 'col': 9},
    
    # Row 5
    {'state_alpha': 'HI', 'state_name': 'Hawaii', 'row': 5, 'col': 0},
    {'state_alpha': 'OK', 'state_name': 'Oklahoma', 'row': 5, 'col': 4},
    {'state_alpha': 'LA', 'state_name': 'Louisiana', 'row': 5, 'col': 5},
    {'state_alpha': 'MS', 'state_name': 'Mississippi', 'row': 5, 'col': 6},
    {'state_alpha': 'AL', 'state_name': 'Alabama', 'row': 5, 'col': 7},
    {'state_alpha': 'NC', 'state_name': 'North Carolina', 'row': 5, 'col': 8},
    {'state_alpha': 'SC', 'state_name': 'South Carolina', 'row': 5, 'col': 9},
    {'state_alpha': 'DC', 'state_name': 'District of Columbia', 'row': 5, 'col': 10},
    
    # Row 6 (bottom)
    {'state_alpha': 'TX', 'state_name': 'Texas', 'row': 6, 'col': 4},
    {'state_alpha': 'GA', 'state_name': 'Georgia', 'row': 6, 'col': 8},
    {'state_alpha': 'FL', 'state_name': 'Florida', 'row': 6, 'col': 9},
])

# Color scales for different measures
COLOR_SCALES = {
    'area': 'Tealgrn',
    'revenue': 'Viridis',
    'yield': 'Plasma',
    'operations': 'Blues',
    'urban': 'Oranges',
    'biotech': 'Purples',
    'default': 'Viridis'
}

# ============================================================================
# THEME AND STYLING - G1/G3: Centralized Segoe UI fonts and color scales
# ============================================================================

LAYOUT_TEMPLATE = {
    'plot_bgcolor': 'white',
    'paper_bgcolor': 'white',
    'font': {'family': 'Segoe UI, Arial, sans-serif', 'size': 12, 'color': '#333'},
    'margin': {'l': 60, 'r': 30, 't': 50, 'b': 50},
}

# Title font style (applied separately to avoid conflicts) - G1: Segoe UI
TITLE_FONT = {'size': 16, 'color': '#333', 'family': 'Segoe UI Semibold, Arial, sans-serif'}


def apply_theme(fig: go.Figure) -> go.Figure:
    """Apply consistent theme to a figure."""
    fig.update_layout(**LAYOUT_TEMPLATE)
    return fig


# ============================================================================
# HEX MAP VISUALIZATION
# ============================================================================

def hex_map_figure(
    data_df: pd.DataFrame,
    value_col: str,
    year: Optional[int] = None,
    selected_state: Optional[str] = None,
    color_scale: str = 'default',
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a hex-tile map of US states colored by a metric.
    
    Args:
        data_df: DataFrame with 'state_alpha' and the value column
        value_col: Column name to use for coloring
        year: If specified, filter to this year
        selected_state: State alpha code to highlight
        color_scale: Key for COLOR_SCALES or a Plotly colorscale name
        title: Optional title for the figure
        
    Returns:
        Plotly Figure object
    """
    # Start with hex layout
    hex_df = HEX_LAYOUT.copy()
    
    # Prepare data for merging
    if not data_df.empty:
        if year is not None and 'year' in data_df.columns:
            merge_data = data_df[data_df['year'] == year].copy()
        else:
            merge_data = data_df.copy()
        
        # Aggregate if there are duplicates
        if value_col in merge_data.columns:
            merge_data = merge_data.groupby('state_alpha').agg({
                value_col: 'sum'
            }).reset_index()
            
            # Merge with hex layout
            hex_df = hex_df.merge(merge_data[['state_alpha', value_col]], 
                                  on='state_alpha', how='left')
    else:
        # If no data, add empty value column for consistent display
        hex_df[value_col] = 0  # Use 0 instead of None for valid color mapping
    
    # Fill NaN values with 0 for valid color mapping
    if value_col in hex_df.columns:
        hex_df[value_col] = hex_df[value_col].fillna(0)
    
    # Get colorscale
    cscale = COLOR_SCALES.get(color_scale, color_scale)
    
    # Create figure
    fig = go.Figure()
    
    # Determine if we should show colorbar (only if we have actual data)
    has_data = bool(hex_df[value_col].sum() > 0)
    
    # Default color for states (when no data)
    default_color = '#7CB9E8'  # Light blue - more appealing than gray
    
    # Add hexagon markers for each state - sized to fit without overlap
    fig.add_trace(go.Scatter(
        x=hex_df['col'],
        y=-hex_df['row'],  # Invert y so row 0 is at top
        mode='markers+text',
        marker=dict(
            symbol='hexagon',
            size=55,  # Sized for compact display (reduced from 75 originally)
            color=hex_df[value_col] if has_data else [default_color] * len(hex_df),
            colorscale=cscale if has_data else None,
            colorbar=dict(
                title=value_col.replace('_', ' ').title(),
                thickness=15,
                len=0.8
            ) if has_data else None,
            line=dict(color='white', width=1),
            showscale=has_data
        ),
        text=hex_df['state_alpha'],
        textposition='middle center',
        textfont=dict(color='white', size=9, family='Segoe UI Semibold'),
        hovertemplate=(
            '<b>%{customdata[0]}</b><br>' +
            (f'{value_col}: ' + '%{customdata[1]:,.0f}<extra></extra>' if has_data 
             else 'Click to load data<extra></extra>')
        ),
        customdata=np.stack([hex_df['state_name'], hex_df[value_col]], axis=-1),
        name=''
    ))
    
    # Highlight selected state
    if selected_state:
        selected = hex_df[hex_df['state_alpha'] == selected_state]
        if not selected.empty:
            fig.add_trace(go.Scatter(
                x=selected['col'],
                y=-selected['row'],
                mode='markers',
                marker=dict(
                    symbol='hexagon',
                    size=60,  # Slightly larger for highlight (5 units larger than base)
                    color='rgba(0,0,0,0)',
                    line=dict(color='#FF6B6B', width=3)
                ),
                hoverinfo='skip',
                name='Selected'
            ))
    
    # Update layout - adjusted ranges for compact hex spacing
    fig.update_layout(
        title=dict(
            text=title or f'US States by {value_col.replace("_", " ").title()}',
            font=TITLE_FONT
        ),
        showlegend=False,
        xaxis=dict(
            showgrid=False, zeroline=False, showticklabels=False,
            range=[-0.3, 11.3], scaleanchor='y', scaleratio=0.9  # Tighter spacing
        ),
        yaxis=dict(
            showgrid=False, zeroline=False, showticklabels=False,
            range=[-6.5, 0.3]  # Reduced for more compact vertical spacing
        ),
        height=550,  # Reduced from 700 for more compact appearance
        **LAYOUT_TEMPLATE
    )
    
    return fig


# ============================================================================
# CHART 1: STATE CROP SUMMARY BAR CHART
# ============================================================================

# Patterns to exclude from aggregation (double-counting totals)
EXCLUDE_COMMODITIES = [
    'FIELD CROPS, TOTAL',
    'FIELD CROPS TOTAL', 
    'CROPS, TOTAL',
    'ALL COMMODITIES',
    'TOTAL'
]

def state_crop_bar_chart(
    data_df: pd.DataFrame,
    state_alpha: str,
    value_col: str = 'area_harvested_acres',
    year: Optional[int] = None,
    top_n: int = 10,  # Issue 2: Changed from 15 to 10
    title: Optional[str] = None,
    color_scale: str = 'Tealgrn'
) -> go.Figure:
    """
    Create a horizontal bar chart of top crops for a selected state.
    
    Args:
        data_df: DataFrame with state_alpha, commodity_desc, and value column
        state_alpha: State to filter to
        value_col: Column to use for bar values
        year: If specified, filter to this year
        top_n: Number of top crops to show
        title: Optional title
        color_scale: Plotly colorscale name
        
    Returns:
        Plotly Figure object
    """
    # Filter data
    df = data_df[data_df['state_alpha'] == state_alpha].copy()
    
    if year is not None and 'year' in df.columns:
        df = df[df['year'] == year]
    
    if df.empty or value_col not in df.columns:
        return _empty_figure(f"No data available for {state_alpha}")
    
    # Issue 1: Exclude total/aggregate commodities to avoid double-counting
    df = df[~df['commodity_desc'].str.upper().isin([x.upper() for x in EXCLUDE_COMMODITIES])]
    df = df[~df['commodity_desc'].str.contains('TOTAL', case=False, na=False)]
    
    # Aggregate by commodity
    agg_df = df.groupby('commodity_desc').agg({
        value_col: 'sum'
    }).reset_index()
    
    # Issue 2: Filter out zero values before getting top N
    agg_df = agg_df[agg_df[value_col] > 0]
    
    # Get top N
    agg_df = agg_df.nlargest(top_n, value_col)
    agg_df = agg_df.sort_values(value_col, ascending=True)
    
    # Compute percentage of total
    total = agg_df[value_col].sum()
    agg_df['pct_of_total'] = (agg_df[value_col] / total * 100).round(1)
    
    # Create figure
    fig = go.Figure()
    
    # Format values - normalize area to 100M acres base, show others as-is
    is_area_col = 'area' in value_col.lower() or 'acres' in value_col.lower()
    
    if is_area_col:
        # Normalize to 100M acres base for better percentage representation
        AREA_BASE = 100_000_000  # 100M acres
        display_values = agg_df[value_col] / AREA_BASE
        text_labels = [f'{v:.2f} ({p:.1f}%)' for v, p in zip(display_values, agg_df['pct_of_total'])]
        hover_template = '<b>%{y}</b><br>' + f'{value_col}: ' + '%{customdata:,.0f} acres<extra></extra>'
    else:
        text_labels = [f'{v:,.0f} ({p:.1f}%)' for v, p in zip(agg_df[value_col], agg_df['pct_of_total'])]
        hover_template = '<b>%{y}</b><br>' + f'{value_col}: ' + '%{x:,.0f}<extra></extra>'
    
    fig.add_trace(go.Bar(
        y=agg_df['commodity_desc'],
        x=display_values if is_area_col else agg_df[value_col],
        orientation='h',
        marker=dict(
            color=agg_df[value_col],  # Use original values for color scale
            colorscale=color_scale,
            showscale=False
        ),
        text=text_labels,
        textposition='outside',
        hovertemplate=hover_template,
        customdata=agg_df[value_col] if is_area_col else agg_df[value_col],  # Show actual acres in hover
        name=''
    ))
    
    # Get state name for title
    state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                 if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
    
    year_str = f' ({year})' if year else ''
    
    # Adjust x-axis title for area columns to show normalized units
    if is_area_col:
        x_title = f'{value_col.replace("_", " ").title()} (per 100M acres)'
    else:
        x_title = value_col.replace('_', ' ').title()
    
    fig.update_layout(
        title=dict(
            text=title or f'Top Crops in {state_name} by {value_col.replace("_", " ").title()}{year_str}',
            font=TITLE_FONT
        ),
        xaxis_title=x_title,
        yaxis_title='',
        height=max(300, top_n * 25 + 100),
        **LAYOUT_TEMPLATE
    )
    
    return fig


# ============================================================================
# CHART 2: TIME SERIES / TREND CHARTS
# ============================================================================

def area_trend_chart(
    data_df: pd.DataFrame,
    state_alpha: str,
    crops: Optional[List[str]] = None,
    top_n: int = 5,
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a line chart showing area harvested over time for top crops.
    
    Args:
        data_df: DataFrame with state_alpha, commodity_desc, year, area_harvested_acres
        state_alpha: State to filter to
        crops: List of specific crops to show (if None, uses top N)
        top_n: Number of top crops to show if crops is None
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    df = data_df[data_df['state_alpha'] == state_alpha].copy()
    
    if df.empty or 'area_harvested_acres' not in df.columns:
        return _empty_figure(f"No area data available for {state_alpha}")
    
    # Determine which crops to show
    if crops is None:
        # Get top N crops by total area
        top_crops = df.groupby('commodity_desc')['area_harvested_acres'].sum() \
                      .nlargest(top_n).index.tolist()
    else:
        top_crops = crops
    
    df = df[df['commodity_desc'].isin(top_crops)]
    
    # Sort by year to ensure continuous lines (fixes disjointed line issue)
    df = df.sort_values(['commodity_desc', 'year'])
    
    # Create figure
    fig = px.line(
        df,
        x='year',
        y='area_harvested_acres',
        color='commodity_desc',
        markers=True,
        labels={
            'year': 'Year',
            'area_harvested_acres': 'Area Harvested (acres)',
            'commodity_desc': 'Crop'
        }
    )
    
    state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                 if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
    
    fig.update_layout(
        title=dict(
            text=title or f'Area Harvested Over Time - {state_name}',
            font=TITLE_FONT
        ),
        legend_title='Crop',
        height=400,
        **LAYOUT_TEMPLATE
    )
    fig.update_traces(connectgaps=True)
    
    return fig


# Land use category mappings for aggregation into 4 main categories
LAND_USE_CATEGORIES = {
    'total_cropland': 'Cropland',
    'cropland_used_for_crops': 'Cropland',
    'cropland_used_for_pasture': 'Cropland',
    'cropland_idled': 'Cropland',
    'land_in_urban_areas': 'Urban Land',
    'forest_use_land_(all)': 'Forest Land',
    'grazed_forest_use_land_grazed': 'Forest Land',
    'ungrazed_forest_use_land': 'Forest Land',
    'grassland_pasture_and_range': 'Misc Land',
    'all_special_uses_of_land': 'Misc Land',
    'land_in_rural_transportation_facilities': 'Misc Land',
    'land_in_rural_parks_and_wildlife_areas': 'Misc Land',
    'land_in_defense_and_industrial_areas': 'Urban Land',
    'farmsteads,_roads,_and_miscellaneous_farmland': 'Misc Land',
    'miscellaneous_other_land': 'Misc Land',
}

# Color scheme for the 4 land use categories
LAND_USE_COLORS = {
    'Cropland': '#2E7D32',      # Green
    'Urban Land': '#E65100',     # Orange
    'Forest Land': '#1565C0',    # Blue
    'Misc Land': '#757575',      # Gray
}


def land_use_trend_chart(
    landuse_df: pd.DataFrame,
    state_alpha: str,
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a stacked area chart showing land use composition over time.
    Categorizes land into 4 main types: Cropland, Urban Land, Forest Land, Misc Land.
    E1: Includes vertical line at year of maximum urbanization rate.
    
    Args:
        landuse_df: Pivoted land use DataFrame
        state_alpha: State to filter to
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    df = landuse_df[landuse_df['state_alpha'] == state_alpha].copy()
    
    if df.empty:
        return _empty_figure(f"No land use data available for {state_alpha}")
    
    # Identify land use columns (exclude metadata and computed columns)
    exclude_cols = ['state_alpha', 'state_name', 'year', 'urban_share', 'cropland_share', 'total_land']
    land_cols = [c for c in df.columns if c not in exclude_cols]
    
    if not land_cols:
        return _empty_figure("No land use categories found")
    
    # Melt for grouping
    df_long = df.melt(
        id_vars=['year'],
        value_vars=land_cols,
        var_name='land_type_raw',
        value_name='acres'
    )
    
    # Map to 4 main categories
    df_long['land_category'] = df_long['land_type_raw'].map(LAND_USE_CATEGORIES)
    # Default unmapped to Misc Land
    df_long['land_category'] = df_long['land_category'].fillna('Misc Land')
    
    # Aggregate by year and category
    agg_df = df_long.groupby(['year', 'land_category'])['acres'].sum().reset_index()
    
    # Sort categories for consistent stacking order
    category_order = ['Cropland', 'Forest Land', 'Urban Land', 'Misc Land']
    agg_df['land_category'] = pd.Categorical(agg_df['land_category'], categories=category_order, ordered=True)
    agg_df = agg_df.sort_values(['year', 'land_category'])
    
    # Create area chart with custom colors
    fig = px.area(
        agg_df,
        x='year',
        y='acres',
        color='land_category',
        color_discrete_map=LAND_USE_COLORS,
        category_orders={'land_category': category_order},
        labels={'year': 'Year', 'acres': 'Acres (thousands)', 'land_category': 'Land Use Type'}
    )
    
    # E1 - Add vertical line at year of maximum urbanization rate
    urban_df = agg_df[agg_df['land_category'] == 'Urban Land'].copy()
    if not urban_df.empty and len(urban_df) > 1:
        urban_df = urban_df.sort_values('year')
        urban_df['urban_change'] = urban_df['acres'].diff()
        max_idx = urban_df['urban_change'].idxmax()
        if pd.notna(max_idx):
            max_urban_year = int(urban_df.loc[max_idx, 'year'])  # Convert to int explicitly
            fig.add_vline(
                x=max_urban_year,
                line_dash="dash",
                line_color="#E74C3C",
                annotation_text=f"Peak Urban Growth ({max_urban_year})",
                annotation_position="top right"
            )
    
    # Convert y-axis to thousands for readability
    fig.update_traces(hovertemplate='%{x}<br>%{y:,.0f} acres<extra>%{fullData.name}</extra>')
    
    state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                 if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
    
    fig.update_layout(
        title=dict(
            text=title or f'Land Use Over Time - {state_name}',
            font=TITLE_FONT
        ),
        legend_title='Land Type',
        height=400,
        **LAYOUT_TEMPLATE
    )
    
    return fig


def operations_trend_chart(
    data_df: pd.DataFrame,
    state_alpha: str,
    crops: Optional[List[str]] = None,
    top_n: int = 5,
    title: Optional[str] = None,
    farm_ops_df: Optional[pd.DataFrame] = None
) -> go.Figure:
    """
    Create a chart showing farm operations over time.
    Uses crop-level operations if available, otherwise shows total farm operations.
    
    Args:
        data_df: DataFrame with operations and ops_per_1k_acres columns
        state_alpha: State to filter to
        crops: List of specific crops
        top_n: Number of top crops if crops is None
        title: Optional title
        farm_ops_df: Optional DataFrame with total farm operations by state/year
        
    Returns:
        Plotly Figure object
    """
    df = data_df[data_df['state_alpha'] == state_alpha].copy()
    
    # Check if crop-level operations data exists
    has_crop_ops = 'operations' in df.columns and df['operations'].notna().sum() > 0
    
    # If no crop-level ops, try to use farm_ops_df for total operations
    if not has_crop_ops and farm_ops_df is not None and not farm_ops_df.empty:
        ops_state = farm_ops_df[farm_ops_df['state_alpha'] == state_alpha].copy()
        
        if not ops_state.empty:
            ops_state = ops_state.sort_values('year')
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=ops_state['year'],
                y=ops_state['total_operations'],
                mode='lines+markers',
                name='Total Farm Operations',
                line=dict(color='#2E86AB', width=3),
                marker=dict(size=8)
            ))
            
            state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                         if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
            
            fig.update_layout(
                title=dict(
                    text=title or f'Total Farm Operations - {state_name}',
                    font=TITLE_FONT
                ),
                xaxis_title='Year',
                yaxis_title='Number of Farm Operations',
                height=400,
                **LAYOUT_TEMPLATE
            )
            return fig
    
    # If still no data available
    if df.empty:
        return _empty_figure(f"No data available for {state_alpha}")
    
    if not has_crop_ops:
        return _empty_figure(
            "No operations data available for this state.\n"
            "Crop-level operations data is not present in\n"
            "the loaded NASS datasets."
        )
    
    # Use crop-level operations data
    if crops is None:
        top_crops = df.groupby('commodity_desc')['operations'].sum() \
                      .nlargest(top_n).index.tolist()
    else:
        top_crops = crops
    
    df = df[df['commodity_desc'].isin(top_crops)]
    
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    
    colors = px.colors.qualitative.Set2
    
    for i, crop in enumerate(top_crops):
        crop_df = df[df['commodity_desc'] == crop].sort_values('year')
        color = colors[i % len(colors)]
        
        fig.add_trace(
            go.Scatter(
                x=crop_df['year'],
                y=crop_df['operations'],
                name=f'{crop} (Operations)',
                line=dict(color=color),
                mode='lines+markers'
            ),
            secondary_y=False
        )
        
        if 'ops_per_1k_acres' in crop_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=crop_df['year'],
                    y=crop_df['ops_per_1k_acres'],
                    name=f'{crop} (Ops/1k acres)',
                    line=dict(color=color, dash='dash'),
                    mode='lines'
                ),
                secondary_y=True
            )
    
    state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                 if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
    
    fig.update_layout(
        title=dict(
            text=title or f'Farm Operations Over Time - {state_name}',
            font=TITLE_FONT
        ),
        height=400,
        **LAYOUT_TEMPLATE
    )
    fig.update_yaxes(title_text="Operations", secondary_y=False)
    fig.update_yaxes(title_text="Ops per 1,000 Acres", secondary_y=True)
    
    return fig



def revenue_trend_chart(
    data_df: pd.DataFrame,
    state_alpha: str,
    crops: Optional[List[str]] = None,
    top_n: int = 5,
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a line chart showing revenue over time for top crops.
    
    Args:
        data_df: DataFrame with revenue_usd column
        state_alpha: State to filter to
        crops: List of specific crops
        top_n: Number of top crops
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    df = data_df[data_df['state_alpha'] == state_alpha].copy()
    
    if df.empty or 'revenue_usd' not in df.columns:
        return _empty_figure(f"No revenue data available for {state_alpha}")
    
    # Determine crops
    if crops is None:
        top_crops = df.groupby('commodity_desc')['revenue_usd'].sum() \
                      .nlargest(top_n).index.tolist()
    else:
        top_crops = crops
    
    df = df[df['commodity_desc'].isin(top_crops)]
    
    # Sort by year to ensure continuous lines (fixes disjointed line issue)
    df = df.sort_values(['commodity_desc', 'year'])
    
    fig = px.line(
        df,
        x='year',
        y='revenue_usd',
        color='commodity_desc',
        markers=True,
        labels={
            'year': 'Year',
            'revenue_usd': 'Revenue (USD)',
            'commodity_desc': 'Crop'
        }
    )
    
    state_name = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == state_alpha]['state_name'].iloc[0] \
                 if state_alpha in HEX_LAYOUT['state_alpha'].values else state_alpha
    
    fig.update_layout(
        title=dict(
            text=title or f'Revenue Over Time - {state_name}',
            font=TITLE_FONT
        ),
        legend_title='Crop',
        height=400,
        **LAYOUT_TEMPLATE
    )
    fig.update_traces(connectgaps=True)
    
    # Add annotation for HAY in 2020 (COVID-19 supply chain disruptions)
    if 'HAY' in df['commodity_desc'].values and 2020 in df['year'].values:
        hay_2020 = df[(df['commodity_desc'] == 'HAY') & (df['year'] == 2020)]
        if not hay_2020.empty and 'revenue_usd' in hay_2020.columns:
            fig.add_annotation(
                x=2020,
                y=hay_2020['revenue_usd'].iloc[0],
                text="⚠ COVID-19<br>disruptions",
                showarrow=True,
                arrowhead=2,
                arrowsize=1,
                arrowwidth=2,
                arrowcolor="#ff6b6b",
                ax=-40,
                ay=-40,
                font=dict(size=10, color="#ff6b6b"),
                bgcolor="rgba(255,255,255,0.8)",
                bordercolor="#ff6b6b",
                borderwidth=1
            )
    
    return fig


# ============================================================================
# CHART 3: DIAGNOSTIC / COMPARISON CHARTS
# ============================================================================

def area_vs_urban_scatter(
    crop_df: pd.DataFrame,
    landuse_df: pd.DataFrame,
    state_alpha: Optional[str] = None,
    national_landuse_df: Optional[pd.DataFrame] = None,
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a scatter plot comparing change in cropland vs change in urban land.
    
    Args:
        crop_df: Crop data with area_harvested_acres (not used but kept for consistency)
        landuse_df: Land use data for selected state with cropland and urban land
        state_alpha: If specified, highlight this state
        national_landuse_df: Optional national-level land use data for all states
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    # Use national data if provided, otherwise fall back to landuse_df
    data_to_use = national_landuse_df if national_landuse_df is not None and not national_landuse_df.empty else landuse_df
    
    if data_to_use.empty:
        return _empty_figure("No land use data available")
    
    # Compute changes between earliest and latest year for each state
    years = data_to_use['year'].unique()
    if len(years) < 2:
        return _empty_figure("Need at least 2 years of data for comparison")
    
    early_year = min(years)
    late_year = max(years)
    
    # Check if data has state_alpha or state_name for grouping
    group_col = 'state_alpha' if 'state_alpha' in data_to_use.columns else 'state_name'
    
    early = data_to_use[data_to_use['year'] == early_year].set_index(group_col)
    late = data_to_use[data_to_use['year'] == late_year].set_index(group_col)
    
    # Calculate changes
    changes = pd.DataFrame()
    
    if 'total_cropland' in early.columns:
        changes['cropland_change'] = (late['total_cropland'] - early['total_cropland']) / early['total_cropland'] * 100
    
    if 'land_in_urban_areas' in early.columns:
        changes['urban_change'] = (late['land_in_urban_areas'] - early['land_in_urban_areas']) / early['land_in_urban_areas'] * 100
    
    changes = changes.reset_index()
    changes = changes.rename(columns={group_col: 'state_key'})
    
    # Merge with hex layout to get state_alpha and state_name
    if group_col == 'state_name':
        changes['state_name_upper'] = changes['state_key'].str.upper()
        hex_merge = HEX_LAYOUT.copy()
        hex_merge['state_name_upper'] = hex_merge['state_name'].str.upper()
        changes = changes.merge(hex_merge[['state_alpha', 'state_name', 'state_name_upper']], on='state_name_upper', how='left')
    else:
        changes = changes.merge(HEX_LAYOUT[['state_alpha', 'state_name']], left_on='state_key', right_on='state_alpha', how='left')
    
    if 'cropland_change' not in changes.columns or 'urban_change' not in changes.columns:
        return _empty_figure("Missing cropland or urban data")
    
    # E2 - Color by magnitude of cropland change (absolute value)
    changes['change_magnitude'] = changes['cropland_change'].abs()
    
    # Create scatter - colored by magnitude of change
    fig = px.scatter(
        changes,
        x='urban_change',
        y='cropland_change',
        color='change_magnitude',
        color_continuous_scale='Reds',
        hover_name='state_name',
        hover_data={'state_alpha': True, 'cropland_change': ':.1f', 'urban_change': ':.1f', 'change_magnitude': False},
        labels={
            'urban_change': f'Urban Land Change % ({early_year}-{late_year})',
            'cropland_change': f'Cropland Change % ({early_year}-{late_year})',
            'change_magnitude': 'Change Magnitude'
        }
    )
    
    fig.update_traces(
        marker=dict(size=12)
    )
    fig.update_coloraxes(colorbar_title='|Change %|')
    
    # Highlight selected state with larger marker
    if state_alpha and state_alpha in changes['state_alpha'].values:
        selected = changes[changes['state_alpha'] == state_alpha]
        fig.add_trace(go.Scatter(
            x=selected['urban_change'],
            y=selected['cropland_change'],
            mode='markers+text',
            marker=dict(size=20, color='#FF6B6B', symbol='circle-open', line=dict(width=3)),
            text=selected['state_alpha'],
            textposition='top center',
            textfont=dict(size=12, color='#FF6B6B', family='Arial Black'),
            name='Selected State',
            hoverinfo='skip'
        ))
    
    # Add shaded rectangle for area with highest cropland loss (negative change)
    # This highlights states where cropland shifted significantly
    cropland_min = changes['cropland_change'].min()
    if cropland_min < -5:  # Only add if there's significant loss
        # Find the threshold for bottom 20% of cropland change
        threshold = changes['cropland_change'].quantile(0.2)
        # Rectangle covering high urban growth + high cropland loss quadrant
        fig.add_shape(
            type='rect',
            x0=changes['urban_change'].quantile(0.6),  # High urban growth
            x1=changes['urban_change'].max() * 1.1,
            y0=threshold,
            y1=cropland_min * 1.1,
            fillcolor='rgba(255, 107, 107, 0.15)',
            line=dict(color='rgba(255, 107, 107, 0.5)', width=1, dash='dash'),
            layer='below'
        )
        # Add annotation for the shaded area
        # fig.add_annotation(
        #     x=changes['urban_change'].quantile(0.8),
        #     y=threshold,
        #     #text='High Shift Zone',
        #     showarrow=False,
        #     font=dict(size=10, color='#FF6B6B'),
        #     bgcolor='rgba(255,255,255,0.7)'
        # )
    
    # Add reference lines
    fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)
    fig.add_vline(x=0, line_dash="dash", line_color="gray", opacity=0.5)
    
    fig.update_layout(
        title=dict(
            text=title or f'Cropland vs Urban Land Change ({early_year}-{late_year})',
            font=TITLE_FONT
        ),
        height=450,
        # Fix legend overlap - position colorbar and legend separately
        coloraxis_colorbar=dict(
            title='|Change %|',
            x=1.0,
            y=0.5,
            len=0.5,
            thickness=15
        ),
        legend=dict(
            x=1.0,
            y=1.0,
            xanchor='left',
            yanchor='top',
            bgcolor='rgba(255,255,255,0.8)'
        ),
        **LAYOUT_TEMPLATE
    )
    
    return fig


# NOTE: revenue_vs_area_bubble removed per C2 requirements (replaced by boom_crops_chart for Economics view)


def labor_wage_trends(
    data_df: pd.DataFrame,
    labor_df: pd.DataFrame,
    state_alpha: Optional[str] = None,
    year: Optional[int] = None,
    national_labor_df: Optional[pd.DataFrame] = None,
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a line chart showing farm labor wage rate trends over time.
    Shows how agricultural wages have evolved by state, with option to
    highlight a specific state or compare top/bottom performers.
    
    Data Sources:
    - USDA NASS Farm Labor Survey (limited to CA, FL, HI after 2010)
    - BLS OEWS Agricultural Wages (all states, 2003-2024) - supplemental
    
    Args:
        data_df: Crop data (for context, not used directly)
        labor_df: Labor data for selected state with wage_rate, workers, year, data_source
        state_alpha: If specified, highlight this state and show comparison
        year: If specified, used for context but shows multi-year trend
        national_labor_df: Optional national-level labor data for all states
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    # Use national data if provided, otherwise fall back to labor_df
    data_to_use = national_labor_df if national_labor_df is not None and not national_labor_df.empty else labor_df
    
    # Check if labor data is available
    if data_to_use is None or data_to_use.empty:
        return _empty_figure(
            "Labor data not available.\n"
            "Please ensure the Economics dataset is loaded\n"
            "with LABOR commodity data."
        )
    
    df = data_to_use.copy()
    
    # Check for required columns
    if 'wage_rate' not in df.columns or 'year' not in df.columns:
        return _empty_figure(
            "Labor data missing required fields.\n"
            "Expected: wage_rate, year"
        )
    
    # Clean data - remove rows with NaN in key columns
    df = df.dropna(subset=['wage_rate', 'state_alpha', 'year'])
    
    if df.empty:
        return _empty_figure("No valid labor wage data after filtering")
    
    # Check data sources
    has_bls_data = 'data_source' in df.columns and (df['data_source'] == 'BLS_OEWS').any()
    has_nass_data = 'data_source' in df.columns and (df['data_source'] == 'USDA_NASS').any()
    
    # Merge with state names if not already present
    if 'state_name' not in df.columns or df['state_name'].isna().all():
        df = df.merge(HEX_LAYOUT[['state_alpha', 'state_name']], on='state_alpha', how='left')
    
    # Sort by year
    df = df.sort_values('year')
    
    # Identify states with good data coverage (5+ years of data)
    state_year_counts = df.groupby('state_alpha')['year'].nunique()
    well_covered_states = state_year_counts[state_year_counts >= 5].index.tolist()
    
    # With BLS data, most states should have good coverage now
    # Primary labor states with continuous USDA NASS coverage
    primary_labor_states = ['CA', 'FL', 'HI']
    
    # Calculate average wage by state across all years for ranking
    state_avg_wage = df.groupby('state_alpha')['wage_rate'].mean().sort_values(ascending=False)
    
    fig = go.Figure()
    subtitle = ""
    
    if state_alpha and state_alpha in df['state_alpha'].values:
        # Mode 1: Show selected state with comparison
        
        # Get selected state data
        selected_df = df[df['state_alpha'] == state_alpha]
        selected_name = selected_df['state_name'].iloc[0] if 'state_name' in selected_df.columns else state_alpha
        selected_years = sorted(selected_df['year'].unique())
        n_years = len(selected_years)
        
        # Check data source for selected state
        state_data_sources = selected_df['data_source'].unique() if 'data_source' in selected_df.columns else []
        
        # Check if selected state has limited data (only relevant if no BLS data)
        if n_years <= 3 and not has_bls_data:
            # Limited data - show a comparison with CA/FL/HI who have full coverage
            
            # Add annotation about limited data
            fig.add_annotation(
                text=f"⚠️ {state_alpha} has limited survey data ({selected_years[0]}-{selected_years[-1]})<br>"
                     f"Showing comparison with primary farm labor states (CA, FL, HI)",
                xref="paper", yref="paper",
                x=0.5, y=1.15,
                showarrow=False,
                font=dict(size=11, color='#666'),
                align='center'
            )
            
            # Plot primary labor states (CA, FL, HI) for reference
            colors = {'CA': '#2E8B57', 'FL': '#4169E1', 'HI': '#9370DB'}
            for state in primary_labor_states:
                if state in df['state_alpha'].values:
                    state_data = df[df['state_alpha'] == state]
                    state_name_full = state_data['state_name'].iloc[0] if not state_data.empty else state
                    fig.add_trace(go.Scatter(
                        x=state_data['year'],
                        y=state_data['wage_rate'],
                        mode='lines+markers',
                        line=dict(color=colors.get(state, '#888'), width=2),
                        marker=dict(size=5),
                        name=state,
                        hovertemplate=f'{state_name_full}<br>Year: %{{x}}<br>Wage: $%{{y:.2f}}/hr<extra></extra>'
                    ))
            
            # Plot selected state
            fig.add_trace(go.Scatter(
                x=selected_df['year'],
                y=selected_df['wage_rate'],
                mode='lines+markers',
                line=dict(color='#FF6B6B', width=4),
                marker=dict(size=12, symbol='circle'),
                name=f'{state_alpha} (Selected)',
                hovertemplate=f'{selected_name}<br>Year: %{{x}}<br>Wage: $%{{y:.2f}}/hr<extra></extra>'
            ))
            
            # Calculate average for selected state
            avg_wage = selected_df['wage_rate'].mean()
            subtitle = f'{selected_name}: Avg ${avg_wage:.2f}/hr ({selected_years[0]}-{selected_years[-1]}, {n_years} years of data)'
            chart_title = f'Farm Labor Wages: {selected_name}'
            
        else:
            # Good data coverage - show full comparison
            
            # Calculate national average by year (using all data)
            national_avg = df.groupby('year')['wage_rate'].mean().reset_index()
            
            # Plot other primary states faded
            for state in primary_labor_states:
                if state != state_alpha and state in df['state_alpha'].values:
                    state_data = df[df['state_alpha'] == state]
                    state_name_full = state_data['state_name'].iloc[0] if not state_data.empty else state
                    fig.add_trace(go.Scatter(
                        x=state_data['year'],
                        y=state_data['wage_rate'],
                        mode='lines+markers',
                        line=dict(color='rgba(100,149,237,0.5)', width=2, dash='dot'),
                        marker=dict(size=4),
                        name=state,
                        hovertemplate=f'{state_name_full}<br>Year: %{{x}}<br>Wage: $%{{y:.2f}}/hr<extra></extra>'
                    ))
            
            # Plot national average
            fig.add_trace(go.Scatter(
                x=national_avg['year'],
                y=national_avg['wage_rate'],
                mode='lines+markers',
                line=dict(color='#4682B4', width=3, dash='dash'),
                marker=dict(size=6, symbol='diamond'),
                name='National Avg',
                hovertemplate='National Average<br>Year: %{x}<br>Wage: $%{y:.2f}/hr<extra></extra>'
            ))
            
            # Plot selected state prominently
            fig.add_trace(go.Scatter(
                x=selected_df['year'],
                y=selected_df['wage_rate'],
                mode='lines+markers',
                line=dict(color='#FF6B6B', width=4),
                marker=dict(size=10, symbol='circle'),
                name=f'{state_alpha} (Selected)',
                hovertemplate=f'{selected_name}<br>Year: %{{x}}<br>Wage: $%{{y:.2f}}/hr<extra></extra>'
            ))
            
            # Calculate change for selected state
            first_year = selected_years[0]
            last_year = selected_years[-1]
            first_wage = selected_df[selected_df['year'] == first_year]['wage_rate'].iloc[0]
            last_wage = selected_df[selected_df['year'] == last_year]['wage_rate'].iloc[0]
            pct_change = ((last_wage - first_wage) / first_wage) * 100
            
            subtitle = f'{selected_name}: ${first_wage:.2f} → ${last_wage:.2f}/hr ({pct_change:+.1f}% since {first_year})'
            chart_title = f'Farm Labor Wage Trends: {selected_name}'
        
    else:
        # Mode 2: No state selected - show primary labor states comparison
        chart_title = 'Farm Labor Wage Trends by State'
        
        # Focus on states with good data coverage
        colors = {
            'CA': '#2E8B57',  # Green - California
            'FL': '#4169E1',  # Blue - Florida  
            'HI': '#9370DB',  # Purple - Hawaii
        }
        
        # Calculate national average
        national_avg = df.groupby('year')['wage_rate'].mean().reset_index()
        
        # Plot primary states
        for state in primary_labor_states:
            if state in df['state_alpha'].values:
                state_data = df[df['state_alpha'] == state]
                state_name = state_data['state_name'].iloc[0] if not state_data.empty else state
                fig.add_trace(go.Scatter(
                    x=state_data['year'],
                    y=state_data['wage_rate'],
                    mode='lines+markers',
                    line=dict(color=colors.get(state, '#888'), width=3),
                    marker=dict(size=7),
                    name=state_name,
                    hovertemplate=f'{state_name}<br>Year: %{{x}}<br>Wage: $%{{y:.2f}}/hr<extra></extra>'
                ))
        
        # Plot national average
        fig.add_trace(go.Scatter(
            x=national_avg['year'],
            y=national_avg['wage_rate'],
            mode='lines+markers',
            line=dict(color='#FF8C00', width=3, dash='dash'),
            marker=dict(size=6, symbol='diamond'),
            name='National Avg',
            hovertemplate='National Average<br>Year: %{x}<br>Wage: $%{y:.2f}/hr<extra></extra>'
        ))
        
        # Calculate overall change
        if len(national_avg) >= 2:
            first_wage = national_avg['wage_rate'].iloc[0]
            last_wage = national_avg['wage_rate'].iloc[-1]
            first_yr = int(national_avg['year'].iloc[0])
            last_yr = int(national_avg['year'].iloc[-1])
            pct_change = ((last_wage - first_wage) / first_wage) * 100
            subtitle = f'National avg: ${first_wage:.2f} → ${last_wage:.2f}/hr ({pct_change:+.1f}% from {first_yr}-{last_yr})'
    
    # Add data source annotation
    if has_bls_data:
        source_text = "Data: USDA NASS Farm Labor Survey + BLS Occupational Employment & Wage Statistics (OEWS)"
    else:
        source_text = "Data: USDA NASS Farm Labor Survey (limited state coverage after 2010)"
    
    fig.add_annotation(
        text=source_text,
        xref="paper", yref="paper",
        x=0.5, y=-0.18,  # Moved lower to avoid overlap with x-axis title
        showarrow=False,
        font=dict(size=9, color='#666'),
        align='center'
    )
    
    fig.update_layout(
        title=dict(
            text=f'{title or chart_title}<br><sub>{subtitle}</sub>' if subtitle else (title or chart_title),
            font=TITLE_FONT
        ),
        xaxis=dict(
            title='Year',
            tickmode='linear',
            dtick=2,
            tickformat='d'
        ),
        yaxis=dict(
            title='Wage Rate ($/hour)',
            tickprefix='$'
        ),
        legend=dict(
            orientation='v',
            yanchor='top',
            y=0.99,
            xanchor='left',
            x=1.02,
            font=dict(size=10)
        ),
        height=520,
        plot_bgcolor='white',
        paper_bgcolor='white',
        font={'family': 'Arial, sans-serif', 'size': 12, 'color': '#333'},
        margin={'l': 60, 'r': 120, 't': 80, 'b': 100}  # Extra bottom margin for annotation
    )
    
    return fig


def sector_comparison_chart(
    data_df: pd.DataFrame,
    year: Optional[int] = None,
    metric: str = 'area_harvested_acres',
    title: Optional[str] = None
) -> go.Figure:
    """
    Create a bar chart comparing crops vs livestock sectors.
    
    Args:
        data_df: DataFrame with sector_desc column
        year: If specified, filter to this year
        metric: Metric to compare
        title: Optional title
        
    Returns:
        Plotly Figure object
    """
    df = data_df.copy()
    
    if year is not None and 'year' in df.columns:
        df = df[df['year'] == year]
    
    if df.empty or 'sector_desc' not in df.columns:
        return _empty_figure("No sector data available")
    
    # Aggregate by sector
    agg_df = df.groupby('sector_desc').agg({
        metric: 'sum'
    }).reset_index()
    
    agg_df = agg_df.sort_values(metric, ascending=True)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        x=agg_df[metric],
        y=agg_df['sector_desc'],
        orientation='h',
        marker=dict(
            color=['#2E86AB', '#A23B72', '#F18F01', '#C73E1D'][:len(agg_df)],
        ),
        text=[f'{v:,.0f}' for v in agg_df[metric]],
        textposition='outside'
    ))
    
    year_str = f' ({year})' if year else ''
    fig.update_layout(
        title=dict(
            text=title or f'{metric.replace("_", " ").title()} by Sector{year_str}',
            font=TITLE_FONT
        ),
        xaxis_title=metric.replace('_', ' ').title(),
        yaxis_title='',
        height=300,
        **LAYOUT_TEMPLATE
    )
    
    return fig


def boom_crops_chart(
    data_df: pd.DataFrame,
    metric: str = 'area_harvested_acres',
    top_n: int = 10,
    title: Optional[str] = None,
    state_filter: Optional[str] = None,
    selected_crop: Optional[str] = None  # Issue 6: Add selected_crop parameter
) -> go.Figure:
    """
    Identify and show crops that have grown the most over time.
    
    Args:
        data_df: Crop data (state-level or national summary format)
        metric: Metric to use for measuring growth ('area_harvested_acres' or 'value_num')
        top_n: Number of top "boom" crops to show
        title: Optional title
        state_filter: Optional state alpha code to filter data (D2 enhancement)
        selected_crop: Optional crop to highlight (Issue 6)
        
    Returns:
        Plotly Figure object
    """
    # Check if this is national summary format (has 'value_num' and 'statisticcat_desc')
    is_national_format = 'value_num' in data_df.columns and 'statisticcat_desc' in data_df.columns
    
    if is_national_format:
        # Aggregate national data to get area_harvested_acres
        area_data = data_df[data_df['statisticcat_desc'] == 'AREA HARVESTED'].copy()
        area_data = area_data.groupby(['commodity_desc', 'year']).agg({
            'value_num': 'sum'
        }).reset_index()
        area_data = area_data.rename(columns={'value_num': 'area_harvested_acres'})
        data_df = area_data
        metric = 'area_harvested_acres'
    
    # D2 - Apply state filter if provided
    if state_filter and 'state_alpha' in data_df.columns:
        data_df = data_df[data_df['state_alpha'] == state_filter].copy()
        if data_df.empty:
            return _empty_figure(f"No data available for {state_filter}")
    
    # Issue 1 & 7: Exclude total/aggregate commodities to avoid double-counting
    data_df = data_df[~data_df['commodity_desc'].str.upper().isin([x.upper() for x in EXCLUDE_COMMODITIES])]
    data_df = data_df[~data_df['commodity_desc'].str.contains('TOTAL', case=False, na=False)]
    
    if metric not in data_df.columns:
        return _empty_figure(f"Metric {metric} not available")
    
    # Filter out zero/null values before analysis
    data_df = data_df[data_df[metric] > 0]
    
    # Get early and late periods
    years = sorted(data_df['year'].dropna().unique())
    if len(years) < 5:
        return _empty_figure("Need at least 5 years of data")
    
    early_years = years[:3]
    late_years = years[-3:]
    
    # Calculate average for each period
    early = data_df[data_df['year'].isin(early_years)].groupby('commodity_desc')[metric].mean()
    late = data_df[data_df['year'].isin(late_years)].groupby('commodity_desc')[metric].mean()
    
    # Calculate growth
    growth = pd.DataFrame({
        'early': early,
        'late': late
    })
    growth['pct_change'] = (growth['late'] - growth['early']) / growth['early'] * 100
    growth = growth.dropna()
    growth = growth[growth['early'] > 0]  # Avoid division issues
    
    # Filter out extreme growth rates (>500%) - likely data errors
    extreme_growth_threshold = 500.0
    extreme_crops = growth[growth['pct_change'] > extreme_growth_threshold].index.tolist()
    
    if extreme_crops:
        print(f"  Excluding {len(extreme_crops)} crops with extreme growth (>500%): {extreme_crops[:5]}...")
    
    # Keep only reasonable growth rates
    growth = growth[growth['pct_change'] <= extreme_growth_threshold]
    
    if growth.empty:
        return _empty_figure(f"No growth data available{' for ' + state_filter if state_filter else ''}")
    
    # Get top gainers
    top_gainers = growth.nlargest(top_n, 'pct_change').reset_index()
    top_gainers = top_gainers.sort_values('pct_change', ascending=True)
    
    fig = go.Figure()
    
    # Issue 6: Highlight selected crop with different color
    if selected_crop:
        colors = [
            "#EEC40B" if crop == selected_crop else ('#2ECC71' if x > 0 else '#E74C3C')
            for crop, x in zip(top_gainers['commodity_desc'], top_gainers['pct_change'])
        ]
    else:
        colors = ['#2ECC71' if x > 0 else '#E74C3C' for x in top_gainers['pct_change']]
    
    fig.add_trace(go.Bar(
        x=top_gainers['pct_change'],
        y=top_gainers['commodity_desc'],
        orientation='h',
        marker=dict(color=colors),
        text=[f'{v:+.1f}%' for v in top_gainers['pct_change']],
        textposition='outside'
    ))
    
    fig.add_vline(x=0, line_dash="solid", line_color="gray")
    
    period = f"{min(early_years)}-{max(early_years)} to {min(late_years)}-{max(late_years)}"
    fig.update_layout(
        title=dict(
            text=title or f'Top {top_n} "Boom" Crops by {metric.replace("_", " ").title()} Growth ({period})',
            font=TITLE_FONT
        ),
        xaxis_title='Percent Change',
        yaxis_title='',
        height=max(300, top_n * 30 + 100),
        **LAYOUT_TEMPLATE
    )
    
    # Add annotation if extreme growth crops were excluded
    if extreme_crops:
        annotation_text = f"⚠ {len(extreme_crops)} crop(s) excluded due to extreme growth (>500%):<br>"
        annotation_text += "<br>".join([f"• {crop[:30]}" for crop in extreme_crops[:3]])
        if len(extreme_crops) > 3:
            annotation_text += f"<br>• ...and {len(extreme_crops) - 3} more"
        annotation_text += "<br><i>These require further investigation</i>"
        
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.98, y=0.02,
            text=annotation_text,
            showarrow=False,
            font=dict(size=9, color="#ff6b6b"),
            bgcolor="rgba(255,235,235,0.9)",
            bordercolor="#ff6b6b",
            borderwidth=1,
            align="left",
            xanchor="right",
            yanchor="bottom"
        )
    
    return fig


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _empty_figure(message: str = "No data available") -> go.Figure:
    """Create an empty figure with a message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=16, color="gray")
    )
    fig.update_layout(
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        height=300,
        **LAYOUT_TEMPLATE
    )
    return fig


def get_chart_for_view(
    view_mode: str,
    chart_position: int,
    data: dict,
    state_alpha: Optional[str] = None,
    crop: Optional[str] = None,
    year: Optional[int] = None,
    measure: Optional[str] = None
) -> go.Figure:
    """
    Get the appropriate chart based on view mode and position.
    
    Args:
        view_mode: One of 'Overview', 'Land & Area', 'Labor & Operations', 
                   'Economics & Profitability'
        chart_position: 1, 2, or 3
        data: Dictionary of DataFrames from data_prep
        state_alpha: Selected state
        crop: Selected crop
        year: Selected year
        measure: Selected measure
        
    Returns:
        Plotly Figure object
    """
    state_crop_df = data.get('state_crop_year', pd.DataFrame())
    landuse_df = data.get('landuse', pd.DataFrame())
    
    if state_alpha is None:
        state_alpha = 'IA'  # Default to Iowa
    
    if view_mode == 'Overview':
        if chart_position == 1:
            return state_crop_bar_chart(state_crop_df, state_alpha, 'area_harvested_acres', year)
        elif chart_position == 2:
            return area_trend_chart(state_crop_df, state_alpha)
        else:
            return boom_crops_chart(state_crop_df, 'area_harvested_acres')
    
    elif view_mode == 'Land & Area':
        if chart_position == 1:
            return state_crop_bar_chart(state_crop_df, state_alpha, 'area_harvested_acres', year)
        elif chart_position == 2:
            return land_use_trend_chart(landuse_df, state_alpha)
        else:
            return area_vs_urban_scatter(state_crop_df, landuse_df, state_alpha)
    
    elif view_mode == 'Labor & Operations':
        if chart_position == 1:
            return state_crop_bar_chart(state_crop_df, state_alpha, 'operations', year)
        elif chart_position == 2:
            return operations_trend_chart(state_crop_df, state_alpha)
        else:
            return labor_intensity_scatter(state_crop_df, pd.DataFrame(), state_alpha, year)
    
    elif view_mode == 'Economics & Profitability':
        if chart_position == 1:
            return state_crop_bar_chart(state_crop_df, state_alpha, 'revenue_usd', year)
        elif chart_position == 2:
            return revenue_trend_chart(state_crop_df, state_alpha)
        else:
            # C2 - Use boom_crops_chart with revenue metric
            return boom_crops_chart(state_crop_df, 'revenue_usd')
    
    # NOTE: Yield & Technology view removed per B1 requirements
    
    return _empty_figure("Unknown view mode")


# ============================================================================
# MAIN - For testing
# ============================================================================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, '.')
    from data_prep import load_sample_data
    
    print("Loading sample data...")
    data = load_sample_data()
    
    print("\nGenerating sample figures...")
    
    # Test hex map
    if 'state_crop_year' in data and not data['state_crop_year'].empty:
        state_totals = data['state_crop_year'].groupby(['state_alpha', 'year'])['area_harvested_acres'].sum().reset_index()
        fig = hex_map_figure(state_totals, 'area_harvested_acres', year=2020, selected_state='IA')
        fig.show()
        
        # Test bar chart
        fig2 = state_crop_bar_chart(data['state_crop_year'], 'IA', 'area_harvested_acres', 2020)
        fig2.show()
