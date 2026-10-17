# Contributing

Keep original executed reports immutable. Add new runs under new filenames and state their model,
source pins, hardware count, cache mode, concurrency, actual input/output lengths and limitations.
Never commit keys, private endpoints/configuration or raw generated text. Model weights do not belong here.

Generate data/graphs offline with `python scripts/aggregate_and_plot.py`; run
`python -m unittest discover -s scripts -p 'test_*.py' -v` and `sha256sum -c SHA256SUMS`.
Review plots against the numeric tables. Changing scripts must not silently alter frozen raw reports.
Updating datasets is not permission to run inference or change a deployment.

Publishing this public repository adds no paid infrastructure. Future benchmark runs consume the
operator's existing hardware; do not claim an electricity cost without its actual tariff and power data.
