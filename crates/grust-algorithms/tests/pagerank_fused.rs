//! The fused PageRank pull against the three passes it replaced.
//!
//! The parallel pull once ran three passes per iteration: shares and dangling
//! mass, the pull, the residual. It now runs one, and promises the same bits.
//! Two oracles check that promise at both precisions, on fixtures large
//! enough to reach the pull, at one, two, three and sixteen workers:
//!
//! - `reference`, the three passes written out sequentially in this file, in
//!   the order and grouping the kernel used, including the per-arc weighted
//!   probability and the fixed reduction chunks;
//! - digests produced by the kernel as it stood before the fusion
//!   (origin/work/pagerank-f32 ead3568), at both precisions. The `f64` ones
//!   for the plain PageRank cases are the same numbers `tests/pagerank_pinned.rs`
//!   pins, which is the cross-check on the digest itself.
//!
//! Two more properties. Without a personalization the pull forms
//! `base * (1 / n)` once instead of reading a uniform teleport array per node;
//! a run with an explicitly uniform personalization takes the array path and
//! must produce the same bits. And a weighted pull forms each in-arc's
//! probability once, before the iterations, where the reference forms it per
//! arc per iteration and skips arcs out of dangling rows; the two must agree
//! on a fixture with zero-weight rows and `f64::MAX` weights as well as on a
//! plain one.

use grust_algorithms::{
    ExecutionContext, ExecutionLimits, GraphProjection, Orientation, PageRank, PageRankOptions,
    ProjectionEdge, RankVariant, Score, SnapshotIdentity, pagerank, pagerank_f32,
};

const REDUCTION_CHUNK_LEN: usize = 4096;
const ITERATIONS: usize = 25;

fn context(workers: Option<usize>) -> ExecutionContext {
    let context = ExecutionContext::new(ExecutionLimits {
        memory_bytes: 1 << 30,
        work_units: usize::MAX,
        batch_rows: 8192,
        deadline: None,
    })
    .expect("valid limits");
    match workers {
        Some(workers) => context.with_concurrency(workers).expect("not yet shared"),
        None => context,
    }
}

type Fixture = (usize, Vec<(usize, usize)>, Option<Vec<f64>>);

fn project(context: &ExecutionContext, (nodes, arcs, weights): &Fixture) -> GraphProjection {
    let edges = arcs
        .iter()
        .enumerate()
        .map(|(ordinal, &(source, target))| ProjectionEdge {
            source,
            target,
            ordinal,
            id: None,
        })
        .collect();
    GraphProjection::from_topology(
        SnapshotIdentity::new("fused".into(), "r1".into(), "tests".into()).expect("identity"),
        (0..*nodes).map(|id| id.to_string().into()).collect(),
        edges,
        weights.clone(),
        Orientation::Outgoing,
        context,
    )
    .expect("projection")
}

fn xorshift(seed: u64) -> impl FnMut() -> u64 {
    let mut state = seed;
    move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    }
}

/// `tests/pagerank_pinned.rs`'s graph: a permutation cycle plus chords biased
/// to low rows, so a few sources have very high out-degree.
fn chords(weighted: bool) -> Fixture {
    const NODES: usize = 120_000;
    const EDGES: usize = 600_000;
    let mut random = xorshift(0x2545_F491_4F6C_DD1D);
    let arcs = (0..EDGES)
        .map(|ordinal| {
            if ordinal < NODES {
                (ordinal, (ordinal + 1) % NODES)
            } else {
                let source = (random() % (NODES as u64 / 16)) as usize;
                (source, (random() % NODES as u64) as usize)
            }
        })
        .collect();
    let weights = weighted.then(|| (0..EDGES).map(|index| 1.0 + (index % 7) as f64).collect());
    (NODES, arcs, weights)
}

