# -*- coding: utf-8 -*-
from odoo.tests import BaseCase, tagged

from ..tools.sanitize import sanitize_text, sanitize_exception, sanitize_mapping, MASK


@tagged('post_install', '-at_install', 'abc_va')
class TestSanitize(BaseCase):

    SECRET = '1f60a3503f764f129e3d133d29b76276'
    CLIENT = '792108daf2c344a1bc4f'

    def test_masks_secret_everywhere(self):
        text = f'401 from https://x/y?X-Client-Secret={self.SECRET}&id={self.CLIENT} body={{"s": "{self.SECRET}"}}'
        out = sanitize_text(text, [self.SECRET, self.CLIENT])
        self.assertNotIn(self.SECRET, out)
        self.assertNotIn(self.CLIENT, out)
        self.assertEqual(out.count(MASK), 3)

    def test_ignores_short_or_empty_secrets(self):
        text = 'abc def'
        self.assertEqual(sanitize_text(text, ['', None, 'ab']), text)

    def test_none_text(self):
        self.assertEqual(sanitize_text(None, [self.SECRET]), '')

    def test_exception(self):
        exc = ValueError(f'invalid credentials {self.SECRET}')
        out = sanitize_exception(exc, [self.SECRET])
        self.assertTrue(out.startswith('ValueError:'))
        self.assertNotIn(self.SECRET, out)

    def test_mapping(self):
        headers = {'X-Client-Secret': self.SECRET, 'Accept': 'application/json', 'n': 3}
        out = sanitize_mapping(headers, [self.SECRET])
        self.assertEqual(out['X-Client-Secret'], MASK)
        self.assertEqual(out['Accept'], 'application/json')
        self.assertEqual(out['n'], 3)
