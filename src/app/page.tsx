"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Search, AlertCircle, RefreshCw, TrendingUp, TrendingDown, Award } from "lucide-react";

const API = "http://127.0.0.1:5050";

type ScanStatus = "idle" | "scanning" | "done" | "error";

function useScan(pageMode: "sector" | "single") {
  const [scanStatus, setScanStatus] = useState<ScanStatus>("idle");
  const [progress, setProgress]     = useState({ done: 0, total: 0, current: "", pct: 0 });
  const [results, setResults]       = useState<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [errorMsg, setErrorMsg]     = useState("");
  
  // Track current session so stale callbacks don't interfere
  const activeSessionRef = useRef<string | null>(null);
  const pollRef          = useRef<ReturnType<typeof setInterval> | null>(null);
  const evtRef           = useRef<EventSource | null>(null);

  const stopAll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (evtRef.current)  { evtRef.current.close(); evtRef.current = null; }
  };

  const fetchResults = async (sid: string) => {
    if (activeSessionRef.current !== sid) return;
    stopAll();
    setProgress(p => ({ ...p, current: "Fetching API..." }));
    try {
      const res  = await fetch(`${API}/api/results?session_id=${sid}&t=${Date.now()}`);
      setProgress(p => ({ ...p, current: "API fetched, parsing JSON..." }));
      const data = await res.json();
      setProgress(p => ({ ...p, current: "JSON parsed, sorting..." }));
      const all  = (data.results || []) as any[]; // eslint-disable-line @typescript-eslint/no-explicit-any
      all.sort((a, b) => (b.margin_of_safety ?? -9999) - (a.margin_of_safety ?? -9999));
      setResults(all);
      setProgress(p => ({ ...p, current: "Done!" }));
      setScanStatus("done");
    } catch (e: unknown) {
      setScanStatus("error");
      setProgress(p => ({ ...p, current: "Error fetchResults: " + (e instanceof Error ? e.message : String(e)) }));
    }
  };

  const startPolling = (sessionId: string) => {
    // Stop any existing poll
    stopAll();
    activeSessionRef.current = sessionId;

    // SSE connection disabled to prevent browser connection exhaustion (Max 6 concurrent connections)
    // const evt = new EventSource(`${API}/api/stream?session_id=${sessionId}&t=${Date.now()}`);
    // evtRef.current = evt;
    // evt.onmessage = (e) => {
    //   if (activeSessionRef.current !== sessionId) { evt.close(); return; }
    //   try {
    //     const msg   = JSON.parse(e.data);
    //     const total = msg.total  ?? msg.data?.total  ?? 0;
    //     const done  = msg.done   ?? msg.data?.index  ?? 0;
    //     const tkr   = msg.ticker ?? msg.data?.ticker ?? "";
    //
    //     if (msg.type === "start") {
    //       setProgress(p => ({ ...p, total, current: "Inisialisasi..." }));
    //     } else if (msg.type === "progress") {
    //       const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    //       setProgress({ done, total, current: tkr, pct });
    //     } else if (msg.type === "done") {
    //       evt.close();
    //       setProgress(p => ({ ...p, current: "Menerima event done, fetchResults..." }));
    //       fetchResults(sessionId);
    //     } else if (msg.type === "error") {
    //       evt.close();
    //       if (activeSessionRef.current === sessionId) setScanStatus("idle");
    //     }
    //   } catch {}
    // };
    // evt.onerror = () => {};

    // Fallback polling
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
          fetchResults(sessionId);
        } else if (d.status === "cancelled" || d.status === "error") {
          stopAll();
          if (activeSessionRef.current === sessionId) setScanStatus("idle");
        } else if (d.total) {
          setProgress(p => {
            if (d.progress_count > p.done) {
              const pct = Math.round((d.progress_count / d.total) * 100);
              return { ...p, done: d.progress_count, total: d.total, pct, current: d.ticker || p.current };
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
      setErrorMsg("");
      setProgress({ done: 0, total: 0, current: "Memulai...", pct: 0 });

      const res  = await fetch(`${API}/api/scan-advanced`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode, ticker: ticker.toUpperCase() }),
      });
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      startPolling(data.session_id);
    } catch (e: unknown) {
      setScanStatus("error");
      setErrorMsg(e instanceof Error ? e.message : "Gagal memulai scan");
    }
  };

  // Cleanup on unmount
  useEffect(() => () => stopAll(), []);

  return { scanStatus, progress, results, errorMsg, startScan };
}

