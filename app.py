import os
import sys

# Ensure current directory is first in path to avoid importing from subdirectories
current_dir = os.path.abspath(os.path.dirname(__file__))
if current_dir in sys.path:
    sys.path.remove(current_dir)
sys.path.insert(0, current_dir)

from matplotlib import colors
from dash import Dash, html, dcc, callback, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
from data_prep import (
    prepare_all_data, 
    get_available_years, 
    get_available_crops, 
    get_available_states,
    load_state_data,
    process_state_data,
    load_national_labor_summary,
    load_national_landuse_summary,
    load_national_crops_summary
)
from visuals import (
    hex_map_figure,
    state_crop_bar_chart,
    area_trend_chart,
    land_use_trend_chart,
    operations_trend_chart,
    revenue_trend_chart,
    area_vs_urban_scatter,
    labor_wage_trends,
    sector_comparison_chart,
    boom_crops_chart,
    get_chart_for_view,
    HEX_LAYOUT,
    COLOR_SCALES
)


# Dropdown Data Options
# Measure options for dropdown
MEASURE_OPTIONS = [
    {'label': 'Area Harvested (acres)', 'value': 'area_harvested_acres'},
    {'label': 'Area Planted (acres)', 'value': 'area_planted_acres'},
    {'label': 'Revenue (USD)', 'value': 'revenue_usd'},
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

# Crop group options (for filtering within CROPS sector)
CROP_GROUP_OPTIONS = [
    {'label': 'All Crop Groups', 'value': 'ALL'},
    {'label': 'Field Crops', 'value': 'FIELD CROPS'},
    {'label': 'Vegetables', 'value': 'VEGETABLES'},
    {'label': 'Fruit & Tree Nuts', 'value': 'FRUIT & TREE NUTS'},
    {'label': 'Horticulture', 'value': 'HORTICULTURE'},
]

# View mode options - B1: Removed Yield & Technology
VIEW_MODE_OPTIONS = [
    {'label': 'Overview', 'value': 'Overview'},
    {'label': 'Land & Area', 'value': 'Land & Area'},
    {'label': 'Labor & Operations', 'value': 'Labor & Operations'},
    {'label': 'Economics & Profitability', 'value': 'Economics & Profitability'},
]

# App design

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

# App design

def create_app():
    # Initialize Dash app with Bootstrap theme
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True
    )
    
    # Expose server for WSGI (gunicorn)
    server = app.server
    
    # Initialize with empty data (will lazy-load states on demand)
    # For now, get years from a representative state
    sample_state_data = pd.DataFrame()
    try:
        # Try to load Indiana as a sample to get available years
        sample_state_data = load_state_data('INDIANA')
    except:
        print("Warning: Could not load sample state data for UI initialization")
    
    # Get available years
    years = []
    if not sample_state_data.empty and 'year' in sample_state_data.columns:
        years = sorted(sample_state_data['year'].unique().tolist())
    else:
        # Default years if no data available
        years = list(range(2001, 2026))
    
    year_options = [{'label': 'All Years', 'value': 'ALL'}] + \
                   [{'label': str(y), 'value': y} for y in years]
    
    # Get available crops from sample data
    crops = []
    if not sample_state_data.empty and 'commodity_desc' in sample_state_data.columns:
        crops = sorted(sample_state_data['commodity_desc'].dropna().unique().tolist())
    
    crop_options = [{'label': 'All Crops', 'value': 'ALL'}] + \
                   [{'label': c, 'value': c} for c in crops[:50]]  # Limit for performance
    
    # Store empty data dict - will be populated by state loading
    data = {}
    # Store data in app for access in callbacks
    app.data = data
    
    # App layout
    
    # Merge custom styles with SIDEBAR_STYLE
    sidebar_style = {**SIDEBAR_STYLE, 'backgroundColor': '#B8D0D9', 'fontFamily': 'Segoe UI SemiBold, sans-serif'}
    
    sidebar = html.Div(style=sidebar_style,
                       children=[html.H4(children="USDA SURVEY STATISTICS", className="mb-4", 
                                         style={
                                             'textAlign': 'center',
                                             'color': '#081E26',
                                             'fontFamily': 'Segoe UI Semibold, sans-serif'}),
        html.Hr(),

        html.Div(children="Understanding farming one stat at a time", style={
        'textAlign': 'center',
        'color': '#081E26',
        'fontFamily': 'Segoe UI, sans-serif'}),
        html.Hr(),

        # Year dropdown
        html.Label("Year", className="fw-bold"),
        dcc.Dropdown(
            id='year-select',
            options=year_options,
            value='ALL',  # A2 - Default year = ALL YEARS
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
        
        # Crop group filter (always visible, only applies to CROPS sector)
        html.Label("Crop Group", className="fw-bold"),
        dcc.Dropdown(
            id='crop-group-select',
            options=CROP_GROUP_OPTIONS,
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
        # A1 - Measure note div
        html.Div(id='measure-note', style={'fontSize': '11px', 'color': '#666', 'marginTop': '-10px', 'marginBottom': '10px'}),
        
        # Measure guidance
        html.Div([
            html.Small([
                html.Strong("Measure Guide:"),
                html.Br(),
                "• Overview: Area Harvested",
                html.Br(),
                "• Labor & Operations: Operations",
                html.Br(),
                "• Economics: Revenue"
            ], style={'color': '#555', 'fontSize': '10px'})
        ], style={'padding': '8px', 'backgroundColor': '#f0f0f0', 'borderRadius': '4px', 'marginBottom': '10px'}),
        
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
        
    ])
    
    content = html.Div([
        html.Div([
            html.Div([
                html.H3("US Agricultural Overview", id="page-title", style={'fontFamily': 'Segoe UI Semibold, sans-serif'}),
                html.P("Click on a state to see detailed crop information", 
                       className="text-muted", id="page-subtitle")
            ]),
            # Data source citations in top right
            html.Div([
                html.Small([
                    html.Strong("Data Sources: "),
                    html.Br(),
                    "• USDA NASS Quick Stats",
                    "• USDA ERS Major Land Uses",
                    "• BLS OEWS Wage Statistics"
                ], style={'color': '#666', 'textAlign': 'right', 'fontSize': '11px'})
            ], style={'position': 'absolute', 'top': '10px', 'right': '60px'})
        ], className="mb-4", style={'position': 'relative'}),
        
        # Hex Map
        dbc.Card([
            dbc.CardBody([
                dcc.Graph(id='hex-map', config={'displayModeBar': False}, style={'height': '550px'})
            ])
        ], style=CARD_STYLE),
        
        # Chart 1 - Full width row
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(id="chart-1-header", style={'fontFamily': 'Segoe UI Semibold, sans-serif'}),
                    dbc.CardBody([
                        dcc.Graph(id='chart-1', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=12)
        ]),
        
        # Chart 2
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Span(id="chart-2-header", style={'fontFamily': 'Segoe UI Semibold, sans-serif'}),
                        html.Button("Show All Crops", id="reset-crop-btn", 
                                    className="btn btn-sm btn-outline-secondary float-end",
                                    style={'marginLeft': '10px', 'display': 'none'})
                    ]),
                    dbc.CardBody([
                        dcc.Graph(id='chart-2', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=12)
        ]),
        
        # Chart 3
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader(id="chart-3-header", style={'fontFamily': 'Segoe UI Semibold, sans-serif'}),
                    dbc.CardBody([
                        # D1 - Overview boom toggle
                        html.Div(id='overview-boom-toggle-container', children=[
                            dcc.RadioItems(
                                id='overview-boom-toggle',
                                options=[
                                    {"label": "National", "value": "national"},
                                    {"label": "Selected State", "value": "state"}
                                ],
                                value="national",
                                inline=True,
                                style={'marginBottom': '10px', 'fontSize': '12px'}
                            )
                        ], style={'display': 'none'}),
                        dcc.Graph(id='chart-3', config={'displayModeBar': False})
                    ])
                ], style=CARD_STYLE)
            ], width=12)
        ]),
        
        # Hidden stores for state management - H1: Default to Indiana
        dcc.Store(id='selected-state', data='IN'),
        dcc.Store(id='selected-crop', data=None)
        
    ], style=CONTENT_STYLE)
    
    app.layout = html.Div([sidebar, content])
    
    # Callbacks
    
    @app.callback(
        Output('hex-map', 'figure'),
        [Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('measure-select', 'value'),
         Input('selected-state', 'data')]
    )

    # I decided to use a HEX MAP instead of a choropleth map for better visualization of state-level data.
    # I felt that most dashboards use choropleth maps and wanted to try something different.
    # The HEX MAP is easier to read when states are small like in the northeast region.
    # It also helps us identify crops and measures in each state uniformly.

    def update_hex_map(year, sector, measure, selected_state):
        """Update the hexagonal map visualization with national data."""
        print(f"\n=== HEX MAP CALLBACK ===")
        print(f"Measure: {measure}, Year: {year}, Sector: {sector}")
        
        # Change color scale for different selected filters
        if 'area' in measure:
            cscale = 'Tealgrn'
        elif 'revenue' in measure or 'price' in measure:
            cscale = 'Viridis'
        elif 'yield' in measure:
            cscale = 'Plasma'
        else:
            cscale = 'Blues'
        
        year_str = f" ({year})" if year != 'ALL' else ""
        title = f"US States - Click to View Data{year_str}"
        
        # Load national crops data for hex map coloring
        try:
            national_df = load_national_crops_summary()
            
            if not national_df.empty:
                # Map measure to statisticcat_desc
                measure_mapping = {
                    'area_harvested_acres': 'AREA HARVESTED',
                    'area_planted_acres': 'AREA PLANTED',
                    'revenue_usd': 'SALES',
                    'operations': 'OPERATIONS',
                    'ops_per_1k_acres': 'OPERATIONS'  # Will compute this later
                }
                
                stat_cat = measure_mapping.get(measure)
                if not stat_cat:
                    # If measure not in mapping, return empty
                    map_df = pd.DataFrame()
                else:
                    # Filter to the statistic category
                    map_df = national_df[national_df['statisticcat_desc'] == stat_cat].copy()
                    
                    # Filter by year if specified
                    if year != 'ALL' and 'year' in map_df.columns:
                        year_int = int(year)
                        map_df = map_df[map_df['year'] == year_int]
                    
                    # Filter by sector if specified
                    if sector != 'ALL' and 'group_desc' in map_df.columns:
                        # Note: sector in dropdown is like 'CROPS', 'ANIMALS & PRODUCTS'
                        # group_desc in data is like 'FIELD CROPS', 'VEGETABLES', etc.
                        # For now, skip sector filtering since group_desc is more granular
                        pass
                    
                    # Aggregate by state_alpha
                    if not map_df.empty and 'state_alpha' in map_df.columns:
                        # Sum value_num by state
                        map_df = map_df.groupby('state_alpha')['value_num'].sum().reset_index()
                        # Rename value_num to the measure name for hex_map_figure
                        map_df = map_df.rename(columns={'value_num': measure})
                        print(f"Prepared hex map data: {len(map_df)} states")
                        print(f"Sample:\n{map_df.head()}")
                        
                        # For ops_per_1k_acres, we would need area data too - skip for now
                        if measure == 'ops_per_1k_acres':
                            map_df = pd.DataFrame()  # Can't compute without area data
                    else:
                        print("Warning: Empty map_df or missing state_alpha column")
                        map_df = pd.DataFrame()
            else:
                map_df = pd.DataFrame()
        except Exception as e:
            print(f"Could not load national data for hex map: {e}")
            import traceback
            traceback.print_exc()
            map_df = pd.DataFrame()
        
        return hex_map_figure(
            map_df, 
            measure,
            year=None,  # Already filtered in callback
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
        if click_data is None:
            return current_state
        try:
            point = click_data['points'][0]
            if 'customdata' in point:
                state_name = point['customdata'][0]
                state_row = HEX_LAYOUT[HEX_LAYOUT['state_name'] == state_name]
                if not state_row.empty:
                    return state_row['state_alpha'].iloc[0]
            elif 'text' in point:
                return point['text']
        except (KeyError, IndexError):
            pass
        return current_state
    
    @app.callback(
        Output('selected-crop', 'data'),
        [Input('chart-1', 'clickData'),
         Input('crop-search', 'value'),
         Input('reset-crop-btn', 'n_clicks')],
        [State('selected-crop', 'data')]
    )
    def update_selected_crop(click_data, crop_search, reset_clicks, current_crop):
        """Update selected crop when bar chart is clicked or crop is searched."""
        # https://dash.plotly.com/advanced-callbacks

        triggered_id = ctx.triggered_id
        
        # Reset button clears crop selection
        if triggered_id == 'reset-crop-btn':
            return None
            
        if triggered_id == 'crop-search' and crop_search and crop_search != 'ALL':
            return crop_search
        if triggered_id == 'chart-1' and click_data:
            try:
                return click_data['points'][0]['y']
            except (KeyError, IndexError):
                pass
        return current_crop
    
    # Show/hide reset button based on crop selection
    @app.callback(
        Output('reset-crop-btn', 'style'),
        [Input('selected-crop', 'data')]
    )
    def toggle_reset_button(selected_crop):
        if selected_crop:
            return {'marginLeft': '10px'}
        return {'marginLeft': '10px', 'display': 'none'}
    
    @app.callback(
        Output('chart-1', 'figure'),
        [Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('crop-group-select', 'value'),
         Input('measure-select', 'value'),
         Input('selected-state', 'data'),
         Input('viewmode-tabs', 'value')]
    )
    def update_chart_1(year, sector, crop_group, measure, selected_state, view_mode):
        """Update Chart 1 - State crop summary."""

        if selected_state is None:
            return _empty_fig("Click a state on the map to see details")
        
        # Get state name from state_alpha for data loading
        state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
        if state_row.empty:
            return _empty_fig("Invalid state selected")
        
        state_name = state_row['state_name'].iloc[0].upper()
        processed_data = process_state_data(state_name)
        df = processed_data.get('state_crop_year', pd.DataFrame())
        
        if df.empty:
            return _empty_fig("No data available for this state")
        
        # Apply sector filter
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        
        # Apply crop group filter if crops sector selected
        if sector == 'CROPS' and crop_group != 'ALL' and 'group_desc' in df.columns:
            df = df[df['group_desc'] == crop_group]
        
        # Set measure based on view mode
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
         Input('viewmode-tabs', 'value'),
         Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('crop-group-select', 'value')]
    )
    def update_chart_2(selected_state, selected_crop, view_mode, year_value, sector, crop_group):
        """Update Chart 2 - Trend chart with subtitle for year filter."""

        if selected_state is None:
            return _empty_fig("Select a state to see trends")
        
        # Get state name from state_alpha for data loading
        state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
        if state_row.empty:
            return _empty_fig("Invalid state selected")
        
        state_name = state_row['state_name'].iloc[0].upper()
        processed_data = process_state_data(state_name)
        df = processed_data.get('state_crop_year', pd.DataFrame())
        landuse_df = processed_data.get('landuse', pd.DataFrame())
        farm_ops_df = processed_data.get('farm_operations', pd.DataFrame())
        
        # Apply sector filter
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        
        # Apply crop group filter if crops sector selected
        if sector == 'CROPS' and crop_group != 'ALL' and 'group_desc' in df.columns:
            df = df[df['group_desc'] == crop_group]
        
        # A3 - Generate subtitle for year filter context
        if year_value and year_value != 'ALL':
            subtitle = f"Year filter: {year_value}"
        else:
            subtitle = "All years"
        
        if view_mode == 'Overview':
            # If a crop is selected from chart 1, show only that crop's trend
            if selected_crop:
                fig = area_trend_chart(df, selected_state, crops=[selected_crop])
            else:
                fig = area_trend_chart(df, selected_state)
            fig.update_layout(title=dict(text=f"Area Trend<br><sup>{subtitle}</sup>"))
            return fig
        elif view_mode == 'Land & Area':
            if not landuse_df.empty:
                fig = land_use_trend_chart(landuse_df, selected_state)
            else:
                fig = area_trend_chart(df, selected_state)
            fig.update_layout(title=dict(text=f"Land Use Trend<br><sup>{subtitle}</sup>"))
            return fig
        elif view_mode == 'Labor & Operations':
            fig = operations_trend_chart(df, selected_state, farm_ops_df=farm_ops_df)
            fig.update_layout(title=dict(text=f"Operations Trend<br><sup>{subtitle}</sup>"))
            return fig
        elif view_mode == 'Economics & Profitability':
            # If a crop is selected from chart 1, show only that crop's revenue trend
            if selected_crop:
                fig = revenue_trend_chart(df, selected_state, crops=[selected_crop])
            else:
                fig = revenue_trend_chart(df, selected_state)
            fig.update_layout(title=dict(text=f"Revenue Trend<br><sup>{subtitle}</sup>"))
            return fig
        return _empty_fig("Select a view mode")
    
    @app.callback(
        Output('chart-3', 'figure'),
        [Input('year-select', 'value'),
         Input('selected-state', 'data'),
         Input('selected-crop', 'data'),
         Input('viewmode-tabs', 'value'),
         Input('overview-boom-toggle', 'value'),
         Input('sector-select', 'value'),
         Input('crop-group-select', 'value')]
    )
    def update_chart_3(year, selected_state, selected_crop, view_mode, boom_toggle, sector, crop_group):
        """Update Chart 3 - Diagnostic/comparison chart."""
        
        if selected_state is None:
            return _empty_fig("Select a state to see details")
        
        # Get state name from state_alpha for data loading
        state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
        if state_row.empty:
            return _empty_fig("Invalid state selected")
        
        state_name = state_row['state_name'].iloc[0].upper()
        processed_data = process_state_data(state_name)
        df = processed_data.get('state_crop_year', pd.DataFrame())
        landuse_df = processed_data.get('landuse', pd.DataFrame())
        labor_df = processed_data.get('labor', pd.DataFrame())
        
        if df.empty:
            return _empty_fig("No data available for this state")
        
        # Apply sector filter
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        
        # Apply crop group filter if crops sector selected
        if sector == 'CROPS' and crop_group != 'ALL' and 'group_desc' in df.columns:
            df = df[df['group_desc'] == crop_group]
        
        year_val = None if year == 'ALL' else year
        
        if view_mode == 'Overview':
            # Boom toggle: national vs selected state
            if boom_toggle == 'state' and selected_state:
                return boom_crops_chart(df, 'area_harvested_acres', state_filter=selected_state, selected_crop=selected_crop)
            else:
                # Load national crops data for national view
                national_crops = load_national_crops_summary()
                if not national_crops.empty:
                    # Apply crop group filter to national data if CROPS sector selected
                    if sector == 'CROPS' and crop_group != 'ALL' and 'group_desc' in national_crops.columns:
                        national_crops = national_crops[national_crops['group_desc'] == crop_group]
                    return boom_crops_chart(national_crops, 'area_harvested_acres', selected_crop=selected_crop)
                return boom_crops_chart(df, 'area_harvested_acres', selected_crop=selected_crop)
        
        elif view_mode == 'Land & Area':
            # Load national land use for all-states scatter plot
            national_landuse = load_national_landuse_summary()
            return area_vs_urban_scatter(df, landuse_df, selected_state, national_landuse)
        
        elif view_mode == 'Labor & Operations':
            # Load national labor for all-states comparison
            national_labor = load_national_labor_summary()
            return labor_wage_trends(df, labor_df, selected_state, year_val, national_labor)
        
        elif view_mode == 'Economics & Profitability':
            return boom_crops_chart(df, 'revenue_usd', selected_crop=selected_crop)
        
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
         Input('selected-state', 'data'),
         Input('year-select', 'value')]
    )
    def update_headers(view_mode, selected_state, year_value):
        """Update page and chart headers based on view mode with context."""
        # G2 - Add state and year context to headers
        state_str = ""
        year_str = ""
        if selected_state:
            state_row = HEX_LAYOUT[HEX_LAYOUT['state_alpha'] == selected_state]
            if not state_row.empty:
                state_str = f" - {state_row['state_name'].iloc[0]}"
        if year_value and year_value != 'ALL':
            year_str = f" ({year_value})"
        
        headers = {
            'Overview': (
                f"US Agricultural Overview{state_str}{year_str}",
                f"Top Crops by Area{state_str}",
                "Area Trends Over Time",
                "Fastest Growing Crops"
            ),
            'Land & Area': (
                f"Land & Area Analysis{state_str}{year_str}",
                f"Crops by Area Harvested{state_str}",
                "Land Use Composition",
                "Cropland vs Urban Change"
            ),
            'Labor & Operations': (
                f"Labor & Operations{state_str}{year_str}",
                f"Crops by Number of Operations{state_str}",
                "Operations Trends",
                "Labor Intensity by Crop"
            ),
            'Economics & Profitability': (
                f"Economics & Profitability{state_str}{year_str}",
                f"Crops by Revenue{state_str}",
                "Revenue Trends",
                "Boom Crops (Revenue)"
            )
        }
        
        return headers.get(view_mode, headers['Overview'])
    
    # A1 - Callback for measure-note (shows current measure description)
    @app.callback(
        Output('measure-note', 'children'),
        [Input('measure-select', 'value')]
    )
    def update_measure_note(measure):
        """Update the measure note based on selected measure."""
        measure_notes = {
            'area_harvested_acres': 'Total harvested area in acres',
            'production_units': 'Total production in standard units',
            'yield_per_acre': 'Production per acre harvested',
            'revenue_usd': 'Estimated revenue in USD',
            'num_operations': 'Number of farm operations'
        }
        return measure_notes.get(measure, '')
    
    # D1 - Callback to show/hide overview-boom-toggle based on view mode
    @app.callback(
        Output('overview-boom-toggle-container', 'style'),
        [Input('viewmode-tabs', 'value')]
    )
    def toggle_boom_visibility(view_mode):
        """Show boom toggle only in Overview mode."""
        if view_mode == 'Overview':
            return {'display': 'block', 'marginBottom': '10px'}
        return {'display': 'none'}
    
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
# MAIN - Create app instance at module level for gunicorn
# ============================================================================

# Create the app instance at module level for gunicorn to import
app = create_app()

# Expose the Flask server object for WSGI servers (gunicorn, uwsgi, etc.)
server = app.server

if __name__ == "__main__":
    # For local development with Flask dev server
    print("\n" + "=" * 60)
    print("Starting USDA Agricultural Dashboard")
    print("=" * 60)
    print("Open your browser to: http://127.0.0.1:8050")
    print("Press Ctrl+C to stop the server")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=8050, debug=True)
