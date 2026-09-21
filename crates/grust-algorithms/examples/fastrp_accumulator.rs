//! Measure what FastRP's accumulator width costs, in accuracy and in time.
//!
//!     fastrp_accumulator accuracy [options]
//!     fastrp_accumulator time     [options]
//!
//! The same synthetic generator serves both modes, so an accuracy cell and a
//! timing cell with the same options describe the same graph. Storage is `f32`
//! throughout; only the registers the neighbourhood sums are formed in change.
//!
//! The generator exists to stress a summation, not to look like a social
//! network: `--hubs` nodes of out-degree `--hub-degree` are the worst case,
//! because they sum the most terms, and `--weights mixed` spreads the term
//! magnitudes over orders of magnitude, which is what actually destroys an
//! `f32` running total.

use std::time::Instant;

use grust_algorithms::{
    Accumulator, ExecutionContext, ExecutionLimits, FastRpOptions, GraphProjection, Orientation,
    ProjectionEdge, SnapshotIdentity, fast_rp_with,
};
use rayon::prelude::*;

/// A splitmix64 stream, so a configuration is reproducible from its seed
/// alone and does not depend on the crate's own random module.
struct Rng(u64);

impl Rng {
    fn next(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }
    fn below(&mut self, bound: usize) -> usize {
        (self.next() % bound as u64) as usize
    }
    fn unit(&mut self) -> f64 {
        (self.next() >> 11) as f64 / (1u64 << 53) as f64
    }
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Weights {
    /// Every arc weighs one: the easiest case for an `f32` total.
    Uniform,
    /// Log-uniform over six orders of magnitude, shuffled.
    Mixed,
    /// Log-uniform, but laid out largest first inside each node's arc range,
    /// which is the adversarial order for a running total.
    Descending,
}

struct Config {
    nodes: usize,
    degree: usize,
    hubs: usize,
    hub_degree: usize,
    dimension: usize,
    weights: Weights,
    twins: usize,
    seed: u64,
    workers: usize,
    samples: usize,
    k: usize,
    label: String,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            nodes: 20_000,
            degree: 16,
            hubs: 4,
            hub_degree: 8_000,
            dimension: 256,
            weights: Weights::Mixed,
            twins: 0,
            seed: 7,
            workers: 0,
            samples: 512,
            k: 10,
            label: String::new(),
        }
    }
}

