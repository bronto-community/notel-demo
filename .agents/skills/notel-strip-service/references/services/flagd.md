# flagd (flag definitions, JSON)

## Observability removed
- demo.flagd.json: the `emitRawPii` flag (DECISIONS, Flags). It was the only
  flag with `metadata.schedulable: false`.

## Behavior-preserving replacements
- none. The 17 other flags, including all failure-scenario flags, are
  unchanged.

## Traps
- Remove the block textually to keep the file's formatting; validate with
  `json.load` afterwards.
- flagd-ui's scheduler test used `emitRawPii` to cover `metadata.schedulable`;
  update it together (see flagd-ui.md).
- The flagd image itself is configured in compose (infra script), not here.

## Dormant transitive OTel
- `ghcr.io/open-feature/flagd` image (known dormant case in DECISIONS).

## Verify
- `python3 -c "import json;d=json.load(open('src/flagd/demo.flagd.json'));assert 'emitRawPii' not in d['flags']"`
- flagd-ui image build (its test stage loads this file).
