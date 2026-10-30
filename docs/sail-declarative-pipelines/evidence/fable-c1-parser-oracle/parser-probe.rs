use std::io::{self, BufRead};
type SparkResult<T> = Result<T, ()>;
mod errors { pub fn invalid_attribute_name_syntax(_: &str) {} }
fn parse_attribute_name(name: &str) -> SparkResult<Vec<String>> {
    // Spark indexes UTF-16 units; only '`' and '.' are compared, and neither is
    // part of a surrogate pair, so iterating scalar values is equivalent.
    let chars: Vec<char> = name.chars().collect();
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut in_backtick = false;
    let mut i = 0;
    while i < chars.len() {
        let char = chars[i];
        if in_backtick {
            if char == '`' {
                if i + 1 < chars.len() && chars[i + 1] == '`' {
                    current.push('`');
                    i += 1;
                } else {
                    in_backtick = false;
                    if i + 1 < chars.len() && chars[i + 1] != '.' {
                        return Err(errors::invalid_attribute_name_syntax(name));
                    }
                }
            } else {
                current.push(char);
            }
        } else if char == '`' {
            if !current.is_empty() {
                return Err(errors::invalid_attribute_name_syntax(name));
            }
            in_backtick = true;
        } else if char == '.' {
            if i == 0 || chars[i - 1] == '.' || i == chars.len() - 1 {
                return Err(errors::invalid_attribute_name_syntax(name));
            }
            parts.push(std::mem::take(&mut current));
        } else {
            current.push(char);
        }
        i += 1;
    }
    if in_backtick {
        return Err(errors::invalid_attribute_name_syntax(name));
    }
    parts.push(current);
    Ok(parts)
}

fn main() { for line in io::stdin().lock().lines() { let line=line.unwrap(); let bytes: Vec<u8>=(0..line.len()).step_by(2).map(|i|u8::from_str_radix(&line[i..i+2],16).unwrap()).collect(); let name=String::from_utf8(bytes).unwrap(); match parse_attribute_name(&name) { Ok(parts)=>println!("OK:{}",parts.iter().map(|s|s.as_bytes().iter().map(|b|format!("{b:02x}")).collect::<String>()).collect::<Vec<_>>().join(",")), Err(_)=>println!("ERR") } } }
