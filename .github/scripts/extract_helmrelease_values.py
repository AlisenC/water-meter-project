"""Extract the HelmRelease's spec.values for standalone `helm lint`/`helm template` runs.

CI has no cluster, so it can't ask Flux to render the HelmRelease -- this pulls
the same values Flux would pass to Helm out of apps/water-meter/release.yaml.
"""

import sys

from ruamel.yaml import YAML

src, dst = sys.argv[1], sys.argv[2]

yaml = YAML()
with open(src) as f:
    data = yaml.load(f)

with open(dst, "w") as f:
    yaml.dump(data["spec"]["values"], f)
