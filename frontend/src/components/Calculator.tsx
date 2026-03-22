"use client";

import { useState } from "react";
import { BarChart3, AlertCircle, ChevronRight, RotateCcw } from "lucide-react";
import { EXPOSURE_CATEGORIES, CategoryConfig, EntityTypeConfig } from "@/lib/exposureConfig";
import ExposureForm from "@/components/ExposureForm";
import RwaResultCard from "@/components/RwaResultCard";
import { calculateRwa } from "@/lib/api";
import { buildRwaRequest } from "@/lib/rwaRequest";
import { cn } from "@/lib/utils";
import { RwaResult } from "@/types/api";

export default function Calculator() {
  const [selectedCategory, setSelectedCategory] = useState<CategoryConfig>(EXPOSURE_CATEGORIES[0]);
  const [selectedEntityType, setSelectedEntityType] = useState<EntityTypeConfig>(
    EXPOSURE_CATEGORIES[0].entityTypes[0]
  );
  const [formValues, setFormValues] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<RwaResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  function handleCategoryChange(cat: CategoryConfig) {
    setSelectedCategory(cat);
    setSelectedEntityType(cat.entityTypes[0]);
    setFormValues({});
    setResult(null);
    setError(null);
  }

  function handleEntityTypeChange(et: EntityTypeConfig) {
    setSelectedEntityType(et);
    setFormValues({});
    setResult(null);
    setError(null);
  }

  async function handleCalculate(values: Record<string, unknown>) {
    setError(null);
    setIsLoading(true);
    const req = buildRwaRequest(selectedCategory.id, selectedEntityType.value, values);

    try {
      const res = await calculateRwa(req);
      setResult(res);
      setFormValues(values);
    } catch (err) {
      setError(err instanceof Error ? err.message : "산출 오류");
    } finally {
      setIsLoading(false);
    }
  }

  function handleReset() {
    setResult(null);
    setError(null);
    setFormValues({});
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Left Panel — Category + EntityType (desktop only) */}
      <aside className="hidden md:flex flex-col flex-none w-56 border-r border-surface-border bg-navy-800/30 overflow-y-auto">
        <div className="p-3">
          {EXPOSURE_CATEGORIES.map((cat) => (
            <div key={cat.id} className="mb-1">
              <button
                onClick={() => handleCategoryChange(cat)}
                className={cn(
                  "w-full text-left px-3 py-2 rounded-lg flex items-center gap-2 text-sm transition-all",
                  selectedCategory.id === cat.id
                    ? "bg-brand-700/30 border border-brand-600/30 text-brand-300"
                    : "text-slate-400 hover:text-slate-200 hover:bg-navy-700"
                )}
              >
                <span className="text-base">{cat.icon}</span>
                <div className="min-w-0">
                  <div className="font-medium truncate">{cat.labelKo}</div>
                  <div className="text-xs text-slate-500 truncate">{cat.label}</div>
                </div>
              </button>

              {/* Entity types under selected category */}
              {selectedCategory.id === cat.id && (
                <div className="ml-3 mt-1 space-y-0.5 border-l border-surface-border pl-2">
                  {cat.entityTypes.map((et) => (
                    <button
                      key={et.value}
                      onClick={() => handleEntityTypeChange(et)}
                      className={cn(
                        "w-full text-left px-2 py-1.5 rounded text-xs transition-all",
                        selectedEntityType.value === et.value
                          ? "bg-brand-600/20 text-brand-300"
                          : "text-slate-500 hover:text-slate-300 hover:bg-navy-700"
                      )}
                    >
                      {et.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </aside>

      {/* Center + Mobile Selectors wrapper */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Mobile Category Selector (mobile only) */}
        <div className="md:hidden flex-none border-b border-surface-border bg-navy-800/40">
          {/* Category pills */}
          <div className="flex gap-2 overflow-x-auto px-3 py-2 scrollbar-hide">
            {EXPOSURE_CATEGORIES.map((cat) => (
              <button
                key={cat.id}
                onClick={() => handleCategoryChange(cat)}
                className={cn(
                  "flex-none flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium whitespace-nowrap transition-all",
                  selectedCategory.id === cat.id
                    ? "bg-brand-600 text-white"
                    : "bg-navy-800 text-slate-400 border border-surface-border"
                )}
              >
                <span>{cat.icon}</span>
                <span>{cat.labelKo}</span>
              </button>
            ))}
          </div>
          {/* Entity type pills */}
          {selectedCategory.entityTypes.length > 1 && (
            <div className="flex gap-1.5 overflow-x-auto px-3 pb-2 scrollbar-hide">
              {selectedCategory.entityTypes.map((et) => (
                <button
                  key={et.value}
                  onClick={() => handleEntityTypeChange(et)}
                  className={cn(
                    "flex-none px-2.5 py-1 rounded-lg text-xs whitespace-nowrap transition-all",
                    selectedEntityType.value === et.value
                      ? "bg-brand-600/20 text-brand-300 border border-brand-600/30"
                      : "text-slate-500 border border-surface-border"
                  )}
                >
                  {et.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Scrollable Content Area */}
        <div className="flex-1 overflow-y-auto p-4 md:p-6">
          <div className="max-w-xl">
            {/* Breadcrumb — desktop only */}
            <div className="hidden md:flex items-center gap-1.5 text-xs text-slate-500 mb-4">
              <span className="text-slate-400">{selectedCategory.icon} {selectedCategory.labelKo}</span>
              <ChevronRight className="w-3 h-3" />
              <span className="text-brand-400">{selectedEntityType.label}</span>
            </div>

            {/* Mobile: current entity type label */}
            <div className="md:hidden mb-3">
              <span className="text-xs font-medium text-brand-400">{selectedEntityType.label}</span>
            </div>

            {/* Entity description */}
            {selectedEntityType.description && (
              <p className="text-xs text-slate-500 bg-navy-800/60 border border-surface-border rounded-lg px-3 py-2 mb-5">
                📋 {selectedEntityType.description}
              </p>
            )}

            {/* 유동화 익스포져 트랜치 구조 안내 */}
            {selectedCategory.id === "securitization" && (
              <div className="mb-4 bg-brand-900/20 border border-brand-700/30 rounded-lg px-4 py-3 space-y-1.5">
                <p className="text-xs font-semibold text-brand-300">📐 트랜치 구조 안내</p>
                <p className="text-xs text-slate-400">
                  Attachment Point(A)와 Detachment Point(D)에 트랜치 구조를 반영합니다.
                </p>
                <div className="text-xs text-slate-500 space-y-0.5 font-mono">
                  <p>· Equity &nbsp;0~5% &nbsp;→ A=0.00, D=0.05</p>
                  <p>· Mezzanine 5~15% → A=0.05, D=0.15</p>
                  <p>· Senior &nbsp;15~100% → A=0.15, D=1.00</p>
                </div>
              </div>
            )}

            <ExposureForm
              categoryId={selectedCategory.id}
              entityType={selectedEntityType}
              initialValues={formValues}
              onSubmit={handleCalculate}
              isLoading={isLoading}
            />

            {error && (
              <div className="mt-4 flex items-start gap-2 bg-red-950/40 border border-red-800/50 rounded-lg px-4 py-3">
                <AlertCircle className="w-4 h-4 text-red-400 flex-none mt-0.5" />
                <p className="text-sm text-red-300">{error}</p>
              </div>
            )}
          </div>

          {/* Mobile Result — inline below form (mobile only) */}
          {result && (
            <div className="md:hidden mt-6 max-w-xl">
              <div className="border-t border-surface-border pt-5">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
                    <BarChart3 className="w-4 h-4 text-brand-400" />
                    산출 결과
                  </div>
                  <button
                    onClick={handleReset}
                    className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 transition-colors"
                  >
                    <RotateCcw className="w-3 h-3" />
                    초기화
                  </button>
                </div>
                <RwaResultCard
                  result={result}
                  exposure={Number(formValues.exposure) || 0}
                  categoryLabel={selectedCategory.labelKo}
                  entityLabel={selectedEntityType.label}
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Panel — Result (desktop only) */}
      <aside className="hidden md:flex flex-col flex-none w-80 border-l border-surface-border bg-navy-800/20 overflow-y-auto p-4">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-300">
            <BarChart3 className="w-4 h-4 text-brand-400" />
            산출 결과
          </div>
          {result && (
            <button
              onClick={handleReset}
              className="text-xs text-slate-500 hover:text-slate-300 flex items-center gap-1 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              초기화
            </button>
          )}
        </div>

        {result ? (
          <RwaResultCard
            result={result}
            exposure={Number(formValues.exposure) || 0}
            categoryLabel={selectedCategory.labelKo}
            entityLabel={selectedEntityType.label}
          />
        ) : (
          <div className="flex flex-col items-center justify-center h-48 text-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-navy-800 border border-surface-border flex items-center justify-center">
              <BarChart3 className="w-6 h-6 text-slate-600" />
            </div>
            <p className="text-sm text-slate-500">
              왼쪽에서 익스포져 유형을 선택하고<br />
              입력값을 채운 뒤 산출 버튼을 누르세요.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
