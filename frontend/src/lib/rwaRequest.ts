import { RwaRequest } from "@/types/api";

function numberValue(values: Record<string, unknown>, key: string): number | undefined {
  return values[key] !== undefined ? Number(values[key]) : undefined;
}

function percentValue(values: Record<string, unknown>, key: string): number | undefined {
  return values[key] !== undefined ? Number(values[key]) / 100 : undefined;
}

function stringValue(values: Record<string, unknown>, key: string): string | undefined {
  return values[key] ? String(values[key]) : undefined;
}

function booleanValue(values: Record<string, unknown>, key: string): boolean {
  return Boolean(values[key]);
}

export function buildCategoryPayload(
  categoryId: string,
  values: Record<string, unknown>
): Partial<RwaRequest> {
  switch (categoryId) {
    case "gov":
      return {
        external_credit_rating: stringValue(values, "external_credit_rating"),
        oecd_grade: values.oecd_grade ? numberValue(values, "oecd_grade") : undefined,
        is_local_currency: booleanValue(values, "is_local_currency"),
        is_korea: booleanValue(values, "is_korea"),
        entity_name: stringValue(values, "entity_name"),
        pse_category: stringValue(values, "pse_category"),
        country_gov_external_credit_rating: stringValue(values, "country_gov_external_credit_rating"),
      };
    case "bank":
      return {
        external_credit_rating: stringValue(values, "external_credit_rating"),
        oecd_grade: values.oecd_grade ? numberValue(values, "oecd_grade") : undefined,
        dd_grade: stringValue(values, "dd_grade"),
        cet1_ratio: values.cet1_ratio ? percentValue(values, "cet1_ratio") : undefined,
        leverage_ratio: values.leverage_ratio ? percentValue(values, "leverage_ratio") : undefined,
        is_foreign_currency: booleanValue(values, "is_foreign_currency"),
        is_trade_lc: booleanValue(values, "is_trade_lc"),
        country_gov_external_credit_rating: stringValue(values, "country_gov_external_credit_rating"),
        country_gov_oecd_grade: values.country_gov_oecd_grade ? numberValue(values, "country_gov_oecd_grade") : undefined,
        issuing_bank_rw: values.issuing_bank_rw ? numberValue(values, "issuing_bank_rw") : undefined,
        is_bank_equiv_regulated: booleanValue(values, "is_bank_equiv_regulated"),
      };
    case "corp":
      return {
        external_credit_rating: stringValue(values, "external_credit_rating"),
        short_grade: stringValue(values, "short_grade"),
        is_sme_legal: booleanValue(values, "is_sme_legal"),
        annual_revenue_eok: numberValue(values, "annual_revenue_eok"),
        total_assets_eok: numberValue(values, "total_assets_eok"),
        country_floor_rw: values.country_floor_rw ? percentValue(values, "country_floor_rw") : undefined,
        debtor_short_rw: values.debtor_short_rw ? percentValue(values, "debtor_short_rw") : undefined,
        pf_stage: stringValue(values, "pf_stage") || "operational",
        pf_op_high_quality: booleanValue(values, "pf_op_high_quality"),
        slotting_grade: stringValue(values, "slotting_grade"),
        slotting_short_or_safe: booleanValue(values, "slotting_short_or_safe"),
      };
    case "realestate":
      return {
        ltv_ratio: values.ltv_ratio ? numberValue(values, "ltv_ratio") : undefined,
        is_eligible: booleanValue(values, "is_eligible"),
        borrower_risk_weight: values.borrower_risk_weight ? percentValue(values, "borrower_risk_weight") : undefined,
        is_residential_exception: booleanValue(values, "is_residential_exception"),
        has_construction_guarantee: booleanValue(values, "has_construction_guarantee"),
        contractor_credit_rating: stringValue(values, "contractor_credit_rating"),
        guarantor_exposure: values.guarantor_exposure ? numberValue(values, "guarantor_exposure") : undefined,
      };
    case "securitization":
      return {
        attachment_point: numberValue(values, "attachment_point"),
        detachment_point: numberValue(values, "detachment_point"),
        k_sa: numberValue(values, "k_sa"),
        w: numberValue(values, "w"),
        p: values.p !== undefined ? numberValue(values, "p") : 1.0,
      };
    default:
      return {};
  }
}

export function buildRwaRequest(
  categoryId: string,
  entityType: string,
  values: Record<string, unknown>
): RwaRequest {
  const request: RwaRequest = {
    exposure_category: categoryId,
    entity_type: entityType,
    exposure: Number(values.exposure) || 0,
    ...buildCategoryPayload(categoryId, values),
  };

  if (categoryId === "ciu") {
    request.ciu_approach = entityType;
    if (values.weighted_avg_rw !== undefined) {
      request.weighted_avg_rw = Number(values.weighted_avg_rw) / 100;
    }
  }

  if (categoryId === "equity") {
    request.equity_type = entityType;
  }

  if (categoryId === "realestate") {
    request.re_exposure_type = entityType;
  }

  if (categoryId === "securitization" && (request.p === undefined || request.p === null)) {
    request.p = 1.0;
  }

  return request;
}
