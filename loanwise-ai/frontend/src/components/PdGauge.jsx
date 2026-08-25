/**
 * The PD Gauge is the signature visual element of LoanWise: a horizontal
 * calibration strip, like an instrument readout, that renders a probability
 * of default against the LOW/MEDIUM/HIGH threshold bands. It appears at full
 * size on the result screen and in miniature wherever a risk score needs a
 * glance-able visual (application lists, admin summaries) — one consistent
 * visual language for "where does this number sit," echoing the fact that
 * model calibration is a first-class concern throughout this system, not an
 * afterthought.
 */
const BANDS = [
  { key: "low", max: 0.10, color: "#1E7F6E", label: "LOW" },
  { key: "medium", max: 0.25, color: "#C08A2E", label: "MEDIUM" },
  { key: "high", max: 1.0, color: "#B23A2E", label: "HIGH" },
];

export function riskColor(category) {
  if (category === "LOW") return "#1E7F6E";
  if (category === "MEDIUM") return "#C08A2E";
  return "#B23A2E";
}

export default function PdGauge({ pdScore, size = "default" }) {
  const pct = Math.max(0, Math.min(1, pdScore)) * 100;
  const isCompact = size === "compact";
  const height = isCompact ? 8 : 14;

  return (
    <div className={isCompact ? "w-32" : "w-full"}>
      <div className="relative rounded-sm overflow-hidden" style={{ height }}>
        <div className="absolute inset-0 flex">
          {BANDS.map((band, i) => {
            const prevMax = i === 0 ? 0 : BANDS[i - 1].max;
            const width = (band.max - prevMax) * 100;
            return (
              <div
                key={band.key}
                style={{ width: `${width}%`, backgroundColor: band.color, opacity: 0.22 }}
              />
            );
          })}
        </div>
        {/* threshold ticks */}
        {[0.10, 0.25].map((t) => (
          <div
            key={t}
            className="absolute top-0 bottom-0 w-px bg-ink/25"
            style={{ left: `${t * 100}%` }}
          />
        ))}
        {/* needle */}
        <div
          className="absolute top-0 bottom-0 w-[3px] bg-ink transition-all duration-500"
          style={{ left: `calc(${pct}% - 1.5px)` }}
        />
      </div>
      {!isCompact && (
        <div className="flex justify-between mt-1.5 font-mono text-[10px] tracking-wide text-ink/50">
          <span>0.00</span>
          <span className="absolute" style={{ marginLeft: "6%" }}>0.10</span>
          <span style={{ marginLeft: "3%" }}>0.25</span>
          <span>1.00</span>
        </div>
      )}
    </div>
  );
}
