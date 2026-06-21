"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { TrendingUp, Search, RefreshCw, AlertCircle } from "lucide-react";

export default function ComparePage() {
  const [tickers, setTickers] = useState("");
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<any[]>([]); // eslint-disable-line @typescript-eslint/no-explicit-any
  const [error, setError] = useState("");

  const handleCompare = async () => {
    if (!tickers.trim()) return;
    setLoading(true);
    setError("");
    setData([]);

    try {
      const res = await fetch(`http://127.0.0.1:5050/api/compare?tickers=${encodeURIComponent(tickers)}`);
      const result = await res.json();
      if (result.error) throw new Error(result.error);
      setData(result.data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Gagal memuat data komparasi");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-col items-center max-w-7xl mx-auto mt-8">
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="text-center mb-8 w-full">
        <h1 className="text-4xl font-extrabold text-white mb-2 flex items-center justify-center gap-3">
          <TrendingUp className="text-purple-400" size={36} /> Perbandingan Saham
        </h1>
        <p className="text-slate-400">Bandingkan valuasi dan fundamental hingga 4 saham secara berdampingan.</p>
      </motion.div>

      <div className="w-full glass-card p-6 mb-8 max-w-3xl">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-3.5 text-slate-400" size={18} />
            <input 
              type="text" 
              value={tickers} onChange={e => setTickers(e.target.value)}
              placeholder="Misal: BBCA, BBRI, BMRI, BBNI"
              className="w-full bg-black/30 border border-white/10 rounded-lg py-3 pl-10 pr-4 text-white font-mono uppercase focus:border-purple-500 outline-none transition-colors"
              onKeyDown={e => e.key === 'Enter' && handleCompare()}
            />
          </div>
          <button 
            onClick={handleCompare} disabled={loading || !tickers.trim()}
            className="bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white font-bold py-3 px-8 rounded-lg flex justify-center items-center gap-2 shadow-lg shadow-purple-900/50 disabled:opacity-50"
          >
            {loading ? <RefreshCw className="animate-spin" size={20} /> : "Bandingkan"}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg flex items-center gap-2 mb-8">
          <AlertCircle size={20} /> {error}
        </div>
      )}

      {data.length > 0 && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full overflow-x-auto glass-card p-0">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr>
                <th className="p-4 border-b border-white/10 bg-white/5 text-slate-400 font-bold w-48">METRIK</th>
                {data.map(d => (
                  <th key={d.ticker} className="p-4 border-b border-white/10 bg-white/5">
                    <div className="text-2xl font-black font-mono text-purple-400">{d.ticker}</div>
                    <div className="text-xs text-slate-400">{d.sector}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="text-sm font-mono">
              <tr>
                <td className="p-4 border-b border-white/5 text-slate-400">Harga Saat Ini</td>
                {data.map(d => <td key={d.ticker} className="p-4 border-b border-white/5 text-white">{d.price ? `Rp ${d.price.toLocaleString('id-ID')}` : 'Data tidak tersedia'}</td>)}
              </tr>
              <tr>
                <td className="p-4 border-b border-white/5 text-slate-400">Market Cap</td>
                {data.map(d => <td key={d.ticker} className="p-4 border-b border-white/5 text-white">{d.market_cap ? `${(d.market_cap / 1e12).toFixed(1)} T` : 'Data tidak tersedia'}</td>)}
              </tr>
              <tr>
                <td className="p-4 border-b border-white/5 text-slate-400">P/E Ratio</td>
                {data.map(d => <td key={d.ticker} className="p-4 border-b border-white/5 text-white">{d.fundamentals?.pe_ratio !== null && d.fundamentals?.pe_ratio !== undefined ? d.fundamentals.pe_ratio.toFixed(2) : 'Data tidak tersedia'}</td>)}
              </tr>
              <tr>
                <td className="p-4 border-b border-white/5 text-slate-400">P/BV Ratio</td>
                {data.map(d => <td key={d.ticker} className="p-4 border-b border-white/5 text-white">{d.fundamentals?.pb_ratio !== null && d.fundamentals?.pb_ratio !== undefined ? d.fundamentals.pb_ratio.toFixed(2) : 'Data tidak tersedia'}</td>)}
              </tr>
              <tr>
                <td className="p-4 border-b border-white/5 text-slate-400">Graham Number</td>
                {data.map(d => {
                  const mos = d.methods?.Graham?.margin_of_safety;
                  const isGood = mos > 0;
                  return (
                    <td key={d.ticker} className="p-4 border-b border-white/5">
                      <div className="text-white mb-1">{d.methods?.Graham?.valuation_price ? `Rp ${d.methods.Graham.valuation_price.toLocaleString('id-ID')}` : 'Data tidak tersedia'}</div>
                      {mos !== undefined && (
                        <span className={`px-2 py-0.5 rounded text-xs font-bold ${isGood ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}`}>
                          {mos > 0 ? '+' : ''}{mos.toFixed(1)}%
                        </span>
                      )}
                    </td>
                  )
                })}
              </tr>
              <tr>
                <td className="p-4 text-slate-400">Technical Trend</td>
                {data.map(d => (
                  <td key={d.ticker} className={`p-4 font-bold uppercase ${d.technical?.trend === 'bullish' ? 'text-green-400' : 'text-red-400'}`}>
                    {d.technical?.trend || 'Data tidak tersedia'}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </motion.div>
      )}
    </div>
  );
}
