extern crate self as sail_common;
mod utils {pub mod root_lowercase;}
mod schema {#[derive(Clone,Copy)] pub enum Case {Sensitive,Insensitive}}
mod lookup;
use std::io::{self,BufRead};
fn text(s:&str)->String{let bytes:Vec<u8>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();String::from_utf8(bytes).unwrap()}
fn main(){for line in io::stdin().lock().lines(){let s=line.unwrap();let mut items=s.split('\t');let n:usize=items.next().unwrap().parse().unwrap();let fields:Vec<String>=(0..n).map(|_|text(items.next().unwrap())).collect();let query=text(items.next().unwrap());let lookup=lookup::FieldLookup::new(&fields);let a=lookup.resolver(schema::Case::Sensitive)(&query).map(|x|x as i64).unwrap_or(-1);let b=lookup.resolver(schema::Case::Insensitive)(&query).map(|x|x as i64).unwrap_or(-1);println!("{a},{b}");}}
