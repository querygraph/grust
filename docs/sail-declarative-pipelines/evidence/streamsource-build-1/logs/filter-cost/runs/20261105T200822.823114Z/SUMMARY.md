# Exploratory filter cost comparison

Shared-host ratios only. Candidate time divided by baseline time: above one means more elapsed time.
Raw samples include every cell and both execution orders. No production throughput or memory ceiling is established.
Read receipt.json for the actual profile, compiler command, source hashes and host limitations.

| Rows/batch | Markers | Data selected | Input batches | Output rows | Output batches baseline/candidate | Ratio median | Ratio min–max |
| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 128 | none | 0% | 512 | 0 | 512/512 | 0.9915 | 0.9600–1.0026 |
| 128 | none | 50% | 512 | 32768 | 512/512 | 0.9931 | 0.9850–1.0241 |
| 128 | none | 100% | 512 | 65536 | 512/512 | 1.0036 | 0.9680–1.0821 |
| 128 | alternating | 0% | 512 | 32768 | 512/65536 | 28.0867 | 25.9622–28.5551 |
| 128 | alternating | 50% | 512 | 49152 | 512/65536 | 17.8927 | 17.7082–19.6208 |
| 128 | alternating | 100% | 512 | 65536 | 512/65536 | 42.8313 | 42.0650–44.2357 |
| 8192 | none | 0% | 8 | 0 | 8/8 | 1.0037 | 0.9953–1.0242 |
| 8192 | none | 50% | 8 | 32768 | 8/8 | 1.0052 | 0.9964–1.0193 |
| 8192 | none | 100% | 8 | 65536 | 8/8 | 1.0008 | 0.8880–1.0375 |
| 8192 | alternating | 0% | 8 | 32768 | 8/65536 | 44.6478 | 43.8898–45.0132 |
| 8192 | alternating | 50% | 8 | 49152 | 8/65536 | 26.8214 | 26.7582–27.4341 |
| 8192 | alternating | 100% | 8 | 65536 | 8/65536 | 141.1032 | 132.7029–143.7696 |

The fixture reuses input buffers and drains output immediately. It does not measure source I/O, planning, distributed execution, retained downstream output or allocator peak memory.
Alternating markers are an intentionally adverse batching case. Extra kernel calls preserve event ordering and must not be removed by moving data across markers.
An unoptimized test run is diagnostic only. Even an optimized run on this shared host remains exploratory; dedicated-host measurements are needed for publishable absolute performance claims.
