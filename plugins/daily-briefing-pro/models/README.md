# Local model workspace

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

This directory is gitignored and is not part of the marketplace package. Place
a refreshed or custom model here when explicitly provisioning an environment;
`fetch_rotation.py` reads `ROTATION_MODEL_DIR` first, then this
package-relative directory. It does not scan arbitrary drives or desktop paths.

Cloud and clean installs do not need this directory: they extract the shipped
`skills/daily-briefing-pro/data/cloud-baseline/models/sw_rotation_model.zip`
into a writable model cache. An explicit model here always wins over the
archive. See `RECONSTRUCTED.md` in the extracted model for the rebuild and
regression notes.

Do not derive model outputs from a cached `rotation_today.json`. Cloud runs
require the original inputs so the model can be refreshed and recomputed for
the requested session.
