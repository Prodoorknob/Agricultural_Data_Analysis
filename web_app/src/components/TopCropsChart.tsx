'use client';

import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell
} from 'recharts';

interface TopCropsChartProps {
    data: { commodity: string; value: number }[];
    title?: string;
    color?: string;
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8', '#82ca9d', '#ffc658', '#8dd1e1', '#a4de6c', '#d0ed57'];

export default function TopCropsChart({ data, title, color = '#2E7D32' }: TopCropsChartProps) {
    if (!data || data.length === 0) {
        return (
            <div className="h-64 flex items-center justify-center text-slate-400 bg-slate-50 rounded-lg border border-dashed border-slate-200">
                No data available for this metric
            </div>
        );
    }

    return (
        <div className="w-full h-[400px] bg-white p-4 rounded-xl shadow-sm">
            {title && <h3 className="text-lg font-semibold mb-4 text-slate-700">{title}</h3>}
            <ResponsiveContainer width="100%" height="100%">
                <BarChart
                    layout="vertical"
                    data={data}
                    margin={{
                        top: 5,
                        right: 30,
                        left: 80, // Space for labels
                        bottom: 5,
                    }}
                >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                    <XAxis type="number" tickFormatter={(val) => val.toLocaleString()} />
                    <YAxis
                        type="category"
                        dataKey="commodity"
                        width={80}
                        tick={{ fontSize: 11 }}
                    />
                    <Tooltip
                        formatter={(value: number | undefined) => [value?.toLocaleString() || '0', 'Value']}
                        cursor={{ fill: 'transparent' }}
                    />
                    <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                        {data.map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                        ))}
                    </Bar>
                </BarChart>
            </ResponsiveContainer>
        </div>
    );
}
