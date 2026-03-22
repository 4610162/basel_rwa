"use client";

import { useState, useEffect, FormEvent } from "react";
import { Loader2, Calculator } from "lucide-react";
import { EntityTypeConfig, FieldConfig } from "@/lib/exposureConfig";
import { cn, formatKRW } from "@/lib/utils";

interface Props {
  categoryId: string;
  entityType: EntityTypeConfig;
  initialValues: Record<string, unknown>;
  onSubmit: (values: Record<string, unknown>) => void;
  isLoading: boolean;
}

export default function ExposureForm({
  entityType,
  initialValues,
  onSubmit,
  isLoading,
}: Props) {
  const DEFAULT_EXPOSURE = 10_000_000_000;

  const [values, setValues] = useState<Record<string, unknown>>({
    exposure: DEFAULT_EXPOSURE,
    ...getFieldDefaults(entityType),
    ...initialValues,
  });

  // Reset when entity type changes
  useEffect(() => {
    setValues({
      exposure: DEFAULT_EXPOSURE,
      ...getFieldDefaults(entityType),
      ...initialValues,
    });
  }, [entityType, initialValues]);

  function handleChange(name: string, value: unknown) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    onSubmit(values);
  }

  const visibleFields = entityType.fields.filter((f) => {
    if (f.label === "" || f.name === "ciu_approach" || f.name === "re_exposure_type") return false;
    if (!f.showWhen) return true;
    const currentVal = values[f.showWhen.field];
    return f.showWhen.values.includes(String(currentVal));
  });

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {/* 익스포져 금액 — 항상 표시 */}
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-slate-300">
          익스포져 금액 (원)
          <span className="text-red-400 ml-1">*</span>
        </label>
        <input
          type="number"
          min={1}
          step="any"
          required
          value={String(values.exposure ?? "")}
          onChange={(e) => handleChange("exposure", e.target.value)}
          placeholder="예: 1000000000 (10억원)"
          className="w-full bg-navy-900 border border-surface-border rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
        />
        {Boolean(values.exposure) && (
          <p className="text-xs text-slate-500">
            {formatKRW(Number(values.exposure))}
          </p>
        )}
      </div>

      {/* 동적 필드 */}
      {visibleFields.map((field) => (
        <DynamicField
          key={field.name}
          field={field}
          value={values[field.name]}
          onChange={(v) => handleChange(field.name, v)}
        />
      ))}

      {/* 필드 없는 카테고리 안내 */}
      {entityType.fields.filter(f => f.label !== "").length === 0 && (
        <div className="bg-amber-950/30 border border-amber-800/30 rounded-lg px-4 py-3 text-xs text-amber-300/80">
          이 익스포져 유형은 추가 입력 없이 고정 위험가중치가 적용됩니다.
        </div>
      )}

      <button
        type="submit"
        disabled={isLoading || !values.exposure}
        className={cn(
          "w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg font-medium text-sm transition-all",
          !isLoading && values.exposure
            ? "bg-brand-600 hover:bg-brand-500 text-white shadow-lg shadow-brand-900/30"
            : "bg-navy-700 text-slate-500 cursor-not-allowed"
        )}
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            산출 중...
          </>
        ) : (
          <>
            <Calculator className="w-4 h-4" />
            RWA 산출
          </>
        )}
      </button>
    </form>
  );
}

function DynamicField({
  field,
  value,
  onChange,
}: {
  field: FieldConfig;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  if (field.type === "boolean") {
    return (
      <div className="flex items-start gap-3 py-1">
        <label className="relative inline-flex items-center cursor-pointer mt-0.5">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={Boolean(value)}
            onChange={(e) => onChange(e.target.checked)}
          />
          <div className="w-10 h-5 bg-navy-700 border border-surface-border peer-checked:bg-brand-600 rounded-full transition-colors relative">
            <div className={cn(
              "absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform",
              Boolean(value) ? "translate-x-5" : "translate-x-0"
            )} />
          </div>
        </label>
        <div>
          <div className="text-sm text-slate-300">{field.label}</div>
          {field.hint && <p className="text-xs text-slate-500 mt-0.5">{field.hint}</p>}
        </div>
      </div>
    );
  }

  if (field.type === "select" && field.options) {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-slate-300">
          {field.label}
          {field.required && <span className="text-red-400 ml-1">*</span>}
        </label>
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value || undefined)}
          required={field.required}
          className="w-full bg-navy-900 border border-surface-border rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:outline-none focus:border-brand-600 transition-colors"
        >
          {field.options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {field.hint && <p className="text-xs text-slate-500">{field.hint}</p>}
      </div>
    );
  }

  if (field.type === "number") {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-slate-300">
          {field.label}
          {field.required && <span className="text-red-400 ml-1">*</span>}
        </label>
        <input
          type="number"
          min={field.min}
          max={field.max}
          step={field.step ?? "any"}
          required={field.required}
          placeholder={field.placeholder}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value === "" ? undefined : e.target.value)}
          className="w-full bg-navy-900 border border-surface-border rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
        />
        {field.hint && <p className="text-xs text-slate-500">{field.hint}</p>}
      </div>
    );
  }

  if (field.type === "text") {
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium text-slate-300">
          {field.label}
          {field.required && <span className="text-red-400 ml-1">*</span>}
        </label>
        <input
          type="text"
          required={field.required}
          placeholder={field.placeholder}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value || undefined)}
          className="w-full bg-navy-900 border border-surface-border rounded-lg px-3 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-brand-600 transition-colors"
        />
        {field.hint && <p className="text-xs text-slate-500">{field.hint}</p>}
      </div>
    );
  }

  return null;
}

function getFieldDefaults(entityType: EntityTypeConfig): Record<string, unknown> {
  const defaults: Record<string, unknown> = {};
  for (const field of entityType.fields) {
    if (field.defaultValue !== undefined) {
      defaults[field.name] = field.defaultValue;
    }
  }
  return defaults;
}
