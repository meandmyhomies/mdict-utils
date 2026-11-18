import os
import subprocess
import sys
import tempfile
import unittest

from mdict_utils import reader
from mdict_utils.writer import pack, pack_mdx_txt


class TestHeadwordsExtraction(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.mdx_path = os.path.join(self.tmpdir.name, 'sample.mdx')
        self.entries = {
            'apple': 'a fruit',
            'banana': 'a yellow fruit',
            'cherry': 'a red fruit',
            '123num': 'a numeric entry',
        }
        txt_path = os.path.join(self.tmpdir.name, 'sample.txt')
        with open(txt_path, 'wb') as f:
            for k, v in self.entries.items():
                f.write(f'{k}\r\n{v}\r\n</>\r\n'.encode('utf-8'))
        dictionary = pack_mdx_txt(txt_path)
        pack(self.mdx_path, dictionary, title='Sample', description='Sample dict', is_mdd=False)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_unpack_headwords_single_file(self):
        outdir = os.path.join(self.tmpdir.name, 'out')
        reader.unpack_headwords(outdir, self.mdx_path)
        out_file = os.path.join(outdir, 'sample.mdx.headwords.txt')
        self.assertTrue(os.path.exists(out_file))
        with open(out_file, 'rt', encoding='utf-8') as f:
            lines = f.read().splitlines()
        self.assertEqual(set(lines), set(self.entries.keys()))
        self.assertEqual(len(lines), len(self.entries))

    def test_unpack_headwords_split_n(self):
        outdir = os.path.join(self.tmpdir.name, 'out_n')
        reader.unpack_headwords(outdir, self.mdx_path, split='2')
        part1 = os.path.join(outdir, 'sample.mdx.part01.headwords.txt')
        part2 = os.path.join(outdir, 'sample.mdx.part02.headwords.txt')
        self.assertTrue(os.path.exists(part1))
        self.assertTrue(os.path.exists(part2))
        collected = []
        for path in (part1, part2):
            with open(path, 'rt', encoding='utf-8') as f:
                collected.extend(f.read().splitlines())
        self.assertEqual(set(collected), set(self.entries.keys()))

    def test_unpack_headwords_split_az(self):
        outdir = os.path.join(self.tmpdir.name, 'out_az')
        reader.unpack_headwords(outdir, self.mdx_path, split='az')
        with open(os.path.join(outdir, 'sample.mdx.a.headwords.txt'), 'rt', encoding='utf-8') as f:
            self.assertEqual(f.read().splitlines(), ['apple'])
        with open(os.path.join(outdir, 'sample.mdx.other.headwords.txt'), 'rt', encoding='utf-8') as f:
            self.assertEqual(f.read().splitlines(), ['123num'])

    def test_unpack_headwords_rejects_non_mdx(self):
        outdir = os.path.join(self.tmpdir.name, 'out_err')
        with self.assertRaises(ValueError):
            reader.unpack_headwords(outdir, os.path.join(self.tmpdir.name, 'sample.mdd'))

    def test_cli_headwords(self):
        outdir = os.path.join(self.tmpdir.name, 'cli_out')
        result = subprocess.run(
            [sys.executable, '-m', 'mdict_utils', '--headwords', '-d', outdir, self.mdx_path],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        out_file = os.path.join(outdir, 'sample.mdx.headwords.txt')
        self.assertTrue(os.path.exists(out_file))
        with open(out_file, 'rt', encoding='utf-8') as f:
            lines = f.read().splitlines()
        self.assertEqual(set(lines), set(self.entries.keys()))

    def test_unpack_full_still_works(self):
        outdir = os.path.join(self.tmpdir.name, 'full_out')
        reader.unpack(outdir, self.mdx_path)
        out_file = os.path.join(outdir, 'sample.mdx.txt')
        self.assertTrue(os.path.exists(out_file))
        with open(out_file, 'rt', encoding='utf-8') as f:
            content = f.read()
        for key, val in self.entries.items():
            self.assertIn(key, content)
            self.assertIn(val, content)


if __name__ == '__main__':
    unittest.main()
