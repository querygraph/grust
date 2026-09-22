//! The floating-point type a rank kernel keeps its scores in.
//!
//! PageRank has one implementation, generic over [`Score`], which `f64` and
//! `f32` implement and nothing else can: the trait is sealed. The kernel forms
//! every score, per-arc probability, dangling mass, teleport share and `base`
//! in the score type, and accumulates the L1 residual between iterations in
//! `f64` whatever the score type is, which is the arrangement
//! `neo4j-labs/graph` uses for its `f32` PageRank, so the two can be run at one
//! precision under one stopping rule.

use std::ops::{Add, AddAssign, Div, Mul, Sub};

mod sealed {
    pub trait Sealed {}
    impl Sealed for f32 {}
    impl Sealed for f64 {}
}

/// A score precision: `f64`, the default, or `f32`.
///
/// Implemented for exactly those two types. The conversions are the ordinary
/// `as` casts, so [`Score::from_f64`] rounds an `f64` to the nearest `f32` and
/// is the identity on `f64`, which is what keeps the `f64` kernel's bits where
/// they were before it became generic.
pub trait Score:
    sealed::Sealed
    + Copy
    + Send
    + Sync
    + PartialOrd
    + std::fmt::Debug
    + Add<Output = Self>
    + Sub<Output = Self>
    + Mul<Output = Self>
    + Div<Output = Self>
    + AddAssign
    + 'static
{
    /// Additive identity.
    const ZERO: Self;
    /// Round an `f64` to this precision.
    fn from_f64(value: f64) -> Self;
    /// Widen to `f64`; exact for both implementations.
    fn to_f64(self) -> f64;
    /// Absolute value.
    fn abs(self) -> Self;
    /// Neither infinite nor NaN.
    fn is_finite(self) -> bool;
}

impl Score for f64 {
    const ZERO: Self = 0.0;
    #[inline(always)]
    fn from_f64(value: f64) -> Self {
        value
    }
    #[inline(always)]
    fn to_f64(self) -> f64 {
        self
    }
    #[inline(always)]
    fn abs(self) -> Self {
        f64::abs(self)
    }
    #[inline(always)]
    fn is_finite(self) -> bool {
        f64::is_finite(self)
    }
}

impl Score for f32 {
    const ZERO: Self = 0.0;
    #[inline(always)]
    fn from_f64(value: f64) -> Self {
        value as f32
    }
    #[inline(always)]
    fn to_f64(self) -> f64 {
        f64::from(self)
    }
    #[inline(always)]
    fn abs(self) -> Self {
        f32::abs(self)
    }
    #[inline(always)]
    fn is_finite(self) -> bool {
        f32::is_finite(self)
    }
}
