"""
DEMO VERSION - Dashboard Application
Limited to 2019-2024 data only for demonstration purposes.
"""

import os
import sys

# Force demo to use local files by default (not S3)
if 'USE_S3' not in os.environ:
    os.environ['USE_S3'] = 'False'

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

# Import from DEMO versions
from data_prep_demo import (
    prepare_all_data, 
    get_available_years, 
    get_available_crops, 
    get_available_states,
    load_state_data,
    process_state_data,
    load_national_labor_summary,
    load_national_landuse_summary,
    load_national_crops_summary,
    DEMO_START_YEAR,
    DEMO_END_YEAR,
    DEMO_STATE_ALPHAS
)
from visuals_demo import (
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
MEASURE_OPTIONS = [
    {'label': 'Area Harvested (acres)', 'value': 'area_harvested_acres'},
    {'label': 'Area Planted (acres)', 'value': 'area_planted_acres'},
    {'label': 'Revenue (USD)', 'value': 'revenue_usd'},
    {'label': 'Operations', 'value': 'operations'},
    {'label': 'Ops per 1,000 Acres', 'value': 'ops_per_1k_acres'},
]

SECTOR_OPTIONS = [
    {'label': 'All Sectors', 'value': 'ALL'},
    {'label': 'Crops', 'value': 'CROPS'},
    {'label': 'Animals & Products', 'value': 'ANIMALS & PRODUCTS'},
    {'label': 'Economics', 'value': 'ECONOMICS'},
]

CROP_GROUP_OPTIONS = [
    {'label': 'All Crop Groups', 'value': 'ALL'},
    {'label': 'Field Crops', 'value': 'FIELD CROPS'},
    {'label': 'Vegetables', 'value': 'VEGETABLES'},
    {'label': 'Fruit & Tree Nuts', 'value': 'FRUIT & TREE NUTS'},
    {'label': 'Horticulture', 'value': 'HORTICULTURE'},
]

VIEW_MODE_OPTIONS = [
    {'label': 'Overview', 'value': 'Overview'},
    {'label': 'Land & Area', 'value': 'Land & Area'},
    {'label': 'Labor & Operations', 'value': 'Labor & Operations'},
    {'label': 'Economics & Profitability', 'value': 'Economics & Profitability'},
]

# Styles
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


def create_app():
    """Create and configure the Dash application."""
    app = Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True
    )
    
    server = app.server
    
    # Initialize with sample data
    sample_state_data = pd.DataFrame()
    try:
        sample_state_data = load_state_data('INDIANA')
    except:
        print("Warning: Could not load sample state data for UI initialization")
    
    # DEMO: Use fixed year range 2019-2024
    years = list(range(DEMO_START_YEAR, DEMO_END_YEAR + 1))
    year_options = [{'label': 'All Years', 'value': 'ALL'}] + \
                   [{'label': str(y), 'value': y} for y in years]
    
    # Get available crops
    crops = []
    if not sample_state_data.empty and 'commodity_desc' in sample_state_data.columns:
        crops = sorted(sample_state_data['commodity_desc'].dropna().unique().tolist())
    
    crop_options = [{'label': 'All Crops', 'value': 'ALL'}] + \
                   [{'label': c, 'value': c} for c in crops[:50]]
    
    data = {}
    app.data = data
    
    # Import layout and callbacks from original app
    from app import (
        SIDEBAR_STYLE, CONTENT_STYLE, CARD_STYLE, DROPDOWN_STYLE,
        _empty_fig
    )
    
    # Create DEMO banner
    demo_banner = dbc.Alert(
        [
            html.H5("🎯 DEMO MODE", className="alert-heading"),
            html.P(f"Data limited to {DEMO_START_YEAR}-{DEMO_END_YEAR} for demonstration purposes."),
            html.P(f"Available states: {', '.join(DEMO_STATE_ALPHAS)}", style={'margin-bottom': '0', 'font-size': '14px'})
        ],
        color="info",
        style={'margin-bottom': '20px'}
    )
    
    # Sidebar
    sidebar = html.Div([
        demo_banner,
        html.H3("USDA Dashboard", style={'margin-bottom': '30px', 'color': '#2c3e50'}),
        
        html.Label("View Mode:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.RadioItems(
            id='viewmode-tabs',
            options=VIEW_MODE_OPTIONS,
            value='Overview',
            style={'margin-bottom': '20px'}
        ),
        
        html.Div(id='overview-boom-toggle-container', children=[
            dcc.RadioItems(
                id='overview-boom-toggle',
                options=[
                    {'label': 'Standard View', 'value': 'standard'},
                    {'label': 'Boom Crops', 'value': 'boom'}
                ],
                value='standard',
                inline=True
            )
        ], style={'display': 'block', 'marginBottom': '10px'}),
        
        html.Label("Sector:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.Dropdown(
            id='sector-select',
            options=SECTOR_OPTIONS,
            value='ALL',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Label("Crop Group:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.Dropdown(
            id='cropgroup-select',
            options=CROP_GROUP_OPTIONS,
            value='ALL',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Label("Measure:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.Dropdown(
            id='measure-select',
            options=MEASURE_OPTIONS,
            value='area_harvested_acres',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Label("Year:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.Dropdown(
            id='year-select',
            options=year_options,
            value='ALL',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Label("Crop:", style={'font-weight': 'bold', 'margin-bottom': '5px'}),
        dcc.Dropdown(
            id='crop-select',
            options=crop_options,
            value='ALL',
            clearable=False,
            style=DROPDOWN_STYLE
        ),
        
        html.Div(id='selected-state-display', style={'margin-top': '30px'}),
        html.Div(id='measure-note', style={'margin-top': '10px', 'font-size': '12px', 'color': 'gray'})
    ], style=SIDEBAR_STYLE)
    
    # Main content
    content = html.Div([
        html.H1(id='page-title', children="USDA Agricultural Overview (DEMO)", 
                style={'margin-bottom': '20px', 'color': '#2c3e50'}),
        
        dbc.Card([
            dbc.CardBody([
                dcc.Graph(id='hex-map', style={'height': '600px'})
            ])
        ], style=CARD_STYLE),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5(id='chart1-title', children="Chart 1"),
                        dcc.Graph(id='chart1', style={'height': '400px'})
                    ])
                ], style=CARD_STYLE)
            ], width=6),
            
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5(id='chart2-title', children="Chart 2"),
                        dcc.Graph(id='chart2', style={'height': '400px'})
                    ])
                ], style=CARD_STYLE)
            ], width=6)
        ]),
        
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H5(id='chart3-title', children="Chart 3"),
                        dcc.Graph(id='chart3', style={'height': '400px'})
                    ])
                ], style=CARD_STYLE)
            ], width=12)
        ])
    ], style=CONTENT_STYLE)
    
    app.layout = html.Div([
        dcc.Store(id='selected-state', data=None),
        dcc.Store(id='state-data-cache', data={}),
        sidebar,
        content
    ])
    
    # Import all callbacks from original app by executing the callback registration
    # We'll copy the key callbacks here
    
    @app.callback(
        Output('selected-state', 'data'),
        [Input('hex-map', 'clickData')],
        [State('selected-state', 'data')]
    )
    def update_selected_state(click_data, current_state):
        """Update selected state when hex map is clicked."""
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
        Output('selected-state-display', 'children'),
        [Input('selected-state', 'data')]
    )
    def display_selected_state(state):
        """Display the currently selected state."""
        if state is None:
            return html.Div([
                html.P("Click on a state in the map to view details", 
                      style={'font-size': '14px', 'color': 'gray'})
            ])
        
        return html.Div([
            html.H5("Selected State:", style={'margin-bottom': '5px'}),
            html.P(state, style={'font-size': '18px', 'font-weight': 'bold', 'color': '#3498db'})
        ])
    
    @app.callback(
        Output('hex-map', 'figure'),
        [Input('measure-select', 'value'),
         Input('year-select', 'value'),
         Input('sector-select', 'value'),
         Input('selected-state', 'data')]
    )
    def update_hex_map(measure, year, sector, selected_state):
        """Update the hexagonal map visualization."""
        # Change color scale based on measure
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
        
        # Create empty dataframe for initial display
        empty_df = pd.DataFrame()
        
        return hex_map_figure(
            empty_df,
            measure,
            selected_state=selected_state,
            color_scale=cscale,
            title=title
        )
    
    @app.callback(
        [Output('chart1', 'figure'),
         Output('chart2', 'figure'),
         Output('chart3', 'figure'),
         Output('chart1-title', 'children'),
         Output('chart2-title', 'children'),
         Output('chart3-title', 'children')],
        [Input('selected-state', 'data'),
         Input('viewmode-tabs', 'value'),
         Input('overview-boom-toggle', 'value'),
         Input('measure-select', 'value'),
         Input('year-select', 'value'),
         Input('crop-select', 'value'),
         Input('sector-select', 'value'),
         Input('cropgroup-select', 'value')]
    )
    def update_charts(state, view_mode, boom_toggle, measure, year, crop, sector, crop_group):
        """Update all three charts based on selections."""
        if state is None:
            empty = _empty_fig("Select a state from the map")
            return empty, empty, empty, "Chart 1", "Chart 2", "Chart 3"
        
        try:
            # Process state data (automatically loads and processes)
            processed = process_state_data(state)
            
            # Apply crop group filter if CROPS sector is selected
            if sector == 'CROPS' and crop_group != 'ALL':
                # Filter state_crop_year dataframe by crop group
                if 'state_crop_year' in processed and 'group_desc' in processed['state_crop_year'].columns:
                    df = processed['state_crop_year']
                    processed['state_crop_year'] = df[df['group_desc'] == crop_group]
            
            # Get the three charts for current view mode
            year_int = None if year == 'ALL' else int(year)
            
            fig1 = get_chart_for_view(view_mode, 1, processed, state, crop, year_int, measure)
            fig2 = get_chart_for_view(view_mode, 2, processed, state, crop, year_int, measure)
            fig3 = get_chart_for_view(view_mode, 3, processed, state, crop, year_int, measure)
            
            # Generate titles based on view mode
            if view_mode == 'Overview':
                titles = ["Top Crops by Area", "Area Trends", "Boom Crops"]
            elif view_mode == 'Land & Area':
                titles = ["Top Crops by Area", "Land Use Trends", "Area vs Urban Land"]
            elif view_mode == 'Labor & Operations':
                titles = ["Farm Operations", "Operations Trends", "Labor Intensity"]
            else:  # Economics & Profitability
                titles = ["Top Crops by Revenue", "Revenue Trends", "Boom Crops (Revenue)"]
            
            return fig1, fig2, fig3, titles[0], titles[1], titles[2]
            
        except Exception as e:
            print(f"Error updating charts: {e}")
            import traceback
            traceback.print_exc()
            empty = _empty_fig(f"Error: {str(e)}")
            return empty, empty, empty, "Error", "Error", "Error"
    
    @app.callback(
        Output('page-title', 'children'),
        [Input('viewmode-tabs', 'value')]
    )
    def update_title(view_mode):
        """Update page title based on view mode."""
        titles = {
            'Overview': "USDA Agricultural Overview (DEMO 2019-2024)",
            'Land & Area': "Land Use & Area Analysis (DEMO 2019-2024)",
            'Labor & Operations': "Labor & Operations Analysis (DEMO 2019-2024)",
            'Economics & Profitability': "Economic & Profitability Analysis (DEMO 2019-2024)"
        }
        return titles.get(view_mode, "USDA Dashboard (DEMO 2019-2024)")
    
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


# Create the app instance
app = create_app()
server = app.server

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("Starting USDA Agricultural Dashboard - DEMO MODE")
    print(f"Data Range: {DEMO_START_YEAR}-{DEMO_END_YEAR}")
    print("=" * 60)
    print("Open your browser to: http://127.0.0.1:8050")
    print("Press Ctrl+C to stop the server")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=8050, debug=True)
