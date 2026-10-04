"""Pure candidate refusal, Git identity and mocked FD controls; no subprocess."""

import json
import resource
import unittest
from pathlib import Path
from unittest.mock import patch

import allocator_models as native
import committed_models as m
import committed_owner as owner
from pydantic import ValidationError

ROOT = Path(__file__).parent
FIXTURES = ROOT / "candidate-metadata"


class CommittedGateControls(unittest.TestCase):
    def fixtures(self) -> tuple[m.Config, m.Candidate, m.CandidateWait, native.Plan]:
        producer = m.Candidate.model_validate_json(
            (FIXTURES / "candidate-receipt.json").read_bytes()
        )
        waited = m.CandidateWait.model_validate_json(
            (FIXTURES / "candidate-launch.json").read_bytes()
        )
        plan = native.Plan.model_validate_json(
            (FIXTURES / "candidate-plan.json").read_bytes()
        )
        if producer.binary is None or waited.owner_receipt is None:
            raise AssertionError("fixture is not the complete closed actual candidate")
        config = m.Config(
            root=m.BASE / "C4-allocation-run03-committed",
            repository=plan.source.parent,
            candidate_configuration=producer.configuration,
            candidate_receipt=waited.owner_receipt,
            candidate_launch=native.Pin(
                path=plan.root / "launch-receipt.json", bytes=1, sha256="0" * 64
            ),
            candidate_binary=producer.binary,
            reused_owner_freeze=native.Pin(
                path=m.BASE / "C4-allocation-owner02/freeze01.json",
                bytes=1,
                sha256=m.REUSE_FREEZE_SHA,
            ),
            helpers={
                name: native.Pin(path=ROOT / name, bytes=1, sha256="0" * 64)
                for name in m.HELPERS
            },
        )
        return config, producer, waited, plan

    def test_complete_closed_candidate_is_admitted_purely(self) -> None:
        owner.check_candidate(*self.fixtures())

    def test_incomplete_six_control_schedule_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        producer.steps.pop()
        with self.assertRaisesRegex(ValueError, "six gates and six complete controls"):
            owner.check_candidate(config, producer, waited, plan)

    def test_forced_cleanup_control_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        producer.steps[6].forced_cleanup = True
        with self.assertRaisesRegex(ValueError, "lifecycle unqualified"):
            owner.check_candidate(config, producer, waited, plan)

    def test_numeric_boolean_closure_is_refused(self) -> None:
        _, producer, _, _ = self.fixtures()
        raw = producer.model_dump(mode="json")
        raw["locks_released"] = 1
        with self.assertRaises(ValidationError):
            m.Candidate.model_validate_json(json.dumps(raw))

    def test_numeric_boolean_step_wait_is_refused(self) -> None:
        _, producer, _, _ = self.fixtures()
        raw = producer.model_dump(mode="json")
        raw["steps"][6]["waited"] = 1
        with self.assertRaises(ValidationError):
            m.Candidate.model_validate_json(json.dumps(raw))

    def test_boolean_zero_returncode_is_refused(self) -> None:
        _, producer, _, _ = self.fixtures()
        raw = producer.model_dump(mode="json")
        raw["steps"][6]["returncode"] = False
        with self.assertRaises(ValidationError):
            m.Candidate.model_validate_json(json.dumps(raw))

    def test_wrong_probe_binary_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        producer.steps[6].argv[0] = "/unknown/not-admitted"
        with self.assertRaisesRegex(ValueError, "probe binary/arguments differ"):
            owner.check_candidate(config, producer, waited, plan)

    def test_unlocked_release_command_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        producer.steps[5].argv.remove("--locked")
        with self.assertRaisesRegex(ValueError, "locked Rust command/profile"):
            owner.check_candidate(config, producer, waited, plan)

    def test_actual_wait_on_other_owner_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        waited.owner_pid = producer.owner_pid + 1
        with self.assertRaisesRegex(ValueError, "actual owner wait differs"):
            owner.check_candidate(config, producer, waited, plan)

    def test_changed_optimized_binary_identity_is_refused(self) -> None:
        config, producer, waited, plan = self.fixtures()
        config.candidate_binary = config.candidate_binary.model_copy(
            update={"sha256": "0" * 64}
        )
        with self.assertRaisesRegex(ValueError, "source/artifact attempt differs"):
            owner.check_candidate(config, producer, waited, plan)

    def proof(self, config: m.Config, plan: native.Plan) -> m.GitProof:
        return m.GitProof(
            head=config.commit,
            tree=config.tree,
            detached=True,
            status="",
            tracked=["probe/" + name for name in plan.source_files],
        )

    def test_clean_exact_commit_and_eight_files_are_required(self) -> None:
        config, _, _, plan = self.fixtures()
        proof = self.proof(config, plan)
        owner.require_git(config, proof, set(plan.source_files))
        for changed in (
            proof.model_copy(update={"head": "0" * 40}),
            proof.model_copy(update={"status": " M probe/src/main.rs"}),
            proof.model_copy(update={"detached": False}),
            proof.model_copy(update={"tracked": [*proof.tracked, proof.tracked[0]]}),
        ):
            with self.assertRaisesRegex(ValueError, "exact committed eight-file"):
                owner.require_git(config, changed, set(plan.source_files))

    def test_fd_soft8192_retains_existing_hard_ceiling(self) -> None:
        with (
            patch.object(
                resource, "getrlimit", side_effect=[(1024, 1048576), (8192, 1048576)]
            ),
            patch.object(resource, "setrlimit") as setter,
        ):
            before, after = owner.fd_limit()
        setter.assert_called_once_with(resource.RLIMIT_NOFILE, (8192, 1048576))
        self.assertEqual(before.hard, after.hard)
        self.assertEqual(after.soft, 8192)

    def test_fd_insufficient_hard_ceiling_refuses_before_mutation(self) -> None:
        with (
            patch.object(resource, "getrlimit", return_value=(1024, 8191)),
            patch.object(resource, "setrlimit") as setter,
            self.assertRaisesRegex(ValueError, "hard ceiling below8192"),
        ):
            owner.fd_limit()
        setter.assert_not_called()

    def test_reused_owner_freeze_mismatch_is_refused(self) -> None:
        config, _, _, _ = self.fixtures()
        raw = config.model_dump(mode="json")
        raw["reused_owner_freeze"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValidationError, "owner02 identity differs"):
            m.Config.model_validate_json(json.dumps(raw))

    def test_no_probe_or_os_claim_can_be_added(self) -> None:
        config, _, _, _ = self.fixtures()
        receipt = m.Receipt(
            owner_pid=99999,
            owner_token="synthetic",
            configuration=config.candidate_configuration,
            started_utc="synthetic-control",
        )
        for field in ("repeated_allocator_probes", "graph_or_OS_memory_qualified"):
            raw = receipt.model_dump(mode="json")
            raw[field] = True
            with self.assertRaises(ValidationError):
                m.Receipt.model_validate_json(json.dumps(raw))
            raw[field] = 0
            with self.assertRaisesRegex(ValidationError, "literal Boolean"):
                m.Receipt.model_validate_json(json.dumps(raw))


if __name__ == "__main__":
    unittest.main()
