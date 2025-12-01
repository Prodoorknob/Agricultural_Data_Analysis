"""
app.py - Plotly Dash Application for USDA Agricultural Dashboard

This module creates a complete Dash web application with:
- Hex-tile map of US states
- Interactive filters (Year, Sector, Measure, View Mode)
- Drill-down from state to crop level
- Multiple view modes for different analysis perspectives

To run locally:
    python app.py

For Jupyter/Colab:
    from app import create_app
    app = create_app()
    app.run_server(mode='inline')  # or mode='external'
"""

import os
import sys

# Ensure we can import from the same directory
sys.path.insert(0, os.path.dirname(__file__))

from dash import Dash, html, dcc, callback, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd

# Import our modules
from data_prep import (
    prepare_all_data, 
    get_available_years, 
    get_available_crops, 
    get_available_states,
    load_sample_data
)
from visuals import (
    hex_map_figure,
    state_crop_bar_chart,
    area_trend_chart,
    land_use_trend_chart,
    operations_trend_chart,
    yield_biotech_trend_chart,
    revenue_trend_chart,
    area_vs_urban_scatter,
    revenue_vs_area_bubble,
    labor_wage_trends,
    yield_vs_biotech_scatter,
    sector_comparison_chart,
    boom_crops_chart,
    get_chart_for_view,
    HEX_LAYOUT
)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Set to True for faster loading during development
USE_SAMPLE_DATA = True

# Measure options for dropdown
MEASURE_OPTIONS = [
    {'label': 'Area Harvested (acres)', 'value': 'area_harvested_acres'},
    {'label': 'Area Planted (acres)', 'value': 'area_planted_acres'},
    {'label': 'Revenue (USD)', 'value': 'revenue_usd'},
    {'label': 'Yield per Acre', 'value': 'yield_per_acre'},
    {'label': 'Operations', 'value': 'operations'},
    {'label': 'Ops per 1,000 Acres', 'value': 'ops_per_1k_acres'},
]

# Sector options
SECTOR_OPTIONS = [
    {'label': 'All Sectors', 'value': 'ALL'},
    {'label': 'Crops', 'value': 'CROPS'},
    {'label': 'Animals & Products', 'value': 'ANIMALS & PRODUCTS'},
    {'label': 'Economics', 'value': 'ECONOMICS'},
]

# View mode options
VIEW_MODE_OPTIONS = [
    {'label': 'Overview', 'value': 'Overview'},
    {'label': 'Land & Area', 'value': 'Land & Area'},
    {'label': 'Labor & Operations', 'value': 'Labor & Operations'},
    {'label': 'Economics & Profitability', 'value': 'Economics & Profitability'},
    {'label': 'Yield & Technology', 'value': 'Yield & Technology'},
]

# ============================================================================
# STYLES
# ============================================================================

SIDEBAR_STYLE = {
    'position': 'fixed',
    'top': 0,
    'left': 0,
    'bottom': 0,
    'width': '280px',
    'padding': '20px',
    'background-color': '#f8f9fa',
    'overflow-y': 'auto',
    'border-right': '1px solid #e0e0e0'
}

CONTENT_STYLE = {
    'margin-left': '300px',
    'padding': '20px',
    'background-color': 'white'
}

CARD_STYLE = {
    'margin-bottom': '15px',
    'border-radius': '8px',
    'box-shadow': '0 2px 4px rgba(0,0,0,0.1)'
}

DROPDOWN_STYLE = {
    'margin-bottom': '15px'
}

# ============================================================================
# APP CREATION
# ============================================================================

