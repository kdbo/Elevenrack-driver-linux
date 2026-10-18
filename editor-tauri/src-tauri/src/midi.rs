// SPDX-License-Identifier: MIT
use crate::protocol::parse_hex;
use midir::{Ignore, MidiInput, MidiInputConnection, MidiOutput, MidiOutputConnection};
use serde_json::{json, Value};
use std::{
    sync::{mpsc, Arc, Mutex},
    thread,
    time::{Duration, Instant},
};

type Reply = Result<Option<Value>, String>;
struct Request {
    session: String,
    message: Value,
    reply: mpsc::Sender<Reply>,
}
#[derive(Clone)]
pub struct MidiService {
    requests: mpsc::Sender<Request>,
}
/// ALSA card of the Rack whose MIDI ports are connected, shared with the level meter.
pub type ConnectedCard = Arc<Mutex<Option<i32>>>;
#[derive(Clone)]
struct Port {
    index: usize,
    local: usize,
    name: String,
    kind: &'static str,
    client: Option<u32>,
    device: Option<(String, String)>,
}
fn client_id(name: &str) -> Option<u32> {
    let (client, port) = name.split_whitespace().last()?.split_once(':')?;
    let _: u32 = port.parse().ok()?;
    client.parse().ok()
}
// ALSA card number of a sequencer client, for matching the Rack's audio node.
fn client_card(client: u32) -> Option<i32> {
    let card = unsafe {
        let mut seq = std::ptr::null_mut();
        if alsa_sys::snd_seq_open(&mut seq, c"default".as_ptr(), 3, 1) < 0 {
            return None;
        }
        let mut info = std::ptr::null_mut();
        if alsa_sys::snd_seq_client_info_malloc(&mut info) < 0 {
            alsa_sys::snd_seq_close(seq);
            return None;
        }
        let card = if alsa_sys::snd_seq_get_any_client_info(seq, client as i32, info) >= 0 {
            alsa_sys::snd_seq_client_info_get_card(info)
        } else {
            -1
        };
        alsa_sys::snd_seq_client_info_free(info);
        alsa_sys::snd_seq_close(seq);
        card
    };
    (card >= 0).then_some(card)
}
// Resolve the sequencer client to its physical USB location, not enumeration order.
fn device_identity(client: Option<u32>) -> Option<(String, String)> {
    let card = client_card(client?)?;
    let proc = std::path::PathBuf::from(format!("/proc/asound/card{card}"));
    if std::fs::read_to_string(proc.join("usbid")).ok()?.trim() != "0dba:b011" {
        return None;
    }
    let path = std::fs::canonicalize(format!("/sys/class/sound/card{card}/device")).ok()?;
    let usb = path
        .ancestors()
        .find(|p| p.join("idVendor").exists() && p.join("idProduct").exists())?;
    let card_id = std::fs::read_to_string(proc.join("id")).ok()?;
    Some((
        format!("usb:{}", usb.display()),
        match card_id.trim() {
            "Rack" => "Eleven Rack 1".to_string(),
            id => id
                .strip_prefix("Rack_")
                .and_then(|suffix| suffix.parse::<u32>().ok())
                .and_then(|number| number.checked_add(1))
                .map(|number| format!("Eleven Rack {number}"))
                .unwrap_or_else(|| format!("Eleven Rack ({id})")),
        },
    ))
}
fn ports() -> Result<Vec<Port>, String> {
    let input = MidiInput::new("Eleven Rack Tauri discovery").map_err(|e| e.to_string())?;
    let output = MidiOutput::new("Eleven Rack Tauri discovery").map_err(|e| e.to_string())?;
    let mut result = Vec::new();
    for (local, port) in input.ports().iter().enumerate() {
        let name = input.port_name(port).map_err(|e| e.to_string())?;
        if name.contains("Eleven Rack Tauri") {
            continue;
        }
        result.push(Port {
            index: result.len(),
            local,
            client: client_id(&name),
            device: device_identity(client_id(&name)),
            name,
            kind: "in",
        });
    }
    for (local, port) in output.ports().iter().enumerate() {
        let name = output.port_name(port).map_err(|e| e.to_string())?;
        if name.contains("Eleven Rack Tauri") {
            continue;
        }
        result.push(Port {
            index: result.len(),
            local,
            client: client_id(&name),
            device: device_identity(client_id(&name)),
            name,
            kind: "out",
        });
    }
    Ok(result)
}
fn port_event(ports: &[Port]) -> Value {
    json!({"type":"ports","devices":ports.iter().map(|p| json!({"index":p.index,"name":p.name,
        "kind":p.kind,"desc":p.device.as_ref().map(|d|d.1.as_str()).unwrap_or("ALSA MIDI"),"alsaClient":p.client,"deviceId":p.device.as_ref().map(|d|d.0.as_str())})).collect::<Vec<_>>()})
}
pub fn list_ports() -> Result<Value, String> {
    Ok(port_event(&ports()?))
}
pub fn probe_identity() -> Result<Value, String> {
    let (events, receiver) = mpsc::channel();
    let service = MidiService::start(events, false, Default::default());
    let session = "identity-probe".to_string();
    let result = (|| -> Result<Value, String> {
        let ports = service
            .command(session.clone(), json!({"cmd":"list_ports"}))?
            .ok_or("No MIDI ports")?;
        let devices = ports["devices"]
            .as_array()
            .ok_or("Invalid MIDI port response")?;
        let input = devices
            .iter()
            .find(|p| {
                p["kind"] == "in"
                    && p["name"]
                        .as_str()
                        .is_some_and(|n| n.contains("Eleven Rack") && n.contains("Rig"))
            })
            .ok_or("No Eleven Rack Rig input")?;
        let output = devices
            .iter()
            .find(|p| {
                p["kind"] == "out"
                    && p["alsaClient"] == input["alsaClient"]
                    && p["name"] == input["name"]
            })
            .ok_or("No matching Eleven Rack Rig output")?;
        service.command(
            session.clone(),
            json!({"cmd":"connect","inPort":input["index"],"outPort":output["index"]}),
        )?;
        service.command(
            session.clone(),
            json!({"cmd":"send","hex":"F0 7E 7F 06 01 F7"}),
        )?;
        let deadline = Instant::now() + Duration::from_secs(3);
        while let Ok(event) =
            receiver.recv_timeout(deadline.saturating_duration_since(Instant::now()))
        {
            if let Some(bytes) = event["message"]["bytes"].as_array() {
                if bytes.len() > 6
                    && bytes[0] == 0xf0
                    && bytes[1] == 0x7e
                    && bytes[3] == 6
                    && bytes[4] == 2
                {
                    return Ok(
                        json!({"ok":true,"input":input["name"],"output":output["name"],"identity":event["message"]}),
                    );
                }
            }
            if Instant::now() >= deadline {
                break;
            }
        }
        Err("No MIDI identity reply within three seconds".into())
    })();
    let _ = service.command(session, json!({"cmd":"disconnect"}));
    result
}
impl MidiService {
    pub fn start(events: mpsc::Sender<Value>, disabled: bool, card: ConnectedCard) -> Self {
        let (requests, receiver) = mpsc::channel::<Request>();
        thread::spawn(move || {
            let mut actor = Actor {
                events,
                disabled,
                known: Vec::new(),
                owner: None,
                input: None,
                output: None,
                selected: None,
                replies: None,
                card,
            };
            let mut previous = Value::Null;
            loop {
                match receiver.recv_timeout(Duration::from_secs(1)) {
                    Ok(request) => {
                        let result = actor.command(&request.session, &request.message);
                        let _ = request.reply.send(result);
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    Err(mpsc::RecvTimeoutError::Timeout) => {
                        if let Ok(event) = actor.refresh() {
                            if previous != event {
                                previous = event.clone();
                                let _ = actor.events.send(json!({"message":event}));
                            }
                        }
                    }
                }
            }
        });
        Self { requests }
    }
    pub fn command(&self, session: String, message: Value) -> Reply {
        if session.is_empty() || session.len() > 128 {
            return Err("Invalid MIDI session".into());
        }
        let (reply, response) = mpsc::channel();
        self.requests
            .send(Request {
                session,
                message,
                reply,
            })
            .map_err(|_| "MIDI worker stopped")?;
        response
            .recv_timeout(Duration::from_secs(5))
            .map_err(|_| "MIDI command timed out")?
    }
}
struct Actor {
    events: mpsc::Sender<Value>,
    disabled: bool,
    known: Vec<Port>,
    owner: Option<String>,
    input: Option<MidiInputConnection<()>>,
    output: Option<MidiOutputConnection>,
    selected: Option<(String, String)>,
    replies: Option<mpsc::Receiver<Vec<u8>>>,
    card: ConnectedCard,
}
impl Actor {
    fn disconnect(&mut self) {
        self.input.take();
        self.output.take();
        self.owner = None;
        self.selected = None;
        self.replies = None;
        *self.card.lock().unwrap() = None;
    }
    fn refresh(&mut self) -> Result<Value, String> {
        let found = if self.disabled { Vec::new() } else { ports()? };
        if let Some((input, output)) = &self.selected {
            if !found.iter().any(|p| p.kind == "in" && &p.name == input)
                || !found.iter().any(|p| p.kind == "out" && &p.name == output)
            {
                let _ = self
                    .events
                    .send(json!({"session":self.owner,"message":{"type":"disconnected"}}));
                self.disconnect();
            }
        }
        self.known = found;
        Ok(port_event(&self.known))
    }
    fn command(&mut self, session: &str, message: &Value) -> Reply {
        match message
            .get("cmd")
            .and_then(Value::as_str)
            .ok_or("Expected a MIDI command")?
        {
            "reset" => {
                self.disconnect();
                Ok(Some(self.refresh()?))
            }
            "list_ports" => Ok(Some(self.refresh()?)),
            "connect" => {
                if self.disabled {
                    return Err("MIDI is disabled for this preview session".into());
                }
                if self.owner.as_deref().is_some_and(|owner| owner != session) {
                    return Err("MIDI ports belong to another session".into());
                }
                let find = |key: &str, kind: &str| -> Result<Port, String> {
                    let index = message[key].as_u64().ok_or("Invalid MIDI port index")? as usize;
                    self.known
                        .iter()
                        .find(|p| p.index == index && p.kind == kind)
                        .cloned()
                        .ok_or_else(|| "MIDI ports changed; refresh the port list".into())
                };
                let input = find("inPort", "in")?;
                let output = find("outPort", "out")?;
                if input.client.is_none()
                    || !input.name.to_lowercase().contains("eleven rack")
                    || !output.name.to_lowercase().contains("eleven rack")
                    || input.client != output.client
                    || input.device.is_none()
                    || input.device != output.device
                {
                    return Err("Select input and output from the same Eleven Rack".into());
                }
                let mut mi =
                    MidiInput::new("Eleven Rack Tauri Input").map_err(|e| e.to_string())?;
                let mo = MidiOutput::new("Eleven Rack Tauri Output").map_err(|e| e.to_string())?;
                let ip = mi
                    .ports()
                    .get(input.local)
                    .cloned()
                    .ok_or("Input disconnected")?;
                let op = mo
                    .ports()
                    .get(output.local)
                    .cloned()
                    .ok_or("Output disconnected")?;
                if mi.port_name(&ip).map_err(|e| e.to_string())? != input.name
                    || mo.port_name(&op).map_err(|e| e.to_string())? != output.name
                {
                    return Err("MIDI ports changed; refresh".into());
                }
                self.disconnect();
                mi.ignore(Ignore::None);
                let events = self.events.clone();
                let owner = session.to_string();
                let (tx, rx) = mpsc::sync_channel(16);
                let connection=mi.connect(&ip,"Eleven Rack Tauri receive",move|_,bytes,_| {
                    if bytes.is_empty() || bytes[0]>=0xf8 { return; }
                    let hex=bytes.iter().map(|b|format!("{b:02X}")).collect::<Vec<_>>().join(" ");
                    if bytes.len()==8 && bytes[..4]==[0xf0,0x13,0x0b,0x0f] && bytes[5]==0x3d { let _=tx.try_send(bytes.to_vec()); }
                    let _=events.send(json!({"session":owner,"message":{"type":"midi_in","bytes":bytes,"hex":hex}}));
                },()).map_err(|e|e.to_string())?;
                let output_connection = mo
                    .connect(&op, "Eleven Rack Tauri send")
                    .map_err(|e| e.to_string())?;
                self.input = Some(connection);
                self.output = Some(output_connection);
                self.owner = Some(session.into());
                self.selected = Some((input.name.clone(), output.name.clone()));
                self.replies = Some(rx);
                *self.card.lock().unwrap() = input.client.and_then(client_card);
                Ok(Some(
                    json!({"type":"connected","inPort":input.index,"outPort":output.index,"deviceId":input.device.as_ref().map(|d|&d.0),"deviceLabel":input.device.as_ref().map(|d|&d.1)}),
                ))
            }
            "disconnect" => {
                if self.owner.as_deref().is_some_and(|owner| owner != session) {
                    return Err("Session does not own MIDI ports".into());
                }
                self.disconnect();
                Ok(Some(json!({"type":"disconnected"})))
            }
            "send" => {
                if self.owner.as_deref() != Some(session) {
                    return Err("Session does not own MIDI ports".into());
                }
                let bytes = parse_hex(message["hex"].as_str().ok_or("Missing MIDI hex")?)?;
                self.output
                    .as_mut()
                    .ok_or("MIDI disconnected")?
                    .send(&bytes)
                    .map_err(|e| e.to_string())?;
                Ok(None)
            }
            "rig_input" | "rig_input_for_device" => {
                if message["cmd"] == "rig_input_for_device" {
                    let expected = self
                        .selected
                        .as_ref()
                        .and_then(|(name, _)| device_identity(client_id(name)))
                        .map(|d| d.0);
                    if message["deviceId"].as_str() != expected.as_deref() {
                        return Ok(Some(json!({"type":"rig_input","available":false})));
                    }
                }
                if self.owner.as_deref() != Some(session) {
                    return Ok(Some(json!({"type":"rig_input","available":false})));
                }
                let value = message
                    .get("value")
                    .filter(|v| !v.is_null())
                    .map(|v| v.as_u64().filter(|v| *v < 9).ok_or("Invalid Rig Input"))
                    .transpose()?;
                let replies = self.replies.as_ref().ok_or("MIDI disconnected")?;
                for _ in replies.try_iter() {}
                let output = self.output.as_mut().ok_or("MIDI disconnected")?;
                if let Some(value) = value {
                    output
                        .send(&[0xf0, 0x13, 0x0b, 0x0f, 0, 0x3d, value as u8, 0xf7])
                        .map_err(|e| e.to_string())?;
                }
                output
                    .send(&[0xf0, 0x13, 0x0b, 0x0f, 1, 0x3d, 0xf7])
                    .map_err(|e| e.to_string())?;
                let deadline = Instant::now() + Duration::from_secs(2);
                while let Ok(bytes) =
                    replies.recv_timeout(deadline.saturating_duration_since(Instant::now()))
                {
                    if bytes.len() == 8
                        && bytes[..4] == [0xf0, 0x13, 0x0b, 0x0f]
                        && [2, 0x12].contains(&bytes[4])
                        && bytes[5] == 0x3d
                        && bytes[6] < 9
                        && bytes[7] == 0xf7
                    {
                        if value.is_some_and(|v| v != u64::from(bytes[6])) {
                            return Err("Rack did not confirm Rig Input change".into());
                        }
                        return Ok(Some(
                            json!({"type":"rig_input","available":true,"value":bytes[6]}),
                        ));
                    }
                    if Instant::now() >= deadline {
                        break;
                    }
                }
                Err("No recognized Rig Input reply".into())
            }
            _ => Err("Unknown MIDI command".into()),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn discovery_keeps_identical_rack_names_separate_by_usb_location() {
        let make = |index, client, id: &str, label: &str| Port {
            index,
            local: index,
            name: format!("Eleven Rack:Eleven Rack Rig {client}:0"),
            kind: "in",
            client: Some(client),
            device: Some((id.into(), label.into())),
        };
        let event = port_event(&[
            make(0, 20, "usb:/one", "Rack one"),
            make(1, 24, "usb:/two", "Rack two"),
        ]);
        assert_ne!(
            event["devices"][0]["deviceId"],
            event["devices"][1]["deviceId"]
        );
        assert_eq!(event["devices"][1]["desc"], "Rack two");
        // ALSA renumbering must not alter the saved physical identity.
        let moved = port_event(&[make(0, 28, "usb:/one", "Rack one")]);
        assert_eq!(
            event["devices"][0]["deviceId"],
            moved["devices"][0]["deviceId"]
        );
    }
    #[test]
    fn disabled_backend_never_opens_midi_and_rejects_unowned_writes() {
        let (events, _) = mpsc::channel();
        let service = MidiService::start(events, true, Default::default());
        let ports = service
            .command("test".into(), json!({"cmd":"list_ports"}))
            .unwrap()
            .unwrap();
        assert!(ports["devices"].as_array().unwrap().is_empty());
        assert!(service
            .command(
                "test".into(),
                json!({"cmd":"connect","inPort":0,"outPort":1})
            )
            .is_err());
        assert!(service
            .command("test".into(), json!({"cmd":"send","hex":"C0 01"}))
            .is_err());
        assert!(service
            .command("".into(), json!({"cmd":"list_ports"}))
            .is_err());
    }
    #[test]
    fn alsa_client_pairing_reads_only_complete_addresses() {
        assert_eq!(client_id("Eleven Rack:Eleven Rack MIDI 1 24:0"), Some(24));
        assert_eq!(client_id("Eleven Rack"), None);
        assert_eq!(client_id("Eleven Rack 24"), None);
    }
}
