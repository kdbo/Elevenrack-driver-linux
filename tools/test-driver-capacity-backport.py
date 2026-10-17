#!/usr/bin/env python3
"""Check conditional upstream backport, including refusal of partial fixes."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('prepare', ROOT/'packaging/prepare-driver.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)

CARD = '''struct snd_usb_endpoint {
\tunsigned int maxframesize;      /* max packet size in frames */
};
'''
ENDPOINT = '''void queue(void) {
\tif (implicit_fb) {
\t\tctx->packets = packet->packets;
\t\tmemcpy(ctx->packet_size, packet->packet_size,
\t\t       packet->packets * sizeof(packet->packet_size[0]));
\t}
}
void allocate(void) {
\t/* allocate and initialize data urbs */
\tfor (i = 0; i < ep->nurbs; i++) {
\t\tstruct snd_urb_ctx *u = &ep->urb[i];
\t\tu->index = i;
\t\tu->ep = ep;
\t\tu->packets = urb_packs;
\t\tu->buffer_size = maxsize * u->packets;
\t\tif (fmt->fmt_type == UAC_FORMAT_TYPE_II)
\t\t\tu->packets++; /* for transfer delimiter */
\t\tu->urb = usb_alloc_urb(u->packets, GFP_KERNEL);
\t}
}
'''


class CapacityBackport(unittest.TestCase):
    def fixed(self):
        return prepare.implicit_feedback_capacity(CARD, ENDPOINT)[:2]

    def test_missing_fix_is_backported_and_delimiter_precedes_capacity(self):
        card, endpoint, status = prepare.implicit_feedback_capacity(CARD, ENDPOINT)
        self.assertEqual(status, 'backported')
        self.assertIn('unsigned int max_urb_packs;', card)
        self.assertLess(endpoint.index('urb_packs++;'), endpoint.index('ep->max_urb_packs ='))
        self.assertLess(endpoint.index('ep->max_urb_packs ='), endpoint.index('for (i = 0;'))
        self.assertNotIn('u->packets++;', endpoint)

    def test_existing_fix_is_preserved_byte_for_byte(self):
        card, endpoint = self.fixed()
        self.assertEqual(prepare.implicit_feedback_capacity(card, endpoint),
                         (card, endpoint, 'already present'))

    def test_distro_whitespace_and_comments_do_not_duplicate_fix(self):
        card, endpoint = self.fixed()
        endpoint = endpoint.replace('min_t(int, packet->packets,',
                                    'min_t( int, /* distro backport */ packet->packets,')
        self.assertEqual(prepare.implicit_feedback_capacity(card, endpoint)[2], 'already present')

    def test_partial_fix_or_unbounded_copy_is_rejected(self):
        card, endpoint = self.fixed()
        for c, e in [(card, ENDPOINT), (CARD, endpoint),
                     (card, endpoint.replace('ctx->packets * sizeof', 'packet->packets * sizeof')),
                     (card, endpoint.replace('ep->max_urb_packs = urb_packs;', ''))]:
            with self.subTest(card=c, endpoint=e):
                with self.assertRaises(RuntimeError):
                    prepare.implicit_feedback_capacity(c, e)

    def test_unknown_layout_is_rejected(self):
        with self.assertRaises(RuntimeError):
            prepare.implicit_feedback_capacity(CARD, ENDPOINT.replace('ctx->packets =', 'ctx->other ='))

    def test_pre_7_0_copy_loop_is_left_unchanged(self):
        card = CARD.replace('};', '\tint packet_size[MAX_PACKS_HS];\n'
                                  '\tuint32_t packet_size[MAX_PACKS_HS];\n};')
        endpoint = ENDPOINT.replace(
            '\t\tctx->packets = packet->packets;\n'
            '\t\tmemcpy(ctx->packet_size, packet->packet_size,\n'
            '\t\t       packet->packets * sizeof(packet->packet_size[0]));\n',
            '\t\tfor (i = 0; i < packet->packets; i++)\n'
            '\t\t\tctx->packet_size[i] = packet->packet_size[i];\n')
        self.assertEqual(prepare.implicit_feedback_capacity(card, endpoint),
                         (card, endpoint, 'not needed (feedback does not resize URBs)'))
        # Ubuntu 6.8 also resizes the URB from feedback, so the loop needs the fix.
        resized = endpoint.replace('\t\tfor (i', '\t\tctx->packets = packet->packets;\n\t\tfor (i')
        card, fixed, status = prepare.implicit_feedback_capacity(card, resized)
        self.assertEqual(status, 'backported')
        self.assertIn('for (i = 0; i < ctx->packets; i++)', fixed)
        self.assertNotIn('i < packet->packets', fixed)
        self.assertEqual(prepare.implicit_feedback_capacity(card, fixed)[2], 'already present')
        with self.assertRaises(RuntimeError):
            prepare.implicit_feedback_capacity(card, fixed.replace(
                'i < ctx->packets; i++)', 'i < packet->packets; i++)'))

    def test_comment_cannot_pretend_to_be_an_existing_fix(self):
        card, endpoint = self.fixed()
        assignment = 'ep->max_urb_packs = urb_packs;'
        endpoint = endpoint.replace(assignment, '/* ' + assignment + ' */')
        with self.assertRaises(RuntimeError):
            prepare.implicit_feedback_capacity(card, endpoint)


if __name__ == '__main__':
    unittest.main()
