"""Display-only specificity projection; no inference or threshold evaluation."""

from collections import Counter
from copy import deepcopy

STATUSES = {
    "accepted",
    "baseline_negative",
    "inherited_combined_rejection",
    "insufficient_profile_support",
    "uncertain_Cas_association",
}


def project(row):
    from .summary import SummaryError

    ev = row.get("specificity_evidence")
    repair = row.get("repair_evidence")
    status = row.get("decision_status")
    abstained = row.get("abstained_from_baseline_Cas_call")
    if not isinstance(ev, dict) or not isinstance(repair, dict) or status not in STATUSES:
        raise SummaryError("specificity decision provenance is unavailable")
    from .release_contract import SPECIFICITY_MANIFEST_SHA256

    if ev.get("manifest_sha256") != SPECIFICITY_MANIFEST_SHA256:
        raise SummaryError("specificity overlay does not match the selected release")
    core = ev.get("core_original_prediction")
    if (
        not isinstance(core, dict)
        or type(core.get("is_cas")) is not bool
        or type(abstained) is not bool
    ):
        raise SummaryError("original-core decision provenance is invalid")
    if type(row.get("is_cas")) is not bool or abstained != (core["is_cas"] and not row["is_cas"]):
        raise SummaryError("specificity abstention disagrees with canonical call")
    if (
        (status == "accepted") != row["is_cas"]
        or (status == "baseline_negative") != (not core["is_cas"])
        or (
            not row["is_cas"]
            and (
                row.get("cas_family") is not None
                or row.get("result") != "no cas"
                or row.get("classification") != dict.fromkeys(["class", "type", "subtype"])
            )
        )
    ):
        raise SummaryError("specificity status disagrees with canonical classification")
    searches = [ev.get(k) for k in ["core_search", "inherited_search", "new_search"]]
    if any(not isinstance(search, dict) for search in searches) or [
        search.get("Z") for search in searches
    ] != [361, 370, 387]:
        raise SummaryError("specificity search-space provenance is invalid")
    missing = row.get("hard_negative_hit_present") is False
    return deepcopy(
        {
            "is_cas": row["is_cas"],
            "result": row["result"],
            "cas_family": row["cas_family"],
            **row["classification"],
            "decision_status": status,
            "abstained_from_baseline_Cas_call": abstained,
            "core_original_prediction": core,
            "repair_evidence": repair,
            "specificity_metadata": {
                k: v
                for k, v in ev.items()
                if k
                not in {"core_search", "inherited_search", "new_search", "core_original_prediction"}
            },
            "search_spaces": {"core": 361, "inherited": 370, "new": 387},
            "score_scope": "original_core_before_specificity_overlay",
            "score_interpretation": "Uncalibrated original-core evidence; the core margin and threshold do not determine the final specificity decision.",
            "hard_negative_hit_present": row.get("hard_negative_hit_present"),
            "hard_negative_score_interpretation": "No negative hit; stored sentinel is not observed negative evidence."
            if missing
            else "Observed original-core negative-profile score; not a probability.",
        }
    )


def decorate(summary, rows):
    counts = Counter(p["decision_status"] for p in rows)
    summary["schema_version"] = "1.2.0"
    summary["specificity_decisions"] = {
        "status_counts": dict(counts),
        "supported_count": counts["accepted"],
        "baseline_negative_count": counts["baseline_negative"],
        "abstained_count": sum(p["abstained_from_baseline_Cas_call"] for p in rows),
        "interpretation": "Supported calls, original-core negatives and withheld original-core calls are separate outcomes. Withheld evidence is not an accepted protein or locus.",
    }
    summary["overview"]["abstained_protein_count"] = summary["specificity_decisions"][
        "abstained_count"
    ]
    summary["overview"]["baseline_negative_protein_count"] = counts["baseline_negative"]
    summary["warnings"].append(
        "Original-core margins and stored missing-negative sentinel values are not calibrated confidence or final specificity thresholds. Full raw evidence and withheld cassette candidates are available in the downloads."
    )
    return summary
