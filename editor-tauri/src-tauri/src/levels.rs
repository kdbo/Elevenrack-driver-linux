// SPDX-License-Identifier: MIT
// Rig Out L/R levels for the VU meters. pw-record captures only the Rig L/R
// channels of the connected Rack's PipeWire capture node; nothing is stored.
use crate::midi::ConnectedCard;
use serde_json::{json, Value};
use std::{
    io::Read,
    process::{Child, Command, Stdio},
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

const UPDATES_PER_SECOND: u32 = 30;

#[derive(Debug, PartialEq)]
struct Source {
    node: String,
    channels: [String; 2],
    rate: u32,
}

fn number(value: &Value) -> Option<u32> {
    value
        .as_u64()
        .or_else(|| value.as_str()?.trim().parse().ok())
        .and_then(|v| u32::try_from(v).ok())
}

// The graph rate in use, so the meter stream never asks PipeWire to switch it.
fn graph_rate(dump: &[Value]) -> Option<u32> {
    let settings = dump.iter().find(|o| {
        o["type"] == "PipeWire:Interface:Metadata" && o["props"]["metadata.name"] == "settings"
    })?;
    let entries = settings["metadata"].as_array()?;
    let get = |key: &str| {
        entries
            .iter()
            .find(|e| e["subject"] == 0 && e["key"] == key)
            .and_then(|e| number(&e["value"]))
    };
    get("clock.force-rate")
        .filter(|rate| *rate > 0)
        .or_else(|| get("clock.rate"))
}

// The Rack capture node on `card` and the positions of its Rig L/R ports.
fn find_source(dump: &[Value], card: i32, card_id: Option<&str>) -> Option<Source> {
    let paths = [Some(card.to_string()), card_id.map(str::to_string)];
    let on_card = |path: &str| {
        paths
            .iter()
            .flatten()
            .any(|c| path.starts_with(&format!("hw:{c},")))
    };
    let port_channel = |node: u64, name: &str| {
        dump.iter()
            .filter(|o| o["type"] == "PipeWire:Interface:Port")
            .map(|o| &o["info"]["props"])
            .find(|p| {
                p["node.id"].as_u64() == Some(node)
                    && p["port.direction"] == "out"
                    && p["port.name"].as_str().is_some_and(|n| n.ends_with(name))
            })
            .and_then(|p| p["audio.channel"].as_str().map(str::to_string))
    };
    dump.iter()
        .filter(|o| o["type"] == "PipeWire:Interface:Node")
        .find_map(|o| {
            let props = &o["info"]["props"];
            if props["media.class"] != "Audio/Source"
                || !props["api.alsa.path"].as_str().is_some_and(on_card)
            {
                return None;
            }
            let id = o["id"].as_u64()?;
            let channels = [port_channel(id, "Rig L")?, port_channel(id, "Rig R")?];
            let running = o["info"]["params"]["Format"]
                .as_array()
                .and_then(|f| f.first())
                .and_then(|f| number(&f["rate"]));
            Some(Source {
                node: props["node.name"].as_str()?.to_string(),
                channels,
                rate: running.or_else(|| graph_rate(dump)).unwrap_or(48000),
            })
        })
}

fn locate(card: i32) -> Option<Source> {
    let output = Command::new("pw-dump")
        .stderr(Stdio::null())
        .output()
        .ok()?;
    let dump: Vec<Value> = serde_json::from_slice(&output.stdout).ok()?;
    let id = std::fs::read_to_string(format!("/proc/asound/card{card}/id")).ok();
    find_source(&dump, card, id.as_deref().map(str::trim))
}

fn spawn(source: &Source) -> std::io::Result<Child> {
    Command::new("pw-record")
        .args(["--raw", "--format", "s16", "--channels", "2"])
        .args(["--channel-map", &source.channels.join(",")])
        .args(["--rate", &source.rate.to_string()])
        .args(["--target", &source.node])
        // Large latency so the meter never lowers the graph quantum.
        .args(["--latency", "4096"])
        .args([
            "-P",
            "{ stream.dont-remix = true node.dont-reconnect = true \
             node.name = \"eleven-rack-editor-meters\" \
             node.description = \"Eleven Rack Editor meters\" }",
            "-",
        ])
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
}

// Linear RMS (0..1) of interleaved stereo s16 for every `window` frames.
fn read_levels(mut input: impl Read, window: usize, levels: mpsc::Sender<(f64, f64)>) {
    let mut chunk = [0u8; 8192];
    let mut pending = Vec::new();
    let (mut left, mut right, mut frames) = (0.0f64, 0.0f64, 0usize);
    while let Ok(read) = input.read(&mut chunk) {
        if read == 0 {
            return;
        }
        pending.extend_from_slice(&chunk[..read]);
        let whole = pending.len() / 4 * 4;
        for frame in pending[..whole].chunks_exact(4) {
            let l = f64::from(i16::from_le_bytes([frame[0], frame[1]])) / 32768.0;
            let r = f64::from(i16::from_le_bytes([frame[2], frame[3]])) / 32768.0;
            left += l * l;
            right += r * r;
            frames += 1;
            if frames == window {
                let n = window as f64;
                if levels
                    .send(((left / n).sqrt(), (right / n).sqrt()))
                    .is_err()
                {
                    return;
                }
                (left, right, frames) = (0.0, 0.0, 0);
            }
        }
        pending.drain(..whole);
    }
}

fn meter(card: &ConnectedCard, expected: i32, source: &Source, emit: &impl Fn(Value)) {
    let Ok(mut child) = spawn(source) else {
        emit(json!({"available":false,"reason":"pw-record unavailable"}));
        thread::sleep(Duration::from_secs(5));
        return;
    };
    let stdout = child.stdout.take().expect("piped stdout");
    let (sender, receiver) = mpsc::channel();
    let window = (source.rate / UPDATES_PER_SECOND).max(1) as usize;
    thread::spawn(move || read_levels(stdout, window, sender));
    let (mut last, mut idle) = (Instant::now(), false);
    while *card.lock().unwrap() == Some(expected) {
        match receiver.recv_timeout(Duration::from_millis(250)) {
            Ok((l, r)) => {
                (last, idle) = (Instant::now(), false);
                emit(json!({"available":true,"running":true,"l":l,"r":r,"rate":source.rate}));
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if !idle && last.elapsed() > Duration::from_millis(500) {
                    idle = true;
                    emit(json!({"available":true,"running":false}));
                }
            }
            // pw-record exited, e.g. because the Rack was unplugged.
            Err(mpsc::RecvTimeoutError::Disconnected) => break,
        }
    }
    let _ = child.kill();
    let _ = child.wait();
}

/// Follow the connected Rack and emit `vu-levels` payloads for the renderer.
pub fn start(card: ConnectedCard, emit: impl Fn(Value) + Send + 'static) {
    thread::spawn(move || {
        // Report each unavailable reason once, not on every retry.
        let mut unavailable: Option<&str> = None;
        let mut report = |reason: Option<&'static str>| {
            if let Some(reason) = reason.filter(|r| unavailable != Some(*r)) {
                emit(json!({"available":false,"reason":reason}));
            }
            unavailable = reason;
        };
        loop {
            let Some(current) = *card.lock().unwrap() else {
                report(Some("no Rack connected"));
                thread::sleep(Duration::from_secs(1));
                continue;
            };
            let Some(source) = locate(current) else {
                report(Some("Rack audio node not found"));
                thread::sleep(Duration::from_secs(2));
                continue;
            };
            report(None);
            meter(&card, current, &source, &emit);
            thread::sleep(Duration::from_millis(500));
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dump(path: &str, format: Value) -> Vec<Value> {
        let port = |id: u64, name: &str, channel: &str| {
            json!({"id":id,"type":"PipeWire:Interface:Port","info":{"props":{
                "node.id":59,"port.direction":"out","port.name":name,"audio.channel":channel}}})
        };
        vec![
            json!({"id":59,"type":"PipeWire:Interface:Node","info":{"props":{
                "media.class":"Audio/Source","api.alsa.path":path,
                "node.name":"alsa_input.usb-Digidesign_Eleven_Rack-01.capture.0.0"},
                "params":{"Format":format}}}),
            port(70, "Guitar In", "AUX0"),
            port(72, "Eleven Rig L", "AUX2"),
            port(73, "Eleven Rig R", "AUX3"),
            json!({"id":30,"type":"PipeWire:Interface:Metadata","props":{"metadata.name":"settings"},
                "metadata":[{"subject":0,"key":"clock.rate","value":48000},
                            {"subject":0,"key":"clock.force-rate","value":"96000"}]}),
        ]
    }

    #[test]
    fn finds_rig_channels_on_the_connected_card_and_keeps_the_running_rate() {
        let source = find_source(&dump("hw:1,0", json!([{"rate":44100}])), 1, None).unwrap();
        assert_eq!(
            source,
            Source {
                node: "alsa_input.usb-Digidesign_Eleven_Rack-01.capture.0.0".into(),
                channels: ["AUX2".into(), "AUX3".into()],
                rate: 44100,
            }
        );
        assert!(find_source(&dump("hw:2,0", json!([])), 1, None).is_none());
        assert!(find_source(&dump("hw:11,0", json!([])), 1, None).is_none());
        assert!(find_source(&dump("hw:Rack,0", json!([])), 1, Some("Rack")).is_some());
    }

    #[test]
    fn idle_node_uses_the_forced_graph_rate() {
        let source = find_source(&dump("hw:1,0", json!([])), 1, None).unwrap();
        assert_eq!(source.rate, 96000);
    }

    #[test]
    fn rms_is_computed_per_window_across_partial_reads() {
        let mut bytes = Vec::new();
        for _ in 0..4 {
            bytes.extend_from_slice(&16384i16.to_le_bytes());
            bytes.extend_from_slice(&0i16.to_le_bytes());
        }
        // A reader that returns one byte at a time splits every frame.
        struct Trickle(std::io::Cursor<Vec<u8>>);
        impl Read for Trickle {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                let one = buf.len().min(1);
                self.0.read(&mut buf[..one])
            }
        }
        let (sender, receiver) = mpsc::channel();
        read_levels(Trickle(std::io::Cursor::new(bytes)), 2, sender);
        let levels: Vec<_> = receiver.iter().collect();
        assert_eq!(levels, vec![(0.5, 0.0), (0.5, 0.0)]);
    }
}