function MosBadge({ mos }: { mos: number | null }) {
  if (mos === null) return <span className="text-slate-500 text-xs">—</span>;
  const pos = mos > 0;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-bold border
      ${pos ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30" : "bg-red-500/10 text-red-400 border-red-500/20"}`}>
      {pos ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
      {pos ? "+" : ""}{mos.toFixed(1)}%
    </span>
  );
}

function ResultCard({ item, idx }: { item: any; idx: number }) { // eslint-disable-line @typescript-eslint/no-explicit-any
  const ok  = item.status === "ok";
  const mos = item.margin_of_safety;

  return (
    <motion.a
      href={`/stock?ticker=${item.ticker}`}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: idx * 0.03, duration: 0.3 }}
      className={`glass-card p-5 flex flex-col gap-3 cursor-pointer border-t-2 no-underline
        ${ok && mos && mos > 20 ? "border-t-emerald-500 hover:shadow-emerald-900/30"
          : ok && mos && mos > 0 ? "border-t-blue-500 hover:shadow-blue-900/30"
          : "border-t-slate-700 hover:shadow-slate-900/30"}
        hover:shadow-xl hover:-translate-y-1 transition-all duration-200`}
    >
      {/* Header */}
      <div className="flex justify-between items-start">
        <div>
          <div className="text-xl font-black font-mono text-white">{item.ticker}</div>
          <div className="text-slate-400 text-sm font-mono">
            Rp {item.current_price?.toLocaleString("id-ID") ?? "—"}
          </div>
        </div>
        <MosBadge mos={mos} />
      </div>

      {!ok ? (
        <div className="text-xs text-slate-500 italic">{item.error_msg || "Data tidak tersedia"}</div>
      ) : (
        <>
          {/* Harga Wajar (Model Terbaik) */}
          <div className="flex justify-between items-center text-sm bg-gradient-to-r from-amber-500/20 to-amber-900/20 border border-amber-500/30 rounded-lg p-2 mb-3">
            <span className="text-amber-200/90 font-medium">Wajar ({item.method})</span>
            <span className="font-mono text-amber-100 font-bold">Rp {item.valuation_price?.toLocaleString("id-ID")}</span>
          </div>

          {/* Metrics */}
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <div className="flex justify-between">
              <span className="text-slate-500">EPS</span>
              <span className="font-mono text-slate-300">{item.eps ? item.eps.toFixed(0) : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">BVPS</span>
              <span className="font-mono text-slate-300">{item.bvps ? item.bvps.toFixed(0) : "—"}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">EPS Growth</span>
              <span className={`font-mono ${(item.eps_growth ?? 0) > 0 ? "text-emerald-400" : "text-red-400"}`}>
                {item.eps_growth != null ? `${item.eps_growth > 0 ? "+" : ""}${item.eps_growth.toFixed(1)}%` : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">DPS</span>
              <span className="font-mono text-slate-300">{item.dps ? item.dps.toFixed(0) : "—"}</span>
            </div>
          </div>

          {/* Sektor */}
          <div className="mt-auto">
            <span className="text-xs text-slate-500 uppercase tracking-wider">{item.sector}</span>
          </div>
        </>
      )}
    </motion.a>
  );
}

export default function ScannerPage() {
  const [mode,   setMode]   = useState<"sector" | "single">("sector");
  const [ticker, setTicker] = useState("");
  const { scanStatus, progress, results, errorMsg, startScan } = useScan(mode);

  const handleStart = () => {
    if (mode === "single" && !ticker.trim()) return;
    startScan(mode, ticker.trim());
  };

  const ok     = results.filter(r => r.status === "ok");
  const cheap  = ok.filter(r => (r.margin_of_safety ?? 0) > 10);
  const errors = results.filter(r => r.status !== "ok");

  return (
    <div className="flex flex-col items-center max-w-5xl mx-auto mt-8">
      {/* Hero */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/10 border border-blue-500/20 text-blue-400 text-xs font-bold uppercase tracking-widest mb-4">
          <Award size={12} /> IDX Advanced Screener
        </div>
        <h1 className="text-4xl md:text-5xl font-extrabold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 via-purple-400 to-amber-400 mb-3">
          IDX Value Scanner
        </h1>
        <p className="text-slate-400 text-base max-w-xl mx-auto leading-relaxed">
          Mesin screening valuasi otomatis menggunakan Graham, P/E, P/BV, DDM, Peter Lynch, dan DCF.
          Mendukung seluruh <span className="text-white font-semibold">±160 emiten IHSG</span>.
        </p>
      </motion.div>

      {/* Control Card */}
      <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} className="glass-card w-full max-w-2xl p-6 mb-8">
        {/* Mode Toggle */}
        <div className="flex bg-black/30 p-1 rounded-lg mb-5">
          {(["sector", "single"] as const).map(m => (
            <button key={m} onClick={() => setMode(m)}
              className={`flex-1 py-2 rounded-md font-semibold text-sm transition-all
                ${mode === m ? "bg-blue-600 text-white shadow-md" : "text-slate-400 hover:text-white"}`}>
              {m === "sector" ? "🌐 Semua Sektor (±160 Saham)" : "🔍 Single Ticker"}
            </button>
          ))}
        </div>

        <AnimatePresence>
          {mode === "single" && (
            <motion.div key="input" initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden mb-4">
              <div className="relative">
                <Search className="absolute left-3 top-3.5 text-slate-400" size={16} />
                <input type="text" value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
                  placeholder="Kode saham (BBCA, ASII, TLKM...)"
                  className="w-full bg-black/30 border border-white/10 rounded-lg py-3 pl-9 pr-4 text-white font-mono font-bold tracking-widest focus:border-blue-500 outline-none transition-colors"
                  onKeyDown={e => e.key === "Enter" && handleStart()} />
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button onClick={handleStart} disabled={scanStatus === "scanning"}
          className="w-full bg-gradient-to-r from-blue-600 to-violet-600 hover:from-blue-500 hover:to-violet-500 text-white font-bold py-3 rounded-lg flex items-center justify-center gap-2 shadow-lg shadow-violet-900/40 disabled:opacity-50 transition-all hover:shadow-xl">
          {scanStatus === "scanning" ? <RefreshCw size={18} className="animate-spin" /> : <Play size={18} />}
          {scanStatus === "scanning" ? `Menganalisis ${progress.current}...` : "Mulai Scan"}
        </button>

        {/* Progress */}
        <AnimatePresence>
          {scanStatus === "scanning" && (
            <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden mt-5 text-center">
              <div className="text-sm text-slate-300 mb-2">
                Memproses <span className="font-mono font-bold text-blue-400">{progress.current}</span>
              </div>
              <div className="h-1.5 bg-white/5 rounded-full overflow-hidden mb-2">
                <motion.div className="h-full rounded-full bg-gradient-to-r from-blue-500 to-violet-500"
                  animate={{ width: `${progress.pct}%` }} transition={{ duration: 0.4 }} />
              </div>
              <div className="text-xs font-mono text-slate-500">
                {progress.done} / {progress.total} saham ({progress.pct}%)
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Error */}
        {scanStatus === "error" && (
          <div className="mt-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 flex items-center gap-2 text-sm">
            <AlertCircle size={16} /> {errorMsg}
          </div>
        )}
      </motion.div>

      {/* Results */}
      {scanStatus === "done" && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full">
          {/* Summary Bar */}
          <div className="flex flex-wrap gap-4 mb-6 p-4 glass-card">
            <div className="text-center">
              <div className="text-2xl font-black text-white">{results.length}</div>
              <div className="text-xs text-slate-400">Total Dipindai</div>
            </div>
            <div className="w-px bg-white/10" />
            <div className="text-center">
              <div className="text-2xl font-black text-emerald-400">{cheap.length}</div>
              <div className="text-xs text-slate-400">Undervalued (&gt;10% MoS)</div>
            </div>
            <div className="w-px bg-white/10" />
            <div className="text-center">
              <div className="text-2xl font-black text-blue-400">{ok.length}</div>
              <div className="text-xs text-slate-400">Data Berhasil</div>
            </div>
            <div className="w-px bg-white/10" />
            <div className="text-center">
              <div className="text-2xl font-black text-slate-500">{errors.length}</div>
              <div className="text-xs text-slate-400">Gagal / Partial</div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {results.map((item, idx) => (
              <ResultCard key={`${item.ticker}-${idx}`} item={item} idx={idx} />
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}
