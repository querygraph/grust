mod root_lowercase;
use std::io::{self,BufRead};
fn main(){for line in io::stdin().lock().lines(){let s=line.unwrap();let bytes:Vec<u8>=(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect();let value=String::from_utf8(bytes).unwrap();let lower=root_lowercase::spark_root_lowercase(&value);println!("{}",lower.as_bytes().iter().map(|b|format!("{b:02x}")).collect::<String>());}}
