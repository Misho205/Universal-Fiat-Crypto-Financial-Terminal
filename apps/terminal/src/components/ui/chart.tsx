"use client";
import * as React from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

/** Accessible bar chart: svg has title/desc, plus a visually-hidden data table fallback. */
export function StateBarChart({ data, label }: { data: { name: string; value: number }[]; label: string }) {
  const tableId = React.useId();
  return (
    <figure className="w-full">
      <div role="img" aria-label={label} aria-describedby={tableId} className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="currentColor" opacity={0.2} />
            <XAxis dataKey="name" tick={{ fontSize: 12 }} />
            <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
            <Tooltip />
            <Bar dataKey="value" fill="rgb(var(--brand-600))" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table id={tableId} className="sr-only">
        <caption>{label}</caption>
        <tbody>{data.map((d) => <tr key={d.name}><th scope="row">{d.name}</th><td>{d.value}</td></tr>)}</tbody>
      </table>
    </figure>
  );
}
