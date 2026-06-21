"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Target, Search, Play, RefreshCw, TrendingUp, TrendingDown, CheckCircle, XCircle } from "lucide-react";

const API = "http://127.0.0.1:5050";

function useScan(pageMode: "sector" | "single") {
  const [scanStatus, setScanStatus] = useState<"idle" | "scanning" | "done" | "error">("idle");
  const [progress, setProgress]     = useState({ done: 0, total: 0, current: "", pct: 0 });
  const [results, setResults]       = useState<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any
  
  // Track current session so stale callbacks don't interfere
  const activeSessionRef = useRef<string | null>(null);
  const pollRef          = useRef<ReturnType<typeof setInterval> | null>(null);
  const evtRef           = useRef<EventSource | null>(null);

  const stopAll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (evtRef.current)  { evtRef.current.close(); evtRef.current = null; }
  };

  const fetchResults = async (sessionId: string) => {
    // Guard: only process results for the current active session
    if (activeSessionRef.current !== sessionId) return;
    stopAll();
    setProgress(p => ({ ...p, current: "Fetching API..." }));
    try {
      const res  = await fetch(`${API}/api/results?session_id=${sessionId}&t=${Date.now()}`);
      setProgress(p => ({ ...p, current: "API fetched, parsing JSON..." }));
      const data = await res.json();
      setProgress(p => ({ ...p, current: "JSON parsed, sorting..." }));
      const all  = (data.results || []) as any[]; // eslint-disable-line @typescript-eslint/no-explicit-any
      all.sort((a, b) => {
        const aHP = a.high_probability_status?.includes("🔥") ? 1 : 0;
        const bHP = b.high_probability_status?.includes("🔥") ? 1 : 0;
        if (aHP !== bHP) return bHP - aHP;
        return (b.margin_of_safety ?? -9999) - (a.margin_of_safety ?? -9999);
      });
      setResults(all);
      setProgress(p => ({ ...p, current: "Done!" }));
      setScanStatus("done");
    } catch (e: unknown) {
      setScanStatus("error");
      setProgress(p => ({ ...p, current: "Error fetchResults: " + (e instanceof Error ? e.message : String(e)) }));
    }
  };

  const startPolling = (sessionId: string) => {
    // Stop any existing poll first
    stopAll();
    activeSessionRef.current = sessionId;
    
    // SSE connection disabled to prevent browser connection exhaustion

    // Safety poll every 2s as fallback (in case SSE misses the done event)
    pollRef.current = setInterval(async () => {
      if (activeSessionRef.current !== sessionId) {
        clearInterval(pollRef.current!); pollRef.current = null;
        return;
      }
      try {
        const s = await fetch(`${API}/api/status?session_id=${sessionId}&t=${Date.now()}`);
        const d = await s.json();
        if (d.status === "done") {
          setProgress(p => ({ ...p, current: "Fallback status done, fetchResults..." }));
          fetchResults(sessionId); // fetchResults will call stopAll()
        } else if (d.status === "cancelled" || d.status === "error") {
          stopAll();
          if (activeSessionRef.current === sessionId) setScanStatus("idle");
        } else if (d.total) {
          setProgress(p => {
            if (d.progress_count > p.done) {
              const pct = Math.round((d.progress_count / d.total) * 100);
              return { ...p, done: d.progress_count, total: d.total, pct };
            }
            return p;
          });
        }
      } catch (err: unknown) {
        setProgress(p => ({ ...p, current: "Error poll: " + (err instanceof Error ? err.message : String(err)) }));
      }
    }, 2000);
  };

  // Auto-restore on mount OR when mode changes — but only if NOT already scanning
  useEffect(() => {
    // Don't override an in-progress scan
    if (activeSessionRef.current) return;
    const restore = async () => {
      try {
        const res  = await fetch(`${API}/api/global-status?t=${Date.now()}`);
        const data = await res.json();
        if (!data.active || data.mode !== pageMode) return;
        if (data.status === "done") {
          activeSessionRef.current = data.session_id;
          fetchResults(data.session_id);
        } else if (data.status === "running" || data.status === "queued") {
          setScanStatus("scanning");
          setProgress({
            done: data.progress_count, total: data.total,
            current: data.ticker || "Memulihkan...",
            pct: data.total ? Math.round((data.progress_count / data.total) * 100) : 0,
          });
          startPolling(data.session_id);
        }
      } catch {}
    };
    restore();
    return () => { /* don't stopAll on mode change; user may be mid-scan */ };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pageMode]);

  const startScan = async (mode: string, ticker: string) => {
    try {
      // Reset state
      stopAll();
      activeSessionRef.current = null;
      setScanStatus("scanning");
      setResults([]);
      setProgress({ done: 0, total: 0, current: "Memulai...", pct: 0 });

      const res  = await fetch(`${API}/api/scan-advanced`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, ticker: ticker.toUpperCase() }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      startPolling(data.session_id);
    } catch {
      setScanStatus("error");
    }
  };

  // Cleanup on unmount
  useEffect(() => () => stopAll(), []);

  return { scanStatus, progress, results, startScan };
}

