"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import { RefreshCw, BarChart2, Info, Zap } from "lucide-react";

const API = "http://127.0.0.1:5050";

type HeatNode = {
  ticker: string;
  sector_key: string;
  sector: string;
  price: number | null;
  mos: number | null;
  method: string | null;
  market_cap: number;
  status: string;
};

function getMosColor(mos: number | null): { bg: string; text: string; border: string; glow: string } {
  if (mos === null) return { bg: "bg-slate-800", text: "text-slate-400", border: "border-slate-700", glow: "" };
  if (mos > 40)  return { bg: "bg-emerald-900/60", text: "text-emerald-300", border: "border-emerald-500/60", glow: "shadow-emerald-900/50" };
  if (mos > 20)  return { bg: "bg-green-900/50",   text: "text-green-300",   border: "border-green-500/50",   glow: "shadow-green-900/30" };
  if (mos > 0)   return { bg: "bg-teal-900/40",    text: "text-teal-300",    border: "border-teal-500/40",    glow: "" };
  if (mos > -20) return { bg: "bg-amber-900/40",   text: "text-amber-300",   border: "border-amber-500/40",   glow: "" };
  if (mos > -40) return { bg: "bg-orange-900/50",  text: "text-orange-300",  border: "border-orange-500/50",  glow: "" };
  return { bg: "bg-red-900/60", text: "text-red-300", border: "border-red-500/60", glow: "shadow-red-900/40" };
}

function TickerTile({ node, idx }: { node: HeatNode; idx: number }) {
  const { bg, text, border, glow } = getMosColor(node.mos);
  const [hovered, setHovered] = useState(false);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ delay: Math.min(idx * 0.005, 1), duration: 0.2 }}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={`relative rounded-lg border cursor-default transition-all duration-150 select-none
        ${bg} ${border} ${glow ? `shadow-lg ${glow}` : ""}
        ${hovered ? "scale-110 z-10 shadow-2xl" : ""}
      `}
      style={{ padding: "6px 8px", minWidth: "52px" }}
    >
      <div className={`text-xs font-black font-mono leading-tight ${text}`}>{node.ticker}</div>
      {node.mos !== null && (
        <div className={`text-[10px] font-mono leading-none mt-0.5 ${text} opacity-80`}>
          {node.mos > 0 ? "+" : ""}{node.mos.toFixed(0)}%
        </div>
      )}

      {/* Tooltip */}
      {hovered && (
        <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 min-w-[160px] pointer-events-none">
          <div className="glass-card p-3 text-xs shadow-xl border border-white/20">
            <div className="font-black font-mono text-white text-sm mb-1">{node.ticker}</div>
            <div className="text-slate-400 mb-1">{node.sector}</div>
            {node.price && <div className="text-slate-300">Rp {node.price.toLocaleString("id-ID")}</div>}
            {node.mos !== null && (
              <div className={`font-bold mt-1 ${node.mos > 0 ? "text-emerald-400" : "text-red-400"}`}>
                MoS: {node.mos > 0 ? "+" : ""}{node.mos.toFixed(1)}%
              </div>
            )}
            {node.method && <div className="text-slate-500 text-[10px] mt-0.5">{node.method}</div>}
          </div>
          <div className="w-2 h-2 bg-white/10 rotate-45 mx-auto -mt-1 border-r border-b border-white/20" />
        </div>
      )}
    </motion.div>
  );
}