/// `tests/pagerank_pinned.rs`'s dangling graph: half the nodes have no
/// out-arcs, so the dangling mass is a long reduction at every iteration.
fn dangling() -> Fixture {
    const N: usize = 200_000;
    let mut next = xorshift(0x9E37_79B9_7F4A_7C15);
    let arcs = (0..3 * N)
        .map(|_| {
            let source = (next() % (N as u64 / 2)) as usize;
            let target = next() % N as u64;
            (source, (target * target / N as u64) as usize)
        })
        .collect();
    (N, arcs, None)
}

/// A weighted graph with the cases the scaling exists for: two parallel arcs
/// of `f64::MAX`, fifty rows whose only arc weighs zero (dangling although an
/// arc exists), a node with no arc at all, and chords from a quarter of the
/// rows. Large enough to reach the pull.
fn zero_rows() -> Fixture {
    const N: usize = 3000;
    let mut random = xorshift(0x94D0_49BB_1331_11EB);
    let mut arcs = Vec::new();
    let mut weights = Vec::new();
    for node in 0..N - 1 {
        arcs.push((node, node + 1));
        weights.push(if (2900..2950).contains(&node) {
            0.0
        } else {
            1.0 + (node % 5) as f64
        });
    }
    for _ in 0..2 {
        arcs.push((0, 1));
        weights.push(f64::MAX);
    }
    for index in 0..N {
        let source = (random() % (N as u64 / 4)) as usize;
        arcs.push((source, (random() % N as u64) as usize));
        weights.push(1.0 + (index % 7) as f64);
    }
    assert!((N + arcs.len()) * 2 >= 1 << 14, "must reach the pull");
    (N, arcs, Some(weights))
}

fn charged(context: &ExecutionContext) -> usize {
    context
        .usage()
        .expect("usage")
        .counted_work()
        .expect("counted")
}

/// Everything a run produces, comparable exactly. Scores are compared through
/// their bits, widened to `f64` for `f32`, which is exact.
type Exact = (Vec<u64>, usize, u64, bool);

fn exact<F: Score>(result: &PageRank<F>) -> Exact {
    (
        result
            .values()
            .iter()
            .map(|score| score.to_f64().to_bits())
            .collect(),
        result.iterations(),
        result.residual().to_bits(),
        result.converged(),
    )
}

fn fnv(state: &mut u64, word: u64) {
    for byte in word.to_le_bytes() {
        *state ^= u64::from(byte);
        *state = state.wrapping_mul(0x0000_0100_0000_01B3);
    }
}

/// `tests/pagerank_pinned.rs`'s digest, over the same words.
fn digest((scores, iterations, residual, converged): &Exact) -> u64 {
    let mut state = 0xCBF2_9CE4_8422_2325;
    for &score in scores {
        fnv(&mut state, score);
    }
    fnv(&mut state, *iterations as u64);
    fnv(&mut state, *residual);
    fnv(&mut state, u64::from(*converged));
    state
}

/// The work the pull charges for `k` iterations: the closed formula
/// `tests/pagerank_pinned.rs` states, plus the personalization's three
/// passes. The push charges a different total, so the work one call charges
/// identifies the path exactly.
fn pull_work(fixture: &Fixture, personalized: bool, k: usize) -> usize {
    let (n, m, weighted) = (fixture.0, fixture.1.len(), fixture.2.is_some());
    2 * n
        + if weighted { n + 2 * m } else { 0 }
        + if personalized { 3 * n } else { 0 }
        + k * (3 * n + m)
}

/// Run both precisions on one projection, on a fresh execution, asserting
/// each took the pull.
fn both(workers: usize, fixture: &Fixture, options: PageRankOptions<'_>) -> (Exact, Exact) {
    let context = context(Some(workers));
    let graph = project(&context, fixture);
    // The transpose is built lazily by the first pull; the calls measured
    // below both find it built.
    let _ = pagerank(&graph, options).expect("warm");
    let personalized = options.personalization.is_some();
    let before = charged(&context);
    let double = pagerank(&graph, options).expect("f64");
    assert_eq!(
        charged(&context) - before,
        pull_work(fixture, personalized, double.iterations()),
        "f64 at {workers} workers did not take the pull"
    );
    let before = charged(&context);
    let single = pagerank_f32(&graph, options).expect("f32");
    assert_eq!(
        charged(&context) - before,
        pull_work(fixture, personalized, single.iterations()),
        "f32 at {workers} workers did not take the pull"
    );
    (exact(&double), exact(&single))
}

