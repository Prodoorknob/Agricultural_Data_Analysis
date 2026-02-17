'use client';

import React, { useEffect, useState, useMemo } from 'react';
import Map, { Source, Layer } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import { US_STATES } from '../utils/serviceData';

const US_STATES_GEOJSON_URL = 'https://d2ad6b4ur7yvpq.cloudfront.net/naturalearth-3.3.0/ne_110m_admin_1_states_provinces_shp.geojson';

interface StateSingleMapProps {
  selectedState: string | undefined;
  mapData: Record<string, number>;
}

export default function StateSingleMap({ selectedState, mapData }: StateSingleMapProps) {
  const [geojson, setGeojson] = useState<any>(null);
  const [bounds, setBounds] = useState<[[number, number], [number, number]] | null>(null);

  // Load and filter GeoJSON for selected state
  useEffect(() => {
    if (!selectedState) {
      setGeojson(null);
      setBounds(null);
      return;
    }

    fetch(US_STATES_GEOJSON_URL)
      .then(res => res.json())
      .then(data => {
        const stateFeature = data.features.find((f: any) => 
          f.properties.postal === selectedState && f.properties.iso_a2 === 'US'
        );
        
        if (stateFeature) {
          const filtered = {
            type: 'FeatureCollection',
            features: [stateFeature]
          };
          setGeojson(filtered);
          
          // Calculate bounds from geometry
          const coords = stateFeature.geometry.coordinates;
          let minLng = Infinity, maxLng = -Infinity, minLat = Infinity, maxLat = -Infinity;
          
          const processCoords = (coordArray: any) => {
            if (typeof coordArray[0] === 'number') {
              minLng = Math.min(minLng, coordArray[0]);
              maxLng = Math.max(maxLng, coordArray[0]);
              minLat = Math.min(minLat, coordArray[1]);
              maxLat = Math.max(maxLat, coordArray[1]);
            } else {
              coordArray.forEach(processCoords);
            }
          };
          
          processCoords(coords);
          setBounds([[minLng, minLat], [maxLng, maxLat]]);
        }
      })
      .catch(err => console.warn('Failed to load state GeoJSON:', err));
  }, [selectedState]);

  const stateValue = selectedState ? mapData[selectedState] || 0 : 0;
  const stateName = selectedState ? US_STATES[selectedState] : '';

  const fillLayer: any = useMemo(() => ({
    id: 'state-fill',
    type: 'fill',
    paint: {
      'fill-color': stateValue > 0 ? '#19e63c' : '#374151',
      'fill-opacity': 0.6
    }
  }), [stateValue]);

  const borderLayer: any = {
    id: 'state-border',
    type: 'line',
    paint: {
      'line-color': '#19e63c',
      'line-width': 3
    }
  };

  if (!selectedState) {
    return (
      <div className="bg-[#1a1d24] border border-[#2a4030] rounded-xl p-6 h-full flex items-center justify-center">
        <div className="text-center">
          <span className="material-symbols-outlined text-gray-600 text-[64px] mb-4 block">map</span>
          <p className="text-gray-400">Select a state to view its map</p>
        </div>
      </div>
    );
  }

  if (!geojson || !bounds) {
    return (
      <div className="bg-[#1a1d24] border border-[#2a4030] rounded-xl p-6 h-full flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin size-12 border-4 border-[#19e63c] border-t-transparent rounded-full mx-auto mb-4"></div>
          <p className="text-gray-400">Loading {stateName} map...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-[#1a1d24] border border-[#2a4030] rounded-xl overflow-hidden h-full flex flex-col">
      <div className="p-4 border-b border-[#2a4030]">
        <h3 className="text-lg font-semibold text-white flex items-center gap-2">
          <span className="material-symbols-outlined text-[#19e63c]">map</span>
          {stateName}
        </h3>
        <p className="text-sm text-gray-400 mt-1">
          Current Value: {stateValue > 0 ? stateValue.toLocaleString() : 'N/A'}
        </p>
      </div>
      
      <div className="flex-1 relative min-h-0">
        <Map
          key={selectedState}
          initialViewState={{
            bounds: bounds as any,
            fitBoundsOptions: { padding: 40 }
          }}
          style={{ width: '100%', height: '100%' }}
          mapStyle="https://basemaps.cartocdn.com/gl/dark-matter-nolabels-gl-style/style.json"
          attributionControl={false}
          dragPan={true}
          scrollZoom={false}
          doubleClickZoom={false}
          touchZoomRotate={false}
        >
          {geojson && (
            <Source id="state" type="geojson" data={geojson}>
              <Layer {...fillLayer} />
              <Layer {...borderLayer} />
            </Source>
          )}
        </Map>
      </div>
      
      <div className="p-3 bg-[#0f1117] border-t border-[#2a4030]">
        <p className="text-xs text-gray-500 text-center">
          State-level view • County data not available
        </p>
      </div>
    </div>
  );
}
