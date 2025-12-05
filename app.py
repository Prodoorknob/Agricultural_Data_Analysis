import os
import sys

from matplotlib import colors
sys.path.insert(0, os.path.dirname(__file__))
from dash import Dash, html, dcc, callback, Input, Output, State, ctx
import dash_bootstrap_components as dbc
import plotly.graph_objects as go
import pandas as pd
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
    revenue_trend_chart,
    area_vs_urban_scatter,
    labor_wage_trends,
    sector_comparison_chart,
    boom_crops_chart,
    get_chart_for_view,
    HEX_LAYOUT,
    COLOR_SCALES
)


# Set to True for faster loading during development
USE_SAMPLE_DATA = True
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

def create_app(use_sample = USE_SAMPLE_DATA):
    # Initialize Dash app with Bootstrap theme
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True
    )
    # Load data
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
        # Header with data source citations (Issue 3)
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
                    html.Br(),
                    "• USDA ERS Major Land Uses",
                    html.Br(), 
                    "• BLS OEWS Wage Statistics"
                ], style={'color': '#666', 'textAlign': 'right', 'fontSize': '11px'})
            ], style={'position': 'absolute', 'top': '20px', 'right': '30px'})
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
        
        # Chart 2 - Full width row (Issue 4: stacked layout)
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader([
                        html.Span(id="chart-2-header", style={'fontFamily': 'Segoe UI Semibold, sans-serif'}),
                        # Issue 5: Reset button to show all crops
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
        
        # Chart 3 - Full width row (Issue 4: stacked layout)
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

        df = app.data.get('state_crop_year', pd.DataFrame())
        if df.empty:
            return _empty_fig("No data loaded")
        
        # filters
        if year != 'ALL':
            df = df[df['year'] == year]
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
        if measure not in df.columns:
            measure = 'area_harvested_acres'
        
        # Aggregate to state level
        state_totals = df.groupby('state_alpha').agg({measure: 'sum'}).reset_index()
        
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
        
        # Issue 5: Reset button clears crop selection
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
    
    # Issue 5: Show/hide reset button based on crop selection
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
        if sector != 'ALL' and 'sector_desc' in df.columns:
            df = df[df['sector_desc'] == sector]
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
         Input('year-select', 'value')]
    )
    def update_chart_2(selected_state, selected_crop, view_mode, year_value):
        """Update Chart 2 - Trend chart with subtitle for year filter."""

        df = app.data.get('state_crop_year', pd.DataFrame())
        landuse_df = app.data.get('landuse', pd.DataFrame())
        farm_ops_df = app.data.get('farm_operations', pd.DataFrame())
        
        if selected_state is None:
            return _empty_fig("Select a state to see trends")
        
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
         Input('overview-boom-toggle', 'value')]
    )
    def update_chart_3(year, selected_state, selected_crop, view_mode, boom_toggle):
        """Update Chart 3 - Diagnostic/comparison chart."""
        df = app.data.get('state_crop_year', pd.DataFrame())
        landuse_df = app.data.get('landuse', pd.DataFrame())
        labor_df = app.data.get('labor', pd.DataFrame())
        
        year_val = None if year == 'ALL' else year
        
        if view_mode == 'Overview':
            # D2 - Boom toggle: national vs selected state
            if boom_toggle == 'state' and selected_state:
                return boom_crops_chart(df, 'area_harvested_acres', state_filter=selected_state, selected_crop=selected_crop)
            return boom_crops_chart(df, 'area_harvested_acres', selected_crop=selected_crop)
        
        elif view_mode == 'Land & Area':
            return area_vs_urban_scatter(df, landuse_df, selected_state)
        
        elif view_mode == 'Labor & Operations':
            # Show wage trends over time (more insightful than single-year scatter)
            return labor_wage_trends(df, labor_df, selected_state, year_val)
        
        elif view_mode == 'Economics & Profitability':
            # C2 - Replace bubble chart with boom crops (revenue as measure)
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
    app.run(debug=True)
