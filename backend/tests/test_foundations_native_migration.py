from __future__ import annotations

from copy import deepcopy

from app.storage import LearningStore


def _legacy_item() -> dict:
    return {
        "pathwayId": "foundations-curriculum",
        "moduleId": "foundations",
        "sceneId": "foundations-progress",
        "status": "complete",
        "activeInteractionIndex": 5,
        "completedActionIds": ["S0", "S1", "S2", "S3"],
        "state": {
            "completedScenes": 4,
            "totalScenes": 13,
            "foundationState": {
                "completed": ["S0", "S1", "S2", "S3", "not-a-scene"],
                "skipped": ["S2"],
                "needsReview": ["S4"],
                "current": 5,
                "bestAccuracy": 77,
                "guidance": "minimal",
                "nv": {"rate": True, "qrs": True, "untrusted": True},
                "testedOut": {"1": True, "4": True, "9": True},
            },
        },
    }


def _by_scene(items: list[dict]) -> dict[str, dict]:
    return {str(item["sceneId"]): item for item in items}


def test_legacy_foundations_projects_to_non_mastering_native_rows_once(tmp_path) -> None:
    store = LearningStore(tmp_path / "foundations-migration.db")
    learner_id = "migration-learner"
    store.upsert_pathway_progress(learner_id, [_legacy_item()])
    legacy_before = deepcopy(
        store.get_pathway_progress(learner_id, "foundations-curriculum")
    )

    migrated = store.migrate_foundations_to_native(learner_id)
    assert migrated["result"] == "migrated"
    assert migrated["resumeSceneId"] == "S5"
    assert migrated["legacyPracticePreserved"] is True

    scenes = _by_scene(migrated["items"])
    assert set(scenes) == {f"S{index}" for index in range(13)}
    assert scenes["S0"]["status"] == "viewed"
    assert scenes["S1"]["status"] == "attempted"
    assert scenes["S2"]["status"] == "skipped"
    assert scenes["S3"]["status"] == "attempted"
    assert scenes["S4"]["status"] == "needs-review"
    assert scenes["S5"]["status"] == "viewed"
    assert all(item["status"] != "complete" for item in scenes.values())
    assert all(item["completedActionIds"] == [] for item in scenes.values())

    s0_state = scenes["S0"]["state"]
    assert s0_state["foundationsMigration"]["migrationVersion"] == "foundations-native-v2"
    assert s0_state["legacyPresentation"] == {
        "guidance": "minimal",
        "unlockedReferenceIds": ["qrs", "rate"],
        "placementHistory": [
            {"part": "1", "result": "passed_legacy_single_item"},
            {"part": "4", "result": "passed_legacy_single_item"},
        ],
        "legacyCapstoneScore": 77.0,
    }
    assert store.get_pathway_progress(
        learner_id, "foundations-curriculum"
    ) == legacy_before

    replay = store.migrate_foundations_to_native(learner_id)
    assert replay["result"] == "replay"
    assert replay["items"] == migrated["items"]

    changed_legacy = _legacy_item()
    changed_legacy["state"]["foundationState"]["current"] = 8
    store.upsert_pathway_progress(learner_id, [changed_legacy])
    native_before_conflict = store.get_pathway_progress(
        learner_id, "production-curriculum"
    )
    conflict = store.migrate_foundations_to_native(learner_id)
    assert conflict["result"] == "source_conflict"
    assert conflict["items"] == native_before_conflict


def test_migration_never_downgrades_preexisting_native_work(tmp_path) -> None:
    store = LearningStore(tmp_path / "foundations-native-preserve.db")
    learner_id = "native-learner"
    store.upsert_pathway_progress(
        learner_id,
        [{
            "pathwayId": "production-curriculum",
            "moduleId": "foundations",
            "sceneId": "S1",
            "status": "complete",
            "activeInteractionIndex": 2,
            "completedActionIds": ["native-reviewed-action"],
            "state": {"evidence": {"native-reviewed-action": {"correct": True}}},
        }],
    )
    store.upsert_pathway_progress(learner_id, [_legacy_item()])

    migrated = store.migrate_foundations_to_native(learner_id)
    scenes = _by_scene(migrated["items"])
    assert scenes["S1"]["status"] == "complete"
    assert scenes["S1"]["activeInteractionIndex"] == 2
    assert scenes["S1"]["completedActionIds"] == ["native-reviewed-action"]
    assert scenes["S1"]["state"]["evidence"]["native-reviewed-action"]["correct"] is True


