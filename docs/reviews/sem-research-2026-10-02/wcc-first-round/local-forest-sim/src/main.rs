//! How many edges would a per-partition union-find leave?
//!
//! Reads two BIGINT endpoint columns from a Parquet edge file, splits the
//! edges into P partitions three ways, and runs one union-find per partition
//! in a single pass, as a `mapPartitions` would. A partition's output is its
//! spanning forest in star form: one pair `(vertex, local root)` for every
//! vertex that is not its own root, which is `V_p - c_p` pairs. The union of
//! those forests has the components of the input, so it can replace the edge
//! list. This program counts the pairs and times the pass; it writes nothing.
//!
//! Partitionings:
//! - `contiguous`: P equal runs in file order, the shape of a Parquet scan
//!   split by row-group ranges;
//! - `roundrobin`: edge i goes to partition i mod P, the shape of a keyless
//!   repartition;
//! - `hash_src`: partition by a hash of the source id, the shape of
//!   `repartition(P, src)`.
//!
//! It then merges the forests in one more union-find and checks that the
//! number of components equals that of a union-find over all the edges.
//! Prints one JSON object per (partitioning, P).

use std::fs::File;
use std::path::{Path, PathBuf};
use std::time::Instant;

use arrow_array::{Array, Int64Array};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::ProjectionMask;
use rayon::prelude::*;
use rustc_hash::FxHashMap;

fn read_edges(path: &Path, src: &str, dst: &str) -> (Vec<i64>, Vec<i64>) {
    let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path).unwrap()).unwrap();
    let groups = builder.metadata().num_row_groups();
    let per_group: Vec<(Vec<i64>, Vec<i64>)> = (0..groups)
        .into_par_iter()
        .map(|group| {
            let builder = ParquetRecordBatchReaderBuilder::try_new(File::open(path).unwrap()).unwrap();
            let schema = builder.parquet_schema();
            let leaves: Vec<usize> = [src, dst]
                .iter()
                .map(|name| schema.columns().iter().position(|c| c.name() == *name).expect("column"))
                .collect();
            let mask = ProjectionMask::leaves(schema, leaves);
            let reader = builder.with_row_groups(vec![group]).with_projection(mask).build().unwrap();
            let (mut s, mut d) = (Vec::new(), Vec::new());
            for batch in reader {
                let batch = batch.unwrap();
                let column = |name: &str| {
                    batch.column_by_name(name).unwrap().as_any().downcast_ref::<Int64Array>().unwrap().clone()
                };
                let (a, b) = (column(src), column(dst));
                assert_eq!(a.null_count() + b.null_count(), 0);
                s.extend_from_slice(a.values());
                d.extend_from_slice(b.values());
            }
            (s, d)
        })
        .collect();
    let total: usize = per_group.iter().map(|(s, _)| s.len()).sum();
    let (mut s, mut d) = (Vec::with_capacity(total), Vec::with_capacity(total));
    for (a, b) in per_group {
        s.extend(a);
        d.extend(b);
    }
    (s, d)
}

/// A union-find over ids first seen in the stream: a hash map to local
/// indices, parents in a vector, union by smaller original id, path halving.
struct Forest {
    index: FxHashMap<i64, u32>,
    ids: Vec<i64>,
    parent: Vec<u32>,
    components: usize,
}

impl Forest {
    fn new() -> Self {
        Self { index: FxHashMap::default(), ids: Vec::new(), parent: Vec::new(), components: 0 }
    }

    fn local(&mut self, id: i64) -> u32 {
        let next = self.ids.len() as u32;
        let slot = *self.index.entry(id).or_insert(next);
        if slot == next {
            self.ids.push(id);
            self.parent.push(next);
            self.components += 1;
        }
        slot
    }

    fn find(&mut self, mut x: u32) -> u32 {
        while self.parent[x as usize] != x {
            let grand = self.parent[self.parent[x as usize] as usize];
            self.parent[x as usize] = grand;
            x = grand;
        }
        x
    }

    fn union(&mut self, a: i64, b: i64) {
        let (a, b) = (self.local(a), self.local(b));
        let (ra, rb) = (self.find(a), self.find(b));
        if ra != rb {
            // The smaller original id is the root, so a star's centre is its minimum.
            let (root, child) = if self.ids[ra as usize] < self.ids[rb as usize] { (ra, rb) } else { (rb, ra) };
            self.parent[child as usize] = root;
            self.components -= 1;
        }
    }

    /// The star pairs `(vertex, root)` for every vertex that is not a root.
    fn stars(&mut self) -> Vec<(i64, i64)> {
        let mut pairs = Vec::with_capacity(self.ids.len() - self.components);
        for x in 0..self.ids.len() as u32 {
            let root = self.find(x);
            if root != x {
                pairs.push((self.ids[x as usize], self.ids[root as usize]));
            }
        }
        pairs
    }
}

