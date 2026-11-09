"use client";

import React, { useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Legend,
} from "recharts";
import {
  RefreshCw,
  Download,
  Eye,
  Heart,
  MessageCircle,
  Repeat2,
  Quote,
  ExternalLink,
  Search,
  Filter,
} from "lucide-react";
import { useAccountGrowth, useAnalyticsOverview } from "@/hooks/useAnalytics";

export default function PerformanceTab() {
  const { data: overview, isLoading, triggerCollect, isCollecting } = useAnalyticsOverview();
  const { data: snapshots = [] } = useAccountGrowth();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedNiche, setSelectedNiche] = useState("all");

  const handleManualCollect = async () => {
    try {
      const res = await triggerCollect();
      alert(`Metrik berhasil ditarik: ${res.metrics_saved} bucket baru disimpan.`);
    } catch (err: any) {
      alert(err?.message || "Gagal menarik metrik.");
    }
  };

  const handleExportCsv = () => {
    if (!overview?.recent_posts || overview.recent_posts.length === 0) {
      alert("Tidak ada data untuk diekspor.");
      return;
    }

    const headers = [
      "Post ID",
      "Published At",
      "Niche",
      "Style",
      "Product",
      "Latest Views",
      "Latest Likes",
      "Latest Replies",
      "Latest Reposts",
      "Text Snippet",
    ];

    const rows = overview.recent_posts.map((p) => [
      p.post_id,
      p.published_at,
      p.niche_name || "",
      p.style_name || "",
      p.product_title || "",
      p.latest_views,
      p.latest_likes,
      p.latest_replies,
      p.latest_reposts,
      `"${p.text_snippet.replace(/"/g, '""')}"`,
    ]);

    const csvContent =
      "data:text/csv;charset=utf-8," +
      [headers.join(","), ...rows.map((r) => r.join(","))].join("\n");

    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `threads_analytics_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-slate-400 text-xs">
        Memuat analytics performa...
      </div>
    );
  }

  // Filter posts
  const filteredPosts = (overview?.recent_posts || []).filter((p) => {
    const matchesSearch =
      p.text_snippet.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (p.product_title || "").toLowerCase().includes(searchQuery.toLowerCase());
    const matchesNiche = selectedNiche === "all" || p.niche_name === selectedNiche;
    return matchesSearch && matchesNiche;
  });

  const availableNiches = Array.from(
    new Set((overview?.recent_posts || []).map((p) => p.niche_name).filter(Boolean))
  ) as string[];

  // Growth chart data
  const growthChartData = snapshots.map((s) => ({
    time: s.captured_at.slice(5, 10),
    Followers: s.followers || 0,
    "Profile Views": s.profile_views || 0,
  }));

  return (
    <div className="space-y-6">
      {/* KPI Cards & Trigger Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
          Ringkasan Metrik Terbit
        </h2>
        <div className="flex items-center gap-2">
          <button
            onClick={handleManualCollect}
            disabled={isCollecting}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isCollecting ? "animate-spin text-indigo-600" : ""}`} />
            <span>{isCollecting ? "Menarik..." : "Tarik Metrik Sekarang"}</span>
          </button>
          <button
            onClick={handleExportCsv}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-900 dark:bg-white text-white dark:text-slate-900 hover:bg-slate-800 text-xs font-semibold shadow-sm transition-colors"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Ekspor CSV</span>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <span className="text-[11px] font-medium text-slate-500">Post Terbit</span>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {overview?.total_posts_published || 0}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <Eye className="w-3.5 h-3.5 text-indigo-500" />
            <span>Total Views</span>
          </div>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {(overview?.total_views || 0).toLocaleString()}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <Heart className="w-3.5 h-3.5 text-rose-500" />
            <span>Total Likes</span>
          </div>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {(overview?.total_likes || 0).toLocaleString()}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1">
          <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <MessageCircle className="w-3.5 h-3.5 text-blue-500" />
            <span>Total Replies</span>
          </div>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {(overview?.total_replies || 0).toLocaleString()}
          </div>
        </div>
        <div className="p-4 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-1 col-span-2 sm:col-span-1">
          <div className="flex items-center gap-1 text-[11px] font-medium text-slate-500">
            <Repeat2 className="w-3.5 h-3.5 text-emerald-500" />
            <span>Total Reposts</span>
          </div>
          <div className="text-xl font-black text-slate-900 dark:text-slate-100">
            {(overview?.total_reposts || 0).toLocaleString()}
          </div>
        </div>
      </div>

      {/* Account Growth Chart */}
      {growthChartData.length > 0 && (
        <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-3">
          <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
            Tren Pertumbuhan Akun (Followers & Profile Views)
          </h3>
          <div className="h-56 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={growthChartData} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                <XAxis dataKey="time" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    fontSize: "12px",
                    backgroundColor: "#1e293b",
                    border: "none",
                    borderRadius: "8px",
                    color: "#fff",
                  }}
                />
                <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "5px" }} />
                <Line type="monotone" dataKey="Followers" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
                <Line type="monotone" dataKey="Profile Views" stroke="#10b981" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Posts Table */}
      <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
            Daftar Postingan Terbit & Metrik per Bucket
          </h3>

          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Cari konten atau produk..."
                className="pl-8 pr-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-900 dark:text-slate-100 w-44 sm:w-56"
              />
            </div>

            {availableNiches.length > 0 && (
              <select
                value={selectedNiche}
                onChange={(e) => setSelectedNiche(e.target.value)}
                className="px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs text-slate-700 dark:text-slate-300"
              >
                <option value="all">Semua Niche</option>
                {availableNiches.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            )}
          </div>
        </div>

        {filteredPosts.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-400">
            Tidak ada postingan terbit yang sesuai filter.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-200 dark:border-slate-800 text-slate-500 font-semibold">
                  <th className="py-2.5 px-3">Postingan & Produk</th>
                  <th className="py-2.5 px-3">Niche / Gaya</th>
                  <th className="py-2.5 px-3">Terbit (Waktu)</th>
                  <th className="py-2.5 px-3 text-right">Views</th>
                  <th className="py-2.5 px-3 text-right">Likes</th>
                  <th className="py-2.5 px-3 text-right">Replies</th>
                  <th className="py-2.5 px-3 text-right">Reposts</th>
                  <th className="py-2.5 px-3 text-center">Tautan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {filteredPosts.map((p) => (
                  <tr key={p.post_id} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-2.5 px-3 max-w-xs">
                      <div className="font-medium text-slate-900 dark:text-slate-100 truncate">
                        {p.text_snippet}
                      </div>
                      {p.product_title && (
                        <div className="text-[10px] text-indigo-600 dark:text-indigo-400 truncate">
                          Produk: {p.product_title}
                        </div>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-slate-600 dark:text-slate-400 whitespace-nowrap">
                      <div>{p.niche_name || "—"}</div>
                      <div className="text-[10px] text-slate-400 font-mono">{p.style_name || "—"}</div>
                    </td>
                    <td className="py-2.5 px-3 text-slate-500 whitespace-nowrap font-mono text-[11px]">
                      {p.published_at ? p.published_at.slice(0, 16).replace("T", " ") : "—"}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono font-bold text-slate-800 dark:text-slate-200">
                      {p.latest_views.toLocaleString()}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-600 dark:text-slate-400">
                      {p.latest_likes}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-600 dark:text-slate-400">
                      {p.latest_replies}
                    </td>
                    <td className="py-2.5 px-3 text-right font-mono text-slate-600 dark:text-slate-400">
                      {p.latest_reposts}
                    </td>
                    <td className="py-2.5 px-3 text-center">
                      {p.permalink ? (
                        <a
                          href={p.permalink}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-1 rounded text-slate-400 hover:text-indigo-600 inline-block"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      ) : (
                        <span className="text-slate-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
