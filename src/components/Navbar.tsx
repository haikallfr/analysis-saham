"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { LayoutDashboard, TrendingUp, BarChart2, CheckCircle } from "lucide-react";

export default function Navbar() {
  const pathname = usePathname();

  const links = [
    { href: "/", label: "Scanner", icon: LayoutDashboard },
    { href: "/heatmap", label: "Heatmap", icon: BarChart2 },
    { href: "/compare", label: "Compare", icon: TrendingUp },
  ];

  return (
    <header className="sticky top-0 z-50 w-full glass-card border-x-0 border-t-0 rounded-none mb-8 px-6 py-4 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center font-bold text-white shadow-lg">
          V
        </div>
        <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-400">
          ValueScanner
        </h1>
      </div>
      
      <nav className="flex gap-2">
        {links.map((link) => {
          const Icon = link.icon;
          const isActive = pathname === link.href;
          
          return (
            <Link
              key={link.href}
              href={link.href}
              className={`relative px-4 py-2 rounded-full text-sm font-medium transition-colors flex items-center gap-2
                ${isActive ? "text-white" : "text-slate-400 hover:text-white hover:bg-white/5"}`}
            >
              <Icon size={16} />
              {link.label}
              {isActive && (
                <motion.div
                  layoutId="navbar-indicator"
                  className="absolute inset-0 border border-blue-500/50 bg-blue-500/10 rounded-full -z-10"
                  transition={{ type: "spring", stiffness: 300, damping: 30 }}
                />
              )}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