/// The three-pass pull as it stood before the fusion, sequentially, generic
/// over the score precision. Pass one forms each source's share
/// `score / (out-degree + damp)` and the dangling mass in fixed chunks; pass
/// two pulls into each target in in-arc order, forming each weighted arc's
/// probability from the source's scale and total as it goes and skipping an
/// arc out of a dangling row; pass three sums the residual in `f64` in fixed
/// chunks. The transpose lists a target's in-arcs by source, then by arc.
fn reference<F: Score>(fixture: &Fixture, options: PageRankOptions<'_>) -> Exact {
    let (n, arcs, weights) = fixture;
    let n = *n;
    let weighted = weights.is_some();
    let mut rows: Vec<Vec<(usize, f64)>> = vec![Vec::new(); n];
    for (index, &(source, target)) in arcs.iter().enumerate() {
        rows[source].push((target, weights.as_ref().map_or(1.0, |w| w[index])));
    }
    let mut in_rows: Vec<Vec<(usize, f64)>> = vec![Vec::new(); n];
    for (source, row) in rows.iter().enumerate() {
        for &(target, weight) in row {
            in_rows[target].push((source, weight));
        }
    }
    let uniform = F::from_f64(1.0 / n as f64);
    let teleport: Vec<F> = match options.personalization {
        None => vec![uniform; n],
        Some(values) => {
            let maximum = values.iter().fold(0.0f64, |largest, &v| largest.max(v));
            let mut total = 0.0;
            let mut shares = Vec::with_capacity(n);
            for &value in values {
                let share = value / maximum;
                shares.push(F::from_f64(share));
                total += share;
            }
            shares
                .iter()
                .map(|share| F::from_f64(share.to_f64() / total))
                .collect()
        }
    };
    let scales: Vec<f64> = rows
        .iter()
        .map(|row| row.iter().fold(0.0f64, |largest, &(_, w)| largest.max(w)))
        .collect();
    let totals: Vec<F> = rows
        .iter()
        .zip(&scales)
        .map(|(row, &scale)| {
            let mut total = F::ZERO;
            if scale > 0.0 {
                for &(_, w) in row {
                    total += F::from_f64(w / scale);
                }
            }
            total
        })
        .collect();
    let damp = match options.variant {
        RankVariant::PageRank => F::ZERO,
        RankVariant::ArticleRank if weighted => {
            let mut sum = F::ZERO;
            for chunk in totals.chunks(REDUCTION_CHUNK_LEN) {
                let mut part = F::ZERO;
                for &total in chunk {
                    part += total;
                }
                sum += part;
            }
            sum / F::from_f64(n as f64)
        }
        RankVariant::ArticleRank => F::from_f64(arcs.len() as f64) / F::from_f64(n as f64),
    };
    let damping = F::from_f64(options.damping);
    let retained = F::from_f64(1.0 - options.damping);
    let mut scores = vec![uniform; n];
    let mut residual = f64::INFINITY;
    for iteration in 1..=options.max_iterations {
        let mut shares = vec![F::ZERO; n];
        let mut dangling = F::ZERO;
        for first in (0..n).step_by(REDUCTION_CHUNK_LEN) {
            let mut part = F::ZERO;
            for node in first..(first + REDUCTION_CHUNK_LEN).min(n) {
                if weighted {
                    if totals[node] <= F::ZERO {
                        part += scores[node];
                    }
                } else if rows[node].is_empty() {
                    part += scores[node];
                } else {
                    shares[node] = scores[node] / (F::from_f64(rows[node].len() as f64) + damp);
                }
            }
            dangling += part;
        }
        let base = retained + damping * dangling;
        let mut next = vec![F::ZERO; n];
        for (node, value) in next.iter_mut().enumerate() {
            let mut sum = F::ZERO;
            for &(source, weight) in &in_rows[node] {
                if weighted {
                    if totals[source] <= F::ZERO {
                        continue;
                    }
                    let probability =
                        F::from_f64(weight / scales[source]) / (totals[source] + damp);
                    sum += scores[source] * probability;
                } else {
                    sum += shares[source];
                }
            }
            *value = base * teleport[node] + damping * sum;
            assert!(
                value.is_finite(),
                "the reference produced a nonfinite score"
            );
        }
        residual = 0.0;
        for first in (0..n).step_by(REDUCTION_CHUNK_LEN) {
            let mut part = 0.0f64;
            for node in first..(first + REDUCTION_CHUNK_LEN).min(n) {
                part += (next[node] - scores[node]).abs().to_f64();
            }
            residual += part;
        }
        scores = next;
        if residual <= options.tolerance {
            return exact_of(&scores, iteration, residual, true);
        }
    }
    exact_of(&scores, options.max_iterations, residual, false)
}

