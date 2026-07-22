import json

import pytest

from app.subskill_tasks import build_subskill_task, grade_subskill_task


def _task(*, concept: str, subskill: str, variant: int = 0, case_focus: str | None = None):
    return build_subskill_task(
        case_id="focused-content-case",
        case_concept=concept,
        subskill=subskill,
        case_focus=case_focus or concept,
        contrast_family={concept, "normal_ecg"},
        variant=variant,
    )


@pytest.mark.parametrize("subskill", ["synthesize", "apply_in_context"])
def test_structured_choices_are_deterministic_opaque_and_server_graded(subskill):
    first = _task(concept="right_bundle_branch_block", subskill=subskill, variant=2)
    repeated = _task(concept="right_bundle_branch_block", subskill=subskill, variant=2)
    changed_hidden_focus = _task(
        concept="right_bundle_branch_block",
        subskill=subskill,
        variant=2,
        case_focus="left_bundle_branch_block",
    )

    assert first and repeated and changed_hidden_focus
    assert first.public == repeated.public == changed_hidden_focus.public
    assert first.correct_answer == repeated.correct_answer == changed_hidden_focus.correct_answer
    assert first.public["kind"] == "single_choice"
    assert len(first.public["options"]) == 4
    assert all(set(option) == {"id", "label"} for option in first.public["options"])
    assert len({option["label"] for option in first.public["options"]}) == 4
    assert "correctAnswer" not in first.public
    assert "bounded_synthesis" not in json.dumps(first.public)
    assert "bounded_application" not in json.dumps(first.public)
    if subskill == "synthesize":
        assert first.public["frameworkVersion"] == (
            "focused-systematic-interpretation-v1"
        )
        assert [row["key"] for row in first.public["frameworkSteps"]] == [
            "rate",
            "rhythm",
            "axis",
            "intervals",
            "conduction",
            "st_t",
            "hypertrophy",
            "synthesis",
        ]
        assert all(
            set(row) == {"key", "label", "prompt", "placeholder"}
            for row in first.public["frameworkSteps"]
        )

    correct = grade_subskill_task(first, answer=first.correct_answer or "")
    wrong_id = next(
        option["id"]
        for option in first.public["options"]
        if option["id"] != first.correct_answer
    )
    wrong = grade_subskill_task(first, answer=wrong_id)
    assert correct["complete"] is True and correct["correct"] is True
    assert wrong["complete"] is True and wrong["correct"] is False


@pytest.mark.parametrize("variant", [0, 1, 2])
def test_synthesis_choices_use_prioritized_domain_evidence_without_giveaway_extremes(variant):
    conduction = _task(
        concept="right_bundle_branch_block", subskill="synthesize", variant=variant
    )
    rhythm = _task(
        concept="atrial_fibrillation", subskill="synthesize", variant=variant
    )
    ischemia = _task(
        concept="myocardial_ischemia", subskill="synthesize", variant=variant
    )
    assert conduction and rhythm and ischemia

    conduction_text = " ".join(
        option["label"] for option in conduction.public["options"]
    ).casefold()
    rhythm_text = " ".join(option["label"] for option in rhythm.public["options"]).casefold()
    ischemia_text = " ".join(
        option["label"] for option in ischemia.public["options"]
    ).casefold()
    assert "qrs duration, morphology, and lead distribution" in conduction_text
    assert "atrial activity, and atrioventricular relationship" in rhythm_text
    assert "st-t morphology, anatomic lead distribution" in ischemia_text

    banned_cues = (
        "acute and unstable",
        "immediate treatment",
        "exclude clinically important disease",
        "repeat every available machine label",
        "always",
        "never",
    )
    for contract in (conduction, rhythm, ischemia):
        labels = [option["label"] for option in contract.public["options"]]
        combined = " ".join(labels).casefold()
        assert not any(cue in combined for cue in banned_cues)
        # The alternatives should read like comparable interpretation
        # strategies, rather than one nuanced answer beside terse caricatures.
        assert min(len(label) for label in labels) >= 145
        assert max(len(label) for label in labels) - min(len(label) for label in labels) <= 85


@pytest.mark.parametrize(
    ("concept", "required_context"),
    [
        ("right_bundle_branch_block", "structural or device records"),
        ("atrial_fibrillation", "blood pressure and perfusion"),
        ("myocardial_ischemia", "serial ecgs or a valid prior"),
        ("qtc_prolongation", "manual qt/qtc and qrs verification"),
    ],
)
def test_application_choices_rehearse_concept_specific_information_boundaries(
    concept, required_context
):
    contract = _task(concept=concept, subskill="apply_in_context", variant=0)
    assert contract
    labels = [option["label"] for option in contract.public["options"]]
    combined = " ".join(labels).casefold()
    assert required_context in combined
    assert "select the best-fitting pathway" in combined

    banned_cues = (
        "proof that",
        "date onset",
        "without first",
        "choose a medication",
        "procedure",
        "disposition",
        "resuscitation",
        "immediate treatment",
        "always",
        "never",
    )
    assert not any(cue in combined for cue in banned_cues)
    assert min(len(label) for label in labels) >= 145
    assert max(len(label) for label in labels) - min(len(label) for label in labels) <= 60


def test_structured_choice_variants_change_wording_without_changing_contract_shape():
    for subskill in ("synthesize", "apply_in_context"):
        contracts = [
            _task(
                concept="right_bundle_branch_block",
                subskill=subskill,
                variant=variant,
            )
            for variant in range(3)
        ]
        assert all(contract is not None for contract in contracts)
        assert len({contract.public["prompt"] for contract in contracts}) == 3
        assert len(
            {
                tuple(option["label"] for option in contract.public["options"])
                for contract in contracts
            }
        ) == 3
        assert all(contract.evidence_source.startswith("curated_") for contract in contracts)
        assert all(contract.independently_assessable is False for contract in contracts)
