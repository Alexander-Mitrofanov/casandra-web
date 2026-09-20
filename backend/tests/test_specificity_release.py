"""Reject mismatched releases and malformed specificity evidence before publication."""

from copy import deepcopy
from dataclasses import replace

import pytest
from fake_tools import protein_prediction

from casandra_web.specificity_projection import project
from casandra_web.summary import SummaryError
from casandra_web.worker import Worker


@pytest.mark.parametrize(
    "field,value",
    [
        ("casandra_program_version", "0.3.0.dev0"),
        ("casandra_bundle_id", "another-dev2-bundle"),
        ("casandra_bundle_manifest_sha256", "b" * 64),
    ],
)
def test_worker_rejects_unpaired_identity_before_running_tools(settings, field, value):
    with pytest.raises(RuntimeError, match="paired backend release"):
        Worker(replace(settings, **{field: value})).validate_runtime()


@pytest.mark.parametrize("malformed", [None, [], "Z361", {"Z": 370}])
def test_malformed_search_evidence_is_a_validation_error(malformed):
    row = protein_prediction("cas3", "MTEST")
    row["specificity_evidence"]["core_search"] = malformed
    with pytest.raises(SummaryError, match="search-space provenance"):
        project(row)


@pytest.mark.parametrize(
    "status",
    [
        "inherited_combined_rejection",
        "insufficient_profile_support",
        "uncertain_Cas_association",
    ],
)
def test_withheld_call_keeps_raw_evidence_without_accepted_labels(status):
    row = protein_prediction("cas3", "MTEST")
    core = deepcopy(row["specificity_evidence"]["core_original_prediction"])
    row.update(
        is_cas=False,
        result="no cas",
        cas_family=None,
        classification=dict.fromkeys(("class", "type", "subtype")),
        decision_status=status,
        abstained_from_baseline_Cas_call=True,
    )
    view = project(row)
    assert view["core_original_prediction"] == core
    assert view["abstained_from_baseline_Cas_call"] is True
    assert view["is_cas"] is False and view["result"] == "no cas"
    assert all(view[key] is None for key in ("cas_family", "class", "type", "subtype"))
    row["classification"]["subtype"] = "I-E"
    with pytest.raises(SummaryError, match="canonical classification"):
        project(row)


def test_specificity_manifest_must_match_the_selected_release():
    row = protein_prediction("cas3", "MTEST")
    row["specificity_evidence"]["manifest_sha256"] = "f" * 64
    with pytest.raises(SummaryError, match="selected release"):
        project(row)
