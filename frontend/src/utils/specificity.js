// Presentation only. Inference decisions come from the versioned result.
export const isAbstained = (row) => row?.abstained_from_baseline_Cas_call === true;
export function decisionLabel(row) {
  if (isAbstained(row)) return "Withheld Cas evidence";
  if (row?.decision_status === "baseline_negative") return "Original-core negative";
  if (row?.decision_status === "accepted") return "Supported Cas call";
  return row?.is_cas === false ? "no cas" : "Cas call";
}
export function reasonLabel(row) {
  return ({ inherited_combined_rejection: "Inherited specificity rule withheld this call",
    insufficient_profile_support: "Insufficient profile support",
    uncertain_Cas_association: "Competing evidence leaves Cas association uncertain",
    baseline_negative: "Original core did not call Cas", accepted: "All applied specificity rules passed" })[row?.decision_status] || "Legacy result";
}
