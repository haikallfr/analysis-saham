"use client";

import { useEffect, useState, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { 
  TrendingUp, TrendingDown, Activity, DollarSign, Target, 
  PieChart, Briefcase, RefreshCw, AlertCircle, Star
} from "lucide-react";

export interface StockData {
  error?: string;
  ticker?: string;
  name?: string;
  sector?: string;
  industry?: string;
  price?: number;
  market_cap?: number;
  pe?: number;
  pbv?: number;
  dps?: number;
  eps?: number;
  bvps?: number;
  eps_growth?: number;
  fundamentals?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  technical?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  accumulation?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  methods?: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  recommended_method?: string;
  recommendation_reason?: string;
  dcf?: any; // eslint-disable-line @typescript-eslint/no-explicit-any
  audit_flags?: string[];
  blended_fair_value?: number;
}

function StockDetailContent() {
  const searchParams = useSearchParams();
  const ticker = searchParams.get("ticker")?.toUpperCase() || "";

  const [data, setData] = useState<StockData | null>(null);
  const [loading, setLoading] = useState(!!ticker);
  const [error, setError] = useState(ticker ? "" : "Ticker tidak ditemukan. Harap sertakan ?ticker=KODE");

  useEffect(() => {
    if (!ticker) return;

    const fetchDetail = async () => {
      try {
        const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:5050";
        const res = await fetch(`${API}/api/stock/${ticker}`);
        const result = await res.json();
        
        if (result.status === "error" || result.error_msg) throw new Error(result.error_msg || "Data saham tidak ditemukan.");
        
        // We deliberately do not throw error here so partial data is still displayed
        setData(result);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Gagal memuat detail saham.");
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
  }, [ticker]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <RefreshCw className="animate-spin text-blue-500 mb-4" size={48} />
        <h2 className="text-xl text-slate-300 font-mono">Mengumpulkan Data {ticker}...</h2>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <AlertCircle className="text-red-500 mb-4" size={64} />
        <h2 className="text-2xl font-bold text-white mb-2">Oops!</h2>
        <p className="text-red-400">{error}</p>
        <button onClick={() => window.location.href = '/'} className="mt-6 text-blue-400 hover:text-blue-300 underline">
          Kembali ke Scanner
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { name, sector, price, market_cap, fundamentals, methods, dcf, technical, accumulation, recommended_method } = data;

  const formatRp = (val: number | string | null | undefined) => val ? `Rp ${Number(val).toLocaleString("id-ID")}` : "Data tidak tersedia";
  const formatPct = (val: number | null | undefined) => val !== null && val !== undefined ? `${val > 0 ? '+' : ''}${val.toFixed(1)}%` : "Data tidak tersedia";

  return (
    <div className="max-w-6xl mx-auto py-8 px-4">
      {/* Header Profile */}
      <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }} className="glass-card p-8 mb-8 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
          <Briefcase size={120} />
        </div>
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 relative z-10">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <h1 className="text-5xl font-black font-mono text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-violet-400">
                {ticker}
              </h1>
              <span className="px-3 py-1 rounded-full bg-white/10 text-slate-300 text-sm font-semibold border border-white/5">
                {sector}
              </span>
            </div>
            <h2 className="text-2xl text-slate-300 font-medium">{name}</h2>
          </div>
          <div className="text-left md:text-right">
            <div className="text-sm text-slate-400 mb-1">Harga Saat Ini</div>
            <div className="text-4xl font-black font-mono text-white mb-1">
              {formatRp(price)}
            </div>
            <div className="text-sm text-slate-400">
              Market Cap: <span className="text-white">{((market_cap || 0) / 1e12).toFixed(2)} Triliun</span>
            </div>
          </div>
        </div>
      </motion.div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Kolom Kiri: Fundamental & Teknis */}
        <div className="lg:col-span-1 flex flex-col gap-8">
          
          {/* Fundamental */}
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.1 }} className="glass-card p-6">
            <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2 border-b border-white/10 pb-2">
              <PieChart className="text-blue-400" size={20} /> Fundamental
            </h3>
            <div className="space-y-3 font-mono text-sm">
              <div className="flex justify-between">
                <span className="text-slate-400">EPS (Laba per Lembar)</span>
                <span className="text-white font-bold">{fundamentals?.eps !== null && fundamentals?.eps !== undefined ? fundamentals.eps.toFixed(2) : "Data tidak tersedia"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">BVPS (Nilai Buku)</span>
                <span className="text-white font-bold">{fundamentals?.bvps !== null && fundamentals?.bvps !== undefined ? fundamentals.bvps.toFixed(2) : "Data tidak tersedia"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">P/E Ratio</span>
                <span className="text-white font-bold">{fundamentals?.pe_ratio !== null && fundamentals?.pe_ratio !== undefined ? `${fundamentals.pe_ratio.toFixed(2)} x` : "Data tidak tersedia"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">P/BV Ratio</span>
                <span className="text-white font-bold">{fundamentals?.pb_ratio !== null && fundamentals?.pb_ratio !== undefined ? `${fundamentals.pb_ratio.toFixed(2)} x` : "Data tidak tersedia"}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Dividen (DPS)</span>
                <span className="text-white font-bold">{fundamentals?.dps !== null && fundamentals?.dps !== undefined ? fundamentals.dps.toFixed(2) : "Data tidak tersedia"}</span>
              </div>
            </div>
          </motion.div>

          {/* Teknis & Akumulasi */}
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.2 }} className="glass-card p-6">
            <h3 className="text-lg font-bold text-white mb-4 flex items-center gap-2 border-b border-white/10 pb-2">
              <Activity className="text-purple-400" size={20} /> Teknis & Akumulasi
            </h3>
            <div className="space-y-4 font-mono text-sm">
              <div>
                <div className="flex justify-between mb-1">
                  <span className="text-slate-400">Tren Jangka Menengah</span>
                  <span className={`font-bold ${technical?.trend === 'Bullish' ? 'text-emerald-400' : 'text-red-400'}`}>
                    {technical?.trend || "Data tidak tersedia"}
                  </span>
                </div>
                <div className="flex gap-2 text-xs text-slate-500">
                  <span>MA50: {formatRp(technical?.ma50)}</span>
                  <span>|</span>
                  <span>MA200: {formatRp(technical?.ma200)}</span>
                </div>
              </div>
              
              <div className="flex justify-between items-center border-t border-white/5 pt-3">
                <span className="text-slate-400">RSI (14)</span>
                <span className={`font-bold ${
                  technical?.rsi < 30 ? 'text-emerald-400' : technical?.rsi > 70 ? 'text-red-400' : 'text-blue-400'
                }`}>
                  {technical?.rsi !== null && technical?.rsi !== undefined ? technical.rsi.toFixed(1) : "Data tidak tersedia"}
                </span>
              </div>

              <div className="border-t border-white/5 pt-3">
                <div className="flex justify-between mb-2">
                  <span className="text-slate-400">Akumulasi (OBV)</span>
                  <span className={`font-bold ${
                    accumulation?.score >= 60 ? 'text-emerald-400' : accumulation?.score <= 40 ? 'text-red-400' : 'text-amber-400'
                  }`}>
                    {accumulation?.signal || "Data tidak tersedia"}
                  </span>
                </div>
                <div className="h-2 w-full bg-white/5 rounded-full overflow-hidden">
                  <div 
                    className={`h-full rounded-full ${accumulation?.score >= 60 ? 'bg-emerald-500' : accumulation?.score <= 40 ? 'bg-red-500' : 'bg-amber-500'}`}
                    style={{ width: `${accumulation?.score || 0}%` }}
                  />
                </div>
              </div>
            </div>
          </motion.div>

        </div>

        {/* Kolom Kanan: Valuasi */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.3 }} className="glass-card p-6 h-full">
            <h3 className="text-xl font-bold text-white mb-6 flex items-center gap-2 border-b border-white/10 pb-3">
              <DollarSign className="text-emerald-400" size={24} /> Model Valuasi & Harga Wajar
            </h3>
            
            {data?.audit_flags && data.audit_flags.length > 0 && (
              <div className="mb-4 space-y-2">
                {data.audit_flags.map((flag: string, idx: number) => (
                  <div key={idx} className="bg-red-500/10 border border-red-500/20 text-red-400 p-3 rounded-lg text-sm flex items-start gap-2">
                    <AlertCircle size={16} className="mt-0.5 shrink-0" />
                    <span>{flag}</span>
                  </div>
                ))}
              </div>
            )}

            {data?.blended_fair_value && (
              <div className="mb-6 bg-gradient-to-r from-emerald-500/20 to-blue-500/20 border border-emerald-500/30 rounded-xl p-5 flex items-center justify-between">
                <div>
                  <h4 className="text-emerald-400 font-bold flex items-center gap-2">
                    <Target size={20} /> Konsensus Nilai Wajar (Blended)
                  </h4>
                  <p className="text-xs text-slate-400 mt-1">Gabungan 60% Model Intrinsik + 40% Relatif Terbaik</p>
                </div>
                <div className="text-2xl font-black font-mono text-white">
                  {formatRp(data.blended_fair_value)}
                </div>
              </div>
            )}
            
            <div className="grid gap-4">
              {Object.entries(methods || {}).map(([method, data]: [string, any]) => {
                const mos = data?.margin_of_safety;
                const price_val = data?.valuation_price;
                const isUndervalued = mos > 0;
                const isValid = data?.is_applicable && price_val !== null && price_val !== undefined;

                return (
                  <div 
                    key={method} 
                    className={`rounded-xl p-4 flex flex-col sm:flex-row items-center justify-between gap-4 transition-colors ${
                      method === recommended_method 
                        ? 'bg-gradient-to-r from-amber-500/20 to-transparent border border-amber-500/40 ring-1 ring-amber-500/20 shadow-[0_0_20px_rgba(245,158,11,0.1)]'
                        : 'bg-black/30 border border-white/5 hover:bg-white/5'
                    }`}
                  >
                    <div className="flex items-center gap-3 w-full sm:w-auto">
                      <div className={`p-2 rounded-lg ${
                        method === recommended_method ? 'bg-amber-500/20 text-amber-400' : (isValid ? 'bg-blue-500/20 text-blue-400' : 'bg-slate-800 text-slate-500')
                      }`}>
                        {method === recommended_method ? <Star size={20} className="fill-amber-400" /> : <Target size={20} />}
                      </div>
                      <div>
                        <div className="font-bold text-white flex items-center gap-2">
                          {data?.label || `${method} Model`}
                          {method === recommended_method && (
                            <div className="bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded text-[10px] uppercase flex items-center gap-1 border border-amber-500/30" title="Model Valuasi Terbaik">
                              Terbaik
                            </div>
                          )}
                        </div>
                        <div className="text-xs text-slate-400">{data?.formula || "Harga Wajar Estimasi"}</div>
                      </div>
                    </div>

                    <div className="flex items-center justify-between sm:justify-end gap-6 w-full sm:w-auto">
                      <div className="text-left sm:text-right">
                        <div className="text-xl font-mono font-black text-white">
                          {isValid ? formatRp(price_val) : "-"}
                        </div>
                      </div>
                      
                      <div className={`flex flex-col items-end min-w-[80px]`}>
                        <div className="text-xs text-slate-400 mb-1">Margin of Safety</div>
                        {isValid ? (
                          <div className={`flex items-center gap-1 px-2 py-1 rounded text-sm font-bold border
                            ${isUndervalued ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' : 'bg-red-500/10 text-red-400 border-red-500/20'}`}>
                            {isUndervalued ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                            {formatPct(mos)}
                          </div>
                        ) : (
                          <span className="text-slate-500 text-[10px] sm:text-xs max-w-[120px] text-right leading-tight">
                            {data?.not_applicable_reason || "Data tidak tersedia"}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

          </motion.div>
        </div>
      </div>
    </div>
  );
}

export default function StockDetailPage() {
  return (
    <Suspense fallback={
      <div className="flex flex-col items-center justify-center min-h-[60vh]">
        <RefreshCw className="animate-spin text-blue-500 mb-4" size={48} />
      </div>
    }>
      <StockDetailContent />
    </Suspense>
  );
}
