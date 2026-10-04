//! Two example kernels: one with no scratch, one with scratch.

use std::sync::Arc;

use arrow_array::{RecordBatch, UInt32Array, UInt64Array};
use arrow_schema::{DataType, Field, Schema};

use crate::{admitted_buffer, scratch, Csr, Estimate, Host, Kernel, KernelError};

/// Out-degree of every vertex. Output only.
pub struct OutDegree;

impl Kernel for OutDegree {
    fn name(&self) -> &'static str {
        "out_degree"
    }
    fn estimate(&self, n: usize, _m: usize) -> Estimate {
        Estimate {
            scratch_bytes: 0,
            output_bytes: 8 * n as u64,
        }
    }
    fn run(&self, csr: Csr<'_>, host: &Arc<dyn Host>) -> Result<RecordBatch, KernelError> {
        let degree = admitted_buffer::<u64>(host, csr.n(), |out| {
            for (v, slot) in out.iter_mut().enumerate() {
                *slot = csr.row(v).len() as u64;
            }
            Ok(())
        })?;
        let schema = Arc::new(Schema::new(vec![Field::new(
            "degree",
            DataType::UInt64,
            false,
        )]));
        Ok(RecordBatch::try_new(schema, vec![Arc::new(UInt64Array::new(degree, None))]).unwrap())
    }
}

/// Weakly connected components by union-find. Scratch: a parent per vertex.
/// The component label is the smallest dense id in the component.
pub struct Wcc;

impl Kernel for Wcc {
    fn name(&self) -> &'static str {
        "wcc"
    }
    fn estimate(&self, n: usize, _m: usize) -> Estimate {
        Estimate {
            scratch_bytes: 4 * n as u64,
            output_bytes: 4 * n as u64,
        }
    }
    fn run(&self, csr: Csr<'_>, host: &Arc<dyn Host>) -> Result<RecordBatch, KernelError> {
        let n = csr.n();
        let (mut parent, _scratch) = scratch::<u32>(host, n)?;
        for (v, p) in parent.iter_mut().enumerate() {
            *p = v as u32;
        }
        fn find(parent: &mut [u32], mut x: u32) -> u32 {
            while parent[x as usize] != x {
                parent[x as usize] = parent[parent[x as usize] as usize];
                x = parent[x as usize];
            }
            x
        }
        for v in 0..n {
            if v % 4096 == 0 && host.is_cancelled() {
                return Err(KernelError::Cancelled);
            }
            for &w in csr.row(v) {
                let (a, b) = (find(&mut parent, v as u32), find(&mut parent, w));
                if a != b {
                    let (low, high) = if a < b { (a, b) } else { (b, a) };
                    parent[high as usize] = low;
                }
            }
        }
        let component = admitted_buffer::<u32>(host, n, |out| {
            for (v, slot) in out.iter_mut().enumerate() {
                *slot = find(&mut parent, v as u32);
            }
            Ok(())
        })?;
        let schema = Arc::new(Schema::new(vec![Field::new(
            "component",
            DataType::UInt32,
            false,
        )]));
        Ok(
            RecordBatch::try_new(schema, vec![Arc::new(UInt32Array::new(component, None))])
                .unwrap(),
        )
        // `_scratch` drops here: the parent array's bytes are returned before the
        // call returns. The output's bytes stay admitted until the batch is dropped.
    }
}
