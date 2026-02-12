'use client';

import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    Legend,
    ResponsiveContainer
} from 'recharts';

interface TrendChartProps {
    data: any[];
    title?: string;
    dataKeys: string[]; // Keys to plot lines for (e.g., 'CORN', 'SOYBEANS')
}

const COLORS = ['#8884d8', '#82ca9d', '#ffc658', '#ff7300', '#0088fe', '#00c49f'];

export default function TrendChart({ data, title, dataKeys }: TrendChartProps) {
    if (!data || data.length === 0) {
        return (
            <div className="h-64 flex items-center justify-center text-slate-400 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                No trend data available
            </div>
        );
    }

    return (
        <div className="w-full h-[400px] bg-white p-4 rounded-xl shadow-sm">
            {title && <h3 className="text-lg font-semibold mb-4 text-slate-700">{title}</h3>}
            <ResponsiveContainer width="100%" height="100%">
                <LineChart
                    data={data}
                    margin={{
                        top: 5,
                        right: 30,
                        left: 20,
                        bottom: 5,
                    }}
                >
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                        dataKey="year"
                        type="number"
                        domain={['dataMin', 'dataMax']}
                        tickFormatter={(tick) => tick.toString()}
                    />
                    <YAxis
                        tickFormatter={(val) =>
                            val >= 1000000 ? `${(val / 1000000).toFixed(1)}M` :
                                val >= 1000 ? `${(val / 1000).toFixed(0)}k` : val
                        }
                    />
                    <Tooltip
                        labelFormatter={(label) => `Year: ${label}`}
                        formatter={(value: number) => [value.toLocaleString(), 'Acres']}
                    />
                    <Legend />
                    {dataKeys.map((key, index) => (
                        <Line
                            key={key}
                            type="monotone"
                            dataKey={key}
                            stroke={COLORS[index % COLORS.length]}
                            strokeWidth={2}
                            dot={{ r: 3 }}
                            activeDot={{ r: 6 }}
                            connectNulls
                        />
                    ))}
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
