# Frozen 300-case public regression runner

Run `run.py` from this directory with an explicit full `--commit` and fresh `--output`. The script retains its historical default; always override it. It operates only on the clean detached `/Users/alexy/src/sail-sdp-gate` checkout, builds its CLI, binds the binary/source hashes, owns port50094 and stops only its own server. Existing output directories and occupied ports are refused.

Example from the integration checkout:

```sh
/Users/alexy/src/sail-pipelines-proposal/.venv/bin/python /Users/alexy/src/grust-sdp/docs/sail-declarative-pipelines/evidence/analysis-order/harness/run.py --commit 26500918b128deacab31b44de3625324a5f40298 --output /tmp/sail-sdp-next-public-fresh
```

The same 300 selected pytest case IDs and 67 pinned upstream Python cases are retained. `preparation.json` freezes all helper/test source hashes. The two streamingness feature fixtures now define their source before testing flow-type rejection; assertions are unchanged and paired Spark4.2.1 qualification is in the parent packet. `fixture-migration.json` records both changed hashes. The reference preparation commit is3847d4e57f56bf5a6fd074decc4efd4d049922d4; source-hash equality remains mandatory on later candidates.

Prior XML/report copies freeze selection provenance and are not results for a later candidate. This runner provides selected regression coverage; add feature-specific tests. It does not prove full Spark SDP acceptance, public CDC/streaming effects, Iggy durability or ORC writing. Preserve failed result directories.
