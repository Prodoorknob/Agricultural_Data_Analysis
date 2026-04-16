/** FastAPI /api/v1/market/* response types */

export interface FuturesPoint {
  date: string;
  settle: number;
  volume?: number | null;
}

export interface FuturesTimeSeriesResponse {
  commodity: string;
  contract_type: string;
  points: FuturesPoint[];
}

export interface ForwardCurvePoint {
  contract_month: string;
  settle: number;
}

export interface ForwardCurveResponse {
  commodity: string;
  as_of_date: string;
  points: ForwardCurvePoint[];
}

export interface DxyPoint {
  date: string;
  value: number;
}

export interface DxyTimeSeriesResponse {
  points: DxyPoint[];
}

export interface ProductionCostResponse {
  commodity: string;
  year: number;
  variable_cost_per_bu: number | null;
  total_cost_per_bu: number | null;
  current_futures_price: number | null;
  margin_per_bu: number | null;
}

export interface FertilizerPriceResponse {
  quarter: string;
  anhydrous_ammonia_ton: number | null;
  dap_ton: number | null;
  potash_ton: number | null;
}
