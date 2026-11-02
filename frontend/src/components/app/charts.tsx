"use client";
import { Bar, BarChart, CartesianGrid, Cell, Legend, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fmtCompact } from "@/lib/utils";

export const PALETTE = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)"];
const axis = { tick: { fontSize: 11, fill: "var(--subtle)" }, axisLine: { stroke: "var(--line)" }, tickLine: false };
export const tooltipStyle = { background: "var(--panel)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12, color: "var(--fg)" };

export function ResultChart({ type, data, x, y }: { type: string; data: Record<string, unknown>[]; x: string; y: string }) {
  const rows = data.map((d) => ({ ...d, [y]: Number(d[y]) }));
  if (type === "pie") {
    return <ResponsiveContainer><PieChart><Pie data={rows} dataKey={y} nameKey={x} innerRadius="45%" outerRadius="80%" paddingAngle={2}>{rows.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}</Pie><Tooltip contentStyle={tooltipStyle} /><Legend wrapperStyle={{ fontSize: 12 }} /></PieChart></ResponsiveContainer>;
  }
  if (type === "line") {
    return <ResponsiveContainer><LineChart data={rows} margin={{ left: 4, right: 12, top: 8 }}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey={x} {...axis} /><YAxis {...axis} tickFormatter={fmtCompact} width={48} /><Tooltip contentStyle={tooltipStyle} /><Line type="monotone" dataKey={y} stroke="var(--chart-1)" strokeWidth={2} dot={{ r: 3 }} /></LineChart></ResponsiveContainer>;
  }
  return <ResponsiveContainer><BarChart data={rows} margin={{ left: 4, right: 12, top: 8 }}><CartesianGrid stroke="var(--line)" vertical={false} /><XAxis dataKey={x} {...axis} interval={0} angle={rows.length > 6 ? -25 : 0} textAnchor={rows.length > 6 ? "end" : "middle"} height={rows.length > 6 ? 60 : 30} /><YAxis {...axis} tickFormatter={fmtCompact} width={48} /><Tooltip contentStyle={tooltipStyle} cursor={{ fill: "var(--panel-2)" }} /><Bar dataKey={y} fill="var(--chart-1)" radius={[4, 4, 0, 0]} /></BarChart></ResponsiveContainer>;
}
