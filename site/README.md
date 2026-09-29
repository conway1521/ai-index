# site

The published page. `data/readings.json` is written by `python -m aiindex.build`
from the tables in `aiindex/output/tables`, so the page shows only numbers
the build produced. `index.html` is the page, and carries a copy of the
readings so that it opens without a server. The Pages workflow publishes this
folder with the tables and checks beside it under `data/`.
