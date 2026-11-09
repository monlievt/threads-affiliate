"use client";

import React from "react";
import { AlertCircle, Info } from "lucide-react";

interface Props {
  className?: string;
}

export default function ClickAttributionBanner({ className = "" }: Props) {
  return (
    <div
      className={`flex items-start gap-3 p-4 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800/60 text-amber-900 dark:text-amber-200 text-xs leading-relaxed ${className}`}
    >
      <AlertCircle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
      <div>
        <span className="font-bold tracking-tight block mb-0.5">
          Caveat Atribusi Klik Benable (Wajib Diperhatikan):
        </span>
        <p className="text-amber-800 dark:text-amber-300/90">
          Data klik dari Benable hanya dapat diatribusikan ke <strong>produk + periode waktu</strong>, bukan ke post spesifik.
          Data klik menunjukkan <em>performa produk dalam periode ini</em>, bukan performa per post individual.
          Hindari menarik kesimpulan kausalitas antar-post individual hanya berdasarkan metrik klik.
        </p>
      </div>
    </div>
  );
}
