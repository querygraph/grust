use bytes::Bytes;
use orc_rust::{
    compression::Decompressor,
    proto::{Footer, PostScript},
    reader::metadata::read_metadata,
};
use prost::Message;
use serde_json::json;
use std::{
    error::Error,
    fs::File,
    io::{Read, Seek, SeekFrom},
};

fn main() -> Result<(), Box<dyn Error>> {
    let path = std::env::args().nth(1).ok_or("expected ORC file path")?;
    let mut file = File::open(&path)?;
    let metadata = read_metadata(&mut file)?;
    let length = file.metadata()?.len();
    let final_byte = length.checked_sub(1).ok_or("empty file")?;
    file.seek(SeekFrom::Start(final_byte))?;
    let mut size = [0];
    file.read_exact(&mut size)?;
    let postscript_start = final_byte
        .checked_sub(u64::from(size[0]))
        .ok_or("postscript exceeds file")?;
    file.seek(SeekFrom::Start(postscript_start))?;
    let mut raw_postscript = vec![0; usize::from(size[0])];
    file.read_exact(&mut raw_postscript)?;
    let postscript = PostScript::decode(raw_postscript.as_slice())?;
    let footer_length = postscript.footer_length.ok_or("footer length missing")?;
    let footer_start = postscript_start
        .checked_sub(footer_length)
        .ok_or("footer exceeds file")?;
    if footer_start < 3 {
        return Err("footer overlaps file magic".into());
    }
    let footer_length = usize::try_from(footer_length)?;
    const PROBE_LIMIT: usize = 4 * 1024 * 1024;
    if footer_length > PROBE_LIMIT {
        return Err("probe footer byte limit exceeded".into());
    }
    file.seek(SeekFrom::Start(footer_start))?;
    let mut compressed = vec![0; footer_length];
    file.read_exact(&mut compressed)?;
    let decoder = Decompressor::new(Bytes::from(compressed), metadata.compression(), vec![]);
    let mut decoded = vec![];
    decoder
        .take(PROBE_LIMIT as u64 + 1)
        .read_to_end(&mut decoded)?;
    if decoded.len() > PROBE_LIMIT {
        return Err("probe decoded footer limit exceeded".into());
    }
    let footer = Footer::decode(decoded.as_slice())?;
    let types=footer.types.iter().enumerate().map(|(index,t)|json!({"column_id":index,"kind":format!("{:?}",t.kind()),"names":t.field_names,"subtypes":t.subtypes,"attributes":t.attributes.iter().map(|a|json!({"key":a.key,"value":a.value})).collect::<Vec<_>>()})).collect::<Vec<_>>();
    assert_eq!(footer.number_of_rows(), metadata.number_of_rows());
    println!(
        "{}",
        serde_json::to_string_pretty(
            &json!({"path":path,"rows":metadata.number_of_rows(),"compression":format!("{:?}",metadata.compression()),"types":types,"scope":"Public crate APIs recover raw footer attributes lost by RootDataType. Local-file design probe; not production bounds/remote I/O implementation."})
        )?
    );
    Ok(())
}