def create_app(use_sample: bool = USE_SAMPLE_DATA) -> Dash:
    """
    Create and configure the Dash application.
    
    Args:
        use_sample: If True, load only sample data for faster startup
        
    Returns:
        Configured Dash application
    """
    # Initialize Dash app with Bootstrap theme
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True
    )
    
    # Load data
    print("Loading data...")
    if use_sample:
        data = load_sample_data()
    else:
        data = prepare_all_data(sample_frac=None, nass_files=['commodities', 'field_crops'])
    
    # Get available years
    years = []
    if 'state_crop_year' in data and not data['state_crop_year'].empty:
        years = get_available_years(data['state_crop_year'])
    
    year_options = [{'label': 'All Years', 'value': 'ALL'}] + \
                   [{'label': str(y), 'value': y} for y in years]
    
    # Get available crops
    crops = []
    if 'state_crop_year' in data and not data['state_crop_year'].empty:
        crops = get_available_crops(data['state_crop_year'])
    
    crop_options = [{'label': 'All Crops', 'value': 'ALL'}] + \
                   [{'label': c, 'value': c} for c in crops[:50]]  # Limit for performance
    
    # Store data in app for access in callbacks
    app.data = data
    
    # ========================================================================
    # LAYOUT
    # ========================================================================
    
    sidebar = html.Div([
        html.H4("🌾 USDA Dashboard", className="mb-4"),
        html.Hr(),
        
        # Year filter
        html.Label("Year", className="fw-bold"),
        dcc.Dropdown(
            id='year-select',
            options=year_options,
            value='ALL' if not years else years[-1],
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        # Sector filter
        html.Label("Sector", className="fw-bold"),
        dcc.Dropdown(
            id='sector-select',
            options=SECTOR_OPTIONS,
            value='ALL',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        # Measure filter
        html.Label("Measure", className="fw-bold"),
        dcc.Dropdown(
            id='measure-select',
            options=MEASURE_OPTIONS,
            value='area_harvested_acres',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Hr(),
        
        # View mode tabs
        html.Label("View Mode", className="fw-bold"),
        dcc.RadioItems(
            id='viewmode-tabs',
            options=VIEW_MODE_OPTIONS,
            value='Overview',
            labelStyle={'display': 'block', 'margin-bottom': '8px'},
            inputStyle={'margin-right': '8px'}
        ),
        
        html.Hr(),
        
        # Crop search
        html.Label("Jump to Crop", className="fw-bold"),
        dcc.Dropdown(
            id='crop-search',
            options=crop_options,
            value=None,
            placeholder="Search crops...",
            style=DROPDOWN_STYLE
        ),
        
        html.Hr(),
        
        # Selection info
        html.Div(id='selection-info', className="mt-3 p-2 bg-light rounded")
        
    ], style=SIDEBAR_STYLE)
    
    content = html.Div([
        # Header
        html.Div([
            html.H3("US Agricultural Overview", id="page-title"),
            html.P("Click on a state to see detailed crop information", 
                   className="text-muted", id="page-subtitle")
        ], className="mb-4"),
        
        # Hex Map
        dbc.Card([
            dbc.CardBody([
                dcc.Graph(id='hex-map', config={'displayModeBar': False})
            ])
        ], style=CARD_STYLE),
        
        # Charts row
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("State Crop Summary", id="chart-1-header"),
                    dbc.CardBody([
                        dcc.Graph(id='chart-1', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=12)
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Trends Over Time", id="chart-2-header"),
                    dbc.CardBody([
                        dcc.Graph(id='chart-2', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=6),
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("Diagnostic View", id="chart-3-header"),
                    dbc.CardBody([
                        dcc.Graph(id='chart-3', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=6)
        ]),
        
        # Hidden stores for state management
        dcc.Store(id='selected-state', data=None),
        dcc.Store(id='selected-crop', data=None)
        
    ], style=CONTENT_STYLE)
    
    app.layout = html.Div([sidebar, content])
    
    # ========================================================================
    # CALLBACKS
    # ========================================================================
    
    @app.callback(
        Output('hex-map', 'figure'),
        [Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('measure-select', 'value'),
         Input('selected-state', 'data')]
    )
    def update_hex_map(year, sector, measure, selected_state):
        """Update the hex map based on filters."""
        df = app.data.get('state_crop_year', pd.DataFrame())
        
        if df.empty:
            return _empty_fig("No data loaded")
        
        # Filter by year
        if year != 'ALL':
            df = df[df['year'] == year]
        
        # Filter by sector
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        
        # Check if measure exists
        if measure not in df.columns:
            measure = 'area_harvested_acres'
        
        # Aggregate to state level
        state_totals = df.groupby('state_alpha').agg({
            measure: 'sum'
        }).reset_index()
        
        # Determine color scale based on measure
        if 'area' in measure:
            cscale = 'Tealgrn'
        elif 'revenue' in measure or 'price' in measure:
            cscale = 'Viridis'
        elif 'yield' in measure:
            cscale = 'Plasma'
        else:
            cscale = 'Blues'
        
        year_str = f" ({year})" if year != 'ALL' else ""
        title = f"US States by {measure.replace('_', ' ').title()}{year_str}"
        
        return hex_map_figure(
            state_totals, 
            measure, 
            selected_state=selected_state,
            color_scale=cscale,
            title=title
        )
    
    @app.callback(
        Output('selected-state', 'data'),
        [Input('hex-map', 'clickData')],
        [State('selected-state', 'data')]
    )
    def update_selected_state(click_data, current_state):
        """Update selected state when hex map is clicked."""
        if click_data is None:
            return current_state
        
        # Extract state from click data
        try:
            point = click_data['points'][0]
            if 'customdata' in point:
                # Get state name, look up alpha
                state_name = point['customdata'][0]
                state_row = HEX_LAYOUT[HEX_LAYOUT['state_name'] == state_name]
                if not state_row.empty:
                    return state_row['state_alpha'].iloc[0]
            elif 'text' in point:
                # Text contains state alpha
                return point['text']
        except (KeyError, IndexError):
            pass
        
        return current_state
    
    @app.callback(
        Output('selected-crop', 'data'),
        [Input('chart-1', 'clickData'),
         Input('crop-search', 'value')],
        [State('selected-crop', 'data')]
    )
    def update_selected_crop(click_data, crop_search, current_crop):
        """Update selected crop when bar chart is clicked or crop is searched."""
        from dash import ctx
        
        triggered_id = ctx.triggered_id
        
        if triggered_id == 'crop-search' and crop_search and crop_search != 'ALL':
            return crop_search
        
        if triggered_id == 'chart-1' and click_data:
            try:
                return click_data['points'][0]['y']
            except (KeyError, IndexError):
                pass
        
        return current_crop
    
    @app.callback(
        Output('chart-1', 'figure'),
        [Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('measure-select', 'value'),
         Input('selected-state', 'data'),
         Input('viewmode-tabs', 'value')]
    )
    def update_chart_1(year, sector, measure, selected_state, view_mode):
        """Update Chart 1 - State crop summary."""
        df = app.data.get('state_crop_year', pd.DataFrame())
        
        if df.empty:
            return _empty_fig("No data loaded")
        
        if selected_state is None:
            return _empty_fig("Click a state on the map to see details")
        
        # Filter by sector
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        
        # Determine measure based on view mode
        if view_mode == 'Labor & Operations':
            measure = 'operations'
        elif view_mode == 'Economics & Profitability':
            measure = 'revenue_usd'
        elif view_mode == 'Yield & Technology':
            measure = 'yield_per_acre'
        
        if measure not in df.columns:
            measure = 'area_harvested_acres'
        
        year_val = None if year == 'ALL' else year
        
        return state_crop_bar_chart(df, selected_state, measure, year_val)
    
    @app.callback(
        Output('chart-2', 'figure'),
        [Input('selected-state', 'data'),
         Input('selected-crop', 'data'),
         Input('viewmode-tabs', 'value')]
    )
    def update_chart_2(selected_state, selected_crop, view_mode):
        """Update Chart 2 - Trend chart."""
        df = app.data.get('state_crop_year', pd.DataFrame())
        landuse_df = app.data.get('landuse', pd.DataFrame())
        biotech_df = app.data.get('biotech', pd.DataFrame())
        farm_ops_df = app.data.get('farm_operations', pd.DataFrame())
        
        if selected_state is None:
            return _empty_fig("Select a state to see trends")
        
        if view_mode == 'Overview':
            return area_trend_chart(df, selected_state)
        
        elif view_mode == 'Land & Area':
            if not landuse_df.empty:
                return land_use_trend_chart(landuse_df, selected_state)
            return area_trend_chart(df, selected_state)
        
        elif view_mode == 'Labor & Operations':
            return operations_trend_chart(df, selected_state, farm_ops_df=farm_ops_df)
        
        elif view_mode == 'Economics & Profitability':
            return revenue_trend_chart(df, selected_state)
        
        elif view_mode == 'Yield & Technology':
            crop = selected_crop if selected_crop in ['CORN', 'SOYBEANS', 'COTTON'] else 'CORN'
            return yield_biotech_trend_chart(df, biotech_df, selected_state, crop)
        
        return _empty_fig("Select a view mode")
    
    @app.callback(
        Output('chart-3', 'figure'),
        [Input('year-select', 'value'),
         Input('selected-state', 'data'),
         Input('selected-crop', 'data'),
         Input('viewmode-tabs', 'value')]
    )
    def update_chart_3(year, selected_state, selected_crop, view_mode):
        """Update Chart 3 - Diagnostic/comparison chart."""
        df = app.data.get('state_crop_year', pd.DataFrame())
        landuse_df = app.data.get('landuse', pd.DataFrame())
        biotech_df = app.data.get('biotech', pd.DataFrame())
        labor_df = app.data.get('labor', pd.DataFrame())
        
        year_val = None if year == 'ALL' else year
        
        if view_mode == 'Overview':
            return boom_crops_chart(df, 'area_harvested_acres')
        
        elif view_mode == 'Land & Area':
            return area_vs_urban_scatter(df, landuse_df, selected_state)
        
        elif view_mode == 'Labor & Operations':
            # Show wage trends over time (more insightful than single-year scatter)
            return labor_wage_trends(df, labor_df, selected_state, year_val)
        
        elif view_mode == 'Economics & Profitability':
            if selected_state:
                return revenue_vs_area_bubble(df, selected_state, year_val)
            return sector_comparison_chart(df, year_val, 'revenue_usd')
        
        elif view_mode == 'Yield & Technology':
            return yield_vs_biotech_scatter(df, biotech_df, 'CORN')
        
        return _empty_fig("Select a view mode")
    
    @app.callback(
        Output('selection-info', 'children'),
        [Input('selected-state', 'data'),
         Input('selected-crop', 'data')]
    )
    def update_selection_info(selected_state, selected_crop):
        """Update the selection info panel."""
        parts = []
        
        if selected_state:
            state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
            state_name = state_row['state_name'].iloc[0] if not state_row.empty else selected_state
            parts.append(html.Div([
                html.Strong("State: "),
                html.Span(f"{state_name} ({selected_state})")
            ]))
        
        if selected_crop:
            parts.append(html.Div([
                html.Strong("Crop: "),
                html.Span(selected_crop)
            ], className="mt-1"))
        
        if not parts:
            return html.Span("No selection", className="text-muted")
        
        return parts
    
    @app.callback(
        [Output('page-title', 'children'),
         Output('chart-1-header', 'children'),
         Output('chart-2-header', 'children'),
         Output('chart-3-header', 'children')],
        [Input('viewmode-tabs', 'value'),
         Input('selected-state', 'data')]
    )
    def update_headers(view_mode, selected_state):
        """Update page and chart headers based on view mode."""
        state_str = ""
        if selected_state:
            state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
            if not state_row.empty:
                state_str = f" - {state_row['state_name'].iloc[0]}"
        
        headers = {
            'Overview': (
                f"US Agricultural Overview{state_str}",
                "Top Crops by Area",
                "Area Trends Over Time",
                "Fastest Growing Crops"
            ),
            'Land & Area': (
                f"Land & Area Analysis{state_str}",
                "Crops by Area Harvested",
                "Land Use Composition",
                "Cropland vs Urban Change"
            ),
            'Labor & Operations': (
                f"Labor & Operations{state_str}",
                "Crops by Number of Operations",
                "Operations Trends",
                "Labor Intensity by Crop"
            ),
            'Economics & Profitability': (
                f"Economics & Profitability{state_str}",
                "Crops by Revenue",
                "Revenue Trends",
                "Revenue vs Area"
            ),
            'Yield & Technology': (
                f"Yield & Technology{state_str}",
                "Crops by Yield",
                "Yield & Biotech Adoption",
                "Yield vs GE Adoption (All States)"
            )
        }
        
        return headers.get(view_mode, headers['Overview'])
    
    return app


def _empty_fig(message: str) -> go.Figure:
    """Create an empty placeholder figure."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        xref="paper", yref="paper",
        x=0.5, y=0.5,
        showarrow=False,
        font=dict(size=14, color="gray")
    )
    fig.update_layout(
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        height=300,
        plot_bgcolor='white',
        paper_bgcolor='white'
    )
    return fig


# ============================================================================
# COLAB/JUPYTER SUPPORT
# ============================================================================

def run_in_notebook(port: int = 8050, mode: str = 'inline'):
    """
    Run the app in a Jupyter notebook or Google Colab.
    
    Args:
        port: Port number for the server
        mode: 'inline', 'external', or 'jupyterlab'
    """
    app = create_app()
    
    # Check if running in Colab
    try:
        from google.colab import output
        output.serve_kernel_port_as_window(port)
        app.run_server(port=port, debug=False)
    except ImportError:
        # Running in Jupyter
        app.run_server(mode=mode, port=port, debug=False)


def get_figures_for_notebook(
    state_alpha: str = 'IA',
    year: int = 2020,
    use_sample: bool = True
):
    """
    Get all dashboard figures for use in a Jupyter notebook.
    
    Args:
        state_alpha: State to focus on
        year: Year to use for single-year visualizations
        use_sample: Whether to use sample data
        
    Returns:
        Dictionary of Plotly figures
    """
    if use_sample:
        data = load_sample_data()
    else:
        data = prepare_all_data()
    
    df = data.get('state_crop_year', pd.DataFrame())
    landuse = data.get('landuse', pd.DataFrame())
    biotech = data.get('biotech', pd.DataFrame())
    
    if df.empty:
        print("Warning: No data loaded")
        return {}
    
    # Aggregate for hex map
    state_totals = df.groupby('state_alpha')['area_harvested_acres'].sum().reset_index()
    
    figures = {
        'hex_map': hex_map_figure(state_totals, 'area_harvested_acres', 
                                   selected_state=state_alpha, title="US States by Area Harvested"),
        'crop_bar': state_crop_bar_chart(df, state_alpha, 'area_harvested_acres', year),
        'area_trend': area_trend_chart(df, state_alpha),
        'revenue_trend': revenue_trend_chart(df, state_alpha),
        'boom_crops': boom_crops_chart(df, 'area_harvested_acres'),
    }
    
    if not landuse.empty:
        figures['land_use'] = land_use_trend_chart(landuse, state_alpha)
        figures['urban_scatter'] = area_vs_urban_scatter(df, landuse, state_alpha)
    
    if not biotech.empty:
        figures['yield_biotech'] = yield_biotech_trend_chart(df, biotech, state_alpha, 'CORN')
        figures['biotech_scatter'] = yield_vs_biotech_scatter(df, biotech, 'CORN')
    
    return figures


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    app = create_app(use_sample=USE_SAMPLE_DATA)
    print("\n" + "=" * 60)
    print("Starting USDA Agricultural Dashboard")
    print("=" * 60)
    print("Open your browser to: http://127.0.0.1:8050")
    print("Press Ctrl+C to stop the server")
    print("=" * 60 + "\n")
    app.run_server(debug=True)
