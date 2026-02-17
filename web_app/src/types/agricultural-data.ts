
export interface AgDataRow {
    // Core Identifiers
    source_desc: string; // "SURVEY", "CENSUS"
    sector_desc: string; // "CROPS", "ANIMALS & PRODUCTS", "ECONOMICS"
    group_desc: string;  // "FIELD CROPS", "VEGETABLES", "LIVESTOCK", "INCOME"
    commodity_desc: string; // "CORN", "CATTLE", "LABOR"

    // Metrics & Values
    statisticcat_desc: string; // "AREA PLANTED", "INVENTORY", "NET INCOME"
    unit_desc: string;        // "ACRES", "HEAD", "$"
    domain_desc: string;      // "TOTAL", "ORGANIC STATUS", "NAICS"

    // Aggregation
    agg_level_desc: string;   // "STATE", "NATIONAL"
    state_alpha: string;      // "IL", "US"
    year: number;             // 2018, 2022

    // The Value
    value_num: number;        // Parsed numeric value
    // Optional because raw data has "Value" string
    Value?: string | number;
}
