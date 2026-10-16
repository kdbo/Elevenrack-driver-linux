// SPDX-License-Identifier: MIT
use crate::protocol::{safe_leaf, safe_name, tfx, tfx_body};
use regex::Regex;
use serde_json::{json, Value};
use std::{
    collections::{HashMap, HashSet},
    fs,
    io::{Read, Write},
    path::Path,
};
use zip::{write::SimpleFileOptions, ZipArchive, ZipWriter};
const MAX_FILE: u64 = 16 * 1024 * 1024;
fn read_limited(path: &Path) -> Result<Vec<u8>, String> {
    let file = fs::File::open(path).map_err(|e| e.to_string())?;
    if file.metadata().map_err(|e| e.to_string())?.len() > MAX_FILE {
        return Err("File exceeds 16 MiB limit".into());
    }
    let mut bytes = Vec::new();
    file.take(MAX_FILE + 1)
        .read_to_end(&mut bytes)
        .map_err(|e| e.to_string())?;
    if bytes.len() as u64 > MAX_FILE {
        return Err("File exceeds 16 MiB limit".into());
    }
    Ok(bytes)
}
fn xml_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}
fn xml_unescape(s: &str) -> String {
    s.replace("&quot;", "\"")
        .replace("&gt;", ">")
        .replace("&lt;", "<")
        .replace("&amp;", "&")
}
fn tag(text: &str, name: &str) -> Option<String> {
    let re = Regex::new(&format!(r#"<{name}[^>]*>"([^"]*)"</{name}>"#)).ok()?;
    re.captures(text).map(|c| xml_unescape(&c[1]))
}
pub fn read_bank(source: &Path) -> Result<Value, String> {
    let mut archive_files: HashMap<String, Vec<u8>> = HashMap::new();
    let xml = if source
        .extension()
        .is_some_and(|e| e.eq_ignore_ascii_case("zip"))
    {
        let mut zip = ZipArchive::new(std::io::Cursor::new(read_limited(source)?))
            .map_err(|e| e.to_string())?;
        if zip.len() > 256 {
            return Err("Too many archive entries".into());
        }
        let mut total = 0u64;
        for i in 0..zip.len() {
            let mut entry = zip.by_index(i).map_err(|e| e.to_string())?;
            if entry.is_dir() {
                continue;
            }
            total = total.checked_add(entry.size()).ok_or("Archive too large")?;
            if total > MAX_FILE {
                return Err("Expanded archive exceeds 16 MiB limit".into());
            }
            let name = entry.name().map_err(|e| e.to_string())?.to_string();
            safe_leaf(&name)?;
            let mut data = Vec::new();
            entry
                .by_ref()
                .take(MAX_FILE + 1)
                .read_to_end(&mut data)
                .map_err(|e| e.to_string())?;
            if data.len() as u64 > MAX_FILE {
                return Err("Archive entry too large".into());
            }
            if archive_files.insert(name, data).is_some() {
                return Err("Duplicate archive filename".into());
            }
        }
        let mut xmls: Vec<_> = archive_files
            .keys()
            .filter(|k| k.to_lowercase().ends_with(".xml"))
            .collect();
        xmls.sort();
        if xmls.len() != 1 {
            return Err("Bank archive must contain exactly one XML manifest".into());
        }
        String::from_utf8(archive_files[xmls[0]].clone()).map_err(|e| e.to_string())?
    } else {
        String::from_utf8(read_limited(source)?).map_err(|e| e.to_string())?
    };
    let patch = Regex::new(r"(?s)<patch>(.*?)</patch>").unwrap();
    let bank_pattern = Regex::new(r"^[A-Z][1-4]$").unwrap();
    let mut valid = Vec::new();
    let mut problems = Vec::new();
    let mut seen = HashSet::new();
    let mut count = 0;
    for block in patch.captures_iter(&xml) {
        count += 1;
        if count > 104 {
            return Err("Bank manifest exceeds 104 slots".into());
        }
        let bank = tag(&block[1], "bank").ok_or("Missing bank slot")?;
        let filename = tag(&block[1], "file").ok_or("Missing patch filename")?;
        let body = (|| -> Result<Vec<u8>, String> {
            if !bank_pattern.is_match(&bank) || !seen.insert(bank.clone()) {
                return Err("Invalid or duplicate bank slot".into());
            }
            safe_leaf(&filename)?;
            let raw = if !archive_files.is_empty() {
                archive_files
                    .get(&filename)
                    .ok_or("File not found")?
                    .clone()
            } else {
                let folder = source
                    .parent()
                    .ok_or("Missing bank folder")?
                    .canonicalize()
                    .map_err(|e| e.to_string())?;
                let path = folder
                    .join(&filename)
                    .canonicalize()
                    .map_err(|e| e.to_string())?;
                if path.parent() != Some(folder.as_path()) {
                    return Err("Patch leaves the selected bank directory".into());
                }
                read_limited(&path)?
            };
            tfx_body(&raw)
        })();
        match body {
            Ok(body) => valid.push(json!({"bank":bank,"filename":filename,"body":body})),
            Err(reason) => problems.push(json!({"bank":bank,"filename":filename,"reason":reason})),
        }
    }
    if count == 0 {
        return Err("No patch entries found in bank XML".into());
    }
    Ok(
        json!({"ok":true,"valid":valid,"problems":problems,"source":{"generator":tag(&xml,"generator"),"version":tag(&xml,"generator_version"),"exported":tag(&xml,"exported_utc")}}),
    )
}
pub fn load_tfx(path: &Path) -> Result<Value, String> {
    let body = tfx_body(&read_limited(path)?)?;
    Ok(
        json!({"ok":true,"path":path,"filename":path.file_name().map(|n|n.to_string_lossy()),"body":body}),
    )
}
pub fn export_bank(folder: &Path, name: &str, entries: &[Value]) -> Result<Value, String> {
    if entries.is_empty() || entries.len() > 104 {
        return Err("Expected 1–104 bank entries".into());
    }
    let name = safe_name(name, 48);
    safe_leaf(&name)?;
    let directory = folder.join(&name);
    // Refuse an existing export instead of partially replacing an older bank.
    if directory.exists() || folder.join(format!("{name}.zip")).exists() {
        return Err("An export with this name already exists".into());
    }
    let mut prepared = Vec::new();
    let mut names = HashSet::new();
    let mut slots = HashSet::new();
    let mut rows = String::new();
    let slot = Regex::new(r"^[A-Z][1-4]$").unwrap();
    for entry in entries {
        let bank = entry["bank"].as_str().ok_or("Missing bank slot")?;
        let filename = entry["filename"].as_str().ok_or("Missing filename")?;
        safe_leaf(filename)?;
        if !slot.is_match(bank) || !slots.insert(bank) || !names.insert(filename) {
            return Err("Duplicate or invalid bank entry".into());
        }
        let body: Vec<u8> =
            serde_json::from_value(entry["bodyArray"].clone()).map_err(|e| e.to_string())?;
        let data = tfx(&body)?;
        tfx_body(&data)?;
        rows+=&format!("<patch><bank type_=\"string\">\"{}\"</bank><file type_=\"string\">\"{}\"</file></patch>\n",xml_escape(bank),xml_escape(filename));
        prepared.push((filename.to_string(), data));
    }
    let xml=format!("<?xml version=\"1.0\"?>\n<eleven><hardware type_=\"string\">\"Eleven Rack\"</hardware><generator type_=\"string\">\"Eleven Rack Editor Tauri\"</generator><generator_version type_=\"string\">\"{}\"</generator_version><patch_list>{rows}</patch_list></eleven>\n",env!("CARGO_PKG_VERSION"));
    prepared.push((format!("{name}.xml"), xml.into_bytes()));
    let mut zip = ZipWriter::new(std::io::Cursor::new(Vec::new()));
    for (name, data) in &prepared {
        zip.start_file(
            name,
            SimpleFileOptions::default().compression_method(zip::CompressionMethod::Deflated),
        )
        .map_err(|e| e.to_string())?;
        zip.write_all(data).map_err(|e| e.to_string())?;
    }
    let bytes = zip.finish().map_err(|e| e.to_string())?.into_inner();
    fs::create_dir(&directory).map_err(|e| e.to_string())?;
    for (name, data) in prepared {
        fs::write(directory.join(name), data).map_err(|e| e.to_string())?;
    }
    let zip_path = folder.join(format!("{name}.zip"));
    fs::write(&zip_path, bytes).map_err(|e| e.to_string())?;
    Ok(
        json!({"ok":true,"dir":directory,"xmlPath":directory.join(format!("{name}.xml")),"zipPath":zip_path,"count":entries.len()}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    fn temporary() -> PathBuf {
        let p = std::env::temp_dir().join(format!(
            "eleven-tauri-bank-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        fs::create_dir(&p).unwrap();
        p
    }
    #[test]
    fn bank_roundtrip_loose_and_zip() {
        let folder = temporary();
        let mut body = vec![0u8; 256];
        body[..4].copy_from_slice(b"sld6");
        let entries = vec![json!({"bank":"A1","filename":"A & B.tfx","bodyArray":body})];
        let result = export_bank(&folder, "Test", &entries).unwrap();
        for key in ["xmlPath", "zipPath"] {
            let loaded = read_bank(Path::new(result[key].as_str().unwrap())).unwrap();
            assert_eq!(loaded["valid"][0]["body"], json!(body));
            assert_eq!(loaded["problems"].as_array().unwrap().len(), 0);
        }
        assert!(export_bank(&folder, "Test", &entries).is_err());
        fs::remove_dir_all(folder).unwrap();
    }
    #[test]
    fn traversal_is_reported_before_any_import_write() {
        let folder = temporary();
        let xml = folder.join("bank.xml");
        fs::write(
            &xml,
            "<patch><bank>\"A1\"</bank><file>\"../secret.tfx\"</file></patch>",
        )
        .unwrap();
        let loaded = read_bank(&xml).unwrap();
        assert!(loaded["valid"].as_array().unwrap().is_empty());
        assert_eq!(loaded["problems"].as_array().unwrap().len(), 1);
        fs::remove_dir_all(folder).unwrap();
    }
}
