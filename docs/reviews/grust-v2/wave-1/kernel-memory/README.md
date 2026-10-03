# Kernel memory discipline: the contract

Wave 1 of the Grust v2 plan agreed on
[querygraph/grust #36](https://github.com/querygraph/grust/pull/36). Sem asked:
"who allocate input buffers? who own them? lifetime? who allocate output
buffer? who own them? lifetime? We are crossing FFI here ... we must have
clear discipline contract there! Follow Arrow C-Interface philosophy."

The contract is below. It is also code: the sketch crate
[`../sketch/kernel-abi`](../sketch/kernel-abi/src/lib.rs) states it in Rust
types and in a C ABI, and four tests check it through the C ABI with a
counting host. Drafted by Claude for Alexy.

## Summary

1. **Input is the host's, output is the kernel's.** Each side allocates
   what it produces and the other side releases it, exactly once, as the
   Arrow C data interface prescribes for a consumer.
2. **The CSR crosses as one Arrow `LargeList<UInt32>` array.** Its offsets
   are the CSR offsets and its child values are the targets. No new format.
3. **Every byte a kernel allocates is admitted by the host first,** through
   a callback. Scratch is returned before the call ends. Output stays
   admitted until the host releases the output.
4. **The host's callbacks must outlive every output it received,** because
   releasing an output is what returns its bytes.
5. **No panic crosses the boundary.** Failures are codes with a message.

## The rules from the Arrow C data interface

Quoted from the specification
(<https://arrow.apache.org/docs/format/CDataInterface.html>, read
2026-10-03):

| Rule | Section |
|---|---|
| "Any data pointed to by the struct MUST be allocated and maintained by the producer." | Member allocation |
| "Consumers MUST call a base structure's release callback when they won't be using it anymore, but they MUST not call any of its children's release callbacks." | Release callback semantics, for consumers |
| "The release callback MUST mark the structure as released, by setting its `release` member to NULL." It must also release children and "free any data area directly owned by the structure". | Release callback semantics, for producers |
| "The consumer can *move* the `ArrowArray` structure by bitwise copying or shallow member-wise copying. Then it MUST mark the source structure released ... but *without* calling the release callback." | Moving an array |
| "Both the producer and the consumer SHOULD consider the exported data ... to be immutable." | Mutability |
| Buffer alignment to the primitive type is "recommended, but not required". | The ArrowArray structure |

The specification says nothing about threads. This contract adds a rule for
that (rule 6 below).

## The contract

### Who allocates, owns and releases what

| Object | Allocated by | Owned while in use by | `release` called by | Lives until |
|---|---|---|---|---|
| Input CSR buffers (offsets, targets, weights) | host | host (the producer) | the kernel calls the struct's `release`, exactly once | that call |
| Input `ArrowArray` struct | host | kernel, after it **moves** the struct (the host's copy is marked released) | kernel | before `grust_kernel_run` returns, on success and on failure |
| Input `ArrowSchema` | host | host; the kernel only borrows it | host | the host's choice |
| Kernel scratch | kernel | kernel | not exported | before the kernel returns |
| Output buffers | kernel | kernel (the producer) | the host calls the struct's `release`, exactly once | that call |
| Output `ArrowArray` and `ArrowSchema` | kernel | host | host | the host's choice |
| Error string | kernel | host | host, with `grust_error_free` | the host's choice |

### The rules

1. **Input is read-only and released once.** The kernel never writes an
   input buffer. It releases the input when it no longer reads any of it.
   In the sketch that is before the run function returns, on every path.
2. **Output is released once by the host.** Until then the kernel's
   buffers stay valid, whatever thread the host is on.
3. **Admission before allocation.** The kernel calls `reserve(bytes)` before
   allocating scratch or output. A refusal ends the run with
   `BUDGET_EXCEEDED`, after returning whatever was already admitted. Scratch
   bytes are returned (`release(bytes)`) before the run function returns.
   Output bytes are returned when the host releases the output: the output
   buffer carries its reservation, so the reservation lives exactly as long
   as the bytes.
4. **The host outlives its outputs.** The host's callbacks and their context
   stay valid until every output batch received has been released.
5. **No unwinding across the boundary.** A kernel panic is caught and
   returned as `PANICKED` with a message.
6. **Threads.** `reserve`, `release` and `cancelled` are thread-safe. An
   output's `release` may be called from any thread. The kernel uses at most
   `max_threads` threads and creates no thread that outlives the call.
7. **Cancellation.** The kernel polls `cancelled()` in its long loops, and
   stops with `CANCELLED` after returning its scratch.

### The CSR as one Arrow array

A CSR is exactly an Arrow list array: `n` rows, offsets of length `n + 1`,
child values of length `m`.

| CSR | Arrow |
|---|---|
| offsets | the `LargeList` offsets (`int64`, as Arrow's large list uses) |
| targets | the child array, `UInt32` while `n < 2^32` (`UInt64` above) |
| weights, when present | the child becomes a struct `{target: UInt32, weight: Float64}` |
| row `v` | list element `v`: the neighbours of `v`, in arrival order |

So the host exports one array, with the standard C data interface, and
needs no Grust type to do it. A transpose is a second list array.

### The C ABI (version 1)

```c
struct GrustHostV1 {
  void *ctx;
  int32_t (*reserve)(void *ctx, uint64_t bytes);   /* 0 admits */
  void    (*release)(void *ctx, uint64_t bytes);
  int32_t (*cancelled)(void *ctx);                  /* non-zero stops */
  uint32_t max_threads;
};

int32_t grust_kernel_run(const char *name,
                         struct ArrowArray *input,            /* moved: marked released */
                         const struct ArrowSchema *input_schema,
                         const struct GrustHostV1 *host,
                         struct ArrowArray *output,           /* written on success */
                         struct ArrowSchema *output_schema,
                         char **error);                       /* written on failure */
void grust_error_free(char *error);
```

Codes: `OK`, `INVALID_INPUT`, `BUDGET_EXCEEDED`, `CANCELLED`, `PANICKED`,
`UNKNOWN_KERNEL`. Options, when a kernel takes any, would be a JSON string;
the sketch's two kernels take none.

The output is a struct array of `n` rows (or `m` for per-edge results).
Row `i` is dense vertex `i`. There is no id column; the host attaches ids by
position.

### The same contract in Rust

For a host that links the kernels directly, the C ABI is not needed and the
same rules hold in types:

| C ABI | Rust |
|---|---|
| `GrustHostV1` | the `Host` trait: `reserve`, `release`, `is_cancelled`, `max_threads` |
| input `ArrowArray` | `Csr<'a>`, a borrowed view of a `LargeListArray`; it cannot outlive the array or free it |
| admitted output | `admitted_buffer`: an Arrow buffer whose owner holds a `Reservation`, returned when the last reference drops |
| scratch | `scratch()`: a `Vec` plus a `Reservation` that drops before `run` returns |
| `estimate` | `Kernel::estimate(n, m)`: an upper bound on what `run` will reserve, so a host may refuse before starting |

## Checked by the sketch

`cargo test` in `../sketch` runs four tests through the C ABI with a host
that counts bytes
([`kernel-abi/tests/contract.rs`](../sketch/kernel-abi/tests/contract.rs)):

| Test | What it shows |
|---|---|
| `output_bytes_stay_admitted_until_the_host_releases_the_output` | WCC on 6 vertices: peak admitted 48 bytes (scratch and output); 24 bytes still admitted after the call (the output); 0 after the host drops the output. The input's buffer was freed before the call returned. |
| `a_refused_reservation_fails_cleanly_and_leaks_nothing` | With room for the scratch only, the run fails with `BUDGET_EXCEEDED`, the input is still released, and nothing stays admitted. |
| `cancellation_and_unknown_kernels_are_errors_not_panics` | `CANCELLED` and `UNKNOWN_KERNEL` come back as codes; nothing stays admitted. |
| `out_degree_through_the_abi` | A kernel with output and no scratch: 48 bytes admitted until the output is released. |

In every test the host's input struct is marked released after the call, as
the moving rule requires.

## Open questions for Sem

1. **Prepaid or incremental admission.** The sketch reserves as it goes and
   offers `estimate` for a host that wants to admit everything up front.
   Today's Grust charges incrementally; the Sail prototype prepays. Is
   offering both right?
2. **Who owns the thread pool.** Across the C ABI the kernel owns its threads,
   bounded by `max_threads`. A Rust host could lend its own pool instead.
   Should the Rust API take a pool?
3. **Output in pieces.** One batch per run is simplest. A per-edge result on a
   large graph could instead be a stream (the Arrow C stream interface).
   Needed in the first version?
4. **Weights and edge ids.** Proposed as a struct child of the list. An edge's
   position in the targets is its id (yesterday's design note). Agreed?

## Limits

- The sketch has two small kernels and one example graph. It shows the
  contract holds, not that today's thirty kernels already follow it; moving
  them is later work.
- The C ABI was exercised from Rust through `extern "C"` functions in one
  process, not from C or across a dynamic library boundary.
- The Arrow rules were quoted from the current specification page, read
  2026-10-03.