/// Build the projection the whole run uses.
fn build(config: &Config) -> Result<GraphProjection, Box<dyn std::error::Error>> {
    let mut rng = Rng(config.seed);
    // Per node first, so twins can be made by copying a neighbourhood.
    let mut targets: Vec<Vec<usize>> = Vec::with_capacity(config.nodes);
    let mut weights: Vec<Vec<f64>> = Vec::with_capacity(config.nodes);
    for node in 0..config.nodes {
        let out = if node < config.hubs {
            config.hub_degree.min(config.nodes)
        } else {
            config.degree
        };
        targets.push((0..out).map(|_| rng.below(config.nodes)).collect());
        weights.push(
            (0..out)
                .map(|_| match config.weights {
                    Weights::Uniform => 1.0,
                    _ => 10f64.powf(rng.unit() * 6.0 - 3.0),
                })
                .collect(),
        );
    }
    // Twins: pairs of rows whose neighbourhoods agree except in one arc, so
    // their embeddings sit a hair apart and their nearest-neighbour lists have
    // almost no headroom. Without these the ranking test can only report that
    // well-separated lists stayed put.
    for pair in 0..config.twins {
        let (a, b) = (config.hubs + 2 * pair, config.hubs + 2 * pair + 1);
        if b >= config.nodes {
            break;
        }
        targets[b] = targets[a].clone();
        weights[b] = weights[a].clone();
        if let Some(last) = targets[b].last_mut() {
            *last = rng.below(config.nodes);
        }
    }
    if config.weights == Weights::Descending {
        // Largest first inside each node's own arc range, which is the order
        // the kernel sums them in and the adversarial one for a running total.
        for row in weights.iter_mut() {
            row.sort_by(|a, b| b.partial_cmp(a).unwrap());
        }
    }
    let mut pairs: Vec<(usize, usize)> = Vec::new();
    for (node, row) in targets.iter().enumerate() {
        for &target in row {
            pairs.push((node, target));
        }
    }
    let weights: Vec<f64> = weights.into_iter().flatten().collect();
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 48 << 30,
        work_units: usize::MAX,
        batch_rows: 8192,
        deadline: None,
    })?;
    let context = if config.workers == 0 {
        context
    } else {
        context.with_concurrency(config.workers)?
    };
    let names: Vec<_> = (0..config.nodes).map(|n| n.to_string().into()).collect();
    let edges: Vec<_> = pairs
        .iter()
        .enumerate()
        .map(|(ordinal, &(source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect();
    Ok(GraphProjection::from_topology(
        SnapshotIdentity::new("accumulator".into(), "r1".into(), "bench".into())?,
        names,
        edges,
        Some(weights),
        Orientation::Outgoing,
        &context,
    )?)
}

fn options(config: &Config) -> FastRpOptions<'static> {
    FastRpOptions {
        dimension: config.dimension,
        iteration_weights: &[0.0, 1.0, 1.0],
        self_influence: 0.0,
        normalization_strength: 0.0,
        seed: 11,
    }
}

fn median(values: &mut [f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    values.sort_by(|a, b| a.partial_cmp(b).unwrap());
    values[values.len() / 2]
}

/// Cosine between two rows; zero rows give zero, which is then reported as a
/// worst case rather than hidden.
fn cosine(a: &[f32], b: &[f32]) -> f64 {
    let mut dot = 0.0f64;
    let mut na = 0.0f64;
    let mut nb = 0.0f64;
    for (&x, &y) in a.iter().zip(b) {
        dot += f64::from(x) * f64::from(y);
        na += f64::from(x) * f64::from(x);
        nb += f64::from(y) * f64::from(y);
    }
    if na == 0.0 || nb == 0.0 {
        return 0.0;
    }
    dot / (na.sqrt() * nb.sqrt())
}

/// The `k + 1` rows most similar to `row` by cosine, best first, with their
/// scores. The extra row is the first one outside the list, which is what the
/// boundary gap is measured against.
fn neighbours(values: &[f32], d: usize, n: usize, row: usize, k: usize) -> Vec<(usize, f64)> {
    let mine = &values[row * d..(row + 1) * d];
    let mut scored: Vec<(f64, usize)> = (0..n)
        .filter(|&other| other != row)
        .map(|other| (cosine(mine, &values[other * d..(other + 1) * d]), other))
        .collect();
    // Ties break on the row number, so a tie cannot masquerade as a reorder.
    scored.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap().then(a.1.cmp(&b.1)));
    scored.truncate(k + 1);
    scored
        .into_iter()
        .map(|(score, other)| (other, score))
        .collect()
}

struct Diff {
    max_abs: f64,
    median_abs: f64,
    max_rel: f64,
    median_rel: f64,
    worst_cosine: f64,
    median_cosine: f64,
    identical: bool,
    /// Share of components that differ at all. A fixture that leaves this at
    /// zero has not reached the accumulator and is not evidence.
    differing: f64,
}

fn compare(a: &[f32], b: &[f32], d: usize) -> Diff {
    let mut abs: Vec<f64> = Vec::with_capacity(a.len());
    let mut rel: Vec<f64> = Vec::with_capacity(a.len());
    for (&x, &y) in a.iter().zip(b) {
        let difference = (f64::from(x) - f64::from(y)).abs();
        abs.push(difference);
        let scale = f64::from(x).abs().max(f64::from(y).abs());
        if scale > 0.0 {
            rel.push(difference / scale);
        }
    }
    let nonzero = abs.iter().filter(|&&v| v != 0.0).count();
    let identical = nonzero == 0;
    let differing = nonzero as f64 / abs.len().max(1) as f64;
    let mut cosines: Vec<f64> = a
        .chunks(d)
        .zip(b.chunks(d))
        .map(|(x, y)| cosine(x, y))
        .collect();
    let max_abs = abs.iter().copied().fold(0.0f64, f64::max);
    let max_rel = rel.iter().copied().fold(0.0f64, f64::max);
    let worst_cosine = cosines.iter().copied().fold(f64::INFINITY, f64::min);
    Diff {
        max_abs,
        median_abs: median(&mut abs),
        max_rel,
        median_rel: median(&mut rel),
        worst_cosine,
        median_cosine: median(&mut cosines),
        identical,
        differing,
    }
}

fn accuracy(config: &Config) -> Result<(), Box<dyn std::error::Error>> {
    let graph = build(config)?;
    let d = config.dimension;
    let n = graph.node_count();
    let single = fast_rp_with(&graph, options(config), Accumulator::Single)?;
    let double = fast_rp_with(&graph, options(config), Accumulator::Double)?;
    let exact = fast_rp_with(&graph, options(config), Accumulator::Compensated)?;
    println!(
        "== {} | nodes {n} arcs {} dim {d} hubs {}x{} twins {} weights {}",
        config.label,
        graph.edge_count(),
        config.hubs,
        config.hub_degree,
        config.twins,
        match config.weights {
            Weights::Uniform => "uniform",
            Weights::Mixed => "mixed",
            Weights::Descending => "descending",
        }
    );
    for (name, left, right) in [
        ("f32 vs f64", single.values(), double.values()),
        ("f32 vs exact", single.values(), exact.values()),
        ("f64 vs exact", double.values(), exact.values()),
    ] {
        let diff = compare(left, right, d);
        println!(
            "{name:<13} maxabs {:.3e} medabs {:.3e} maxrel {:.3e} medrel {:.3e} \
             1-cos_worst {:.3e} 1-cos_med {:.3e} differing {:.4}{}",
            diff.max_abs,
            diff.median_abs,
            diff.max_rel,
            diff.median_rel,
            1.0 - diff.worst_cosine,
            1.0 - diff.median_cosine,
            diff.differing,
            if diff.identical {
                "  IDENTICAL-BIT-FOR-BIT"
            } else {
                ""
            }
        );
    }

    // The ranking test. A sample of rows, their k nearest by cosine under each
    // accumulator, compared as ordered lists and as sets. The hub rows are put
    // in the sample by hand: they sum the most terms, so a uniform sample of
    // twenty thousand rows would almost never contain one.
    let mut rng = Rng(config.seed ^ 0xABCD);
    let mut sample: Vec<usize> = (0..(config.hubs + 2 * config.twins).min(n)).collect();
    while sample.len() < config.samples.min(n) {
        sample.push(rng.below(n));
    }
    let lists = |values: &[f32]| -> Vec<Vec<(usize, f64)>> {
        sample
            .par_iter()
            .map(|&row| neighbours(values, d, n, row, config.k))
            .collect()
    };
    let a = lists(single.values());
    let b = lists(double.values());
    let c = lists(exact.values());
    // The control. Storage is f32 by decision, so the reference is already
    // rounded to within half an ulp per component before anyone ranks it.
    // Nudging each component of the reference by one ulp, in a direction drawn
    // per component, is a perturbation no accumulator can avoid; a reorder
    // count at that level is the floor any accumulator is measured against.
    let mut noise_rng = Rng(config.seed ^ 0x5EED);
    let noisy: Vec<f32> = exact
        .values()
        .iter()
        .map(|&v| match noise_rng.below(2) {
            0 => v.next_down(),
            _ => v.next_up(),
        })
        .collect();
    let e = lists(&noisy);
    for (name, left, right) in [
        ("f32 vs f64", &a, &b),
        ("f32 vs exact", &a, &c),
        ("f64 vs exact", &b, &c),
        ("1ulp vs exact", &e, &c),
    ] {
        let mut top1 = 0usize;
        let mut set_changed = 0usize;
        let mut order_changed = 0usize;
        for (x, y) in left.iter().zip(right.iter()) {
            let rows = |list: &Vec<(usize, f64)>| -> Vec<usize> {
                list.iter().take(config.k).map(|&(row, _)| row).collect()
            };
            let (x, y) = (rows(x), rows(y));
            if x.first() != y.first() {
                top1 += 1;
            }
            if x != y {
                order_changed += 1;
            }
            let mut xs = x.clone();
            let mut ys = y.clone();
            xs.sort_unstable();
            ys.sort_unstable();
            if xs != ys {
                set_changed += 1;
            }
        }
        println!(
            "{name:<13} top{} membership changed {set_changed}/{} order changed \
             {order_changed}/{} top1 changed {top1}/{}",
            config.k,
            sample.len(),
            sample.len(),
            sample.len()
        );
    }

    // How much headroom the ranking has: the cosine gap a perturbation would
    // have to exceed to reorder a list. Measured on the compensated reference,
    // so it describes the graph rather than either accumulator. Compare it
    // against the `1-cos` figures above: a gap far larger than the
    // perturbation is why nothing reordered, and saying so is the difference
    // between a measured negative and an unexamined one.
    let mut first_gap: Vec<f64> = Vec::new();
    let mut edge_gap: Vec<f64> = Vec::new();
    for list in &c {
        if list.len() > 1 {
            first_gap.push(list[0].1 - list[1].1);
        }
        if list.len() > config.k {
            edge_gap.push(list[config.k - 1].1 - list[config.k].1);
        }
    }
    let smallest = |v: &[f64]| v.iter().copied().fold(f64::INFINITY, f64::min);
    println!(
        "gaps (exact)  rank1-rank2 min {:.3e} med {:.3e} | rank{}-rank{} min {:.3e} med {:.3e}",
        smallest(&first_gap),
        median(&mut first_gap.clone()),
        config.k,
        config.k + 1,
        smallest(&edge_gap),
        median(&mut edge_gap.clone())
    );

    // How far each accumulator moves the scores the ranking is made of: the
    // cosine between a sampled row and each of its reference neighbours,
    // under that accumulator, against the reference. This is first order in
    // the perturbation, where the per-row `1-cos` above is second order, so it
    // is the figure to hold against the gaps.
    let shift = |values: &[f32]| -> (f64, f64) {
        let mut shifts: Vec<f64> = sample
            .par_iter()
            .zip(c.par_iter())
            .map(|(&row, list)| {
                let mine = &values[row * d..(row + 1) * d];
                list.iter()
                    .map(|&(other, reference)| {
                        (cosine(mine, &values[other * d..(other + 1) * d]) - reference).abs()
                    })
                    .fold(0.0f64, f64::max)
            })
            .collect();
        let worst = shifts.iter().copied().fold(0.0f64, f64::max);
        (worst, median(&mut shifts))
    };
    let (single_worst, single_median) = shift(single.values());
    let (double_worst, double_median) = shift(double.values());
    let (noise_worst, noise_median) = shift(&noisy);
    println!(
        "score shift   f32 max {single_worst:.3e} med {single_median:.3e} | \
         f64 max {double_worst:.3e} med {double_median:.3e} | \
         1ulp max {noise_worst:.3e} med {noise_median:.3e}"
    );
    println!();
    Ok(())
}

/// Proportion of CPU time stolen since boot, as `/proc/stat` reports it.
fn steal_ticks() -> Option<(u64, u64)> {
    let text = std::fs::read_to_string("/proc/stat").ok()?;
    let line = text.lines().next()?;
    let fields: Vec<u64> = line
        .split_whitespace()
        .skip(1)
        .filter_map(|f| f.parse().ok())
        .collect();
    let steal = *fields.get(7)?;
    Some((steal, fields.iter().sum()))
}

fn timing(config: &Config, repeats: usize) -> Result<(), Box<dyn std::error::Error>> {
    let graph = build(config)?;
    let before = steal_ticks();
    // Warmup: one full pair, thrown away, so the first timed sample does not
    // pay for page faults the allocator has not taken yet.
    fast_rp_with(&graph, options(config), Accumulator::Single)?;
    fast_rp_with(&graph, options(config), Accumulator::Double)?;
    let mut single: Vec<f64> = Vec::new();
    let mut double: Vec<f64> = Vec::new();
    for repeat in 0..repeats {
        // The order alternates so a drift over the run does not land on one
        // variant only.
        let order = if repeat % 2 == 0 {
            [Accumulator::Single, Accumulator::Double]
        } else {
            [Accumulator::Double, Accumulator::Single]
        };
        for which in order {
            let started = Instant::now();
            let result = fast_rp_with(&graph, options(config), which)?;
            let elapsed = started.elapsed().as_secs_f64();
            std::hint::black_box(result.values()[0]);
            match which {
                Accumulator::Single => single.push(elapsed),
                _ => double.push(elapsed),
            }
        }
    }
    let after = steal_ticks();
    let steal = match (before, after) {
        (Some((s0, t0)), Some((s1, t1))) if t1 > t0 => {
            format!("{:.3}%", 100.0 * (s1 - s0) as f64 / (t1 - t0) as f64)
        }
        _ => "unavailable".to_string(),
    };
    let stat = |samples: &mut Vec<f64>| -> (f64, f64, f64) {
        let low = samples.iter().copied().fold(f64::INFINITY, f64::min);
        let high = samples.iter().copied().fold(0.0f64, f64::max);
        (median(samples), low, high)
    };
    let (ms, mn, mx) = stat(&mut single);
    let (ds, dn, dx) = stat(&mut double);
    println!(
        "{:<28} nodes {} arcs {} dim {} | f32 med {:.4}s [{:.4}, {:.4}] | \
         f64 med {:.4}s [{:.4}, {:.4}] | f64/f32 {:.3} | repeats {} | steal {}",
        config.label,
        graph.node_count(),
        graph.edge_count(),
        config.dimension,
        ms,
        mn,
        mx,
        ds,
        dn,
        dx,
        ds / ms,
        repeats,
        steal
    );
    Ok(())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let mode = args.next().unwrap_or_else(|| "accuracy".into());
    let mut config = Config::default();
    let mut repeats = 5usize;
    while let Some(flag) = args.next() {
        let mut value = || args.next().ok_or_else(|| format!("{flag} needs a value"));
        match flag.as_str() {
            "--nodes" => config.nodes = value()?.parse()?,
            "--degree" => config.degree = value()?.parse()?,
            "--hubs" => config.hubs = value()?.parse()?,
            "--hub-degree" => config.hub_degree = value()?.parse()?,
            "--dimension" => config.dimension = value()?.parse()?,
            "--twins" => config.twins = value()?.parse()?,
            "--seed" => config.seed = value()?.parse()?,
            "--workers" => config.workers = value()?.parse()?,
            "--samples" => config.samples = value()?.parse()?,
            "--k" => config.k = value()?.parse()?,
            "--repeats" => repeats = value()?.parse()?,
            "--label" => config.label = value()?,
            "--weights" => {
                config.weights = match value()?.as_str() {
                    "uniform" => Weights::Uniform,
                    "mixed" => Weights::Mixed,
                    "descending" => Weights::Descending,
                    other => return Err(format!("unknown weights `{other}`").into()),
                }
            }
            other => return Err(format!("unknown argument `{other}`").into()),
        }
    }
    if config.label.is_empty() {
        config.label = format!(
            "n{} d{} hub{}x{}",
            config.nodes, config.dimension, config.hubs, config.hub_degree
        );
    }
    match mode.as_str() {
        "accuracy" => accuracy(&config),
        "time" => timing(&config, repeats),
        other => Err(format!("unknown mode `{other}`").into()),
    }
}
