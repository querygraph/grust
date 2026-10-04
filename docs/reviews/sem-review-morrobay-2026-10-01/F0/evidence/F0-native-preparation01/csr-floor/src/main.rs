//! F0: the floor of a CSR build from Parquet, with nothing of Sail in the way.
//!
//! Reads `id` from a vertex file and two endpoint columns from an edge file
//! (files or directories of Parquet, BIGINT columns), maps the i64 ids to
//! dense indices, and builds an adjacency: degree count, prefix sum, fill.
//! The graph is taken as valid: ids unique, every endpoint a vertex. Vertex
//! ids stay i64 (the `ids` array); the dense targets are u32 under a checked
//! bound, or u64 with `--wide`. Neighbour order within a row is arrival
//! order; nothing is sorted except the id array used for the mapping. The
//! mapping is a direct table when the ids span at most 16 slots per vertex
//! and a binary search over the sorted ids otherwise (`--no-table` forces it).
//!
//! Prints one JSON object with the wall time of each phase.

use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, AtomicU64, Ordering::Relaxed};
use std::time::Instant;

use arrow_array::{Array, Int64Array};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::ProjectionMask;
use rayon::prelude::*;

fn parquet_files(path: &Path) -> Vec<PathBuf> {
    if path.is_file() {
        return vec![path.to_path_buf()];
    }
    let mut files: Vec<PathBuf> = std::fs::read_dir(path)
        .unwrap_or_else(|e| panic!("{}: {e}", path.display()))
        .map(|entry| entry.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "parquet"))
        .collect();
    files.sort();
    files
}

/// Decode the named BIGINT columns, one task per row group, into one vector per column.
fn read_columns(path: &Path, names: &[&str]) -> Vec<Vec<i64>> {
    let mut tasks = Vec::new(); // (file, row group, first row, rows)
    let mut total = 0usize;
    for file in parquet_files(path) {
        let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(&file).unwrap()).unwrap();
        for (group, meta) in builder.metadata().row_groups().iter().enumerate() {
            let rows = meta.num_rows() as usize;
            tasks.push((file.clone(), group, total, rows));
            total += rows;
        }
    }
    let columns: Vec<Vec<AtomicU64>> =
        names.iter().map(|_| (0..total).into_par_iter().map(|_| AtomicU64::new(0)).collect()).collect();
    tasks.par_iter().for_each(|(file, group, first, rows)| {
        let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(file).unwrap()).unwrap();
        let schema = builder.parquet_schema();
        let leaves: Vec<usize> = names
            .iter()
            .map(|name| {
                schema.columns().iter().position(|c| c.name() == *name)
                    .unwrap_or_else(|| panic!("{}: no column {name}", file.display()))
            })
            .collect();
        let mask = ProjectionMask::leaves(schema, leaves);
        let reader = builder.with_row_groups(vec![*group]).with_projection(mask).with_batch_size(1 << 16).build().unwrap();
        let mut row = *first;
        for batch in reader {
            let batch = batch.unwrap();
            for (name, column) in names.iter().zip(&columns) {
                let values = batch.column_by_name(name).unwrap().as_any().downcast_ref::<Int64Array>()
                    .unwrap_or_else(|| panic!("column {name} is not BIGINT"));
                assert_eq!(values.null_count(), 0, "column {name} has nulls");
                for (slot, value) in column[row..row + values.len()].iter().zip(values.values()) {
                    slot.store(*value as u64, Relaxed);
                }
            }
            row += batch.num_rows();
        }
        assert_eq!(row, first + rows);
    });
    columns.into_iter().map(|c| c.into_iter().map(|v| v.into_inner() as i64).collect()).collect()
}

fn flag(args: &[String], name: &str) -> bool {
    args.iter().any(|a| a == name)
}

