#!/usr/bin/env python3
"""Validate and publish observed concurrency data; never run inference."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

from aggregate_and_plot import DEPTHS, write_checksums

LEVELS=[1,2,4]


def read_grid(root):
    raw=root/'results/glm53-standard-mtp-c1-c2-c4.json'
    report=json.loads(raw.read_text())
    meta=json.loads((root/'results/concurrency-methodology.json').read_text())
    timing=json.loads((root/'results/concurrency-request-timings-derived.json').read_text())['events']
    if hashlib.sha256(raw.read_bytes()).hexdigest()!=meta['raw_results_sha256']:
        raise ValueError('Raw result SHA mismatch')
    if report['version']!='0.4.0' or report['max_concurrency']!=4 or report['latency_mode']!='generation':
        raise ValueError('Different client/latency/concurrency configuration')
    params=meta['parameters']
    if (report['model']!=meta['model']['repository'] or params['depths']!=DEPTHS
        or params['concurrencies']!=LEVELS or (params['pp'],params['tg'],params['runs'])!=(512,256,2)):
        raise ValueError('Methodology disagrees with requested model/grid')
    entries=report['benchmarks']
    pairs=[(x['context_size'],x['concurrency']) for x in entries]
    if len(pairs)!=42 or set(pairs)!={(d,c) for d in DEPTHS for c in LEVELS}:
        raise ValueError('Missing, duplicate or different grid points')
    expected=3*len(DEPTHS)*sum(LEVELS)+6
    observed=meta['native_counter_deltas_all_traffic']['requests_total']
    interference=meta['interference']
    if (interference['expected_total_requests']!=expected
        or interference['observed_native_completed_requests']!=observed
        or interference['additional_unattributed_requests']!=observed-expected):
        raise ValueError('Inconsistent traffic accounting')
    if observed!=expected and meta['benchmark_cache_reuse_attributable']:
        raise ValueError('Global cache counts cannot be assigned to this benchmark')
    clean=observed==expected and interference['inflight_above_four_samples']==0
    if interference['clean_scaling_comparison']!=clean:
        raise ValueError('Clean-scaling claim conflicts with observed traffic')
    start_events=[e for e in timing if e['type']=='request_start']
    starts={e['request_id']:e for e in start_events}
    ends=[e for e in timing if e['type']=='request_end']
    first_events=[e for e in timing if e['type']=='request_first_token']
    firsts={e['request_id']:e for e in first_events}
    if len(first_events)!=196 or len(firsts)!=196 or set(firsts)!=set(starts):
        raise ValueError('Missing or duplicate first-token event')
    if len(start_events)!=196 or len(starts)!=196 or len(ends)!=196 or set(starts)!={e['request_id'] for e in ends}:
        raise ValueError('Missing or duplicate measured request')
    for e in ends:
        s=starts[e['request_id']]
        if e['total_tokens']!=256 or e['error'] or e['prompt_tokens']!=s['context_size']+512:
            raise ValueError('Actual input/output length or success mismatch')
    rows=[]
    for x in entries:
        c=x['concurrency'];d=x['context_size']
        if x['prompt_size']!=512 or x['response_size']!=256:
            raise ValueError('Different pp/tg')
        if any(sum(e['context_size']==d and e['concurrency']==c and e['run_index']==i for e in starts.values())!=c for i in (1,2)):
            raise ValueError('Not two measured batches per grid point')
        per=x['tg_req_throughput'];agg=x['tg_throughput'];ttft=x['e2e_ttft']
        if len(agg['values'])!=2 or len(per['values'])!=2*c or len(ttft['values'])!=2*c:
            raise ValueError('Incomplete metric samples')
        for metric in (per,agg,ttft):
            if not all(math.isfinite(v) and v>=0 for v in [metric['mean'],metric['std'],*metric['values']]):
                raise ValueError('Invalid measurement')
        expected_times=sorted(firsts[id]['ttft_s'] for id,s in starts.items() if s['context_size']==d and s['concurrency']==c)
        actual_times=sorted(v/1000 for v in ttft['values'])
        if any(not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9) for a,b in zip(expected_times,actual_times)):
            raise ValueError('TTFT disagrees with original request events')
        rows.append({'context_depth':d,'input_tokens':d+512,'output_tokens':256,'concurrency':c,
            'measured_batches':2,'measured_requests':2*c,
            'ttft_seconds':ttft['mean']/1000,'ttft_std_seconds':ttft['std']/1000,
            'ttft_median_seconds':statistics.median(actual_times),
            'ttft_min_seconds':min(actual_times),'ttft_max_seconds':max(actual_times),
            'per_stream_decode_tps':per['mean'],'per_stream_decode_std_tps':per['std'],
            'aggregate_decode_window_tps':agg['mean'],'aggregate_decode_window_std_tps':agg['std'],
            'comparison_status':'no_extra_completions_observed' if clean else 'mixed_load_not_isolated_scaling'})
    return rows,meta


def write_report(root, rows, meta):
    interference=meta['interference']
    lines=['# Observed concurrency 1 / 2 / 4', '',
        '**Completed matrix, NOT a clean concurrency-scaling comparison.**',
        f"The client accounts for {interference['expected_total_requests']} requests including warmups/probes; native completions increased {interference['observed_native_completed_requests']}.",
        f"There were **{interference['additional_unattributed_requests']} additional/unattributed completions**, and {interference['inflight_above_four_samples']} samples with more than four in flight.",
        'The source of additional work is not identified. Do not attribute every delay or rate solely to concurrency.', '',
        'Same 14 depths, pp512/tg256/exactTG, two measured batches at each level:42 grid points and196 requests.',
        'Each input was depth+512 and every measured output exactly256. Service/container unchanged; no restart,',
        'tuning or cache flush. This is a new c1 baseline in the same sweep, not the earlier c1 study reused.', '',
        'Means below use2/4/8 individual requests at c1/c2/c4 respectively. Only two batches per point.', '',
        '## Mean request TTFT (seconds)', '',
        'First reasoning or content token, not necessarily visible final-answer text.',
        '![Observed TTFT](graphs/concurrency-ttft.png)', '']
    lookup={(r['context_depth'],r['concurrency']):r for r in rows}
    for field,title,graph in [('ttft_seconds',None,None),
            ('per_stream_decode_tps','## Mean per-stream decode (tokens/second)','graphs/concurrency-per-stream.png'),
            ('aggregate_decode_window_tps','## Batch decode-window aggregate (tokens/second)','graphs/concurrency-aggregate.png')]:
        if title:
            lines+=['',title,'',f'![{title[3:]}]({graph})','']
        lines+=['| Context depth | c1 | c2 | c4 |','|---:|---:|---:|---:|']
        for d in DEPTHS:
            lines.append(f"| {d:,} | "+' | '.join(f"{lookup[d,c][field]:.2f}" for c in LEVELS)+' |')
    lines+=['','## Interpretation', '',
        '- Per-stream rate excludes its own prefill but includes pauses while other work runs. Aggregate spans',
        '  the batch\'s first token to its last token;',
        '  staggered prefill/admission can fall inside that window. It is not concurrency times mean per-stream TPS.',
        '- Do not infer a clean speedup/efficiency curve or a tuning recommendation from this mixed-load run.',
        '- Global cache deltas include extra traffic; the benchmark\'s own cache reuse cannot be assigned.',
        '- Client/tokenizer/corpus-file hashes match the first study, but reported corpus-token count differs',
        '  (141280 versus143040). Download-versus-cache text loading can normalize line endings. All levels here',
        '  use one loaded corpus; random input strings are not identical across runs.',
        '- Four native decoding lanes were observed. That does not prove every point had four simultaneously decoding.',
        '- Sampled available memory minimum6.56GiB head/10.92GiB worker, swap0; not an8GiB-floor safety pass.',
        '- No per-turn cache diagnosis, quality test, long-context/soak or cold-host-boot qualification.', '',
        '[Raw report](results/glm53-standard-mtp-c1-c2-c4.json) · [Methodology](results/concurrency-methodology.json) ·',
        '[CSV](dataset-concurrency.csv) · [JSON](dataset-concurrency.json). Original single-stream reports remain unchanged.', '']
    (root/'concurrency.md').write_text('\n'.join(lines))


def build(root):
    rows,meta=read_grid(root)
    (root/'dataset-concurrency.json').write_text(json.dumps(rows,indent=2)+'\n')
    with (root/'dataset-concurrency.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    for field,label,name in [('ttft_seconds','Mean request TTFT (seconds)','ttft'),
        ('per_stream_decode_tps','Mean per-stream decode (tokens/second)','per-stream'),
        ('aggregate_decode_window_tps','Batch decode-window aggregate (tokens/second)','aggregate')]:
        fig,ax=plt.subplots(figsize=(10,6.2));fig.subplots_adjust(left=.11,right=.97,bottom=.20,top=.80)
        for c,color in zip(LEVELS,('#2465a7','#b75b00','#654399')):
            points=[r for r in rows if r['concurrency']==c]
            ax.plot([r['context_depth'] for r in points],[r[field] for r in points],'o-',color=color,label=f'c{c}')
        fig.suptitle('GLM native MTP · observed concurrency 1 / 2 / 4',y=.97,fontsize=14)
        ax.set_title('Extra/unattributed requests present — NOT isolated scaling',fontsize=10,color='#973d2c',pad=16)
        ax.set(xlabel='Context depth (tokens; total input = depth + 512)',ylabel=label)
        ax.set_ylim(bottom=0);ax.grid(alpha=.25);ax.legend()
        footer=fig.text(.5,.025,'Means · 2 batches/point · n=2/4/8 requests at c1/c2/c4 · 256 output tokens · 2026-10-17',ha='center',fontsize=8)
        fig.canvas.draw();renderer=fig.canvas.get_renderer()
        if footer.get_window_extent(renderer).overlaps(ax.xaxis.label.get_window_extent(renderer)):
            raise ValueError('Footer overlaps x-axis label')
        fig.savefig(root/f'graphs/concurrency-{name}.png',dpi=160);plt.close(fig)
    write_report(root,rows,meta)
    write_checksums(root)
    return rows


if __name__=='__main__':build(Path(__file__).resolve().parents[1])
