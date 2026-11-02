
extern crate self as datafusion;
extern crate self as sail_common;
pub extern crate arrow;
mod utils {pub mod root_lowercase;}
mod schema {#[derive(Clone,Copy)]pub enum Case {Sensitive,Insensitive}impl Case{pub fn label(self)->&'static str{match self{Self::Sensitive=>"case-sensitive",Self::Insensitive=>"case-insensitive"}}}}
mod lookup;
mod error {
 #[derive(Debug)]pub struct Structured {pub condition:String}
 #[derive(Debug)]pub enum SparkError{Structured(Structured),Invalid(String)}
 impl SparkError {pub fn invalid(s:String)->Self{Self::Invalid(s)}}
 impl std::fmt::Display for SparkError{fn fmt(&self,f:&mut std::fmt::Formatter<'_>)->std::fmt::Result{write!(f,"{self:?}")}}
 pub type SparkResult<T>=Result<T,SparkError>;
}
// Record-shaped intent adapter; no source adapter or validation execution is tested.
mod pipelines {pub mod streaming {pub mod intent {
 #[derive(Clone,Debug,PartialEq,Eq,serde::Serialize,serde::Deserialize)]pub struct BatchIntent {pub ranges:Vec<Range>}
 #[derive(Clone,Debug,PartialEq,Eq,serde::Serialize,serde::Deserialize)]pub struct Range{pub partition:String,pub incarnation:String,pub start:String,pub end:String}
}}}
mod prepared;
use prepared::*;
use std::{collections::HashMap,sync::Arc};
use arrow::{array::{Int64Array,Array},buffer::{ScalarBuffer,NullBuffer},datatypes::{DataType,Field,Schema,SchemaRef},record_batch::RecordBatch};
fn identity(case:&str,key:&str)->InputIdentity{InputIdentity{flow:vec!["flow".into()],batch_id:1,intent:pipelines::streaming::intent::BatchIntent{ranges:vec![pipelines::streaming::intent::Range{partition:"p0".into(),incarnation:"inc:1".into(),start:"pos:0".into(),end:"pos:2".into()}]},evaluation:EvaluationContext{case:case.into(),keys:vec![key.into()],sequencing:"1".into(),delete_condition:None,column_selection:None}}}
fn receipt(id:&InputIdentity)->ValidationReceipt{ValidationReceipt::record(id,&Ok(()))}
fn schema()->SchemaRef{let md:HashMap<String,String>=[("a","1"),("b","2"),("c","3")].into_iter().map(|(k,v)|(k.into(),v.into())).collect();let field=Field::new("a.b",DataType::Int64,false).with_metadata(md.clone());Arc::new(Schema::new_with_metadata(vec![field],md))}
fn main(){
 let id=identity("case-insensitive","A.B");let first=schema();let rows=vec![RecordBatch::try_new(first.clone(),vec![Arc::new(Int64Array::from(vec![2,1]))]).unwrap()];let sealed=seal(id.clone(),receipt(&id),&first,&rows).unwrap();
 for _ in 0..64 {let next=schema();assert_eq!(first,next);let reversed=vec![RecordBatch::try_new(next.clone(),vec![Arc::new(Int64Array::from(vec![1,2]))]).unwrap()];let again=seal(id.clone(),receipt(&id),&next,&reversed).unwrap();assert_eq!(sealed.schema_digest,again.schema_digest);assert_eq!(sealed.content_digest,again.content_digest);verify(&id,&sealed,&next,&reversed).unwrap();}
 println!("equal_schema_reconstructions=64");
 for n in 0..=2 {let s=schema();let rows=vec![RecordBatch::try_new(s.clone(),vec![Arc::new(Int64Array::from((0..n).collect::<Vec<i64>>()))]).unwrap()];let mut local=id.clone();local.intent.ranges[0].end=format!("pos:{n}");if n==0{local.intent.ranges.clear();}seal(local.clone(),receipt(&local),&s,&rows).unwrap();let sensitive=identity("case-sensitive","A.B");assert!(seal(sensitive.clone(),receipt(&sensitive),&s,&rows).is_err());}println!("case_and_literal_dot_row_counts=3");
 let mut mutations=Vec::new();let mut x=sealed.clone();x.identity.flow.push("other".into());mutations.push(x);let mut x=sealed.clone();x.identity.batch_id+=1;mutations.push(x);let mut x=sealed.clone();x.identity_digest="wrong".into();mutations.push(x);let mut x=sealed.clone();x.validation.identity_digest="wrong".into();mutations.push(x);let mut x=sealed.clone();x.validation.outcome=ValidationOutcome::Failed{condition:"failure".into()};mutations.push(x);let mut x=sealed.clone();x.completion_required=false;mutations.push(x);let mut x=sealed.clone();x.row_count+=1;mutations.push(x);let mut x=sealed.clone();x.schema_digest="wrong".into();mutations.push(x);let mut x=sealed.clone();x.content_digest="wrong".into();mutations.push(x);
 for x in &mutations {assert!(verify(&id,x,&first,&rows).is_err());}println!("rejected_manifest_mutations={}",mutations.len());
 let mut other=id.clone();other.flow.push("other".into());let foreign=seal(other.clone(),receipt(&other),&first,&rows).unwrap();verify(&other,&foreign,&first,&rows).unwrap();assert!(verify(&id,&foreign,&first,&rows).is_err());println!("wrong_expected_identity=rejected");
 let invalid=identity("unknown-case","a.b");assert!(matches!(seal(invalid.clone(),receipt(&invalid),&first,&rows),Err(SealError::UnknownCase{..})));println!("unknown_case=rejected");
 let encoded=serde_json::to_vec(&sealed).unwrap();let decoded:PreparedBatch=serde_json::from_slice(&encoded).unwrap();verify(&id,&decoded,&first,&rows).unwrap();println!("serde_roundtrip=verified");
 let null_schema=Arc::new(Schema::new(vec![Field::new("id",DataType::Int64,false),Field::new("payload",DataType::Int64,true)]));
 let array=|hidden|Int64Array::new(ScalarBuffer::from(vec![10,hidden]),Some(NullBuffer::from(vec![true,false])));
 let a=array(111);let b=array(222);assert_eq!(a,b);let make=|v:Int64Array|RecordBatch::try_new(null_schema.clone(),vec![Arc::new(Int64Array::from(vec![1,2])),Arc::new(v)]).unwrap();let aa=make(a);let bb=make(b);assert_eq!(aa,bb);let nid=identity("case-sensitive","id");let sa=seal(nid.clone(),receipt(&nid),&null_schema,&[aa]).unwrap();let sb=seal(nid.clone(),receipt(&nid),&null_schema,&[bb.clone()]).unwrap();
 println!("logical_null_rows_equal=true\nnull_a_content={}\nnull_b_content={}\nnull_equivalent_verify={:?}",sa.content_digest,sb.content_digest,verify(&nid,&sa,&null_schema,&[bb]));
}
