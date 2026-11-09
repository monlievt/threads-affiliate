"use client";

import React, { useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
  CartesianGrid,
} from "recharts";
import {
  Play,
  CheckCircle2,
  XCircle,
  Plus,
  Sparkles,
  AlertTriangle,
  Trophy,
  ArrowRight,
  TrendingUp,
  Clock,
} from "lucide-react";
import {
  useAllocateNextArm,
  useExperimentDetails,
  useExperimentEvaluation,
  useExperimentProgress,
  useExperimentsList,
} from "@/hooks/useExperiments";
import CreateExperimentModal from "./CreateExperimentModal";

export default function ExperimentsTab() {
  const { data: experiments = [], isLoading, updateStatus, isUpdatingStatus } = useExperimentsList();
  const [selectedExpId, setSelectedExpId] = useState<string | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [nextArmSuggestion, setNextArmSuggestion] = useState<string | null>(null);

  // Active or selected experiment
  const activeExp =
    experiments.find((e) => e.id === selectedExpId) ||
    experiments.find((e) => e.status === "running") ||
    experiments[0];

  const currentExpId = activeExp?.id || null;

  const { data: progress } = useExperimentProgress(currentExpId);
  const { data: evaluation } = useExperimentEvaluation(currentExpId);
  const allocateMutation = useAllocateNextArm(currentExpId);

  const handleStatusChange = async (newStatus: string) => {
    if (!currentExpId) return;
    try {
      await updateStatus({ id: currentExpId, newStatus });
    } catch (err: any) {
      alert(err?.message || "Gagal mengubah status eksperimen.");
    }
  };

  const handleAllocateNext = async () => {
    if (!currentExpId) return;
    try {
      const res = await allocateMutation.mutateAsync({});
      if (res.has_eligible_arm && res.recommended_arm) {
        setNextArmSuggestion(`Gunakan Arm: "${res.recommended_arm.label}" (${res.reason})`);
      } else {
        setNextArmSuggestion(res.reason);
      }
    } catch (err: any) {
      setNextArmSuggestion("Gagal mendapatkan alokasi.");
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center p-12 text-slate-400 text-xs">
        Memuat data eksperimen...
      </div>
    );
  }

  // Format chart data from evaluation or progress
  const chartData = (evaluation?.arms || []).map((a) => ({
    name: a.label,
    "Views 72h (Median)": a.median_views_72,
    "ER 72h (%)": Math.round(a.median_er_72 * 1000) / 10, // converted to %
    n: a.n,
  }));

  return (
    <div className="space-y-6">
      {/* Header & Experiment Selector */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <label className="text-xs font-semibold text-slate-500">Pilih Eksperimen:</label>
          <select
            value={currentExpId || ""}
            onChange={(e) => setSelectedExpId(e.target.value)}
            className="px-3 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-xs font-medium text-slate-900 dark:text-slate-100"
          >
            {experiments.map((e) => (
              <option key={e.id} value={e.id}>
                [{e.status.toUpperCase()}] {e.name} ({e.phase})
              </option>
            ))}
          </select>
        </div>

        <button
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold shadow-sm transition-colors self-start sm:self-auto"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Buat Eksperimen Baru</span>
        </button>
      </div>

      {!activeExp ? (
        <div className="p-8 text-center border border-dashed border-slate-300 dark:border-slate-800 rounded-xl">
          <Sparkles className="w-8 h-8 mx-auto text-slate-400 mb-2" />
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">Belum Ada Eksperimen</h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
            Mulai Fase 1 dengan menguji 3 niche kandidat menggunakan satu gaya tetap (curator) untuk menemukan ceruk audiens terbaik.
          </p>
          <button
            onClick={() => setIsModalOpen(true)}
            className="px-4 py-2 rounded-md bg-indigo-600 text-white text-xs font-semibold"
          >
            Buka Wizard Eksperimen
          </button>
        </div>
      ) : (
        <>
          {/* Active Experiment Card */}
          <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 dark:border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">{activeExp.name}</h2>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      activeExp.status === "running"
                        ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300"
                        : activeExp.status === "completed"
                        ? "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300"
                        : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    {activeExp.status}
                  </span>
                  <span className="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] font-mono">
                    Fase: {activeExp.phase}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Mulai: {activeExp.start_date} · Total Target: {progress?.total_target_posts || 0} postingan · Progres Keseluruhan: {progress?.overall_progress_pct || 0}%
                </p>
              </div>

              {/* Status Action Buttons */}
              <div className="flex items-center gap-2">
                {activeExp.status === "planned" && (
                  <button
                    onClick={() => handleStatusChange("running")}
                    disabled={isUpdatingStatus}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-sm transition-colors"
                  >
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Mulai Uji Coba</span>
                  </button>
                )}

                {activeExp.status === "running" && (
                  <>
                    <button
                      onClick={() => handleStatusChange("completed")}
                      disabled={isUpdatingStatus}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Tandai Selesai</span>
                    </button>
                    <button
                      onClick={() => handleStatusChange("aborted")}
                      disabled={isUpdatingStatus}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-rose-300 text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/40 text-xs font-semibold transition-colors"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>Gugurkan</span>
                    </button>
                  </>
                )}
              </div>
            </div>

            {/* Arm Progress Cards */}
            <div>
              <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 mb-3 uppercase tracking-wider">
                Papan Lengan Uji (Arms) & Sampel n
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {(progress?.arms || []).map((arm) => {
                  const evalArm = evaluation?.arms.find((a) => a.arm_id === arm.arm_id);
                  const isInsufficient = evalArm ? evalArm.insufficient_data : arm.published_posts < 8;

                  return (
                    <div
                      key={arm.arm_id}
                      className="p-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 space-y-2.5"
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-slate-900 dark:text-slate-100">{arm.label}</span>
                        {isInsufficient ? (
                          <span className="px-2 py-0.5 rounded-full bg-amber-100 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 text-[10px] font-bold flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            <span>Data Kurang (n &lt; 8)</span>
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 text-[10px] font-bold">
                            Valid (n ≥ 8)
                          </span>
                        )}
                      </div>

                      <div className="flex items-baseline justify-between text-xs text-slate-500">
                        <span>Sampel Selesai (72j):</span>
                        <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                          {arm.metrics_completed_72h} / {arm.target_posts} post
                        </span>
                      </div>

                      {/* Progress Bar */}
                      <div className="w-full bg-slate-200 dark:bg-slate-700 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                          style={{ width: `${Math.min(100, arm.progress_pct)}%` }}
                        />
                      </div>

                      <div className="flex items-center justify-between text-[11px] text-slate-400 pt-1">
                        <span>Total Draf: {arm.total_drafts}</span>
                        <span>Terbit: {arm.published_posts}</span>
                        <span>{arm.progress_pct}%</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* rule_v1 Decision Recommendation Panel */}
          {evaluation && (
            <div
              className={`p-5 rounded-xl border ${
                evaluation.recommendation === "winner_found"
                  ? "bg-emerald-50/60 dark:bg-emerald-950/20 border-emerald-200 dark:border-emerald-800/60"
                  : evaluation.recommendation === "no_clear_winner"
                  ? "bg-blue-50/60 dark:bg-blue-950/20 border-blue-200 dark:border-blue-800/60"
                  : "bg-amber-50/60 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800/60"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    {evaluation.recommendation === "winner_found" ? (
                      <div className="p-1.5 rounded-md bg-emerald-600 text-white">
                        <Trophy className="w-4 h-4" />
                      </div>
                    ) : evaluation.recommendation === "no_clear_winner" ? (
                      <div className="p-1.5 rounded-md bg-blue-600 text-white">
                        <TrendingUp className="w-4 h-4" />
                      </div>
                    ) : (
                      <div className="p-1.5 rounded-md bg-amber-600 text-white">
                        <AlertTriangle className="w-4 h-4" />
                      </div>
                    )}
                    <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                      Rekomendasi Keputusan rule_v1:{" "}
                      {evaluation.recommendation === "winner_found"
                        ? "Pemenang Teridentifikasi!"
                        : evaluation.recommendation === "no_clear_winner"
                        ? "Belum Ada Pemenang Jelas"
                        : "Data Kurang (Sampel Belum Mencukupi)"}
                    </h3>
                  </div>

                  <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed font-medium">
                    {evaluation.explanation}
                  </p>

                  <div className="text-[11px] text-slate-500 space-x-3 pt-1">
                    <span>Formula: 0.4·ER72 + 0.4·ClickRate + 0.2·Views72 (median)</span>
                    <span>·</span>
                    <span>Ambang Menang: ≥ 1.25x runner-up</span>
                  </div>
                </div>

                {evaluation.recommendation === "no_clear_winner" && (
                  <button
                    onClick={() => alert(`Rekomendasi: Tambahkan target ${evaluation.recommended_extension_posts} draf baru.`)}
                    className="shrink-0 px-3 py-1.5 rounded-md bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold shadow-sm transition-colors"
                  >
                    Perpanjang Uji (+{evaluation.recommended_extension_posts} post)
                  </button>
                )}
              </div>

              {/* Outliers Warning if any */}
              {evaluation.arms.some((a) => a.outliers_views.length > 0 || a.outliers_er.length > 0) && (
                <div className="mt-3 p-3 rounded-lg bg-amber-100/70 dark:bg-amber-900/40 border border-amber-300 dark:border-amber-800 text-[11px] text-amber-900 dark:text-amber-200">
                  <span className="font-bold">Penanda Outlier Viral (&gt; 3x Median):</span> Ditemukan postingan
                  dengan lonjakan drastis. Skor evaluasi terlindung karena menggunakan nilai <strong>median</strong>,
                  namun operator disarankan meninjau konten outlier tersebut secara manual untuk inspirasi materi hook berikutnya.
                </div>
              )}
            </div>
          )}

          {/* Comparison Recharts Chart */}
          <div className="p-5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm space-y-3">
            <h3 className="text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wider">
              Grafik Perbandingan Metrik Median per Arm (72 Jam)
            </h3>
            {chartData.length === 0 ? (
              <div className="h-48 flex items-center justify-center text-xs text-slate-400">
                Belum ada postingan berumur 72 jam dengan metrik lengkap.
              </div>
            ) : (
              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="left" orientation="left" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} unit="%" />
                    <Tooltip
                      contentStyle={{
                        fontSize: "12px",
                        backgroundColor: "#1e293b",
                        border: "none",
                        borderRadius: "8px",
                        color: "#fff",
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: "11px", paddingTop: "10px" }} />
                    <Bar yAxisId="left" dataKey="Views 72h (Median)" fill="#6366f1" radius={[4, 4, 0, 0]} />
                    <Bar yAxisId="right" dataKey="ER 72h (%)" fill="#10b981" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Next Arm Generator Helper */}
          {activeExp.status === "running" && (
            <div className="p-4 rounded-xl border border-indigo-100 dark:border-indigo-950 bg-indigo-50/40 dark:bg-indigo-950/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
              <div className="space-y-0.5">
                <div className="font-bold text-indigo-950 dark:text-indigo-200 flex items-center gap-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                  <span>Perencana Alokasi Konten Otomatis (Anti-Streak)</span>
                </div>
                <p className="text-slate-600 dark:text-slate-400">
                  {nextArmSuggestion || "Rekomendasikan arm dengan jadwal berimbang dan rotasi niche berikutnya."}
                </p>
              </div>
              <button
                onClick={handleAllocateNext}
                disabled={allocateMutation.isPending}
                className="px-3 py-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 text-white font-semibold flex items-center gap-1 self-start sm:self-auto shrink-0 transition-colors"
              >
                <span>{allocateMutation.isPending ? "Menghitung..." : "Alokasikan Arm"}</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}
        </>
      )}

      {/* Modal Wizard */}
      <CreateExperimentModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onSuccess={() => {
          setIsModalOpen(false);
        }}
      />
    </div>
  );
}