fn exact_of<F: Score>(scores: &[F], iterations: usize, residual: f64, converged: bool) -> Exact {
    (
        scores
            .iter()
            .map(|score| score.to_f64().to_bits())
            .collect(),
        iterations,
        residual.to_bits(),
        converged,
    )
}

fn fixed(variant: RankVariant) -> PageRankOptions<'static> {
    PageRankOptions {
        variant,
        max_iterations: ITERATIONS,
        // Zero tolerance runs every iteration, so the work charged is a
        // closed formula of the graph and identifies the kernel that ran.
        tolerance: 0.0,
        ..Default::default()
    }
}

const WIDTHS: [usize; 4] = [1, 2, 3, 16];

/// Digests produced at ead3568 by the three-pass pull, `f64` then `f32`.
struct Case {
    label: &'static str,
    fixture: fn() -> Fixture,
    options: PageRankOptions<'static>,
    pinned: [u64; 2],
}

/// The reference and the pinned digests, at both precisions and every width.
fn check(case: &Case, personalization: Option<Vec<f64>>) {
    let fixture = (case.fixture)();
    let options = PageRankOptions {
        personalization: personalization.as_deref(),
        ..case.options
    };
    let expected = (
        reference::<f64>(&fixture, options),
        reference::<f32>(&fixture, options),
    );
    let digests = (digest(&expected.0), digest(&expected.1));
    println!(
        "{}: f64 {:#018x}, f32 {:#018x}",
        case.label, digests.0, digests.1
    );
    assert_eq!(
        digests.0, case.pinned[0],
        "{}: f64 reference vs ead3568",
        case.label
    );
    assert_eq!(
        digests.1, case.pinned[1],
        "{}: f32 reference vs ead3568",
        case.label
    );
    for workers in WIDTHS {
        let (double, single) = both(workers, &fixture, options);
        let differing =
            |got: &Exact, want: &Exact| got.0.iter().zip(&want.0).filter(|(a, b)| a != b).count();
        assert_eq!(
            differing(&double, &expected.0),
            0,
            "{} at {workers} workers: f64 scores differ from the reference",
            case.label
        );
        assert_eq!(
            (double.1, double.2, double.3),
            (expected.0.1, expected.0.2, expected.0.3),
            "{} at {workers} workers: f64 iterations, residual or convergence differ",
            case.label
        );
        assert_eq!(
            differing(&single, &expected.1),
            0,
            "{} at {workers} workers: f32 scores differ from the reference",
            case.label
        );
        assert_eq!(
            (single.1, single.2, single.3),
            (expected.1.1, expected.1.2, expected.1.3),
            "{} at {workers} workers: f32 iterations, residual or convergence differ",
            case.label
        );
    }
}

