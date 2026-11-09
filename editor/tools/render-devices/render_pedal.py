# Render a stompbox look-alike with Blender (Cycles) for the editor.
#
#   python3 art.py <device> <outdir>/_art-<device>
#   blender -b -P render_pedal.py -- <device> <outdir>
#
# Writes, at 80 px per cm (2x the editor's 40 CSS px per cm):
#   <device>-body.png         the enclosure seen from straight above, no knobs
#   <device>-knob.png         one knob without its pointer (lit; the editor adds its shadow)
#   <device>-pointer.png      the knob's pointer on its own, for the editor to turn
#   <device>.json             sizes and knob/LED centres in CSS px
# The printed artwork is drawn with PIL (art.py) and laid on as a decal.
# Shapes, colours and layout only: the rack's model names, no maker's logo.

import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import devices  # noqa: E402
import rhelp as R  # noqa: E402
from rhelp import PX_PER_CM, reset, lights, camera, render  # noqa: E402


argv = sys.argv[sys.argv.index('--') + 1:]
DEV, OUT = argv[0], argv[1]
SPEC = devices.DEVICES[DEV]
os.makedirs(OUT, exist_ok=True)


# ── body ──
sc = reset(SPEC.get('samples', 96))
devices.ART_DIR = os.path.join(OUT, '_art-' + DEV)   # art.py has drawn the decals here
SPEC['build'](R, SPEC['decals'])
lights()
if SPEC.get('ink'):
    R.ink(SPEC['ink'])
W, H = SPEC['frame']
camera(W, H)
render(os.path.join(OUT, DEV + '-body.png'))

# ── knob, then its pointer alone ──
sc = reset(SPEC.get('samples', 96))
k = SPEC['knob']
SPEC['build_knob'](R, pointer=False)
lights(0.25)
if SPEC.get('ink'):
    R.ink(SPEC['ink'] * 0.8)
camera(k['frame'], k['frame'])
render(os.path.join(OUT, DEV + '-knob.png'))

sc = reset(SPEC.get('samples', 96))
SPEC['build_knob'](R, pointer=True)
lights(0.25)
camera(k['frame'], k['frame'])
render(os.path.join(OUT, DEV + '-pointer.png'))

# ── other moving parts (a slider's carriage ...), each on its own ──
for name, (build, frame) in SPEC.get('sprites', {}).items():
    sc = reset(SPEC.get('samples', 96))
    build(R)
    lights(0.25)
    camera(frame, frame)
    render(os.path.join(OUT, DEV + '-' + name + '.png'))

css = PX_PER_CM / 2
meta = {
    'width': round(W * css), 'height': round(H * css),
    'knob': round(k['frame'] * css),
    # knob centre in CSS px, and its scale (1 = the rendered knob's size)
    'knobs': {name: [round((v[0] + W / 2) * css, 1), round((H / 2 - v[1]) * css, 1), v[2] if len(v) > 2 else 1]
              for name, v in SPEC['knobs'].items()},
    'led': [round((SPEC['led'][0] + W / 2) * css, 1), round((H / 2 - SPEC['led'][1]) * css, 1)],
}
with open(os.path.join(OUT, DEV + '.json'), 'w') as f:
    json.dump(meta, f, indent=1)