def test_native_foundations_resume_uses_allowlisted_scene_deep_link(tmp_path) -> None:
    store = LearningStore(tmp_path / "foundations-resume.db")
    learner_id = "resume-learner"
    store.upsert_pathway_progress(
        learner_id,
        [{
            "pathwayId": "production-curriculum",
            "moduleId": "foundations",
            "sceneId": "S7",
            "status": "attempted",
            "activeInteractionIndex": 1,
            "completedActionIds": [],
            "state": {},
        }],
    )

    resume = store.get_learning_resume_snapshot(learner_id)
    assert resume["primary"]["destination"] == {
        "kind": "guided",
        "moduleId": "foundations",
        "sceneId": "S7",
    }
    assert resume["primary"]["completed"] == 0
    assert resume["primary"]["total"] == 13


def test_review_later_persists_without_erasing_actions_or_completed_work(tmp_path) -> None:
    store = LearningStore(tmp_path / "foundations-review-later.db")
    learner_id = "review-later-learner"
    base = {
        "pathwayId": "production-curriculum",
        "moduleId": "foundations",
        "sceneId": "S4",
        "status": "needs-review",
        "activeInteractionIndex": 2,
        "completedActionIds": ["m01-s4-regular-marks"],
        "state": {
            "status": "needs-review",
            "activeInteractionIndex": 2,
            "revealedMechanismCount": 3,
            "teachingStep": 2,
            "teachingVisitedSteps": [0, 1, 2],
            "teachingComplete": True,
            "evidence": {"m01-s4-regular-marks": {"correct": True}},
            "equivalentRetryCount": 1,
            "assistedInteractionIds": ["m01-s4-regular-marks"],
            "reviewLater": False,
        },
    }
    store.upsert_pathway_progress(learner_id, [base])
    skipped = store.upsert_pathway_progress(
        learner_id,
        [{
            **base,
            "status": "skipped",
            # This is the actual-shaped stale runtime sent by the frontend,
            # including nested fields that must not erase newer evidence.
            "activeInteractionIndex": 0,
            "completedActionIds": [],
            "state": {
                "status": "skipped",
                "activeInteractionIndex": 0,
                "revealedMechanismCount": 1,
                "teachingStep": 0,
                "teachingVisitedSteps": [0],
                "teachingComplete": False,
                "evidence": {},
                "equivalentRetryCount": 0,
                "assistedInteractionIds": [],
                "reviewLater": True,
            },
        }],
    )[0]
    # The monotonic evidence status remains intact; the dedicated presentation
    # flag suppresses automatic resume without allowing a stale client to
    # downgrade newer work.
    assert skipped["status"] == "needs-review"
    assert skipped["completedActionIds"] == ["m01-s4-regular-marks"]
    assert skipped["state"]["evidence"]["m01-s4-regular-marks"]["correct"] is True
    assert skipped["state"]["assistedInteractionIds"] == ["m01-s4-regular-marks"]
    assert skipped["state"]["activeInteractionIndex"] == 2
    assert skipped["state"]["revealedMechanismCount"] == 3
    assert skipped["state"]["teachingStep"] == 2
    assert skipped["state"]["teachingVisitedSteps"] == [0, 1, 2]
    assert skipped["state"]["teachingComplete"] is True
    assert skipped["state"]["equivalentRetryCount"] == 1
    assert skipped["state"]["reviewLater"] is True
    assert store.get_learning_resume_snapshot(learner_id)["primary"] is None

    with_new_evidence = store.upsert_pathway_progress(
        learner_id,
        [{
            **base,
            "status": "skipped",
            "completedActionIds": ["m01-s4-irregular-rate"],
            "state": {
                "status": "skipped",
                "activeInteractionIndex": 3,
                "revealedMechanismCount": 3,
                "evidence": {
                    "m01-s4-irregular-rate": {
                        "correct": False,
                        "attempts": 2,
                        "score": 0.6,
                    },
                },
                "equivalentRetryCount": 1,
                "assistedInteractionIds": ["m01-s4-irregular-rate"],
                "reviewLater": True,
            },
        }],
    )[0]
    assert set(with_new_evidence["state"]["evidence"]) == {
        "m01-s4-regular-marks",
        "m01-s4-irregular-rate",
    }
    assert with_new_evidence["state"]["evidence"]["m01-s4-regular-marks"]["correct"] is True
    assert with_new_evidence["state"]["evidence"]["m01-s4-irregular-rate"]["attempts"] == 2
    assert with_new_evidence["state"]["assistedInteractionIds"] == [
        "m01-s4-regular-marks",
        "m01-s4-irregular-rate",
    ]

    completed = store.upsert_pathway_progress(
        learner_id,
        [{**base, "status": "complete", "activeInteractionIndex": 3}],
    )[0]
    assert completed["status"] == "complete"
    preserved = store.upsert_pathway_progress(
        learner_id,
        [{**base, "status": "skipped"}],
    )[0]
    assert preserved["status"] == "complete"
