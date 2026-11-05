# Bundled model workspace

Place the original industry-rotation model at:

```text
models/sw_rotation_model/
  run.py
  config.json
  data/
    ths_industry_info.csv
    ths_industry_daily.csv
    benchmark_csi300.csv
  outputs/
```

The model code, parameters, training history, and scoring outputs are not part
of this repository. `fetch_rotation.py` reads `ROTATION_MODEL_DIR` first, then
this package-relative directory. On Windows it also recognizes the historical
development path, but never scans another drive.

Do not derive model outputs from a cached `rotation_today.json`. Cloud runs
require the original inputs so the model can be refreshed and recomputed for
the requested session.