fn mix(id: i64) -> u64 {
    let mut x = id as u64;
    x ^= x >> 33;
    x = x.wrapping_mul(0xff51afd7ed558ccd);
    x ^= x >> 33;
    x = x.wrapping_mul(0xc4ceb9fe1a85ec53);
    x ^ (x >> 33)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let path = PathBuf::from(&args[1]);
    let (src, dst) = (args.get(2).map_or("source", String::as_str), args.get(3).map_or("target", String::as_str));
    let partitions: Vec<usize> = args
        .get(4)
        .map_or("1,4,10,16,64,256,1024".to_string(), String::clone)
        .split(',')
        .map(|p| p.parse().unwrap())
        .collect();
    let started = Instant::now();
    let (s, d) = read_edges(&path, src, dst);
    let edges = s.len();
    eprintln!("read {edges} edges in {:.2}s", started.elapsed().as_secs_f64());

    // The reference: one union-find over everything.
    let started = Instant::now();
    let mut whole = Forest::new();
    for (a, b) in s.iter().zip(&d) {
        whole.union(*a, *b);
    }
    let (vertices, components) = (whole.ids.len(), whole.components);
    let whole_seconds = started.elapsed().as_secs_f64();
    println!(
        "{{\"graph\":\"{}\",\"edges\":{edges},\"endpoint_vertices\":{vertices},\"components\":{components},\"one_union_find_seconds\":{whole_seconds:.3},\"one_union_find_edges_per_second\":{:.0}}}",
        path.file_name().unwrap().to_string_lossy(),
        edges as f64 / whole_seconds
    );
    drop(whole);

    for scheme in ["contiguous", "roundrobin", "hash_src"] {
        for &p in &partitions {
            if p == 1 && scheme != "contiguous" {
                continue;
            }
            // Bucket the edge positions; contiguous needs no copy.
            let buckets: Vec<Vec<u32>> = if scheme == "contiguous" {
                Vec::new()
            } else {
                let mut buckets: Vec<Vec<u32>> = (0..p).map(|_| Vec::with_capacity(edges / p + 1)).collect();
                for i in 0..edges {
                    let b = if scheme == "roundrobin" { i % p } else { (mix(s[i]) % p as u64) as usize };
                    buckets[b].push(i as u32);
                }
                buckets
            };
            assert!(edges <= u32::MAX as usize);
            let started = Instant::now();
            let results: Vec<(usize, usize, f64, Vec<(i64, i64)>)> = (0..p)
                .into_par_iter()
                .map(|part| {
                    let t = Instant::now();
                    let mut forest = Forest::new();
                    if scheme == "contiguous" {
                        let (lo, hi) = (edges * part / p, edges * (part + 1) / p);
                        for i in lo..hi {
                            forest.union(s[i], d[i]);
                        }
                    } else {
                        for &i in &buckets[part] {
                            forest.union(s[i as usize], d[i as usize]);
                        }
                    }
                    let stars = forest.stars();
                    (forest.ids.len(), forest.components, t.elapsed().as_secs_f64(), stars)
                })
                .collect();
            let wall = started.elapsed().as_secs_f64();
            let forest_edges: usize = results.iter().map(|r| r.3.len()).sum();
            let max_vertices = results.iter().map(|r| r.0).max().unwrap();
            let sum_vertices: usize = results.iter().map(|r| r.0).sum();
            let cpu: f64 = results.iter().map(|r| r.2).sum();
            // Merge the forests and check the answer.
            let started = Instant::now();
            let mut merged = Forest::new();
            for (_, _, _, stars) in &results {
                for (a, b) in stars {
                    merged.union(*a, *b);
                }
            }
            let merge_seconds = started.elapsed().as_secs_f64();
            // A vertex whose every edge is a self-loop is in no star; count it apart.
            let merged_components = merged.components + (vertices - merged.ids.len());
            assert_eq!(merged_components, components, "the forests lost or joined a component");
            println!(
                "{{\"scheme\":\"{scheme}\",\"partitions\":{p},\"forest_edges\":{forest_edges},\"kept_fraction\":{:.4},\"sum_partition_vertices\":{sum_vertices},\"max_partition_vertices\":{max_vertices},\"pass_wall_seconds\":{wall:.3},\"pass_cpu_seconds\":{cpu:.3},\"edges_per_cpu_second\":{:.0},\"merge_seconds\":{merge_seconds:.3}}}",
                forest_edges as f64 / edges as f64,
                edges as f64 / cpu
            );
        }
    }
}
