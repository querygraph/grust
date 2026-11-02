use std::{collections::HashMap,sync::Arc};
use arrow_schema::{Schema,SchemaRef,Field,DataType};
use sha2::{Digest,Sha256};
fn hex(bytes:impl AsRef<[u8]>)->String{bytes.as_ref().iter().map(|b|format!("{b:02x}")).collect()}
fn schema()->SchemaRef{let metadata:HashMap<String,String>=[("alpha","one"),("beta","two"),("gamma","three"),("delta","four")].into_iter().map(|(k,v)|(k.to_owned(),v.to_owned())).collect();Arc::new(Schema::new_with_metadata(vec![Field::new("id",DataType::Int64,false)],metadata))}
fn main(){let first=schema();for attempt in 1..=128{let second=schema();assert_eq!(first,second);let a=hex(Sha256::digest(format!("{first:?}").as_bytes()));let b=hex(Sha256::digest(format!("{second:?}").as_bytes()));if a!=b{println!("equal_schemas=true\nattempt={attempt}\nfirst_digest={a}\nsecond_digest={b}\nfirst_debug_hex={}\nsecond_debug_hex={}",hex(format!("{first:?}").as_bytes()),hex(format!("{second:?}").as_bytes()));return;}}panic!("probe did not observe different HashMap iteration orders");}
