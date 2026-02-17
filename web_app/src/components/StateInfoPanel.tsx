import React from 'react';
import { US_STATES } from '../utils/serviceData';

interface StateInfoProps {
  selectedState: string | undefined;
  selectedYear: number;
  selectedSector: string;
  selectedCommodity?: string | null;
  stateData: any[];
}

export default function StateInfoPanel({ selectedState, selectedYear, selectedSector, selectedCommodity, stateData }: StateInfoProps) {
  // Calculate key metrics for the selected state
  const stateName = selectedState ? US_STATES[selectedState] : 'United States';
  
  const filteredData = stateData.filter(d => {
    if (selectedYear > 0 && d.year !== selectedYear) return false;
    if (selectedCommodity && d.commodity_desc !== selectedCommodity) return false;
    return true;
  });

  // Calculate metrics
  const crops = new Set(filteredData.filter(d => d.sector_desc === 'CROPS').map(d => d.commodity_desc));
  const totalOperations = filteredData
    .filter(d => d.statisticcat_desc === 'OPERATIONS')
    .reduce((sum, d) => sum + (d.value_num || 0), 0);
  
  const totalAreaHarvested = filteredData
    .filter(d => d.statisticcat_desc === 'AREA HARVESTED')
    .reduce((sum, d) => sum + (d.value_num || 0), 0);
  
  const totalRevenue = filteredData
    .filter(d => d.statisticcat_desc === 'SALES' && d.unit_desc === '$')
    .reduce((max, d) => Math.max(max, d.value_num || 0), 0);

  const formatNumber = (num: number) => {
    if (num >= 1000000000) return `$${(num / 1000000000).toFixed(2)}B`;
    if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`;
    if (num >= 1000) return `${(num / 1000).toFixed(1)}K`;
    return num.toFixed(0);
  };

  return (
    <div className="bg-[#1a1d24] border border-[#2a4030] rounded-xl p-6 h-full">
      <div className="flex items-center gap-3 mb-6">
        <div className="size-12 bg-[#19e63c]/20 rounded-lg flex items-center justify-center">
          <span className="material-symbols-outlined text-[#19e63c] text-[28px]">location_on</span>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-white">{stateName}</h2>
          <p className="text-sm text-gray-400">
            {selectedYear > 0 ? selectedYear : 'All Years'} • {selectedSector}
          </p>
        </div>
      </div>

      {selectedCommodity && (
        <div className="mb-6 p-4 bg-[#19e63c]/10 border border-[#19e63c]/30 rounded-lg">
          <div className="flex items-center gap-2 text-[#19e63c]">
            <span className="material-symbols-outlined text-[20px]">eco</span>
            <span className="font-semibold">Viewing: {selectedCommodity}</span>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {/* Key Metrics */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-[#0f1117] p-4 rounded-lg border border-[#2a4030]">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
              <span className="material-symbols-outlined text-[16px]">grass</span>
              <span>CROPS</span>
            </div>
            <div className="text-2xl font-bold text-white">{crops.size}</div>
            <div className="text-xs text-gray-500 mt-1">Different crops</div>
          </div>

          <div className="bg-[#0f1117] p-4 rounded-lg border border-[#2a4030]">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
              <span className="material-symbols-outlined text-[16px]">agriculture</span>
              <span>OPERATIONS</span>
            </div>
            <div className="text-2xl font-bold text-white">{formatNumber(totalOperations)}</div>
            <div className="text-xs text-gray-500 mt-1">Farm operations</div>
          </div>

          <div className="bg-[#0f1117] p-4 rounded-lg border border-[#2a4030]">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
              <span className="material-symbols-outlined text-[16px]">landscape</span>
              <span>AREA</span>
            </div>
            <div className="text-2xl font-bold text-white">{formatNumber(totalAreaHarvested)}</div>
            <div className="text-xs text-gray-500 mt-1">Acres harvested</div>
          </div>

          <div className="bg-[#0f1117] p-4 rounded-lg border border-[#2a4030]">
            <div className="flex items-center gap-2 text-gray-400 text-xs mb-2">
              <span className="material-symbols-outlined text-[16px]">payments</span>
              <span>REVENUE</span>
            </div>
            <div className="text-2xl font-bold text-[#19e63c]">
              {totalRevenue > 0 ? formatNumber(totalRevenue) : 'N/A'}
            </div>
            <div className="text-xs text-gray-500 mt-1">Total sales</div>
          </div>
        </div>

        {/* Additional Info */}
        <div className="mt-6 p-4 bg-[#0f1117] rounded-lg border border-[#2a4030]">
          <div className="flex items-start gap-3">
            <span className="material-symbols-outlined text-blue-400 text-[20px]">info</span>
            <div className="flex-1">
              <h3 className="text-sm font-semibold text-white mb-2">Data Source</h3>
              <p className="text-xs text-gray-400 leading-relaxed">
                USDA QuickStats Survey data. Revenue data available for Census years (2007, 2012, 2017, 2022).
                Area and production data collected annually.
              </p>
            </div>
          </div>
        </div>

        {!selectedState && (
          <div className="mt-4 p-4 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <div className="flex items-start gap-3">
              <span className="material-symbols-outlined text-amber-400 text-[20px]">arrow_selector_tool</span>
              <div className="flex-1">
                <p className="text-xs text-amber-200 leading-relaxed">
                  Select a state from the dropdown above to view detailed agricultural data and analysis.
                </p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
