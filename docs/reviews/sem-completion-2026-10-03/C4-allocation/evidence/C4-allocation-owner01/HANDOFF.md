# Native C4 standalone allocator owner

Source preparation only; no Cargo or allocator execution happened here. Root must wait for active C2 gates to close before seeding a fresh private SSD target/cache. Root owns actual native gates and publication.

## Plan

allocator_models.Plan and plan.schema.json are the contract. Fresh physical result root directly under completion base named C4-allocation-run01; disjoint physical standalone source, private target/cargo_home and recorded seed manifests. Never an active C2 target/cache. Bind all eight frozen probe files from C4-allocation-native01/freeze01.json SHA82aaef4e7c4689621fd15ef18d54de5f1e68161e141d82a8884d020e73408e9f. Source paths may rebase, exact full bytes/hash set may not. source_origins is ordered concatenation of preparation.json copied_native_sources, lowerer_and_registry_sources, then df55_factory_source, preserved_historical_meter and dependency_lock_origin. All guarded before/after. Exact compiler/tool pins under1.97.1 x86_64 macOS toolchain; new helper pins and original C2-observer-build01 gate_models.py/gate_owner.py hashes6a33929b…/6125e36d…. Generic ownership functions do not require a new observer tree profile.

Two old shared gate.lock/serial-queue.lock; refuse reused receipts, keep locks after errors. Floors40GiB admission/20GiB active; jobs4/incremental0/offlineLocked. Schedule rustc -Vv; cargo -Vv; cargo fmt --all -- --check; cargo clippy --offline --locked --all-targets -- -D warnings; cargo test --offline --locked --all-targets; cargo build --offline --locked --release. Release opt3/fatLTO/codegen1/debug0/striptrue. Then six fresh processes4096U/A and100kU/A/A/U. Each14-line Rust output retains header,12 allocator phases and full internal semantic controls plus coherent requested-byte counters. No assertion is weakened.

## Root launch

Direct -I script cannot import siblings. Root isolated bootstrap must add this directory and original C2-observer-build01 directory:

```python
import subprocess
python = "/tmp/sem-output-oracle-venv/bin/python"
helpers = "/Volumes/Apo/graph-tests/results/sem-completion-20261003/C4-allocation-owner01"
shared = "/Volumes/Apo/graph-tests/results/sem-completion-20261003/C2-observer-build01"
boot = 'import runpy,sys;sys.path[:0]=sys.argv[1:3];sys.argv=sys.argv[3:];runpy.run_path(sys.argv[0],run_name="__main__")'
argv = [python,"-I","-B","-c",boot,helpers,shared,helpers+"/wait_allocator.py","--plan",PLAN]
# Root opens fresh launcher.log xb; short detached Popen survives tool lifetime.
subprocess.Popen(["/usr/bin/nohup",*argv],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
```

launch-receipt.json records actual ownerPID/wait/exit and receipt pin; receipt.json records all command PID/PGID/wait/log/current immutable closure. Failed/forced steps cannot qualify. Cleanup only unfinished directly owned groups; completed historical PIDs never signalled. Fsync contents+rename, no directory power-loss durability claim. Root independently observes launcher absence and retains raw logs/JSON/source.

## Scope

Copied native9f compact MIN versus actual DF55 ordered last_value factory selected by min_by, identical full3field payload/total key. Not historical generic struct MIN. Requested System allocations/counts, accumulator-reported bytes, Arrow output bytes and per-process lifetime peak RSS stay separate; no MiMalloc/nativequota/fullgraph/uniquephysical/PSS/OS32 claim. Timing exploratory shared host. Exact committed Rust-source gates required again before source publication; a frozen byte-copy verdict is not a Grust-commit verdict.
