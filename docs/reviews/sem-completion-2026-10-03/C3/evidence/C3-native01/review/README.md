# C3: observed native host admission and final lease release

Independent closed-artifact review passes this small **local native accounting control**. It uses the actual4b88 release wheel and native9f Sail runtime. The complete three-cycle degree export contains exactly `(0,1),(1,1),(2,1)` in canonical STRING/BIGINT columns; the staged graph reports three nodes, three edges, revision1, and one finished degree cursor with three rows.

## Actual reservation ledger

Every event is emitted by the actually executed Sail server PID54416. The two different lease ids carry the same exact installed manifest/wheel content identity:
`nutmeg@0.1.0:d0547c480d0ef7d08bbe8186b2b515f069145f77a33793c6bd8cf718f8b8e553`.

| Observed event | Lease id | Native prepaid quota, bytes | Actual host `pool_reserved`, bytes |
|---|---:|---:|---:|
| First session admitted | 1 | 134,217,728 | 134,217,728 |
| First session's final owner released | 1 | 134,217,728 | 0 |
| Fresh replacement admitted | 2 | 134,217,728 | 134,217,728 |
| Replacement's final owner released | 2 | 134,217,728 | 0 |

The host audit reads `MemoryPool::reserved()` at each admission and after the reservation is returned on the final lease drop. These observed counters are stronger evidence than a session-stop acknowledgement or a configured pool sum.

While the first session remains admitted, a distinct second session requests another134,217,728 bytes and receives a typed **native host admission refusal**. Its returned cause explicitly reports greedy pool usage128MiB, total192MiB, and64MiB remaining. No second lease is admitted. After the first lease actually returns to zero, the fresh replacement admits its own lease and has no graphs or reads; its participating native used/peak/staged bytes are all zero. All three session incarnations are distinct.

## Participating native allocations

The first post-degree native diagnostic reports limit134,217,728 bytes, used1,261 bytes, peak34,248 bytes and staged156 bytes. Its retained projection admission is1,105 bytes. The finished degree cursor reports one batch/three rows, live32,963 bytes, peak32,987 bytes and12 work units. These diagnostics describe participating native allocation accounting and the observed cursor; they are separate from the host's coarse prepaid128MiB reservation, OS RSS and unique physical memory.

## Qualification and closure

This passes actual native quota identity, shared-host contention/refusal, final reservation return, replacement isolation, full tiny output correctness, unchanged source/client/helper bytes, and ordinary owned lifecycle closure. Producer and outside oracle both return0 with actual completed waits; the native server returns0, all owned groups are absent, the waited serial owner releases its locks, and the detached supervisor actually waits for it. Source stays clean at Sail9f0aa7d2a and wheel source4b88c8fb4. There are no workers in this declared local control.

This does **not** qualify a32GiB OS envelope, PSS, unique physical accounting, measured nonpool headroom, transport buffers, or operator spill. The64MiB remainder is host reservation capacity, not measured nonpool RAM headroom. The sampler has three500ms samples, which cannot supply an OS hard peak or full phase accounting. This explicitly induced software admission refusal is separate from transport loss, timeout and kernel OOM; it does not diagnose historical X2 failures. All five stronger qualification flags remain false in `portable-accounting.json`.

## Portable evidence

`native-lease-ledger.csv` preserves the complete four-event ledger, `full-degree-result.csv` preserves every result row, and `portable-accounting.json` plus its JSON Schema bind the observed values, source/runtime identities, exact raw-file SHA256 pins and closure. The full native status and raw producer clocks remain in the original private artifact directory. No benchmark performance claim is made by this control.

Raw evidence: `/Users/alexy/src/grust-benchmark-runs/sem-completion-20261003/c3-native01`. Admission, owner, oracle and supervisor evidence: `../queue01`; exact source freeze: `../freeze01.json`.
