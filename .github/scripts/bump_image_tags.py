"""Bump the water-meter HelmRelease's backend/frontend image tags in place.

Uses ruamel.yaml (round-trip mode) instead of yq so the file's existing
comments and formatting survive untouched -- yq's in-place edit reformats
comment blocks and adds spurious blank lines throughout the file.
"""

import sys

from ruamel.yaml import YAML

path, tag = sys.argv[1], sys.argv[2]

yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096

with open(path) as f:
    data = yaml.load(f)

image = data["spec"]["values"].setdefault("image", {})
image.setdefault("backend", {})["tag"] = tag
image.setdefault("frontend", {})["tag"] = tag

with open(path, "w") as f:
    yaml.dump(data, f)
