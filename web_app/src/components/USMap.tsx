
'use client';

import * as React from 'react';
import Map, { Source, Layer } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { useMemo, useState, useCallback, useEffect } from 'react';
import { scaleQuantile } from 'd3-scale';

const US_STATES_GEOJSON_URL = 'https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_110m_admin_1_states_provinces_shp.geojson';

interface USMapProps {
    data: Record<string, number>; // state_alpha -> value
    selectedState?: string;
    onStateSelect: (stateAlpha: string) => void;
}

export default function USMap({ data, selectedState, onStateSelect }: USMapProps) {
    const [hoverInfo, setHoverInfo] = useState<{ feature: any, x: number, y: number } | null>(null);
    const [usGeoJson, setUsGeoJson] = useState<any>(null);

    // Fetch GeoJSON and filter to US states only
    useEffect(() => {
        fetch(US_STATES_GEOJSON_URL)
            .then(res => res.json())
            .then(geojson => {
                // Filter features to only US states (iso_a2 === 'US')
                const usOnly = {
                    ...geojson,
                    features: geojson.features.filter((f: any) =>
                        f.properties.iso_a2 === 'US'
                    )
                };
                setUsGeoJson(usOnly);
            })
            .catch(err => console.warn('Failed to load GeoJSON:', err));
    }, []);

    // Calculate generic quantile scale for coloring
    const colorScale = useMemo(() => {
        const values = Object.values(data).filter(v => v > 0);
        if (!values.length) return () => '#e2e8f0'; // default slate-200

        // Green shades for agriculture
        const range = [
            '#f7fcf5',
            '#e5f5e0',
            '#c7e9c0',
            '#a1d99b',
            '#74c476',
            '#41ab5d',
            '#238b45',
            '#005a32'
        ];

        return scaleQuantile<string>()
            .domain(values)
            .range(range);
    }, [data]);

    // Merge data into GeoJSON (done in style expression usually, but helper here for tooltip)
    const getFeatureValue = useCallback((feature: any) => {
        const code = feature.properties.postal;
        return data[code] || 0;
    }, [data]);

    // MapLibre Style Expression for Fill Color
    const fillLayer: any = useMemo(() => {
        const values = Object.values(data).filter(v => v > 0);

        // If no data, return default static style
        if (values.length === 0) {
            return {
                id: 'states-fill',
                type: 'fill',
                paint: {
                    'fill-color': '#e2e8f0',
                    'fill-opacity': 0.8,
                    'fill-outline-color': '#94a3b8'
                }
            };
        }

        // Construct a "match" expression
        const expression: any[] = ['match', ['get', 'postal']];

        // Add each state's color
        Object.entries(data).forEach(([state, val]) => {
            if (val > 0) {
                expression.push(state);
                expression.push(colorScale(val));
            }
        });

        // Default color feature not found
        expression.push('#f1f5f9');

        return {
            id: 'states-fill',
            type: 'fill',
            paint: {
                'fill-color': expression,
                'fill-opacity': 0.85,
                'fill-outline-color': '#94a3b8' // Visible state borders
            }
        };
    }, [data, colorScale]);

    const highlightLayer: any = {
        id: 'state-highlight',
        type: 'line',
        source: 'states',
        paint: {
            'line-color': '#2563eb', // Blue-600
            'line-width': 3
        },
        // Filter to only the selected state
        filter: ['==', 'postal', selectedState || '']
    };

    // State border lines (always visible)
    const borderLayer: any = {
        id: 'state-borders',
        type: 'line',
        paint: {
            'line-color': '#64748b',
            'line-width': 1,
            'line-opacity': 0.5
        }
    };

    const onHover = useCallback((event: any) => {
        const { features, point } = event;
        const hoveredFeature = features && features[0];
        setHoverInfo(hoveredFeature ? { feature: hoveredFeature, x: point.x, y: point.y } : null);
    }, []);

    const onClick = useCallback((event: any) => {
        const feature = event.features && event.features[0];
        if (feature) {
            onStateSelect(feature.properties.postal);
        }
    }, [onStateSelect]);

    return (
        <div className="relative w-full h-full bg-slate-50 rounded-xl overflow-hidden shadow-inner" style={{ minHeight: '500px' }}>
            <Map
                initialViewState={{
                    longitude: -98.5,
                    latitude: 39.8,
                    zoom: 3.8,
                    pitch: 0,
                    bearing: 0
                }}
                maxBounds={[[-135, 22], [-62, 53]]}
                minZoom={3}
                maxZoom={7}
                style={{ width: '100%', height: '100%' }}
                mapStyle="https://basemaps.cartocdn.com/gl/positron-nolabels-gl-style/style.json"
                interactiveLayerIds={['states-fill']}
                onMouseMove={onHover}
                onClick={onClick}
                attributionControl={false}
            >
                {usGeoJson && (
                    <Source id="states" type="geojson" data={usGeoJson}>
                        <Layer {...fillLayer} />
                        <Layer {...borderLayer} />
                        <Layer {...highlightLayer} />
                    </Source>
                )}

                {/* Tooltip */}
                {hoverInfo && (
                    <div
                        className="absolute z-10 bg-white p-3 rounded-lg shadow-lg pointer-events-none border border-slate-200"
                        style={{ left: hoverInfo.x + 10, top: hoverInfo.y + 10 }}
                    >
                        <div className="font-bold text-slate-800">{hoverInfo.feature.properties.name}</div>
                        <div className="text-sm text-slate-600">
                            {getFeatureValue(hoverInfo.feature).toLocaleString()}
                        </div>
                    </div>
                )}
            </Map>
        </div>
    );
}
