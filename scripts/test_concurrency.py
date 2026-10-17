import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from analyze_concurrency import read_grid

FILES=('glm53-standard-mtp-c1-c2-c4.json','concurrency-methodology.json','concurrency-request-timings-derived.json')


def copy_fixture(root):
    (root/'results').mkdir()
    for name in FILES:
        (root/'results'/name).write_bytes((ROOT/'results'/name).read_bytes())


class ConcurrencyTests(unittest.TestCase):
    def test_complete_matrix_and_explicit_interference(self):
        rows,meta=read_grid(ROOT)
        self.assertEqual(len(rows),42)
        self.assertEqual(sum(r['measured_requests'] for r in rows),196)
        self.assertEqual(meta['interference']['additional_unattributed_requests'],46)
        self.assertFalse(meta['interference']['clean_scaling_comparison'])
        self.assertTrue(all(r['comparison_status']=='mixed_load_not_isolated_scaling' for r in rows))
        self.assertEqual(rows,json.loads((ROOT/'dataset-concurrency.json').read_text()))
        for name in ('concurrency-methodology.json','concurrency-request-timings-derived.json'):
            text=(ROOT/'results'/name).read_text()
            self.assertNotIn('/home/',text);self.assertNotIn('192.168.',text)

    def test_refuse_false_clean_claim(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);copy_fixture(root)
            file=root/'results/concurrency-methodology.json';meta=json.loads(file.read_text())
            meta['interference']['clean_scaling_comparison']=True;file.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'Clean-scaling'):read_grid(root)

    def test_refuse_missing_point_and_bad_actual_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);copy_fixture(root)
            file=root/'results/glm53-standard-mtp-c1-c2-c4.json';data=json.loads(file.read_text());data['benchmarks'].pop()
            file.write_text(json.dumps(data));mf=root/'results/concurrency-methodology.json';meta=json.loads(mf.read_text())
            meta['raw_results_sha256']=hashlib.sha256(file.read_bytes()).hexdigest();mf.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'grid points'):read_grid(root)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);copy_fixture(root)
            file=root/'results/concurrency-request-timings-derived.json';data=json.loads(file.read_text())
            next(e for e in data['events'] if e['type']=='request_end')['total_tokens']=255
            file.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,'length'):read_grid(root)

    def test_keep_per_stream_and_batch_window_distinct(self):
        rows,_=read_grid(ROOT)
        row=next(r for r in rows if r['context_depth']==32768 and r['concurrency']==4)
        raw=json.loads((ROOT/'results/glm53-standard-mtp-c1-c2-c4.json').read_text())
        point=next(r for r in raw['benchmarks'] if r['context_size']==32768 and r['concurrency']==4)
        self.assertEqual(row['aggregate_decode_window_tps'],point['tg_throughput']['mean'])
        self.assertEqual(row['per_stream_decode_tps'],point['tg_req_throughput']['mean'])
        self.assertLess(row['aggregate_decode_window_tps'],row['per_stream_decode_tps'])


if __name__=='__main__':unittest.main()
