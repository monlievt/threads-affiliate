"use client";

import React, { useState } from "react";
import { Check, X, Info } from "lucide-react";
import { ValidatorReportData } from "@/types";

const RULE_DESCRIPTIONS: Record<string, string> = {
  "V-LEN": "Panjang karakter <= batas gaya (maks 500)",
  "V-DISC": "Klausul disclosure afiliasi wajib ada",
  "V-LINK": "Link allowlist resmi (benable.com), maks 1, tanpa pemendek",
  "V-PRICE": "Bebas angka harga, simbol mata uang, diskon %, atau obral/sale",
  "V-CLAIM": "Tanpa klaim medis/kesehatan palsu, jaminan hasil, atau rating karangan",
  "V-URGE": "Tanpa urgensi palsu ('only 3 left', 'ends tonight')",
  "V-SENS": "Bebas konten dewasa, politik, anak di bawah umur, atau sensitif",
  "V-ENG": "Tanpa umpan engagement terlarang ('follow to win', giveaway liar)",
  "V-REPEAT": "Tanpa pengulangan kalimat pembuka identik dalam 10 posting terakhir",
  "V-MISC": "Tanpa tag akun tanpa izin, hashtag maks 2, tanpa karakter zero-width",
};

export default function ValidatorBadgeList({
  report,
}: {
  report: ValidatorReportData | null;
}) {
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null);

  if (!report || !report.results) {
    return (
      <div className="flex items-center gap-1.5 text-[11px] text-slate-400">
        <span>Validator: Belum dievaluasi</span>
      </div>
    );
  }

  const allRules = Object.keys(RULE_DESCRIPTIONS);

  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        {allRules.map((code) => {
          const ruleResult = report.results[code];
          const isValid = ruleResult ? ruleResult.valid : true;
          const shortCode = code.replace("V-", "");

          return (
            <div key={code} className="relative">
              <button
                type="button"
                onClick={() => setActiveTooltip(activeTooltip === code ? null : code)}
                onMouseEnter={() => setActiveTooltip(code)}
                onMouseLeave={() => setActiveTooltip(null)}
                className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono font-bold transition-colors ${
                  isValid
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800"
                    : "bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-400 border border-rose-300 dark:border-rose-800 animate-pulse"
                }`}
                title={ruleResult?.reason || RULE_DESCRIPTIONS[code]}
              >
                {isValid ? (
                  <Check className="w-2.5 h-2.5 stroke-[3]" />
                ) : (
                  <X className="w-2.5 h-2.5 stroke-[3]" />
                )}
                <span>{shortCode}</span>
              </button>

              {/* Explanatory Tooltip on hover/click */}
              {activeTooltip === code && (
                <div className="absolute bottom-full left-0 mb-1 z-30 w-52 p-2 bg-slate-900 text-white text-[10px] rounded shadow-lg border border-slate-700 pointer-events-none">
                  <div className="font-bold flex items-center justify-between border-b border-slate-700 pb-1 mb-1">
                    <span>{code}</span>
                    <span className={isValid ? "text-emerald-400" : "text-rose-400"}>
                      {isValid ? "Lolos" : "Melanggar"}
                    </span>
                  </div>
                  <p className="text-slate-300">{RULE_DESCRIPTIONS[code]}</p>
                  {ruleResult?.reason && !isValid && (
                    <p className="text-rose-300 font-semibold mt-1">
                      Catatan: {ruleResult.reason}
                    </p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
