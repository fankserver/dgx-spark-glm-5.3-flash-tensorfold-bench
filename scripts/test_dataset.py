import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from aggregate_and_plot import DEPTHS, read_points
import run_benchmark


class DatasetTests(unittest.TestCase):
    def test_all_exact_points(self):
        points=read_points(ROOT/'results/glm53-standard-mtp-c1.json')
        self.assertEqual([r['context_depth'] for r in points],DEPTHS)
        self.assertTrue(all(r['input_tokens']==r['context_depth']+512 and r['output_tokens']==256 for r in points))
        self.assertEqual(points,json.loads((ROOT/'dataset.json').read_text()))

    def test_reject_mismatched_points_and_length(self):
        original=json.loads((ROOT/'results/glm53-standard-mtp-c1.json').read_text())
        for field,value in [('context_size',999),('response_size',128)]:
            data=copy.deepcopy(original);data['benchmarks'][0][field]=value
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'bad.json';p.write_text(json.dumps(data))
                with self.assertRaises(ValueError):read_points(p)

    def test_raw_provenance_and_metadata(self):
        meta=json.loads((ROOT/'results/methodology.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'results/glm53-standard-mtp-c1.json').read_bytes()).hexdigest(),meta['raw_results_sha256'])
        self.assertEqual(meta['parameters']['depths'],DEPTHS)
        self.assertEqual(meta['native_counter_deltas_including_warmups']['cached_tokens_total'],0)
        text=(ROOT/'results/methodology.json').read_text()
        self.assertNotIn('/home/',text);self.assertNotIn('192.168.',text)
        for ref in json.loads((ROOT/'results/reference-provenance.json').read_text()):
            self.assertEqual(hashlib.sha256((ROOT/ref['local_path']).read_bytes()).hexdigest(),ref['sha256'])
            self.assertEqual(len(read_points(ROOT/ref['local_path'])),14)

    def test_client_only_runner_preserves_parameters(self):
        fake=types.ModuleType('llama_benchy');fake.__version__='0.4.0'
        corpus=types.ModuleType('llama_benchy.corpus')
        corpus.LightweightTokenizer=types.SimpleNamespace(from_pretrained=lambda name:None)
        with tempfile.TemporaryDirectory() as d:
            key=Path(d)/'key';key.write_text('test-placeholder-not-a-real-key')
            argv=['run_benchmark.py','--base-url','https://example.invalid/v1','--tokenizer','tokenizer.json',
                  '--api-key-file',str(key),'--output',str(Path(d)/'new.json')]
            for levels in ([1],[1,2,4]):
                with self.subTest(concurrency=levels):
                    cli=argv if levels==[1] else argv+['--concurrency',*[str(n) for n in levels]]
                    with patch.dict(sys.modules,{'llama_benchy':fake,'llama_benchy.corpus':corpus}),patch.object(sys,'argv',cli),patch.object(run_benchmark.runpy,'run_module') as run:
                        run_benchmark.main()
                        args=list(sys.argv)
                        run.assert_called_once_with('llama_benchy',run_name='__main__')
                    self.assertEqual(args[args.index('--depth')+1:args.index('--pp')],[str(n) for n in DEPTHS])
                    self.assertEqual(args[args.index('--concurrency')+1:args.index('--format')],[str(n) for n in levels])
                    for flag,value in [('--pp','512'),('--tg','256'),('--runs','2'),('--latency-mode','generation')]:
                        self.assertEqual(args[args.index(flag)+1],value)
                    self.assertIn('--exact-tg',args)
                    self.assertNotIn('--no-cache',args);self.assertNotIn('--enable-prefix-caching',args)


if __name__=='__main__':unittest.main()