#[test]
fn the_fused_pull_is_the_three_passes_bits_at_both_precisions_and_every_width() {
    let cases = [
        Case {
            label: "chords",
            fixture: || chords(false),
            options: fixed(RankVariant::PageRank),
            // CHORDS_PULL in tests/pagerank_pinned.rs.
            pinned: [0xb510_c73b_29a1_f439, 0x9ccf_fd67_2e8e_b81b],
        },
        Case {
            label: "dangling",
            fixture: dangling,
            options: fixed(RankVariant::PageRank),
            // DANGLING_PULL in tests/pagerank_pinned.rs.
            pinned: [0xc53f_6913_91de_b2d0, 0xcce0_e434_d3cc_5601],
        },
        Case {
            label: "chords, ArticleRank",
            fixture: || chords(false),
            options: fixed(RankVariant::ArticleRank),
            pinned: [0x5bc1_cd4d_9745_87dd, 0x2e1d_239c_3fa7_cf88],
        },
        Case {
            label: "chords, converging at 1e-6",
            fixture: || chords(false),
            options: PageRankOptions {
                tolerance: 1e-6,
                max_iterations: 1000,
                ..Default::default()
            },
            pinned: [0x432e_15cd_6a6d_d997, 0x085b_b4a0_853f_fcd6],
        },
    ];
    for case in &cases {
        check(case, None);
    }
    // A personalization that is zero on many nodes and skewed on the rest.
    let personalized = Case {
        label: "dangling, personalized",
        fixture: dangling,
        options: fixed(RankVariant::PageRank),
        pinned: [0x5ccf_ac43_deff_44be, 0x0972_2b26_93f6_4a1a],
    };
    let n = dangling().0;
    check(
        &personalized,
        Some((0..n).map(|node| (node % 7) as f64).collect()),
    );
}

#[test]
fn weighted_probabilities_formed_once_are_the_per_arc_bits() {
    let cases = [
        Case {
            label: "weighted chords",
            fixture: || chords(true),
            options: fixed(RankVariant::PageRank),
            // CHORDS_WEIGHTED_PULL in tests/pagerank_pinned.rs.
            pinned: [0x45be_6e06_23a5_4756, 0x755b_03f7_5632_54c4],
        },
        Case {
            label: "weighted chords, ArticleRank",
            fixture: || chords(true),
            options: fixed(RankVariant::ArticleRank),
            pinned: [0x67be_6594_7120_cb3f, 0xd358_a57b_6363_1a4e],
        },
        Case {
            label: "zero rows",
            fixture: zero_rows,
            options: fixed(RankVariant::PageRank),
            pinned: [0x0f42_40ec_12aa_ae31, 0x1236_f688_4f22_d532],
        },
        Case {
            label: "zero rows, ArticleRank",
            fixture: zero_rows,
            options: fixed(RankVariant::ArticleRank),
            pinned: [0x85b0_c1a5_3197_2383, 0x8d8d_b10b_bb49_5774],
        },
    ];
    for case in &cases {
        check(case, None);
    }
}

/// A uniform personalization normalizes to `1 / n` at the score precision in
/// every slot, the value the uniform path forms from the scalar, whatever
/// the constant it was given.
#[test]
fn the_uniform_path_is_the_teleport_array_s_bits_at_both_precisions() {
    for (label, fixture) in [("chords", chords(false)), ("dangling", dangling())] {
        let n = fixture.0;
        for options in [
            fixed(RankVariant::PageRank),
            fixed(RankVariant::ArticleRank),
            PageRankOptions {
                tolerance: 1e-6,
                max_iterations: 1000,
                ..Default::default()
            },
        ] {
            for workers in [1, 16] {
                let scalar = both(workers, &fixture, options);
                for constant in [1.0, 2.5] {
                    let uniform = vec![constant; n];
                    let array = both(
                        workers,
                        &fixture,
                        PageRankOptions {
                            personalization: Some(&uniform),
                            ..options
                        },
                    );
                    assert!(
                        scalar == array,
                        "{label}, {:?}, {workers} workers, personalization {constant}: \
                         the uniform path and the teleport array differ",
                        options.variant
                    );
                }
            }
        }
    }
}
