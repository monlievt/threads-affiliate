"use client";

import React, { useState } from "react";
import {
  Plus,
  Upload,
  FileSpreadsheet,
  ExternalLink,
  Archive,
  Edit2,
  AlertCircle,
  CheckCircle2,
  AlertTriangle,
  Tag,
  Search,
  Check,
} from "lucide-react";
import {
  useProducts,
  useNiches,
  useCreateProduct,
  useUpdateProduct,
  useArchiveProduct,
  usePreviewProductsCSV,
  useImportProductsCSV,
} from "@/hooks/useCatalog";
import { validateProductUrl } from "@/lib/api";
import { ProductItem, ProductImportResponse } from "@/types";

export default function ProductTab() {
  const [selectedNiche, setSelectedNiche] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [searchQuery, setSearchQuery] = useState<string>("");

  const { data: niches = [] } = useNiches(false);
  const {
    data: products = [],
    isLoading,
    error,
  } = useProducts({
    niche_id: selectedNiche || undefined,
    status: statusFilter || undefined,
    include_archived: statusFilter === "archived",
  });

  const createMutation = useCreateProduct();
  const updateMutation = useUpdateProduct();
  const archiveMutation = useArchiveProduct();
  const previewMutation = usePreviewProductsCSV();
  const importMutation = useImportProductsCSV();

  // Create / Edit Modal State
  const [productModalOpen, setProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<ProductItem | null>(null);
  const [formNicheId, setFormNicheId] = useState("");
  const [formTitle, setFormTitle] = useState("");
  const [formBenableUrl, setFormBenableUrl] = useState("");
  const [formAmazonRef, setFormAmazonRef] = useState("");
  const [formBenefits, setFormBenefits] = useState("");
  const [formTags, setFormTags] = useState("");
  const [formStatus, setFormStatus] = useState<"active" | "paused" | "archived">("active");
  const [urlCheckStatus, setUrlCheckStatus] = useState<{
    checked: boolean;
    valid: boolean;
    message?: string;
  } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  // CSV Import Modal State
  const [csvModalOpen, setCsvModalOpen] = useState(false);
  const [csvContent, setCsvContent] = useState("");
  const [csvPreviewResult, setCsvPreviewResult] = useState<ProductImportResponse | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [importSuccessMessage, setImportSuccessMessage] = useState<string | null>(null);

  // Prohibited price regex check
  const priceRegex = /([$€£¥]|\b\d+(\.\d{1,2})?\s*(usd|dollars|bucks|cents)\b|\b\d+%\s*off\b|\b(sale|discount|price|cheap|promo)\b)/i;
  const titleHasPrice = priceRegex.test(formTitle);
  const benefitsHasPrice = priceRegex.test(formBenefits);

  const handleOpenCreate = () => {
    setEditingProduct(null);
    setFormNicheId(niches[0]?.id || "");
    setFormTitle("");
    setFormBenableUrl("");
    setFormAmazonRef("");
    setFormBenefits("");
    setFormTags("");
    setFormStatus("active");
    setUrlCheckStatus(null);
    setFormError(null);
    setProductModalOpen(true);
  };

  const handleOpenEdit = (p: ProductItem) => {
    setEditingProduct(p);
    setFormNicheId(p.niche_id);
    setFormTitle(p.title);
    setFormBenableUrl(p.benable_url);
    setFormAmazonRef(p.amazon_ref_url || "");
    setFormBenefits(p.benefits.join("; "));
    setFormTags(p.tags.join(", "));
    setFormStatus(p.status);
    setUrlCheckStatus({ checked: true, valid: true });
    setFormError(null);
    setProductModalOpen(true);
  };

  const handleCheckUrl = async () => {
    if (!formBenableUrl.trim()) {
      setUrlCheckStatus({ checked: true, valid: false, message: "URL tidak boleh kosong." });
      return;
    }
    try {
      const res = await validateProductUrl(formBenableUrl.trim());
      if (res.valid) {
        setUrlCheckStatus({ checked: true, valid: true, message: "URL Benable valid (HTTPS benable.com)" });
      } else {
        setUrlCheckStatus({ checked: true, valid: false, message: res.error || "Domain URL tidak valid." });
      }
    } catch (err: any) {
      setUrlCheckStatus({ checked: true, valid: false, message: err.message || "Gagal memverifikasi URL." });
    }
  };

  const handleSubmitProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    if (titleHasPrice || benefitsHasPrice) {
      setFormError("Pelanggaran Kebijakan Nol Harga (V-PRICE): Judul atau manfaat mengandung angka harga, simbol mata uang, atau kata diskon.");
      return;
    }

    const benefitsList = formBenefits
      .split(/[;\n]/)
      .map((b) => b.trim())
      .filter(Boolean);

    const tagsList = formTags
      .split(/[,;\n]/)
      .map((t) => t.trim())
      .filter(Boolean);

    try {
      if (editingProduct) {
        await updateMutation.mutateAsync({
          id: editingProduct.id,
          data: {
            niche_id: formNicheId,
            title: formTitle.trim(),
            benable_url: formBenableUrl.trim(),
            amazon_ref_url: formAmazonRef.trim() || undefined,
            benefits: benefitsList,
            tags: tagsList,
            status: formStatus,
          },
        });
      } else {
        await createMutation.mutateAsync({
          niche_id: formNicheId,
          title: formTitle.trim(),
          benable_url: formBenableUrl.trim(),
          amazon_ref_url: formAmazonRef.trim() || undefined,
          benefits: benefitsList,
          tags: tagsList,
        });
      }
      setProductModalOpen(false);
    } catch (err: any) {
      setFormError(err.message || "Gagal menyimpan produk.");
    }
  };

  const handleArchive = async (p: ProductItem) => {
    if (confirm(`Arsipkan produk "${p.title}"? Status akan diubah menjadi 'archived'.`)) {
      try {
        await archiveMutation.mutateAsync(p.id);
      } catch (err: any) {
        alert(err.message || "Gagal mengarsipkan produk.");
      }
    }
  };

  // CSV Import handlers
  const handleOpenCsvModal = () => {
    setCsvContent("");
    setCsvPreviewResult(null);
    setCsvError(null);
    setImportSuccessMessage(null);
    setCsvModalOpen(true);
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = event.target?.result as string;
      setCsvContent(text);
      setCsvPreviewResult(null);
      setCsvError(null);
    };
    reader.readAsText(file);
  };

  const handlePreviewCsv = async () => {
    if (!csvContent.trim()) {
      setCsvError("Konten CSV kosong. Pilih file atau tempel isi CSV.");
      return;
    }
    setCsvError(null);
    try {
      const res = await previewMutation.mutateAsync(csvContent);
      setCsvPreviewResult(res);
    } catch (err: any) {
      setCsvError(err.message || "Gagal melakukan pratinjau CSV.");
    }
  };

  const handleConfirmImport = async () => {
    if (!csvContent.trim()) return;
    setCsvError(null);
    try {
      const res = await importMutation.mutateAsync(csvContent);
      setImportSuccessMessage(
        `Sukses mengimpor ${res.imported_count} produk! (${res.failed_count} baris galat dilewati).`
      );
      setTimeout(() => {
        setCsvModalOpen(false);
      }, 1800);
    } catch (err: any) {
      setCsvError(err.message || "Gagal mengimpor CSV.");
    }
  };

  const filteredProducts = products.filter((p) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      p.title.toLowerCase().includes(q) ||
      (p.niche_name && p.niche_name.toLowerCase().includes(q)) ||
      p.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-6">
      {/* Top Header & Actions */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            Katalog Produk Afiliasi (Benable)
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400">
            Koleksi produk yang disetujui untuk dijadikan materi postingan Threads.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleOpenCsvModal}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 transition-colors"
          >
            <FileSpreadsheet className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Impor CSV</span>
          </button>
          <button
            onClick={handleOpenCreate}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-900 hover:bg-slate-800 text-white dark:bg-white dark:text-slate-900 dark:hover:bg-slate-100 transition-colors shadow-xs"
          >
            <Plus className="w-4 h-4" />
            <span>Tambah Produk</span>
          </button>
        </div>
      </div>

      {/* Filters & Search */}
      <div className="flex flex-col sm:flex-row items-center justify-between gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          {/* Niche Filter */}
          <select
            value={selectedNiche}
            onChange={(e) => setSelectedNiche(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-hidden"
          >
            <option value="">Semua Niche</option>
            {niches.map((n) => (
              <option key={n.id} value={n.id}>
                {n.name}
              </option>
            ))}
          </select>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-hidden"
          >
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="archived">Archived</option>
          </select>
        </div>

        {/* Search */}
        <div className="relative w-full sm:w-64">
          <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
          <input
            type="text"
            placeholder="Cari judul atau tag..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-200 focus:outline-hidden"
          />
        </div>
      </div>

      {/* Products Table */}
      {isLoading ? (
        <div className="p-8 text-center text-sm text-slate-500 animate-pulse">
          Memuat katalog produk...
        </div>
      ) : error ? (
        <div className="p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Gagal memuat produk: {(error as any).message}</span>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
          <table className="w-full text-left text-xs text-slate-600 dark:text-slate-300">
            <thead className="bg-slate-50 dark:bg-slate-800/60 text-slate-500 dark:text-slate-400 font-semibold border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="py-3 px-4">Judul Produk</th>
                <th className="py-3 px-4">Niche</th>
                <th className="py-3 px-4">Tautan Benable</th>
                <th className="py-3 px-4">Manfaat & Tag</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Aksi</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {filteredProducts.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-slate-400">
                    Tidak ada produk ditemukan. Tambahkan atau impor dari CSV.
                  </td>
                </tr>
              ) : (
                filteredProducts.map((p) => (
                  <tr key={p.id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3.5 px-4 font-medium text-slate-900 dark:text-slate-100 max-w-xs">
                      <div>{p.title}</div>
                      {p.last_used_at && (
                        <span className="text-[10px] text-slate-400 block mt-0.5">
                          Terakhir dipakai: {p.last_used_at.slice(0, 10)}
                        </span>
                      )}
                    </td>
                    <td className="py-3.5 px-4">
                      <span className="inline-block px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
                        {p.niche_name || "Niche"}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 max-w-xs">
                      <a
                        href={p.benable_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-slate-900 dark:text-slate-200 hover:underline font-mono text-[11px]"
                      >
                        <span className="truncate max-w-[180px]">{p.benable_url}</span>
                        <ExternalLink className="w-3 h-3 shrink-0 text-slate-400" />
                      </a>
                    </td>
                    <td className="py-3.5 px-4 max-w-xs">
                      <div className="flex flex-wrap gap-1">
                        {p.tags.slice(0, 3).map((tag, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-sm text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400"
                          >
                            <Tag className="w-2.5 h-2.5" />
                            {tag}
                          </span>
                        ))}
                        {p.tags.length > 3 && (
                          <span className="text-[10px] text-slate-400">+{p.tags.length - 3}</span>
                        )}
                      </div>
                    </td>
                    <td className="py-3.5 px-4">
                      <span
                        className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                          p.status === "active"
                            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-400"
                            : p.status === "paused"
                            ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-400"
                            : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400"
                        }`}
                      >
                        {p.status}
                      </span>
                    </td>
                    <td className="py-3.5 px-4 text-right space-x-1">
                      <button
                        onClick={() => handleOpenEdit(p)}
                        className="p-1 rounded-md text-slate-500 hover:text-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800 dark:hover:text-slate-200 transition-colors"
                        title="Edit Produk"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                      {p.status !== "archived" && (
                        <button
                          onClick={() => handleArchive(p)}
                          className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                          title="Arsipkan Produk"
                        >
                          <Archive className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal: Tambah / Edit Produk */}
      {productModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs overflow-y-auto">
          <div className="w-full max-w-lg rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                {editingProduct ? "Edit Produk Afiliasi" : "Tambah Produk Afiliasi Baru"}
              </h3>
            </div>
            <form onSubmit={handleSubmitProduct} className="p-6 space-y-4">
              {formError && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs">
                  {formError}
                </div>
              )}

              {/* Zero Price Warning Banner */}
              {(titleHasPrice || benefitsHasPrice) && (
                <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                  <span>
                    <strong>Peringatan Kebijakan Nol Harga (V-PRICE):</strong> Jangan sertakan angka harga, mata uang ($), atau klaim diskon/sale. Afiliasi Threads mengutamakan kurasi nilai, bukan penawaran harga.
                  </span>
                </div>
              )}

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Niche Terkait <span className="text-red-500">*</span>
                </label>
                <select
                  required
                  value={formNicheId}
                  onChange={(e) => setFormNicheId(e.target.value)}
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                >
                  <option value="" disabled>Pilih Niche...</option>
                  {niches.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Judul Produk <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder="Misal: Solid Walnut Dual Monitor Riser with Storage"
                  className={`w-full px-3 py-2 text-xs rounded-lg border ${
                    titleHasPrice ? "border-amber-400 bg-amber-50/30" : "border-slate-300 dark:border-slate-700"
                  } bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden`}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  URL Benable (HTTPS Wajib) <span className="text-red-500">*</span>
                </label>
                <div className="flex gap-2">
                  <input
                    type="url"
                    required
                    value={formBenableUrl}
                    onChange={(e) => {
                      setFormBenableUrl(e.target.value);
                      setUrlCheckStatus(null);
                    }}
                    placeholder="https://benable.com/list/xyz atau https://benable.com/item/123"
                    className="flex-1 px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                  />
                  <button
                    type="button"
                    onClick={handleCheckUrl}
                    className="px-3 py-2 text-xs font-medium rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 transition-colors"
                  >
                    Cek URL
                  </button>
                </div>
                {urlCheckStatus && (
                  <p
                    className={`mt-1 text-[11px] flex items-center gap-1 ${
                      urlCheckStatus.valid ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"
                    }`}
                  >
                    {urlCheckStatus.valid ? <CheckCircle2 className="w-3 h-3" /> : <AlertCircle className="w-3 h-3" />}
                    <span>{urlCheckStatus.message}</span>
                  </p>
                )}
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Amazon Reference URL (Opsional, Hanya untuk Referensi Internal)
                </label>
                <input
                  type="url"
                  value={formAmazonRef}
                  onChange={(e) => setFormAmazonRef(e.target.value)}
                  placeholder="https://amazon.com/dp/xyz (tidak akan pernah diposting ke Threads)"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Poin Manfaat / Fitur Utama (Pisahkan dengan titik koma &apos;;&apos;)
                </label>
                <textarea
                  rows={2}
                  value={formBenefits}
                  onChange={(e) => setFormBenefits(e.target.value)}
                  placeholder="Ergonomic neck relief; Integrated cable routing; Solid hardwood construction"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Tag / Kata Kunci (Pisahkan dengan koma)
                </label>
                <input
                  type="text"
                  value={formTags}
                  onChange={(e) => setFormTags(e.target.value)}
                  placeholder="desk-setup, ergonomics, walnut, monitor-stand"
                  className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              {editingProduct && (
                <div>
                  <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                    Status
                  </label>
                  <select
                    value={formStatus}
                    onChange={(e) => setFormStatus(e.target.value as any)}
                    className="w-full px-3 py-2 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100"
                  >
                    <option value="active">Active</option>
                    <option value="paused">Paused</option>
                    <option value="archived">Archived</option>
                  </select>
                </div>
              )}

              <div className="pt-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setProductModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  Batal
                </button>
                <button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending || titleHasPrice || benefitsHasPrice}
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:bg-slate-800 dark:hover:bg-slate-100 transition-colors disabled:opacity-50"
                >
                  {createMutation.isPending || updateMutation.isPending ? "Menyimpan..." : "Simpan Produk"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Impor CSV dengan Pratinjau & Laporan Galat */}
      {csvModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs overflow-y-auto">
          <div className="w-full max-w-2xl rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden my-8">
            <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  Impor Katalog Produk dari CSV
                </h3>
              </div>
              <button
                onClick={() => setCsvModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 text-xs"
              >
                Tutup
              </button>
            </div>

            <div className="p-6 space-y-4 max-h-[80vh] overflow-y-auto">
              {/* Instructions & Prohibited Price Alert */}
              <div className="p-3 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs text-slate-600 dark:text-slate-300 space-y-1.5">
                <p className="font-semibold text-slate-900 dark:text-slate-100">
                  Format Header CSV yang Didukung:
                </p>
                <code className="block p-2 rounded-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 font-mono text-[11px] text-slate-800 dark:text-slate-200">
                  title,niche,benable_url,benefits,tags
                </code>
                <p className="text-[11px] text-amber-700 dark:text-amber-400">
                  ⚠️ <strong>Kebijakan Nol Harga Ketat:</strong> CSV dilarang memiliki kolom harga (price, discount, sale, promo). Jika terdeteksi, seluruh berkas akan langsung ditolak untuk kepatuhan akun.
                </p>
              </div>

              {/* Upload or Paste */}
              <div>
                <label className="block text-xs font-medium text-slate-700 dark:text-slate-300 mb-1">
                  Pilih File CSV (.csv) atau Tempel Konten Teks
                </label>
                <div className="flex items-center gap-3 mb-2">
                  <label className="cursor-pointer inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-xs font-medium text-slate-700 dark:text-slate-200 transition-colors">
                    <Upload className="w-3.5 h-3.5" />
                    <span>Pilih Berkas CSV</span>
                    <input
                      type="file"
                      accept=".csv,text/csv"
                      onChange={handleFileUpload}
                      className="hidden"
                    />
                  </label>
                  <span className="text-[11px] text-slate-400">atau tempel langsung di bawah:</span>
                </div>
                <textarea
                  rows={4}
                  value={csvContent}
                  onChange={(e) => {
                    setCsvContent(e.target.value);
                    setCsvPreviewResult(null);
                    setCsvError(null);
                  }}
                  placeholder="title,niche,benable_url,benefits,tags&#10;Dual Monitor Stand,Desk Setup,https://benable.com/p/stand,Ergonomic,desk;ergonomics"
                  className="w-full px-3 py-2 font-mono text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-hidden"
                />
              </div>

              {/* Action: Pratinjau Impor */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handlePreviewCsv}
                  disabled={previewMutation.isPending || !csvContent.trim()}
                  className="px-3.5 py-2 text-xs font-medium rounded-lg bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 transition-colors disabled:opacity-50"
                >
                  {previewMutation.isPending ? "Menganalisis CSV..." : "Pratinjau Impor (Dry Run)"}
                </button>
              </div>

              {/* CSV Error */}
              {csvError && (
                <div className="p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{csvError}</span>
                </div>
              )}

              {/* Success Message */}
              {importSuccessMessage && (
                <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 shrink-0" />
                  <span>{importSuccessMessage}</span>
                </div>
              )}

              {/* Preview Report Card */}
              {csvPreviewResult && (
                <div className="space-y-4 pt-2 border-t border-slate-100 dark:border-slate-800">
                  {/* Summary Bar */}
                  <div className="grid grid-cols-3 gap-2">
                    <div className="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800 text-center">
                      <div className="text-[10px] text-slate-400">Total Baris</div>
                      <div className="text-base font-bold text-slate-900 dark:text-slate-100">
                        {csvPreviewResult.total_rows}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/30 text-center border border-emerald-200 dark:border-emerald-800/40">
                      <div className="text-[10px] text-emerald-700 dark:text-emerald-400 font-medium">Valid (Siap Impor)</div>
                      <div className="text-base font-bold text-emerald-700 dark:text-emerald-400">
                        {csvPreviewResult.imported_count}
                      </div>
                    </div>
                    <div className="p-2.5 rounded-lg bg-red-50 dark:bg-red-950/30 text-center border border-red-200 dark:border-red-800/40">
                      <div className="text-[10px] text-red-700 dark:text-red-400 font-medium">Galat (Dilewati)</div>
                      <div className="text-base font-bold text-red-700 dark:text-red-400">
                        {csvPreviewResult.failed_count}
                      </div>
                    </div>
                  </div>

                  {/* Errors Report */}
                  {csvPreviewResult.errors.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-xs font-semibold text-red-600 dark:text-red-400 flex items-center gap-1">
                        <AlertCircle className="w-3.5 h-3.5" />
                        <span>Laporan Galat Baris:</span>
                      </div>
                      <div className="max-h-36 overflow-y-auto rounded-lg border border-red-200 dark:border-red-900 bg-red-50/50 dark:bg-red-950/20 p-2 text-[11px] space-y-1">
                        {csvPreviewResult.errors.map((err, idx) => (
                          <div key={idx} className="text-red-800 dark:text-red-300">
                            <strong>Baris {err.row}:</strong> {err.title ? `[${err.title}] ` : ""}{err.reason}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Valid Products Preview Table */}
                  {csvPreviewResult.imported_products.length > 0 && (
                    <div className="space-y-1.5">
                      <div className="text-xs font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                        <Check className="w-3.5 h-3.5" />
                        <span>Pratinjau Baris Valid:</span>
                      </div>
                      <div className="max-h-36 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 text-[11px]">
                        <table className="w-full text-left">
                          <thead className="bg-slate-50 dark:bg-slate-800 text-slate-500 font-medium">
                            <tr>
                              <th className="py-1 px-2">Judul</th>
                              <th className="py-1 px-2">Niche</th>
                              <th className="py-1 px-2">URL Benable</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                            {csvPreviewResult.imported_products.map((p, idx) => (
                              <tr key={idx}>
                                <td className="py-1 px-2 truncate max-w-[180px] font-medium">{p.title}</td>
                                <td className="py-1 px-2 text-slate-500">{p.niche_name || "Niche"}</td>
                                <td className="py-1 px-2 text-slate-400 truncate max-w-[200px]">{p.benable_url}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Bottom Actions */}
              <div className="pt-2 flex items-center justify-end gap-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setCsvModalOpen(false)}
                  className="px-3.5 py-2 text-xs font-medium rounded-lg text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800 transition-colors"
                >
                  Tutup
                </button>
                <button
                  type="button"
                  onClick={handleConfirmImport}
                  disabled={
                    importMutation.isPending ||
                    !csvPreviewResult ||
                    csvPreviewResult.imported_count === 0
                  }
                  className="px-4 py-2 text-xs font-medium rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  {importMutation.isPending ? "Mengimpor..." : `Konfirmasi Impor (${csvPreviewResult?.imported_count || 0} Produk)`}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
