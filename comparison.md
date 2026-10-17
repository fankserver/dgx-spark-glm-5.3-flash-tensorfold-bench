# Matched-depth comparison

Generated from the frozen reports. Arithmetic means of two measured runs; pp512/tg256, concurrency1.
**GLM uses two nodes; historical Qwen and Laguna use one.** These are different models,
quantization, draft methods, dates and software—not an engine-only or per-GPU A/B test.

This is the original single-stream study. The later [c1/c2/c4 matrix](concurrency.md)
is separate and includes additional traffic; do not combine its samples with this baseline.

GLM: standard EXL3/native MTP/TensorFold TP2 (2026-10-17). Historical references:
Qwen3.5 C_bf16_n4 (DFlash4), Laguna-S-2.1 C_dflash_n3 (DFlash3).
The bf16 filename labels Qwen KV, not full-BF16 model weights.
Raw reference files, pinned source commits and hashes are in [reference provenance](results/reference-provenance.json).

## Decode throughput

| Context depth | GLM TP2 tok/s | Qwen TP1 tok/s | Laguna TP1 tok/s |
|---:|---:|---:|---:|
| 0 | 53.58 | 41.00 | 25.45 |
| 512 | 49.61 | 29.38 | 24.61 |
| 1,024 | 49.64 | 34.03 | 23.26 |
| 2,048 | 45.88 | 28.92 | 23.65 |
| 3,072 | 49.28 | 28.12 | 23.00 |
| 4,096 | 44.02 | 27.69 | 24.71 |
| 6,144 | 45.70 | 27.42 | 22.36 |
| 8,192 | 47.83 | 25.87 | 22.97 |
| 12,288 | 49.56 | 24.21 | 25.29 |
| 16,384 | 55.13 | 25.21 | 22.22 |
| 24,576 | 50.10 | 24.55 | 32.59 |
| 32,768 | 48.55 | 22.17 | 21.12 |
| 49,152 | 48.90 | 19.49 | 23.78 |
| 65,536 | 53.02 | 15.30 | 21.21 |

## End-to-end first-token latency

Seconds. GLM first token includes reasoning or content; not necessarily visible final-answer text.
Total input is context depth +512. No claim of identical historical tokenizer/corpus bytes.

| Context depth | GLM TP2 seconds | Qwen TP1 seconds | Laguna TP1 seconds |
|---:|---:|---:|---:|
| 0 | 0.89 | 0.65 | 0.43 |
| 512 | 1.15 | 1.16 | 0.55 |
| 1,024 | 1.38 | 1.63 | 0.68 |
| 2,048 | 1.92 | 2.70 | 1.14 |
| 3,072 | 2.85 | 3.69 | 1.40 |
| 4,096 | 3.59 | 4.80 | 1.88 |
| 6,144 | 4.75 | 6.54 | 2.62 |
| 8,192 | 5.98 | 8.29 | 3.38 |
| 12,288 | 8.40 | 12.67 | 4.93 |
| 16,384 | 10.80 | 17.40 | 6.57 |
| 24,576 | 15.68 | 26.57 | 10.00 |
| 32,768 | 20.65 | 36.96 | 13.63 |
| 49,152 | 30.53 | 61.34 | 21.84 |
| 65,536 | 40.86 | 88.65 | 31.16 |

## What the GLM run establishes

- All 14 requested points and 28 measured requests completed; each generated exactly256 tokens.
- Fresh-prefix TTFT grows with input length; decode means remain44–55tok/s.
- Native cached-token delta was0. Benchy samples random book starts; this is not a conversation-reuse test.
- Server cache stayed enabled. The false prefix flag in the report describes client context-load mode only.
- Existing service and cache state retained; no restart or tuning. No observed competing request.
- No concurrent sweep, 1M test, quality/per-GPU/cost ranking or diagnosis of a particular slow agent turn.

See [methodology](results/methodology.json), [GLM raw results](results/glm53-standard-mtp-c1.json)
and [datasets](dataset.csv) for exact values, scope and provenance.