function PiotroskiGauge({ score }: { score: number }) {
  const pct   = (score / 9) * 100;
  const color = score >= 7 ? "#4ade80" : score >= 4 ? "#fbbf24" : "#f87171";

  return (
    <div className="relative w-12 h-12 flex items-center justify-center" title={`Piotroski F-Score: ${score}/9`}>
      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
        <path fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="4"
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
        <path fill="none" stroke={color} strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${pct}, 100`}
          d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" />
      </svg>
      <span className="absolute text-sm font-black text-white font-mono">{score}</span>
    </div>
  );
}

function StatusIcon({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border
      ${ok ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" : "bg-red-500/10 text-red-400 border-red-500/20"}`}>
      {ok ? <CheckCircle size={10} /> : <XCircle size={10} />}
      {label}
    </span>
  );
}

function HPCard({ item, idx }: { item: any; idx: number }) { // eslint-disable-line @typescript-eslint/no-explicit-any
  const isHP    = item.high_probability_status?.includes("🔥");
  const fScore  = item.piotroski?.score ?? 0;
  const isUp    = item.technical?.is_uptrend;
  const macd    = item.technical?.macd?.status ?? "";
  const isMacd  = macd.includes("bullish") || macd.includes("golden");
  const accScore = item.accumulation?.score ?? 0;
  const mos      = item.margin_of_safety;
  const mStatus  = item.altman_beneish?.m_status;
  const zStatus  = item.altman_beneish?.z_status;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(idx * 0.04, 0.8), duration: 0.35 }}
      className={`glass-card p-5 flex flex-col gap-4 border-t-2 relative overflow-hidden
        ${item.status !== "ok" ? "border-t-slate-700" : isHP ? "border-t-emerald-500" : "border-t-slate-500"}`}
    >
      {isHP && (
        <motion.div
          className="absolute inset-0 rounded-xl bg-emerald-500/5"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ repeat: Infinity, duration: 3 }}
        />
      )}

      {/* Header Row */}
      <div className="flex justify-between items-start relative">
        <div>
          <a href={`/stock?ticker=${item.ticker}`}
            className="text-2xl font-black font-mono text-white hover:text-emerald-400 transition-colors block">
            {item.ticker}
          </a>
          <div className="text-slate-400 text-sm font-mono">
            Rp {item.current_price?.toLocaleString("id-ID") ?? "—"}
          </div>
          {item.valuation_price && (
            <div className="mt-2 inline-flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-200/90 bg-gradient-to-r from-amber-500/20 to-amber-900/20 border border-amber-500/30 px-2 py-1 rounded">
              Wajar: Rp {item.valuation_price.toLocaleString("id-ID")} ({item.method})
            </div>
          )}
        </div>
        {item.status === "ok" && <PiotroskiGauge score={fScore} />}
      </div>

      {item.status !== "ok" ? (
        <div className="text-xs text-slate-500 italic mt-2 flex-1 flex items-center">
          {item.error_msg || "Data fundamental atau teknikal tidak tersedia untuk dianalisis penuh."}
        </div>
      ) : (
        <>
          {/* MoS */}
          {mos !== null && mos !== undefined && (
            <div className={`flex items-center gap-2 text-sm font-bold ${mos > 0 ? "text-emerald-400" : "text-red-400"}`}>
              {mos > 0 ? <TrendingUp size={16} /> : <TrendingDown size={16} />}
              {mos > 0 ? "Undervalued" : "Overvalued"} {mos > 0 ? "+" : ""}{mos.toFixed(1)}% MoS
            </div>
          )}

          {/* Badges */}
          <div className="flex flex-wrap gap-1.5 relative">
            {item.recommended_method
              ? <StatusIcon ok label={`💰 Murah (${item.recommended_method})`} />
              : <StatusIcon ok={false} label="📉 Mahal" />}
            <StatusIcon ok={!!isUp} label={isUp ? "📈 Uptrend" : "📉 Downtrend"} />
            <StatusIcon ok={isMacd} label={`MACD: ${macd || "N/A"}`} />
            <StatusIcon
              ok={accScore >= 60}
              label={`OBV: ${accScore}%`}
            />
          </div>

          {/* Quality Scores */}
          <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs border-t border-white/5 pt-3 relative">
            <div className="flex justify-between">
              <span className="text-slate-500">Z-Score</span>
              <span className={`font-mono font-bold
                ${zStatus === "Safe" ? "text-emerald-400" : zStatus === "Grey" ? "text-amber-400" : "text-red-400"}`}>
                {zStatus ?? "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">M-Score</span>
              <span className={`font-mono font-bold ${mStatus === "Safe" ? "text-emerald-400" : "text-red-400"}`}>
                {mStatus ?? "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">RSI(14)</span>
              <span className={`font-mono font-bold
                ${(item.technical?.rsi14 ?? 50) < 30 ? "text-emerald-400"
                  : (item.technical?.rsi14 ?? 50) > 70 ? "text-red-400"
                  : "text-slate-300"}`}>
                {item.technical?.rsi14?.toFixed(1) ?? "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">F-Score</span>
              <span className={`font-mono font-bold ${fScore >= 7 ? "text-emerald-400" : fScore >= 4 ? "text-amber-400" : "text-red-400"}`}>
                {fScore}/9
              </span>
            </div>
          </div>

          {/* Accumulation Bar */}
          <div className="relative">
            <div className="flex justify-between text-xs mb-1">
              <span className="text-slate-500">Akumulasi Institusi</span>
              <span className={`font-mono font-bold ${accScore >= 60 ? "text-emerald-400" : accScore <= 40 ? "text-red-400" : "text-amber-400"}`}>
                {accScore}%
              </span>
            </div>
            <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${accScore >= 60 ? "bg-emerald-500" : accScore <= 40 ? "bg-red-500" : "bg-amber-500"}`}
                style={{ width: `${accScore}%` }}
              />
            </div>
          </div>

          {/* Final verdict */}
          <div className={`py-2 px-3 rounded-lg text-center text-sm font-extrabold uppercase tracking-widest relative
            ${isHP
              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              : "bg-white/5 text-slate-500 border border-white/5"}`}>
            {isHP && <span className="mr-1">🔥</span>}
            {isHP ? "High Probability" : "Normal"}
          </div>
        </>
      )}
    </motion.div>
  );
}

export default function HighProbabilityPage() {
  const [mode, setMode]     = useState<"sector" | "single">("sector");
  const [ticker, setTicker] = useState("");
  const { scanStatus, progress, results, startScan } = useScan(mode);

  const hpCount = results.filter(r => r.high_probability_status?.includes("🔥")).length;

  return (
    <div className="flex flex-col items-center max-w-6xl mx-auto mt-8">
      {/* Hero */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 text-xs font-bold uppercase tracking-widest mb-4">
          <Target size={12} /> 4 Pilar: Cheap · Quality · Momentum · Accumulation
        </div>
        <h1 className="text-4xl font-extrabold text-white mb-2">High-Probability Scanner</h1>
        <p className="text-slate-400 max-w-lg mx-auto text-sm leading-relaxed">
          Filter ketat: Murah (Valuasi) + F-Score ≥ 7 (Kualitas) + Uptrend + OBV ≥ 60% (Akumulasi)
        </p>
      </motion.div>

      {/* Control */}
      <div className="glass-card w-full max-w-xl p-5 mb-8">
        <div className="flex bg-black/30 p-1 rounded-lg mb-4">
          {(["sector", "single"] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`flex-1 py-2 rounded-md text-sm font-semibold transition-all
                ${mode === m ? "bg-emerald-600 text-white" : "text-slate-400 hover:text-white"}`}>
              {m === "sector" ? "🌐 Semua IHSG" : "🔍 Single"}
            </button>
          ))}
        </div>
        <AnimatePresence>
          {mode === "single" && (
            <motion.div key="inp" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden mb-4">
              <div className="relative">
                <Search className="absolute left-3 top-3.5 text-slate-400" size={15} />
                <input type="text" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="Kode saham (misal: ASII)"
                  className="w-full bg-black/30 border border-white/10 rounded-lg py-3 pl-9 pr-4 text-white font-mono font-bold focus:border-emerald-500 outline-none"
                  onKeyDown={e => e.key === "Enter" && startScan(mode, ticker)} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        <button onClick={() => startScan(mode, ticker)} disabled={scanStatus === "scanning"}
          className="w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-bold py-3 rounded-lg flex justify-center items-center gap-2 shadow-lg shadow-emerald-900/50 disabled:opacity-50">
          {scanStatus === "scanning" ? <RefreshCw size={18} className="animate-spin" /> : <Play size={18} />}
          {scanStatus === "scanning" ? "Memindai..." : "Jalankan Algoritma"}
        </button>
        <AnimatePresence>
          {scanStatus === "error" && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} className="mt-4 bg-red-500/10 border border-red-500/20 text-red-400 p-4 rounded-lg text-center text-sm font-mono">
              Terjadi kesalahan saat memuat hasil. (Status Error)
            </motion.div>
          )}
          {scanStatus === "scanning" && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="mt-4 text-center overflow-hidden">
              <div className="text-emerald-400 font-mono text-sm mb-2 font-bold">{progress.current}</div>
              <div className="h-1.5 bg-white/5 rounded-full overflow-hidden">
                <motion.div className="h-full bg-emerald-500" animate={{ width: `${progress.pct}%` }} transition={{ duration: 0.4 }} />
              </div>
              <div className="text-xs text-slate-500 mt-1 font-mono">
                {progress.done} / {progress.total} ({progress.pct}%)
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Summary */}
      {scanStatus === "done" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full">
          <div className="flex flex-wrap gap-4 mb-6 p-4 glass-card">
            <div className="text-center">
              <div className="text-3xl font-black text-emerald-400">{hpCount}</div>
              <div className="text-xs text-slate-400">🔥 High Probability</div>
            </div>
            <div className="w-px bg-white/10" />
            <div className="text-center">
              <div className="text-3xl font-black text-white">{results.length}</div>
              <div className="text-xs text-slate-400">Total Dianalisis</div>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {results.map((item, idx) => (
              <HPCard key={`${item.ticker}-${idx}`} item={item} idx={idx} />
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
