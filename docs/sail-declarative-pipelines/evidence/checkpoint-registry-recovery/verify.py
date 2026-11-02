"""Verify the archived checkpoint registry packet; does not run builds or tests."""

from collections import Counter
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> object:
    return json.loads(path.read_text())


def git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("grust_root", type=Path, nargs="?", default=Path.cwd())
    parser.add_argument("--sail-repo", type=Path, default=Path("/Users/alexy/src/sail-pipelines-proposal"))
    args = parser.parse_args()
    packet = args.grust_root / "docs/sail-declarative-pipelines/evidence/checkpoint-registry-recovery"
    repo = args.sail_repo
    manifest = read_json(packet / "provenance.json")
    listed = {item["path"] for item in manifest["files"]}
    actual = {str(path.relative_to(packet)) for path in packet.rglob("*") if path.is_file()}
    require(actual == listed | {"provenance.json"}, "archive file inventory changed")
    for item in manifest["files"]:
        data = (packet / item["path"]).read_bytes()
        require(len(data) == item["bytes"] and digest(data) == item["sha256"], item["path"])

    candidate = read_json(packet / "candidate.json")
    gate = read_json(packet / "gate.json")
    commit = "cba833ae08a4844afcb4e5edef0cc894231d0d82"
    base = "ec8e74d57de51149a774cd4f9048d82039704d0c"
    control_commit = "9bbe418025665a87caff3ab6ec27c147c50e5b43"
    spark_commit = "617618396087429b5627a86ce933bb0f5d6645cb"
    require(manifest["sail_commit"] == candidate["commit"] == gate["sail_commit"] == commit, "candidate pin")
    require(candidate["base"] == gate["base"] == base, "base pin")
    require(gate["outcome"] == "passed", "library outcome")
    require([check["name"] for check in gate["checks"]] == ["fmt", "clippy", "rust"], "library checks")
    for check in gate["checks"]:
        require(check["exit_code"] == 0, check["name"])
        require(digest((packet / (check["name"] + ".log")).read_bytes()) == check["sha256"], "gate log hash")
    counts = [int(value) for value in re.findall(r"test result: ok\. (\d+) passed; 0 failed;", (packet / "rust.log").read_text())]
    require(counts == [9, 13, 29] and sum(counts) == 51, "library counts")
    require(manifest["library_counts"] == {"sail-cache": 9, "sail-physical-plan": 13, "sail-session": 29}, "manifest counts")

    sources = read_json(packet / "sources.json")
    for entry in sources["sources"]:
        data = git(repo, "show", entry["commit"] + ":" + entry["path"])
        blob = git(repo, "rev-parse", entry["commit"] + ":" + entry["path"]).decode().strip()
        require(blob == entry["blob"] and len(data) == entry["bytes"] and digest(data) == entry["sha256"], "source pin: " + entry["path"])
        if entry["archived"] is not None:
            require((packet / entry["archived"]).read_bytes() == data, "source archive")
    for label, entry in sources["commits"].items():
        require(git(repo, "rev-parse", entry["commit"] + "^{tree}").decode().strip() == entry["tree"], label + " tree")
        require(git(repo, "show", "-s", "--format=%P", entry["commit"]).decode().split() == entry["parents"], label + " parents")
    require(sources["commits"]["candidate"]["parents"] == sources["commits"]["control"]["parents"] == [base], "direct base parent")
    require(sources["spark_commit"] == spark_commit, "Spark source pin")
    require(git(repo, "diff", "--binary", base, commit) == (packet / "commit.patch").read_bytes(), "candidate diff")
    require(set(git(repo, "diff", "--name-only", base, commit).decode().splitlines()) == set(candidate["paths"]), "candidate scope")

    control = read_json(packet / "control/receipt.json")
    require(control["base"] == base and control["fixed_candidate"] == commit and control["control_commit"] == control_commit, "control pins")
    production_path = control["production_path"]
    before = git(repo, "show", base + ":" + production_path)
    unchanged = git(repo, "show", control_commit + ":" + production_path)
    require(unchanged == before + control["test_only_module_declaration"].encode(), "control production unchanged")
    require(digest(before) == control["base_production_sha256"] == control["control_production_without_test_module_sha256"], "control production hash")
    require(git(repo, "diff", "--name-only", control_commit, commit).decode().splitlines() == [production_path], "control differs only in registry")
    require(set(git(repo, "diff", "--name-only", base, control_commit).decode().splitlines()) == set(candidate["paths"]), "control test-only scope")
    require(git(repo, "diff", "--binary", base, control_commit) == (packet / "control/control.patch").read_bytes(), "control diff")
    control_log = (packet / "control/test.log").read_bytes()
    require(digest(control_log) == control["log_sha256"], "control log hash")
    require(control["exit_code"] == 101 and control["expected_failure_observed"], "expected failing control")
    require(b'Error: "cleanup discarded recovery metadata"' in control_log and b"0 passed; 1 failed;" in control_log, "specific failed assertion")

    release = packet / "release-sail-cache"
    stress = read_json(release / "receipt.json")
    require(stress["commit"] == commit and stress["outcome"] == "passed", "release pin/outcome")
    require(stress["build_exit"] == stress["test_exit"] == 0, "release exit status")
    require(len(stress["load_pids"]) == len(set(stress["load_pids"])) == stress["logical_cpus"] == len(stress["load_worker_exit_codes"]) == 10, "CPU load ownership")
    require(all(code == -15 for code in stress["load_worker_exit_codes"]), "load workers joined")
    require("4 passed; 0 failed; 0 ignored;" in (release / "test.log").read_text(), "optimized test counts")
    artifacts = [json.loads(line) for line in (release / "build.jsonl").read_text().splitlines()]
    executables = [entry for entry in artifacts if entry.get("executable")]
    require(len(executables) == 1 and executables[0]["executable"] == stress["binary"], "release executable")
    require(executables[0]["target"]["name"] == "sail_cache", "release target")
    profile = executables[0]["profile"]
    require(profile["opt_level"] == "3" and profile["test"] and not profile["debug_assertions"], "optimized profile")
    expected_names = {"remote_checkpoint::cleanup_tests::" + name for name in (
        "canceled_cleanup_retains_closed_metadata_for_explicit_retry",
        "partial_delete_failure_retains_descriptor_for_explicit_retry",
        "paused_deletion_seals_admission_without_holding_the_registry_lock",
        "successful_cleanup_is_session_scoped_and_remains_closed",
    )}
    release_names = set(re.findall(r"^test (\S+) \.\.\. ok$", (release / "test.log").read_text(), re.M))
    require(release_names == expected_names, "optimized test identity")
    require(expected_names <= set(re.findall(r"^test (\S+) \.\.\. ok$", (packet / "rust.log").read_text(), re.M)), "debug test identities")

    public_dir = packet / "public"
    public = read_json(public_dir / "receipt.json")
    require(public["sail_commit"] == commit and public["outcome"] == "passed", "public pin/outcome")
    require(public["before"] == public["after"] and public["before"]["head"] == commit and public["before"]["detached"], "unchanged detached public source")
    require(public["before"]["tree"] == sources["commits"]["candidate"]["tree"], "public tree")
    require(public["server_exit_code"] == 0 and public["remaining_listener_pids"] == [], "owned server teardown")
    require(public["spark_commit"] == spark_commit, "public Spark pin")
    for name, expected in public["artifact_sha256"].items():
        require(digest((public_dir / name).read_bytes()) == expected, "public artifact: " + name)
    for check in public["checks"]:
        require(check["exit_code"] == 0 and digest((public_dir / (check["name"] + ".log")).read_bytes()) == check["log_sha256"], "public check: " + check["name"])
    for path, expected in public["before"]["sources"].items():
        require(digest(git(repo, "show", commit + ":" + path)) == expected, "public source: " + path)
    require(digest(git(repo, "show", commit + ":Cargo.lock")) == public["before"]["cargo_lock_sha256"], "public lock")
    nodes = read_json(public_dir / "selected-nodes.json")
    require(len(nodes) == len(set(nodes)) == 300, "selected public identities")
    pytest_command = next(check["command"] for check in public["checks"] if check["name"] == "pytest")
    require(pytest_command[4:-1] == nodes, "pytest arguments match selected identities")
    xml = ET.parse(public_dir / "pytest.xml")
    suites = list(xml.iter("testsuite"))
    require(len(suites) == 1, "single JUnit suite")
    require([int(suites[0].get(key)) for key in ("tests", "failures", "errors", "skipped")] == [300, 0, 0, 0], "JUnit counts")
    actual_cases = [case.get("classname").replace(".", "/") + ".py::" + case.get("name") for case in xml.iter("testcase")]
    require(Counter(actual_cases) == Counter(nodes), "JUnit identities")
    upstream = read_json(public_dir / "upstream.json")
    require((upstream["tests_run"], upstream["failures"], upstream["errors"], upstream["skipped"]) == (67, 0, 0, 0), "upstream counts")
    require(upstream["server_spark_version"] == upstream["spark_version"] == "4.2.1" and upstream["spark_commit"] == spark_commit, "upstream Spark version/pin")
    require(len(upstream["collected"]) == 67 and len(set(upstream["collected"])) == 63, "upstream unique IDs")
    require(Counter(item["id"] for item in upstream["outcomes"]) == Counter(upstream["collected"]), "upstream outcomes identity")
    require(all(item["outcome"] == "passed" for item in upstream["outcomes"]), "upstream pass outcomes")

    harness = packet / "public-harness"
    for path, expected in read_json(harness / "MANIFEST.json").items():
        require(digest((harness / path).read_bytes()) == expected, "historical harness: " + path)
    require(digest((harness / "run.py").read_bytes()) == public["harness_sha256"], "executed harness hash")
    require(digest((harness / "preparation.json").read_bytes()) == public["preparation_sha256"], "frozen preparation")
    preparation = read_json(harness / "preparation.json")
    require(preparation["sail_commit"] == public["selection_preparation_commit"], "selection provenance")
    require(preparation["source_sha256"] == public["before"]["sources"], "frozen source identities")
    require((harness / "selected-nodes.json").read_bytes() == (public_dir / "selected-nodes.json").read_bytes(), "frozen selection")
    require(read_json(harness / "prior-upstream.json")["collected"] == upstream["collected"], "frozen upstream selection")
    binaries = read_json(packet / "binary-verification.json")
    for entry in binaries["binaries"]:
        expected = public["cli_sha256"] if entry["kind"] == "cli" else stress["binary_sha256"]
        require(entry["matches_recorded_receipt"] and entry["sha256"] == expected, "archive-time binary verification")
    print("PASS checkpoint registry exact-source archive: " + commit)
    print("51 library; 4 optimized under CPU load; 300 public; 67 upstream (63 unique); expected control failure retained")


if __name__ == "__main__":
    main()
