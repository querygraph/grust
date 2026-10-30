"""Isolated tests for the SDP append helper; never append to the canonical log."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import fcntl
import importlib.util
from io import StringIO
from pathlib import Path
import re
import selectors
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


sys.dont_write_bytecode = True
SCRIPT = Path(__file__).with_name("sdp-coordination-append.py")
SPEC = importlib.util.spec_from_file_location("sdp_coordination_append", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("could not load coordination append helper")
APPENDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPENDER)
LEGACY_TIMESTAMP = "2026-10-30T03:45:11.972763+00:00"
LEGACY_ENTRY = f"# Coordination\n\n## {LEGACY_TIMESTAMP} — Codex\n\nEarlier message.\n"
NEW_ENTRY = re.compile(
    r"\n## (?P<timestamp>[^\n]+) — (?:Codex|Fable)\n"
    r"Message-ID: (?P<id>CF-[0-9]{4,})\n\n"
)
WORKER = """
from pathlib import Path
import runpy
import sys

append = runpy.run_path(sys.argv[1])["append_message"]
body = Path(sys.argv[3]).read_bytes().decode("utf-8")
print("ready", flush=True)
print(append(Path(sys.argv[2]), "Fable", body), flush=True)
"""


class AppendTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(prefix="sdp-coordination-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / "coordination.md"

    def test_unicode_and_whitespace_body_are_preserved_exactly(self) -> None:
        bodies = (
            " \t\n\nλ → 東京 🦀\r\n trailing spaces  \t",
            "\n  second body  \n\n\n",
        )
        for index, body in enumerate(bodies, start=1):
            with self.subTest(body=body):
                previous = self.log.read_bytes() if self.log.exists() else b""
                message_id = APPENDER.append_message(self.log, "Codex", body)
                appended = self.log.read_bytes()[len(previous):].decode("utf-8")
                heading, actual_body = appended.split("\n\n", 1)
                self.assertEqual(message_id, f"CF-{index:04d}")
                self.assertIn(f"\nMessage-ID: {message_id}", heading)
                self.assertEqual(actual_body, body if body.endswith("\n") else body + "\n")

    def test_legacy_and_new_references_and_persistent_lock_inode(self) -> None:
        self.log.write_text(LEGACY_ENTRY, encoding="utf-8")
        lock_path = self.log.with_suffix(".lock")
        lock_path.touch()
        original = lock_path.stat()
        first = APPENDER.append_message(self.log, "Codex", "first")
        second = APPENDER.append_message(
            self.log,
            "Fable",
            "second",
            reply_to=(first, f"legacy:{LEGACY_TIMESTAMP}"),
            seen_through=first,
        )
        self.assertEqual((first, second), ("CF-0001", "CF-0002"))
        current = lock_path.stat()
        self.assertEqual((current.st_dev, current.st_ino), (original.st_dev, original.st_ino))
        self.assertIn(
            "Message-ID: CF-0002\nReply-To: CF-0001\n"
            f"Reply-To: legacy:{LEGACY_TIMESTAMP}\nSeen-Through: CF-0001\n\nsecond\n",
            self.log.read_text(encoding="utf-8"),
        )

    def test_invalid_reference_does_not_mutate_log(self) -> None:
        self.log.write_text(LEGACY_ENTRY, encoding="utf-8")
        APPENDER.append_message(self.log, "Codex", "first")
        original = self.log.read_bytes()
        lock_inode = self.log.with_suffix(".lock").stat().st_ino
        for reference in (
            "CF-0002",
            "CF-9999",
            "legacy:2026-10-30T03:45:11.972763Z",
            "legacy:not-a-timestamp",
        ):
            for option in ("reply_to", "seen_through"):
                with self.subTest(reference=reference, option=option):
                    value = [reference] if option == "reply_to" else reference
                    with self.assertRaisesRegex(ValueError, "unknown coordination reference"):
                        APPENDER.append_message(self.log, "Fable", "must not appear", **{option: value})
                    self.assertEqual(self.log.read_bytes(), original)
                    self.assertEqual(self.log.with_suffix(".lock").stat().st_ino, lock_inode)
        absent = self.root / "absent.md"
        with self.assertRaises(ValueError):
            APPENDER.append_message(absent, "Fable", "body", reply_to=["CF-0001"])
        self.assertFalse(absent.exists())

    def test_message_id_mentioned_in_body_does_not_allocate_an_id(self) -> None:
        APPENDER.append_message(self.log, "Codex", "Message-ID: CF-9999\nExample only.")
        self.assertEqual(APPENDER.append_message(self.log, "Fable", "next"), "CF-0002")
        with self.assertRaises(ValueError):
            APPENDER.append_message(self.log, "Fable", "reply", reply_to=["CF-9999"])

    def test_timestamp_is_generated_while_holding_the_lock(self) -> None:
        def now_under_lock(tz: timezone) -> datetime:
            with self.log.with_suffix(".lock").open("a+") as another_handle:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(another_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return datetime(2026, 10, 30, tzinfo=tz)

        with patch.object(APPENDER, "datetime") as clock:
            clock.now.side_effect = now_under_lock
            APPENDER.append_message(self.log, "Codex", "body")
            clock.now.assert_called_once_with(timezone.utc)

    def test_cli_keeps_body_bytes_and_accepts_reference_options(self) -> None:
        self.log.write_text(LEGACY_ENTRY, encoding="utf-8")
        first = APPENDER.append_message(self.log, "Codex", "first")
        body = "  λ\r\n\t keep both ends  "
        body_file = self.root / "body.txt"
        body_file.write_bytes(body.encode("utf-8"))
        output = StringIO()
        argv = [
            str(SCRIPT), "--author", "Fable", "--body-file", str(body_file),
            "--reply-to", first, "--reply-to", f"legacy:{LEGACY_TIMESTAMP}",
            "--seen-through", first,
        ]
        # The production CLI has no path override. Patch its constant only inside
        # this test so the real argument parser never touches the canonical log.
        with patch.object(APPENDER, "CANONICAL_LOG", self.log), patch.object(sys, "argv", argv):
            with redirect_stdout(output):
                APPENDER.main()
        self.assertEqual(output.getvalue(), "CF-0002\n")
        self.assertTrue(self.log.read_bytes().endswith((body + "\n").encode("utf-8")))

    def test_concurrent_processes_get_serial_ids_and_intact_entries(self) -> None:
        count = 12
        lock_path = self.log.with_suffix(".lock")
        processes: list[subprocess.Popen[str]] = []
        bodies: list[str] = []
        returned: dict[str, str] = {}
        try:
            with lock_path.open("a+") as lock:
                inode = lock_path.stat().st_ino
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                for index in range(count):
                    body = f"  writer {index}: λ 東京 🦀\nline two {index}  \t"
                    bodies.append(body)
                    body_file = self.root / f"body-{index}.txt"
                    body_file.write_bytes(body.encode("utf-8"))
                    processes.append(subprocess.Popen(
                        [sys.executable, "-B", "-c", WORKER, str(SCRIPT), str(self.log), str(body_file)],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    ))
                with selectors.DefaultSelector() as ready:
                    for process in processes:
                        self.assertIsNotNone(process.stdout)
                        ready.register(process.stdout, selectors.EVENT_READ)
                    while ready.get_map():
                        events = ready.select(timeout=15)
                        self.assertTrue(events, "writers did not reach the start barrier")
                        for key, _ in events:
                            self.assertEqual(key.fileobj.readline(), "ready\n")
                            ready.unregister(key.fileobj)
                # Every process has started while the shared lock is held.
                # No timing assumption or scheduling delay establishes this gate.
                self.assertFalse(self.log.exists())
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            for process, body in zip(processes, bodies):
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stderr)
                self.assertEqual(stderr, "")
                returned[stdout.strip()] = body + "\n"
            self.assertEqual(len(returned), count)
            text = self.log.read_bytes().decode("utf-8")
            entries = list(NEW_ENTRY.finditer(text))
            self.assertEqual([entry["id"] for entry in entries], [f"CF-{i:04d}" for i in range(1, count + 1)])
            for index, entry in enumerate(entries):
                end = entries[index + 1].start() if index + 1 < count else len(text)
                self.assertEqual(text[entry.end():end], returned[entry["id"]])
                self.assertEqual(datetime.fromisoformat(entry["timestamp"]).tzinfo, timezone.utc)
            self.assertEqual(lock_path.stat().st_ino, inode)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=15)


class ReadSinceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = TemporaryDirectory(prefix="sdp-coordination-read-test-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.log = self.root / "coordination.md"
        self.log.write_text(LEGACY_ENTRY, encoding="utf-8")
        self.first = APPENDER.append_message(self.log, "Codex", "first body\n")
        self.second = APPENDER.append_message(
            self.log, "Fable", "  second λ body  ", reply_to=(self.first,), seen_through=self.first
        )

    def test_entries_after_a_reference_are_returned_verbatim_and_in_order(self) -> None:
        text = self.log.read_text(encoding="utf-8")
        from_legacy, boundary = APPENDER.read_since(self.log, f"legacy:{LEGACY_TIMESTAMP}")
        self.assertEqual(boundary, self.second)
        self.assertTrue(text.endswith(from_legacy))
        self.assertEqual([m["id"] for m in APPENDER.ENTRY_HEADER.finditer(from_legacy)], [self.first, self.second])
        self.assertTrue(from_legacy.startswith("## "))
        from_first, boundary = APPENDER.read_since(self.log, self.first)
        self.assertEqual(boundary, self.second)
        self.assertTrue(from_legacy.endswith(from_first))
        self.assertIn(f"Message-ID: {self.second}\nReply-To: {self.first}\n", from_first)
        self.assertTrue(from_first.endswith("  second λ body  \n"))
        self.assertNotIn("first body", from_first)
        self.assertEqual(APPENDER.read_since(self.log, self.second), ("", self.second))
        # The boundary names the snapshot that was read, so a later append is outside it.
        third = APPENDER.append_message(self.log, "Codex", "third")
        self.assertEqual(APPENDER.read_since(self.log, self.second)[1], third)
        self.assertEqual(APPENDER.read_since(self.log, self.first)[1], third)

    def test_unknown_reference_is_rejected_and_nothing_is_written(self) -> None:
        original = self.log.read_bytes()
        for reference in ("CF-0003", "legacy:2026-10-30T03:45:11.972763Z", "", "CF-1"):
            with (
                self.subTest(reference=reference),
                self.assertRaisesRegex(ValueError, "unknown coordination reference"),
            ):
                APPENDER.read_since(self.log, reference)
        self.assertEqual(self.log.read_bytes(), original)

    def test_reader_preserves_crlf_body_bytes(self) -> None:
        body = "  third λ body\r\nsecond line\r\n"
        third = APPENDER.append_message(self.log, "Codex", body)
        original = self.log.read_bytes()
        text, boundary = APPENDER.read_since(self.log, self.second)
        self.assertEqual(boundary, third)
        self.assertTrue(text.endswith(body))
        self.assertTrue(original.endswith(text.encode("utf-8")))
        self.assertEqual(self.log.read_bytes(), original)

    def test_reader_accepts_timestamp_aliases_accepted_by_append(self) -> None:
        entries = list(APPENDER.ENTRY_HEADER.finditer(self.log.read_text(encoding="utf-8")))
        first_alias = f"legacy:{entries[-2]['timestamp']}"
        last_alias = f"legacy:{entries[-1]['timestamp']}"
        self.assertEqual(APPENDER.read_since(self.log, first_alias), APPENDER.read_since(self.log, self.first))
        self.assertEqual(APPENDER.read_since(self.log, last_alias), ("", self.second))

    def test_cli_since_prints_entries_without_appending_and_rejects_append_options(self) -> None:
        original = self.log.read_bytes()
        output = StringIO()
        errors = StringIO()
        argv = [str(SCRIPT), "--since", self.first]
        with (
            patch.object(APPENDER, "CANONICAL_LOG", self.log),
            patch.object(sys, "argv", argv),
            redirect_stdout(output),
            redirect_stderr(errors),
        ):
            APPENDER.main()
        self.assertEqual(output.getvalue(), APPENDER.read_since(self.log, self.first)[0])
        self.assertEqual(errors.getvalue(), f"read-through: {self.second}\n")
        self.assertEqual(self.log.read_bytes(), original)
        for extra in (["--author", "Fable"], ["--seen-through", self.first], ["--seen-through", ""]):
            with (
                self.subTest(extra=extra),
                patch.object(APPENDER, "CANONICAL_LOG", self.log),
                patch.object(sys, "argv", argv + extra),
                self.assertRaises(SystemExit),
            ):
                APPENDER.main()
        with (
            patch.object(APPENDER, "CANONICAL_LOG", self.log),
            patch.object(sys, "argv", [str(SCRIPT)]),
            self.assertRaises(SystemExit),
        ):
            APPENDER.main()
        self.assertEqual(self.log.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