export default function HeatmapPage() {
  const [nodes, setNodes]     = useState<HeatNode[]>([]);
  const [loading, setLoading] = useState(false);
  const [meta, setMeta]       = useState({ count: 0, source: "", generated_at: "" });
  const [groupBy, setGroupBy] = useState<"sector" | "mos">("sector");

  const fetchHeatmap = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    try {
      const url = `${API}/api/heatmap${forceRefresh ? "?force_refresh=1" : ""}`;
      const res  = await fetch(url);
      const data = await res.json();
      setNodes(data.nodes || []);
      setMeta({ count: data.count || data.nodes?.length || 0, source: data.source || "?", generated_at: data.generated_at || "" });
    } catch (e) {
      console.error("Heatmap fetch failed:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { setTimeout(fetchHeatmap, 0); }, [fetchHeatmap]);

  // Group nodes by sector or MoS band
  const grouped = (() => {
    if (groupBy === "sector") {
      const map: Record<string, HeatNode[]> = {};
      nodes.forEach(n => {
        const key = n.sector || "Lainnya";
        if (!map[key]) map[key] = [];
        map[key].push(n);
      });
      return Object.entries(map).sort((a, b) => b[1].length - a[1].length);
    } else {
      const bands = [
        { label: "🟢 Sangat Murah (MoS > 40%)", test: (m: number | null) => m !== null && m > 40 },
        { label: "🟩 Murah (MoS 20–40%)",       test: (m: number | null) => m !== null && m > 20 && m <= 40 },
        { label: "🟦 Sedikit Murah (0–20%)",     test: (m: number | null) => m !== null && m > 0 && m <= 20 },
        { label: "🟨 Sedikit Mahal (-20–0%)",    test: (m: number | null) => m !== null && m >= -20 && m <= 0 },
        { label: "🟧 Mahal (-40 s/d -20%)",      test: (m: number | null) => m !== null && m < -20 && m >= -40 },
        { label: "🔴 Sangat Mahal (< -40%)",     test: (m: number | null) => m !== null && m < -40 },
        { label: "⬜ Data Tidak Tersedia",        test: (m: number | null) => m === null },
      ];
      return bands.map(b => [b.label, nodes.filter(n => b.test(n.mos))] as [string, HeatNode[]]).filter(([, v]) => v.length > 0);
    }
  })();

  const stats = {
    cheap:     nodes.filter(n => (n.mos ?? 0) > 20).length,
    fair:      nodes.filter(n => (n.mos ?? 0) > 0 && (n.mos ?? 0) <= 20).length,
    expensive: nodes.filter(n => (n.mos ?? 0) <= 0).length,
    noData:    nodes.filter(n => n.mos === null).length,
  };

  return (
    <div className="flex flex-col max-w-7xl mx-auto mt-6 w-full">
      {/* Header */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-6">
        <div>
          <h1 className="text-3xl font-extrabold text-white flex items-center gap-3">
            <BarChart2 className="text-blue-400" size={32} /> Market Heatmap IDX
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Peta valuasi visual seluruh emiten. Warna = tingkat <em>Margin of Safety</em>.
            {meta.count > 0 && <span className="ml-2 text-blue-400 font-bold">{meta.count} saham termuat</span>}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={() => setGroupBy(g => g === "sector" ? "mos" : "sector")}
            className="px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-slate-300 text-sm font-semibold hover:bg-white/10 transition-colors"
          >
            {groupBy === "sector" ? "📊 Group by Valuasi" : "🏭 Group by Sektor"}
          </button>
          <button onClick={() => fetchHeatmap(true)} disabled={loading}
            className="flex items-center gap-2 bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded-lg text-sm font-bold transition-all disabled:opacity-50">
            <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            {loading ? "Memuat..." : "Refresh Live"}
          </button>
        </div>
      </motion.div>

      {/* Legend */}
      <div className="flex flex-wrap gap-2 mb-4 items-center">
        <span className="text-xs text-slate-500 mr-2">Legenda MoS:</span>
        {[
          { color: "bg-emerald-600", label: "> +40%" },
          { color: "bg-green-700",   label: "+20 s/d +40%" },
          { color: "bg-teal-700",    label: "0 s/d +20%" },
          { color: "bg-amber-700",   label: "-20 s/d 0%" },
          { color: "bg-orange-700",  label: "-40 s/d -20%" },
          { color: "bg-red-700",     label: "< -40%" },
          { color: "bg-slate-700",   label: "N/A" },
        ].map(({ color, label }) => (
          <span key={label} className="flex items-center gap-1 text-xs text-slate-400">
            <span className={`w-3 h-3 rounded-sm ${color}`} />
            {label}
          </span>
        ))}
      </div>

      {/* Stats bar */}
      {nodes.length > 0 && (
        <div className="glass-card flex flex-wrap gap-6 px-5 py-3 mb-6 text-sm">
          <div><span className="text-emerald-400 font-black text-lg">{stats.cheap}</span> <span className="text-slate-400">Murah (&gt;20% MoS)</span></div>
          <div><span className="text-teal-400 font-black text-lg">{stats.fair}</span> <span className="text-slate-400">Wajar (0–20%)</span></div>
          <div><span className="text-red-400 font-black text-lg">{stats.expensive}</span> <span className="text-slate-400">Mahal (&lt;0%)</span></div>
          <div><span className="text-slate-500 font-black text-lg">{stats.noData}</span> <span className="text-slate-500">Tanpa Data</span></div>
          {meta.source === "scan_cache" && (
            <div className="ml-auto text-xs text-slate-500 flex items-center gap-1">
              <Zap size={12} className="text-yellow-500" /> Dari hasil scan terakhir
            </div>
          )}
        </div>
      )}

      {/* Main grid */}
      {loading && nodes.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-blue-400">
          <RefreshCw size={40} className="animate-spin mb-4" />
          <div className="font-mono font-bold tracking-widest uppercase text-sm">Memuat Heatmap...</div>
          <div className="text-slate-500 text-xs mt-2">Jalankan Scan terlebih dahulu agar heatmap langsung penuh</div>
        </div>
      ) : nodes.length === 0 ? (
        <div className="glass-card flex flex-col items-center justify-center py-20 text-center">
          <Info size={40} className="text-slate-600 mb-4" />
          <h3 className="text-white font-bold text-lg mb-2">Belum Ada Data Heatmap</h3>
          <p className="text-slate-400 text-sm max-w-md">
            Jalankan <strong>Scanner</strong> atau <strong>High-Probability Scanner</strong> terlebih dahulu.
            Heatmap akan otomatis terisi dari hasil scan Anda.
          </p>
        </div>
      ) : (
        <div className="space-y-6">
          {grouped.map(([groupName, groupNodes]) => (
            <div key={groupName} className="glass-card p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider">{groupName}</h3>
                <span className="text-xs text-slate-500 font-mono">{groupNodes.length} saham</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {groupNodes
                  .sort((a, b) => (b.mos ?? -9999) - (a.mos ?? -9999))
                  .map((node, idx) => (
                    <TickerTile key={node.ticker} node={node} idx={idx} />
                  ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
