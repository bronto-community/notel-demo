# SPDX-License-Identifier: Apache-2.0
import re
import sys

container, allowlist_path = sys.argv[1], sys.argv[2]
rules = []
for raw in open(allowlist_path):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    name, pattern, _reason = (part.strip() for part in line.split(" :: ", 2))
    if name == container:
        rules.append(re.compile(pattern))

for line in sys.stdin:
    line = line.rstrip("\n")
    if not line:
        continue
    verdict = "ALLOWED" if any(r.search(line) for r in rules) else "DENIED"
    print(f"{verdict} {line}")
