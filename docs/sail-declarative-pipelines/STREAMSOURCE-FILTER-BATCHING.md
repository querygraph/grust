# Keep marker-safe filtering efficient

Streaming filters must exclude control markers from user predicates while preserving
event order. Retractions cancel earlier rows. Sail encodes data, retractions and
markers in Arrow batches, which can alternate data and control rows. An earlier
marker must precede an error in later data.

## Why batching needs a decision

The implemented filter evaluates contiguous data runs and forwards marker runs.
Ordinary data batches use one direct filtering call. Alternating rows require many
small predicate calls and output batches, even when the input arrived as one batch.

A shared-host diagnostic compared the new filter with its predecessor using
identical safe predicates and verified outputs. Ratios divide new elapsed time
by previous elapsed time. Data-only medians were 0.99 to 1.01. Alternating-marker
medians were 17.9 to 141.1, with one output batch per input row. These measurements
used an unoptimized build; they identify fragmentation without establishing
production throughput.

Keep this implementation as a correctness reference while qualifying its cost.
First repeat the same cases in an optimized build, then vary marker placement and
frequency. Preserve every result, including slower cases.

## Options and next decision

Keeping each run separate gives simple, prompt forwarding but exposes dispatch
cost. Combining evaluated data with its following marker could reduce output
batches, at the cost of buffering, copies and latency. Gathering across markers
would require a different evaluation contract and is outside this repair.

Should a byte-bounded combiner be the next optimization? Require it to emit the
preceding data and marker before evaluating subsequent data. Compare exact ordered
outputs, first-error position, retained bytes and latency against the reference.
Choose a batching policy only if that experiment demonstrates useful savings.

This decision concerns unary filtering. It does not qualify checkpoint alignment,
state snapshots, durable publication or distributed recovery.
