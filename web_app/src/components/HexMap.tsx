'use client';

import React, { useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { PolygonLayer } from '@deck.gl/layers';
import { OrthographicView } from '@deck.gl/core';
import { HEX_LAYOUT, HexState } from '@/lib/hex-layout';

// Helper to calculate hexagon vertices
function getHexagonVertices(center: [number, number], radius: number): [number, number][] {
    const [cx, cy] = center;
    const vertices: [number, number][] = [];
    for (let i = 0; i < 6; i++) {
        const angle = (Math.PI / 3) * i;
        // Rotate by 30 degrees (Math.PI / 6) to point top
        const x = cx + radius * Math.cos(angle + Math.PI / 6);
        const y = cy + radius * Math.sin(angle + Math.PI / 6);
        vertices.push([x, y]);
    }
    return vertices;
}

interface HexMapProps {
    data?: Record<string, number>; // state_alpha -> value
    onStateSelect?: (stateAlpha: string) => void;
    selectedState?: string;
}

export default function HexMap({ data = {}, onStateSelect, selectedState }: HexMapProps) {
    const [hoverInfo, setHoverInfo] = useState<{ object?: HexState & { value: number }, x: number, y: number } | null>(null);

    // Layout parameters
    const HEX_RADIUS = 0.95;

    // Calculate max value for scaling
    const maxValue = useMemo(() => {
        const values = Object.values(data);
        return values.length ? Math.max(...values) : 1;
    }, [data]);

    const layerData = useMemo(() => {
        return HEX_LAYOUT.map(state => {
            // Hex grid offset
            // x = col + (row % 2) / 2
            const x = state.col + (state.row % 2) * 0.5;
            const y = -state.row * Math.sqrt(3) / 2;

            return {
                ...state,
                center: [x * 2.2, y * 2.2] as [number, number], // Scale coordinate space
                value: data[state.state_alpha] || 0
            };
        });
    }, [data]);

    const layers = [
        new PolygonLayer<HexState & { center: [number, number], value: number }>({
            id: 'hex-layer',
            data: layerData,
            pickable: true,
            extruded: true,
            wireframe: true,
            getPolygon: d => getHexagonVertices(d.center, HEX_RADIUS),
            getFillColor: d => {
                if (d.state_alpha === selectedState) return [255, 107, 107]; // Highlight (Red)

                // Simple Blue Gradient Interpolation
                // Min: #e0f2fe (224, 242, 254)
                // Max: #0284c7 (2, 132, 199)
                const t = d.value / maxValue; // 0 to 1

                const r = Math.round(224 + (2 - 224) * t);
                const g = Math.round(242 + (132 - 242) * t);
                const b = Math.round(254 + (199 - 254) * t);

                return [r, g, b];
            },
            getElevation: d => (d.value / maxValue) * 20, // Normalize height to 0-20 units
            getLineColor: [255, 255, 255, 100],
            getLineWidth: 0.1,
            onHover: info => setHoverInfo(info.object ? { object: info.object, x: info.x, y: info.y } : null),
            onClick: info => info.object && onStateSelect?.(info.object.state_alpha),
            updateTriggers: {
                getFillColor: [selectedState, data, maxValue],
                getElevation: [data, maxValue]
            },
            transitions: {
                getElevation: 600,
                getFillColor: 300
            }
        })
    ];

    return (
        <div className="relative w-full h-[500px] bg-slate-50 rounded-xl overflow-hidden shadow-inner flex items-center justify-center">
            {Object.keys(data).length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center z-10 pointer-events-none">
                    <p className="bg-white/80 p-2 rounded text-slate-500 text-sm">Loading / No Data for View...</p>
                </div>
            )}
            <DeckGL
                views={new OrthographicView({ id: 'ortho', controller: true })}
                initialViewState={{
                    target: [12, -7, 0],
                    zoom: 3.5,
                    minZoom: 2,
                    maxZoom: 10,
                    pitch: 45, // Angled view for 3D effect
                    bearing: 0
                }}
                controller={true}
                layers={layers}
            />
            {hoverInfo?.object && (
                <div
                    className="absolute z-10 bg-white p-2 rounded shadow text-sm pointer-events-none border border-slate-100"
                    style={{ left: hoverInfo.x + 10, top: hoverInfo.y + 10 }}
                >
                    <div className="font-bold text-slate-700">{hoverInfo.object.state_name}</div>
                    <div className="text-slate-500">Value: {hoverInfo.object.value.toLocaleString()}</div>
                </div>
            )}
        </div>
    );
}
