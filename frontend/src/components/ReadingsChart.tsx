import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Reading } from "@/api/types";

/**
 * Plots one numeric reading field exactly as returned. The threshold line is drawn only
 * when the detector configuration from the API supplies one.
 */
export function ReadingsChart({ readings, field = "temperature_c", unit = "°C", label = "Temperature", threshold, height = 240 }: {
  readings: Reading[]; field?: string; unit?: string; label?: string; threshold?: number | null; height?: number;
}) {
  const data = readings.map((r) => {
    const v = r.values[field];
    return { t: r.observed_at.slice(11, 19), v: typeof v === "number" ? v : null };
  });
  const axisTick = { fontSize: 11, fill: "var(--color-muted-foreground)", fontFamily: "var(--font-mono)" };
  return (
    <figure className="w-full">
      <div style={{ height }} role="img" aria-label={`${label} (${unit}) over time, ${readings.length} readings${threshold != null ? `, threshold ${threshold} ${unit}` : ""}`}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 10, right: 32, bottom: 18, left: 6 }}>
            <CartesianGrid stroke="var(--color-border)" vertical={false} />
            <XAxis dataKey="t" tick={axisTick} stroke="var(--color-rule-strong)" tickLine={false}
              label={{ value: "Observed (UTC)", position: "insideBottom", offset: -10, fontSize: 11, fill: "var(--color-muted-foreground)" }} />
            <YAxis tick={axisTick} stroke="var(--color-rule-strong)" tickLine={false} width={48} domain={([lo, hi]: readonly [number, number]) => threshold != null ? [Math.min(lo, threshold) - 1, Math.max(hi, threshold) + 1] : [lo - 1, hi + 1]}
              label={{ value: `${label} (${unit})`, angle: -90, position: "insideLeft", offset: 4, fontSize: 11, fill: "var(--color-muted-foreground)", style: { textAnchor: "middle" } }} />
            <Tooltip isAnimationActive={false} formatter={(v) => [`${v} ${unit}`, label]} labelFormatter={(l) => `${l} UTC`}
              contentStyle={{ borderRadius: 2, border: "1px solid var(--color-border)", fontSize: 12, fontFamily: "var(--font-mono)" }} />
            {threshold != null && (
              <ReferenceLine y={threshold} stroke="var(--color-chart-threshold)" strokeDasharray="4 3"
                label={{ value: `threshold ${threshold} ${unit}`, fontSize: 11, fill: "var(--color-attention-foreground)", position: "insideTopRight" }} />
            )}
            <Line type="linear" dataKey="v" name={label} stroke="var(--color-chart-line)" strokeWidth={1.5} dot={{ r: 2.5, strokeWidth: 1 }} isAnimationActive={false} connectNulls={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
