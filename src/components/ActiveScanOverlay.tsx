"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Activity, X, AlertTriangle, CheckCircle, ExternalLink } from "lucide-react";
import Link from "next/link";

export default function ActiveScanOverlay() {
  const [status, setStatus] = useState<any>(null); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    // Poll global status every 3 seconds
    const interval = setInterval(async () => {
      try {
        const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5050";
        const res = await fetch(`${API}/api/global-status?t=${Date.now()}`);
        const data = await res.json();
        if (data.active) {
          setStatus(data);
        } else {
          setStatus(null);
        }
      } catch {
        // silently ignore polling errors
      }
    }, 3000);

    return () => clearInterval(interval);
  }, []);

  const handleCancelOrDismiss = async (isCancel: boolean) => {
    if (!status?.session_id) return;
    if (isCancel) setCanceling(true);
    
    try {
      const endpoint = isCancel ? "/api/cancel-scan" : "/api/dismiss-scan";
      const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5050";
      await fetch(`${API}${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: status.session_id })
      });
      setStatus(null);
    } catch {
      if (isCancel) alert("Gagal membatalkan proses.");
    } finally {
      if (isCancel) setCanceling(false);
    }
  };

  const isDone = status?.status === "done";
  const targetPage = "/";

  return (
    <AnimatePresence>
      {status && (
        <motion.div
          initial={{ opacity: 0, y: 50, x: -20 }}
          animate={{ opacity: 1, y: 0, x: 0 }}
          exit={{ opacity: 0, y: 50, scale: 0.9 }}
          className={`fixed bottom-6 left-6 z-50 glass-card p-4 rounded-xl shadow-2xl border max-w-sm w-full flex flex-col gap-3 transition-colors duration-500
            ${isDone ? "border-emerald-500/50 shadow-emerald-900/20" : "border-blue-500/30 shadow-blue-900/20"}`}
        >
          <div className="flex items-center justify-between">
            <div className={`flex items-center gap-2 font-bold text-sm ${isDone ? "text-emerald-400" : "text-blue-400"}`}>
              {isDone ? <CheckCircle size={16} /> : <Activity size={16} className="animate-pulse" />}
              {isDone ? "Proses Selesai" : "Proses Celery Berjalan"}
            </div>
            <button
              onClick={() => handleCancelOrDismiss(!isDone)}
              disabled={canceling}
              className={`text-slate-400 transition-colors bg-white/5 p-1.5 rounded-md ${isDone ? "hover:text-emerald-400 hover:bg-emerald-500/10" : "hover:text-red-400 hover:bg-red-500/10"}`}
              title={isDone ? "Tutup" : "Batalkan Proses"}
            >
              <X size={16} />
            </button>
          </div>

          <div className="text-xs text-slate-300 flex items-center justify-between">
            <div>
              <span className="text-white font-mono font-bold bg-white/10 px-1.5 py-0.5 rounded mr-1">
                {status.ticker || "Menganalisis"}
              </span>
              <span>
                {status.mode === "single" ? "Single Ticker Scan" : "Full IHSG Scan"}
              </span>
            </div>
          </div>

          {!isDone ? (
            <>
              <div className="w-full bg-black/40 rounded-full h-1.5 overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-blue-500 to-violet-500"
                  animate={{ width: `${status.total > 0 ? (status.progress_count / status.total) * 100 : 0}%` }}
                  transition={{ duration: 0.5 }}
                />
              </div>

              <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono">
                <span>{status.progress_count} / {status.total}</span>
                {status.total > 0 && (
                  <span>{Math.round((status.progress_count / status.total) * 100)}%</span>
                )}
              </div>

              {status.mode !== "single" && (
                <div className="mt-1 flex items-start gap-1.5 text-[10px] text-amber-500/80 bg-amber-500/10 p-2 rounded">
                  <AlertTriangle size={12} className="shrink-0 mt-0.5" />
                  Proses ini akan memblokir scan lain sampai selesai atau dibatalkan.
                </div>
              )}
            </>
          ) : (
            <div className="mt-2">
              <Link
                href={targetPage}
                onClick={() => handleCancelOrDismiss(false)}
                className="w-full flex items-center justify-center gap-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/50 py-2 rounded-lg font-bold text-sm transition-colors"
              >
                Lihat Hasil <ExternalLink size={14} />
              </Link>
            </div>
          )}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
