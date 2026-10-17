#!/usr/bin/env python3
"""Run only the benchmark client against an already-running, explicitly supplied endpoint.
No model download, deployment, restart, cache flush, clock change or server configuration.
"""
import argparse
import os
from pathlib import Path
import runpy
import sys
from urllib.parse import urlsplit

DEPTHS = [0,512,1024,2048,3072,4096,6144,8192,12288,16384,24576,32768,49152,65536]
MODEL = 'Mia-AiLab/GLM-5.3-Flash-EXL3-4bpw-TensorFold'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url',required=True,help='Existing OpenAI-compatible /v1 endpoint')
    parser.add_argument('--tokenizer',required=True,help='Exact checkpoint tokenizer directory or tokenizer.json')
    parser.add_argument('--api-key-file',type=Path,help='Private key file; alternatively OPENAI_API_KEY')
    parser.add_argument('--served-model',default='spark')
    parser.add_argument('--concurrency',type=int,nargs='+',choices=(1,2,4),default=[1],
                        help='Client concurrency levels; default preserves the published single-stream baseline')
    parser.add_argument('--output',type=Path,required=True,help='New report path; do not overwrite frozen published results')
    args=parser.parse_args()
    url=urlsplit(args.base_url)
    if url.scheme not in ('http','https') or url.username or url.password or url.query:
        parser.error('Use a credential-free HTTP(S) endpoint; pass credentials via file/environment')
    if args.output.exists():
        parser.error('Choose a new output file; existing reports are immutable')
    import llama_benchy
    from llama_benchy.corpus import LightweightTokenizer
    if llama_benchy.__version__ != '0.4.0':
        parser.error('This historical comparison requires llama-benchy0.4.0; source hashes are in methodology.json')
    LightweightTokenizer.from_pretrained(args.tokenizer)
    key=args.api_key_file.read_text().strip() if args.api_key_file else os.environ.get('OPENAI_API_KEY','EMPTY')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # Secret enters Python memory only, never the OS command line or stored command examples.
    sys.argv=['llama-benchy','--base-url',args.base_url.rstrip('/'),'--model',MODEL,
              '--served-model-name',args.served_model,'--tokenizer',args.tokenizer,
              '--depth',*[str(n) for n in DEPTHS],'--pp','512','--tg','256','--exact-tg',
              '--runs','2','--latency-mode','generation','--concurrency',*[str(n) for n in args.concurrency],
              '--format','json','--save-result',str(args.output),
              '--emit-progress',str(args.output.with_suffix('.progress.jsonl')),'--exit-on-first-fail',
              '--api-key',key]
    runpy.run_module('llama_benchy',run_name='__main__')


if __name__ == '__main__':
    main()
