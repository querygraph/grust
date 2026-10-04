//! The local half of "Sail feeds the CSR": build an outgoing CSR from edges whose
//! endpoints are already dense ids 0..n-1, as an engine would hand them over.
//!
//!     csr-from-dense --edges <dir or file> --vertices <n> [--src s] [--dst d] [--sorted] [--threads k]
//!
//! No id mapping and no hash table. Two modes:
//! - default: two streaming passes over the Parquet row groups, in parallel. Pass 1
//!   counts out-degrees, a prefix sum gives the offsets, pass 2 fills the targets.
//! - `--sorted`: the input is sorted by source (files in name order, rows in order).
//!   One streaming pass, in order: offsets from the run lengths, targets appended.
//!   The order is checked; an out-of-order row is an error, not a wrong CSR.
//!
//! Only the CSR is kept: offsets u64 (n + 1) and targets u32 (m). Endpoint columns
//! are never held whole. Prints one JSON object.

use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::time::Instant;

use arrow_array::{Array, Int64Array};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::ProjectionMask;
use rayon::prelude::*;

fn option<'a>(args: &'a [String], name: &str, default: &'a str) -> &'a str {
    args.iter().position(|a| a == name).map(|i| args[i + 1].as_str()).unwrap_or(default)
}

fn parquet_files(path: &Path) -> Vec<PathBuf> {
    if path.is_file() {
        return vec![path.to_path_buf()];
    }
    let mut files: Vec<PathBuf> = std::fs::read_dir(path)
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|p| p.extension().is_some_and(|x| x == "parquet"))
        .collect();
    files.sort();
    files
}

/// Every (file, row group) of the input, in file and row-group order.
fn row_groups(files: &[PathBuf]) -> Vec<(PathBuf, usize)> {
    let mut groups = Vec::new();
    for file in files {
        let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(file).unwrap()).unwrap();
        for group in 0..builder.metadata().num_row_groups() {
            groups.push((file.clone(), group));
        }
    }
    groups
}

/// Stream one row group's two endpoint columns, batch by batch.
fn each_batch(file: &Path, group: usize, src: &str, dst: &str, mut visit: impl FnMut(&[i64], &[i64])) {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(file).unwrap()).unwrap();
    let schema = builder.parquet_schema();
    let leaves: Vec<usize> = [src, dst]
        .iter()
        .map(|name| schema.columns().iter().position(|c| c.name() == *name).unwrap_or_else(|| panic!("no column {name}")))
        .collect();
    let mask = ProjectionMask::leaves(schema, leaves);
    let reader = builder.with_row_groups(vec![group]).with_projection(mask).with_batch_size(1 << 16).build().unwrap();
    for batch in reader {
        let batch = batch.unwrap();
        let column = |name: &str| batch.column_by_name(name).unwrap().as_any().downcast_ref::<Int64Array>().unwrap().clone();
        let (s, d) = (column(src), column(dst));
        assert_eq!(s.null_count() + d.null_count(), 0, "null endpoint");
        visit(s.values(), d.values());
    }
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let edges = PathBuf::from(option(&args, "--edges", ""));
    let n: usize = option(&args, "--vertices", "0").parse().unwrap();
    let (src, dst) = (option(&args, "--src", "s"), option(&args, "--dst", "d"));
    let sorted = args.iter().any(|a| a == "--sorted");
    let threads: usize = option(&args, "--threads", "0").parse().unwrap();
    if threads > 0 {
        rayon::ThreadPoolBuilder::new().num_threads(threads).build_global().unwrap();
    }
    assert!(n > 0 && n <= u32::MAX as usize, "--vertices must be in 1..=2^32-1");
    let started = Instant::now();
    let groups = row_groups(&parquet_files(&edges));
    let check = |s: i64, d: i64| {
        assert!(s >= 0 && (s as usize) < n && d >= 0 && (d as usize) < n, "endpoint outside 0..n: ({s}, {d})");
    };

    let (offsets, targets, pass_seconds): (Vec<u64>, Vec<u32>, Vec<f64>) = if sorted {
        let mut offsets = vec![0u64; n + 1];
        let mut targets: Vec<u32> = Vec::new();
        let mut current = 0usize; // next row whose start is not yet written
        let mut previous = -1i64;
        for (file, group) in &groups {
            each_batch(file, *group, src, dst, |s, d| {
                targets.reserve(s.len());
                for (&u, &v) in s.iter().zip(d) {
                    check(u, v);
                    assert!(u >= previous, "input not sorted by source: {u} after {previous}");
                    previous = u;
                    while current <= u as usize {
                        offsets[current] = targets.len() as u64;
                        current += 1;
                    }
                    targets.push(v as u32);
                }
            });
        }
        while current <= n {
            offsets[current] = targets.len() as u64;
            current += 1;
        }
        let seconds = started.elapsed().as_secs_f64();
        (offsets, targets, vec![seconds])
    } else {
        let counts: Vec<AtomicU64> = (0..n + 1).into_par_iter().map(|_| AtomicU64::new(0)).collect();
        groups.par_iter().for_each(|(file, group)| {
            each_batch(file, *group, src, dst, |s, d| {
                for (&u, &v) in s.iter().zip(d) {
                    check(u, v);
                    counts[u as usize].fetch_add(1, Relaxed);
                }
            })
        });
        let counted = started.elapsed().as_secs_f64();
        let mut offsets = vec![0u64; n + 1];
        let mut running = 0u64;
        for (offset, count) in offsets.iter_mut().zip(&counts) {
            *offset = running;
            running += count.load(Relaxed);
        }
        let m = running as usize;
        counts.par_iter().zip(&offsets).for_each(|(cursor, offset)| cursor.store(*offset, Relaxed));
        let slots: Vec<std::sync::atomic::AtomicU32> = (0..m).into_par_iter().map(|_| std::sync::atomic::AtomicU32::new(0)).collect();
        groups.par_iter().for_each(|(file, group)| {
            each_batch(file, *group, src, dst, |s, d| {
                for (&u, &v) in s.iter().zip(d) {
                    let at = counts[u as usize].fetch_add(1, Relaxed);
                    slots[at as usize].store(v as u32, Relaxed);
                }
            })
        });
        let targets: Vec<u32> = slots.into_iter().map(|a| a.into_inner()).collect();
        // Rows are filled in arrival order; offsets[n] is the total.
        let filled = started.elapsed().as_secs_f64();
        (offsets, targets, vec![counted, filled - counted])
    };

    let total = started.elapsed().as_secs_f64();
    let m = targets.len();
    let max_degree = (0..n).into_par_iter().map(|u| offsets[u + 1] - offsets[u]).max().unwrap_or(0);
    let target_sum: u64 = targets.par_iter().map(|&t| t as u64).sum();
    println!(
        "{{\"mode\": \"{}\", \"vertices\": {n}, \"edges\": {m}, \"row_groups\": {}, \"threads\": {}, \
         \"pass_seconds\": {:?}, \"total_seconds\": {total:.3}, \"max_degree\": {max_degree}, \
         \"target_sum\": {target_sum}, \"csr_bytes\": {}}}",
        if sorted { "sorted, one pass" } else { "unsorted, two passes" },
        groups.len(),
        rayon::current_num_threads(),
        pass_seconds.iter().map(|s| (s * 1000.0).round() / 1000.0).collect::<Vec<_>>(),
        (n + 1) * 8 + m * 4
    );
}
