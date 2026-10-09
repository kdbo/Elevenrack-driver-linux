-- WirePlumber 0.4 (Ubuntu 24.04). WirePlumber 0.5 uses the .conf fragment.
local rules = {
  {
    matches = { { { "device.name", "matches", "alsa_card.usb-Digidesign_Eleven_Rack.*" } } },
    apply_properties = {
      ["api.alsa.use-acp"] = false,
      ["api.alsa.use-ucm"] = false,
      ["device.description"] = "Eleven Rack",
    },
  },
  {
    matches = { { { "node.name", "matches", "alsa_input.usb-Digidesign_Eleven_Rack.*" } } },
    apply_properties = {
      ["node.description"] = "Eleven Rack Inputs",
      ["node.nick"] = "Eleven Rack Inputs",
      ["audio.channels"] = 8,
      ["audio.position"] = "[ AUX0 AUX1 AUX2 AUX3 AUX4 AUX5 AUX6 AUX7 ]",
      ["api.alsa.use-chmap"] = false,
      ["node.channel-names"] = '[ "Guitar In" "Mic In" "Eleven Rig L" "Eleven Rig R" "Digital In L" "Digital In R" "Line In L" "Line In R" ]',
      ["node.device-port-name-prefix"] = "",
      ["audio.allowed-rates"] = "[ 44100 48000 88200 96000 ]",
    },
  },
  {
    matches = { { { "node.name", "matches", "alsa_output.usb-Digidesign_Eleven_Rack.*" } } },
    apply_properties = {
      ["node.description"] = "Eleven Rack Outputs",
      ["node.nick"] = "Eleven Rack Outputs",
      ["audio.channels"] = 6,
      ["audio.position"] = "[ AUX0 AUX1 AUX2 AUX3 AUX4 AUX5 ]",
      ["api.alsa.use-chmap"] = false,
      ["node.channel-names"] = '[ "Main Out L" "Main Out R" "Re-Amp L" "Re-Amp R" "Digital Out L" "Digital Out R" ]',
      ["node.device-port-name-prefix"] = "",
      ["audio.allowed-rates"] = "[ 44100 48000 88200 96000 ]",
    },
  },
}
for _, rule in ipairs(rules) do
  table.insert(alsa_monitor.rules, rule)
end
