# Host baseline: Capitola and Morrobay, without any engine

Measured on 2026-10-02 with [`baseline.c`](baseline.c): about 100 lines of
portable C, `cc -O2`, no engine and no VM. It asks how much of the gate's
slowness is the machine.

## What it runs

Each test on one thread, then on N threads at once.

1. **Floating point.** `y = a*x + y` over 4,096 doubles (inside L1).
2. **Sequential memory.** Sum 512 MiB per thread, four passes.
3. **Random memory.** 2^25 dependent reads through one random cycle over
   512 MiB per thread.

## Result

| Test | Capitola, M1 Max, native | Morrobay, Xeon W-2191B, native |
|---|---|---|
| Floating point, 1 thread | 13.5 to 13.9 GFLOP/s | 6.7 to 7.0 GFLOP/s |
| Floating point, all threads | 73 to 84 (10 threads) | 88 (16 threads), 104 (36) |
| Sequential memory, 1 thread | 25 to 30 GiB/s | 13 to 15 GiB/s |
| Sequential memory, all threads | 83 to 113 (10 threads) | 84 to 86 (16 threads) |
| Random read, 1 thread | 142 to 173 ns | 105 ns |
| Random read, all threads | 276 to 313 ns (10 threads) | 114 ns (16 threads) |

Three runs on Capitola, two at 16 threads on Morrobay. Raw records:
[`runs.jsonl`](runs.jsonl). The 36-thread stream figure on Morrobay (15 GiB/s
in total) is 18 GiB of buffers being first touched at once, not a bandwidth;
it is left in the records and not used.

## Reading

- On one thread Morrobay is half of Capitola on arithmetic and on sequential
  memory. On random reads it is faster.
- With 16 threads Morrobay matches or exceeds Capitola's 10 on every test.
- So the hardware explains a factor of about 2 for a single-threaded job and
  about 1 for a job that uses its cores.

## Against what the engines showed

| Engine, cit-Patents WCC unless said | Gate VM over Capitola | What the hardware alone predicts |
|---|---|---|
| Banda ingest, one thread, graph500-24 | 4.7 | about 2 |
| graphframes-rs, 16 workers | 3.8 | about 1 |
| Pecan on Sail, 16 partitions | 10.4 | about 1 |

The rest is the virtual machine. The gate is a colima VM run by QEMU with
HVF: `-machine q35,accel=hvf -smp 32 -m 112640 -cpu host,-avx512vl,-pdpe1gb`
on 18 physical cores, with a virtio block device for the data disk. Two
things in that line are costly for these engines. Nested paging makes every
TLB miss dearer, and 1 GiB pages are disabled, which is what hash joins and
hash maps hit. And 32 virtual CPUs on 18 cores turn cross-thread wake-ups
into VM exits, which is what a many-threaded async runtime does all the time.
That would also explain why Sail, with more threads and more hand-offs per
row than a plain DataFusion binary, loses most.

This is an inference from three tests and one command line. The direct check
is cheap: run `baseline.c` inside the gate container with 16 threads. The
difference between that and the native column is the VM's cost on each kind
of work.

## What follows

- Time on the raw machine. Keep the VM as the Linux functional gate: it is
  where Linux builds, the wheel checks and the container limits are tested.
- A raw-machine cell is a native macOS x86-64 release build of each engine,
  run with the same scripts as the Capitola record
  ([`../A2-local/`](../A2-local/)). Memory limits then come from the engine's
  own pool settings, not from a container.
- Every gate time recorded so far stays what it is: a time in that VM. The
  ratios between engines measured inside it are biased against Sail by an
  amount this baseline does not give.

## Limits

- Three microbenchmarks are not a workload. They bound the hardware factor;
  they do not prove the VM mechanism.
- Morrobay had one busy system process during the run (a media analysis
  daemon at one core) and an idle VM.
- macOS on both hosts. The deployment target is Linux.
