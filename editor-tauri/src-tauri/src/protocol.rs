// SPDX-License-Identifier: MIT
pub fn parse_hex(text: &str) -> Result<Vec<u8>, String> {
    let compact: String = text.chars().filter(|c| !c.is_whitespace()).collect();
    if compact.is_empty() || compact.len() % 2 != 0 || compact.len() > 131072 {
        return Err("Empty, malformed or oversized MIDI message".into());
    }
    let bytes: Result<Vec<_>, _> = compact
        .as_bytes()
        .chunks(2)
        .map(|pair| {
            let word = std::str::from_utf8(pair).map_err(|_| "Invalid hex")?;
            u8::from_str_radix(word, 16).map_err(|_| "Invalid hex")
        })
        .collect();
    let data = bytes.map_err(str::to_string)?;
    if data[0] == 0xf0 {
        if data.len() < 2
            || data.last() != Some(&0xf7)
            || data[1..data.len() - 1].iter().any(|v| *v > 127)
        {
            return Err("Invalid SysEx message".into());
        }
    } else {
        let length = if (0xc0..=0xdf).contains(&data[0]) {
            2
        } else {
            3
        };
        if !(0x80..=0xef).contains(&data[0])
            || data.len() != length
            || data[1..].iter().any(|v| *v > 127)
        {
            return Err("Expected a complete MIDI channel message or SysEx".into());
        }
    }
    Ok(data)
}

pub fn decode_7bit(encoded: &[u8]) -> Result<Vec<u8>, String> {
    if encoded.is_empty()
        || encoded.len() > 65536
        || encoded.iter().any(|b| *b > 127)
        || encoded.len() % 8 == 1
    {
        return Err("Invalid 7-bit patch payload".into());
    }
    let length = encoded.len() / 8 * 7 + (encoded.len() % 8).saturating_sub(1);
    // Consecutive 7-bit words form the binary bitstream, most significant bit first.
    let mut output = Vec::with_capacity(length);
    let (mut bits, mut count) = (0u32, 0usize);
    for byte in encoded {
        bits = (bits << 7) | u32::from(*byte);
        count += 7;
        if count >= 8 {
            count -= 8;
            output.push(((bits >> count) & 255) as u8);
        }
    }
    Ok(output)
}

pub fn tfx(body: &[u8]) -> Result<Vec<u8>, String> {
    if body.is_empty() || body.len() > 65536 {
        return Err("Invalid TFX body length".into());
    }
    let mut data = vec![0; 56];
    data[..4].copy_from_slice(&((body.len() + 56) as u32).to_be_bytes());
    data[8..24].copy_from_slice(b"DigiElvRELVhRig ");
    data.extend_from_slice(body);
    Ok(data)
}
pub fn tfx_body(raw: &[u8]) -> Result<Vec<u8>, String> {
    if raw.len() < 56 || !raw[8..24].starts_with(b"DigiElv") {
        return Err("Invalid TFX header".into());
    }
    let body = &raw[56..];
    if body.len() < 256 {
        return Err("Patch data too small (truncated)".into());
    }
    if !body.windows(4).any(|w| w == b"sld6" || w == b"6dls") {
        return Err("Incomplete patch: no amp block".into());
    }
    Ok(body.to_vec())
}
pub fn safe_leaf(name: &str) -> Result<&str, String> {
    if name.is_empty()
        || name == "."
        || name.contains("..")
        || name.contains(['/', '\\', '\0', ':'])
    {
        return Err("Expected a plain filename".into());
    }
    Ok(name)
}
pub fn safe_name(name: &str, max: usize) -> String {
    let result: String = name
        .chars()
        .map(|c| {
            if c.is_control() || "\\/:*?\"<>|".contains(c) {
                '_'
            } else {
                c
            }
        })
        .take(max)
        .collect();
    if result.trim_matches('.').trim().is_empty() {
        "capture".into()
    } else {
        result
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn channel_messages_and_sysex_are_validated() {
        for input in ["90 40 7f", "c0 01", "F0 13 0B 0F 01 3D F7"] {
            assert!(parse_hex(input).is_ok());
        }
        for input in [
            "", "F0 01", "F0 90 F7", "c0 01 02", "90 40", "ff", "GG", "0", "€",
        ] {
            assert!(parse_hex(input).is_err(), "{input}");
        }
    }
    #[test]
    fn seven_bit_codec_matches_known_bitstream() {
        assert_eq!(
            decode_7bit(&[127, 127, 127, 127, 127, 127, 127, 127]).unwrap(),
            vec![255; 7]
        );
        assert_eq!(
            decode_7bit(&[0x09, 0x0d, 0x0a, 0x67, 0x44, 0x59, 0x71, 0x6f]).unwrap(),
            vec![0x12, 0x34, 0x56, 0x78, 0x96, 0x78, 0xef]
        );
        assert!(decode_7bit(&[0]).is_err());
    }
    #[test]
    fn tfx_roundtrip_and_truncation() {
        let mut body = vec![0; 256];
        body[..4].copy_from_slice(b"sld6");
        let raw = tfx(&body).unwrap();
        assert_eq!(&raw[..4], &312u32.to_be_bytes());
        assert_eq!(tfx_body(&raw).unwrap(), body);
        assert!(tfx_body(&raw[..40]).is_err());
        assert!(tfx_body(&tfx(&[0; 256]).unwrap()).is_err());
    }
    #[test]
    fn paths_cannot_escape_a_bank() {
        for name in ["../a.tfx", "/a.tfx", "x\\a.tfx", "C:a.tfx", "..", ""] {
            assert!(safe_leaf(name).is_err());
        }
        assert!(safe_leaf("A Nice Rig.tfx").is_ok());
        assert_eq!(safe_name("a/b:c", 32), "a_b_c");
    }
}
