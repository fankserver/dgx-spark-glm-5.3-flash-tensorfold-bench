#!/usr/bin/env python3
"""Build datasets and plots from frozen reports; never contact an inference service."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

DEPTHS = [0,512,1024,2048,3072,4096,6144,8192,12288,16384,24576,32768,49152,65536]


def read_points(path):
    report = json.loads(Path(path).read_text())
    if report['version'] != '0.4.0' or report['max_concurrency'] != 1:
        raise ValueError('Expected benchy0.4.0 single-stream report')
    if report['latency_mode'] != 'generation':
        raise ValueError('Different latency method')
    if [p['context_size'] for p in report['benchmarks']] != DEPTHS:
        raise ValueError('Incomplete or different depth set')
    rows = []
    for p in report['benchmarks']:
        if (p['prompt_size'], p['response_size'], p['concurrency']) != (512,256,1):
            raise ValueError('Different pp/tg/concurrency')
        tg, ttft = p['tg_throughput'], p['e2e_ttft']
        if len(tg['values']) != 2 or len(ttft['values']) != 2:
            raise ValueError('Expected two measured samples')
        numbers = [tg['mean'],tg['std'],ttft['mean'],ttft['std'],*tg['values'],*ttft['values']]
        if not all(math.isfinite(x) and x >= 0 for x in numbers):
            raise ValueError('Invalid numeric measurement')
        rows.append({'config':'glm53-standard-native-mtp-c1','context_depth':p['context_size'],
                     'input_tokens':p['context_size']+512,'output_tokens':256,'concurrency':1,'runs':2,
                     'ttft_seconds':ttft['mean']/1000,'ttft_std_seconds':ttft['std']/1000,
                     'decode_tps':tg['mean'],'decode_std_tps':tg['std']})
    return rows


def write_comparison(root, rows):
    qwen=read_points(root/'results/references/qwen35-dflash4.json')
    laguna=read_points(root/'results/references/laguna-s21-dflash3.json')
    text=['# Matched-depth comparison', '',
          'Generated from the frozen reports. Arithmetic means of two measured runs; pp512/tg256, concurrency1.',
          '**GLM uses two nodes; historical Qwen and Laguna use one.** These are different models,',
          'quantization, draft methods, dates and software—not an engine-only or per-GPU A/B test.', '',
          'GLM: standard EXL3/native MTP/TensorFold TP2 (2026-10-17). Historical references:',
          'Qwen3.5 C_bf16_n4 (DFlash4), Laguna-S-2.1 C_dflash_n3 (DFlash3).',
          'The bf16 filename labels Qwen KV, not full-BF16 model weights.',
          'Raw reference files, pinned source commits and hashes are in [reference provenance](results/reference-provenance.json).', '',
          '## Decode throughput', '',
          '| Context depth | GLM TP2 tok/s | Qwen TP1 tok/s | Laguna TP1 tok/s |',
          '|---:|---:|---:|---:|']
    for a,b,c in zip(rows,qwen,laguna):
        text.append(f"| {a['context_depth']:,} | {a['decode_tps']:.2f} | {b['decode_tps']:.2f} | {c['decode_tps']:.2f} |")
    text+=['', '## End-to-end first-token latency', '',
           'Seconds. GLM first token includes reasoning or content; not necessarily visible final-answer text.',
           'Total input is context depth +512. No claim of identical historical tokenizer/corpus bytes.', '',
           '| Context depth | GLM TP2 seconds | Qwen TP1 seconds | Laguna TP1 seconds |',
           '|---:|---:|---:|---:|']
    for a,b,c in zip(rows,qwen,laguna):
        text.append(f"| {a['context_depth']:,} | {a['ttft_seconds']:.2f} | {b['ttft_seconds']:.2f} | {c['ttft_seconds']:.2f} |")
    text+=['', '## What the GLM run establishes', '',
           '- All 14 requested points and 28 measured requests completed; each generated exactly256 tokens.',
           '- Fresh-prefix TTFT grows with input length; decode means remain44–55tok/s.',
           '- Native cached-token delta was0. Benchy samples random book starts; this is not a conversation-reuse test.',
           '- Server cache stayed enabled. The false prefix flag in the report describes client context-load mode only.',
           '- Existing service and cache state retained; no restart or tuning. No observed competing request.',
           '- No concurrent sweep, 1M test, quality/per-GPU/cost ranking or diagnosis of a particular slow agent turn.', '',
           'See [methodology](results/methodology.json), [GLM raw results](results/glm53-standard-mtp-c1.json)',
           'and [datasets](dataset.csv) for exact values, scope and provenance.', '']
    (root/'comparison.md').write_text('\n'.join(text))


def build(root, plots=True):
    rows = read_points(root/'results/glm53-standard-mtp-c1.json')
    (root/'dataset.json').write_text(json.dumps(rows,indent=2)+'\n')
    with (root/'dataset.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    write_comparison(root,rows)
    if plots:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        root.joinpath('graphs').mkdir(exist_ok=True)
        for field, std, label, name in (
                ('ttft_seconds','ttft_std_seconds','First reasoning/content token (seconds)','ttft'),
                ('decode_tps','decode_std_tps','Decode throughput (tokens/second)','decode')):
            fig,ax=plt.subplots(figsize=(10,5.8))
            fig.subplots_adjust(left=.10,right=.97,bottom=.20,top=.90)
            ax.errorbar([x['context_depth'] for x in rows],[x[field] for x in rows],
                        yerr=[x[std] for x in rows],fmt='o-',color='#2465a7',capsize=3,label='GLM native MTP · TP2 / 2 GB10 nodes')
            ax.set(xlabel='Context depth (tokens; total input = depth + 512)',ylabel=label,
                   title='GLM-5.3-Flash / TensorFold — single-stream, fresh prefixes')
            ax.set_ylim(bottom=0);ax.grid(alpha=.25);ax.legend(loc='best')
            footer=fig.text(.5,.025,'Mean ± standard deviation, n=2 · 256 output tokens · 2026-10-17 · not a cache-hit test',ha='center',fontsize=8)
            fig.canvas.draw()
            renderer=fig.canvas.get_renderer()
            if footer.get_window_extent(renderer).overlaps(ax.xaxis.label.get_window_extent(renderer)):
                raise ValueError('Plot footer overlaps x-axis label')
            fig.savefig(root/f'graphs/{name}.png',dpi=160);plt.close(fig)
    files=[root/'results/glm53-standard-mtp-c1.json',root/'results/methodology.json',
           root/'results/reference-provenance.json',root/'dataset.csv',root/'dataset.json',
           *sorted(root.glob('results/references/*.json')),*sorted(root.glob('graphs/*.png'))]
    (root/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(root))+'\n' for p in files))
    return rows


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-plots',action='store_true',help='Only rebuild numeric datasets/checksums')
    args=parser.parse_args()
    build(Path(__file__).resolve().parents[1],plots=not args.no_plots)
