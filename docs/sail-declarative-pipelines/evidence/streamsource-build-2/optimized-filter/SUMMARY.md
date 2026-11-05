# Exploratory filter cost comparison

Shared-host ratios only. Candidate time divided by baseline time: above one means more elapsed time.
Raw samples include every cell and both execution orders. No production throughput or memory ceiling is established.
Read receipt.json for the actual profile, compiler command, source hashes and host limitations.

| Rows/batch | Markers | Data selected | Input batches | Output rows | Output batches baseline/candidate | Ratio median | Ratio min–max |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | none | 0% | 512 | 0 | 512/512 | 1.0057 | 0.8761–1.1101 |
| 128 | none | 50% | 512 | 32768 | 512/512 | 0.9971 | 0.9477–1.0104 |
| 128 | none | 100% | 512 | 65536 | 512/512 | 1.0082 | 0.9855–1.0180 |
| 128 | alternating | 0% | 512 | 32768 | 512/65536 | 47.9481 | 44.3714–48.4157 |
| 128 | alternating | 50% | 512 | 49152 | 512/65536 | 30.5485 | 29.3797–30.7259 |
| 128 | alternating | 100% | 512 | 65536 | 512/65536 | 57.6963 | 56.1741–58.0382 |
| 8192 | none | 0% | 8 | 0 | 8/8 | 1.0046 | 0.9500–1.2695 |
| 8192 | none | 50% | 8 | 32768 | 8/8 | 0.9993 | 0.9977–1.0417 |
| 8192 | none | 100% | 8 | 65536 | 8/8 | 1.0010 | 0.7726–1.0094 |
| 8192 | alternating | 0% | 8 | 32768 | 8/65536 | 106.7252 | 101.5414–108.3678 |
| 8192 | alternating | 50% | 8 | 49152 | 8/65536 | 60.6014 | 54.4346–62.3723 |
| 8192 | alternating | 100% | 8 | 65536 | 8/65536 | 600.5340 | 589.5882–741.5030 |

The fixture reuses input buffers and drains output immediately. It does not measure source I/O, planning, distributed execution, retained downstream output or allocator peak memory.
Alternating markers are an intentionally adverse batching case. Extra kernel calls preserve event ordering and must not be removed by moving data across markers.
An unoptimized test run is diagnostic only. Even an optimized run on this shared host remains exploratory; dedicated-host measurements are needed for publishable absolute performance claims.