fn option<'a>(args: &'a [String], name: &str, default: &'a str) -> &'a str {
    args.iter().position(|a| a == name).map(|i| args[i + 1].as_str()).unwrap_or(default)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let vertices = PathBuf::from(option(&args, "--vertices", ""));
    let edges = PathBuf::from(option(&args, "--edges", ""));
    let (src_name, dst_name) = (option(&args, "--src", "src"), option(&args, "--dst", "dst"));
    let undirected = flag(&args, "--undirected");
    let wide = flag(&args, "--wide");
    let threads: usize = option(&args, "--threads", "0").parse().unwrap();
    if threads > 0 {
        rayon::ThreadPoolBuilder::new().num_threads(threads).build_global().unwrap();
    }
    let started = Instant::now();

    let mut ids = read_columns(&vertices, &["id"]).pop().unwrap();
    let mut endpoints = read_columns(&edges, &[src_name, dst_name]);
    let dst = endpoints.pop().unwrap();
    let src = endpoints.pop().unwrap();
    let read_seconds = started.elapsed().as_secs_f64();

    // Dense indices: position in the sorted id array. Skipped when ids are 0..n already.
    let mapping = Instant::now();
    ids.par_sort_unstable();
    let n = ids.len();
    let m = src.len();
    let identity = n > 0 && ids[0] == 0 && ids[n - 1] == n as i64 - 1;
    assert!(wide || n <= u32::MAX as usize, "more than 2^32 - 1 vertices: use --wide");
    // When the ids span at most 16 slots per vertex, a direct table from id to
    // index replaces the binary search. u32::MAX marks an id that is not a vertex.
    let span = if n == 0 { 0 } else { (ids[n - 1] as i128 - ids[0] as i128 + 1) as u128 };
    let direct = !identity && !flag(&args, "--no-table") && n <= u32::MAX as usize && span <= 16 * n as u128;
    let table: Vec<u32> = if direct {
        let slots: Vec<AtomicU32> = (0..span as usize).into_par_iter().map(|_| AtomicU32::new(u32::MAX)).collect();
        ids.par_iter().enumerate().for_each(|(index, id)| slots[(id - ids[0]) as usize].store(index as u32, Relaxed));
        slots.into_iter().map(AtomicU32::into_inner).collect()
    } else {
        Vec::new()
    };
    let dense = |x: &i64| -> u64 {
        if identity {
            *x as u64
        } else if direct {
            let index = table[(*x - ids[0]) as usize];
            assert!(index != u32::MAX, "an edge endpoint is not a vertex");
            index as u64
        } else {
            ids.binary_search(x).expect("an edge endpoint is not a vertex") as u64
        }
    };
    let s: Vec<u64> = src.par_iter().map(dense).collect();
    let d: Vec<u64> = dst.par_iter().map(dense).collect();
    drop((src, dst));
    let map_seconds = mapping.elapsed().as_secs_f64();

    // Degree count, prefix sum, fill. Arc offsets are u64 whatever the target width.
    let building = Instant::now();
    let arcs = if undirected { 2 * m } else { m };
    let counts: Vec<AtomicU64> = (0..n + 1).into_par_iter().map(|_| AtomicU64::new(0)).collect();
    s.par_iter().for_each(|&u| { counts[u as usize].fetch_add(1, Relaxed); });
    if undirected {
        d.par_iter().for_each(|&v| { counts[v as usize].fetch_add(1, Relaxed); });
    }
    let mut offsets = vec![0u64; n + 1];
    let mut running = 0u64;
    for (offset, count) in offsets.iter_mut().zip(&counts) {
        *offset = running;
        running += count.load(Relaxed);
    }
    assert_eq!(running as usize, arcs);
    counts.par_iter().zip(&offsets).for_each(|(cursor, offset)| cursor.store(*offset, Relaxed));
    let cursors = counts;
    let (checksum, max_degree);
    if wide {
        let targets: Vec<AtomicU64> = (0..arcs).into_par_iter().map(|_| AtomicU64::new(0)).collect();
        s.par_iter().zip(&d).for_each(|(&u, &v)| {
            targets[cursors[u as usize].fetch_add(1, Relaxed) as usize].store(v, Relaxed);
            if undirected {
                targets[cursors[v as usize].fetch_add(1, Relaxed) as usize].store(u, Relaxed);
            }
        });
        checksum = targets.par_iter().map(|t| t.load(Relaxed)).sum::<u64>();
    } else {
        let targets: Vec<AtomicU32> = (0..arcs).into_par_iter().map(|_| AtomicU32::new(0)).collect();
        s.par_iter().zip(&d).for_each(|(&u, &v)| {
            targets[cursors[u as usize].fetch_add(1, Relaxed) as usize].store(v as u32, Relaxed);
            if undirected {
                targets[cursors[v as usize].fetch_add(1, Relaxed) as usize].store(u as u32, Relaxed);
            }
        });
        checksum = targets.par_iter().map(|t| t.load(Relaxed) as u64).sum::<u64>();
    }
    max_degree = offsets.windows(2).map(|w| w[1] - w[0]).max().unwrap_or(0);
    let build_seconds = building.elapsed().as_secs_f64();

    // Every arc contributes its target; an independent sum over the dense endpoints must agree.
    let expected: u64 = d.par_iter().sum::<u64>() + if undirected { s.par_iter().sum::<u64>() } else { 0 };
    assert_eq!(checksum, expected, "the adjacency does not hold the edges");
    println!(
        "{{\"vertices\": {n}, \"edges\": {m}, \"arcs\": {arcs}, \"undirected\": {undirected}, \"target_bits\": {}, \
         \"id_mapping\": \"{}\", \"threads\": {}, \"read_seconds\": {read_seconds:.3}, \
         \"map_seconds\": {map_seconds:.3}, \"build_seconds\": {build_seconds:.3}, \"total_seconds\": {:.3}, \
         \"max_degree\": {max_degree}, \"csr_bytes\": {}}}",
        if wide { 64 } else { 32 },
        if identity { "identity" } else if direct { "direct table" } else { "binary search" },
        rayon::current_num_threads(),
        started.elapsed().as_secs_f64(),
        (n + 1) * 8 + arcs * if wide { 8 } else { 4 } + n * 8,
    );
}
