# notel verification: last run

- Date: 2026-10-01
- Upstream sha: `650354ba` ([chore] profiling: Update firepit to v0.2.0 (#4055))
- notel HEAD: `fb406c83` (branch `sync/650354ba`)
- Compose: `compose.yaml compose.full.yaml compose.extras.yaml compose.agent.yaml notel/verify/compose.canary.yaml`, `--env-file .env --env-file .env.override`
- Host port 8080 was taken by an unrelated container, so the run used `ENVOY_PORT=8081` set in the shell. No files were changed.
- Browser (Playwright) traffic: on (`LOCUST_BROWSER_TRAFFIC_ENABLED=true` is set in compose.yaml).
- Load: 12:33 to 12:47 CEST, silence sidecars attached from 12:34:15 (more than 10 minutes).

## Results

| Step | Result |
| --- | --- |
| 1. Static checks | PASS. Residual scan exits with 0, every allowlist entry has a reason, all seven compose file combinations pass `config -q`, and no direct observability dependencies were found (OTel appears only as indirect Go modules via flagd and as `opentelemetry-api` via fastmcp-slim in agent and mcp) |
| 2. Build | PASS. Prebuilt images were used. Only `frontend-tests` was missing, and it was built |
| 3. Run and silence check | FAIL. flagd makes OTLP connection attempts (see below) |
| 4. Functional | PASS, except Cypress. Checkout went through the API: order `b61d2c0c-bd83-11f1-ac68-6a9db88c814b` appears in the checkout, payment, accounting, email and fraud-detection logs, and the confirmation page renders. `/feature` and `/loadgen` load. No container restarts or OOM kills. All services write stdout logs. Toggling `paymentFailure` to 100% produced "Payment request failed. Invalid token" in payment and "Checkout payment declined" in frontend. The flag was then switched off and the flag file restored byte for byte |
| 4. Cypress | FAIL: 5 of 9 failed (4 of 9 with `baseUrl` set to frontend-proxy). Not caused by notel: none of the specs or the code they test differ from upstream (details below) |
| 5. Silence report | FAIL: flagd only. Log grep: the only hits are `opentelemetry-demo-logo.png` (branding) |
| 6. Image scan | PASS. Three new dormant cases need review |
| 7. Tear down | PASS |

## Silence report

```text
== flagd ==
10:34:10.654540 lo In IP 127.0.0.1.60410 > 127.0.0.1.4318: Flags [S] ...
... 163 SYNs to 127.0.0.1:4318, one every ~5 s, for the whole run
```

The canary recorded zero hits. A positive control (load-generator to `otel-collector:4318`) showed up in both the canary and the sidecar.

## Open issues

1. **flagd is not silent** (it contradicts the "Known dormant cases" entry in DECISIONS). With
   `OTEL_EXPORTER_OTLP_ENDPOINT` removed, `ghcr.io/open-feature/flagd:v0.16.0`
   falls back to `https://localhost:4318`: it sends a TLS ClientHello, about once every 5 s while flags are being
   evaluated. A standalone probe gave 7 SYNs in 32 s under OFREP load. Neither `OTEL_SDK_DISABLED=true` nor
   `OTEL_{TRACES,METRICS,LOGS}_EXPORTER=none` stops it, even though `--help` says traces are not
   exported without `--otel-collector-uri`. Needs a maintainer decision.
2. Cypress failures (upstream issues, not notel):
   - `compose.tests.yaml` sets `baseUrl=http://frontend:8080`, which skips frontend-proxy, so
     `/feature/api/*`, `/images` and `/flagservice` return 404.
   - `Checkout.cy.ts` looks for `[data-cy=checkout-item]`, but the confirmation page doesn't render
     `CheckoutItem`.
   - `CheckoutPaymentFailure` "generic 500": the request races the flag reload. The flag takes effect after about 2 s.
   - `Home` "corrupted session": the spec calls `SessionGateway.getSession()` before
     the visit, so it compares against a different uuid.
   - `ProductDetail` "picture missing": the picture still renders. The code is identical to upstream.
3. The SLF4J "No SLF4J providers" warning predates notel: upstream `3.1.0-ad` prints it too.
4. Silence tooling gap: the sidecars attach only after `up -d`, so the first ~60 s of startup
   are not captured, and neither is the `frontend-tests` container.

## New dormant cases (need maintainer review)

- agent: `langsmith` (via langchain-core) ships `langsmith/integrations/otel` and its own
  tracing. Inactive unless `LANGSMITH_TRACING` or `LANGSMITH_OTEL_ENABLED` is set (neither is). Its target
  (api.smith.langchain.com:443) is not covered by the silence ports.
- load-generator: `locust/opentelemetry.py` (Locust 2.44 has a built-in `--otel`). Inert because no OTel SDK
  is installed.
- frontend-tests image: the Cypress binary bundles the OTel SDK and the OTLP/HTTP exporter (both 16.0.0 from
  the base image and 16.1.0 from npm). Used only for tests.

Known cases confirmed: the Go flagd provider (otel, auto/sdk, otelconnect), the Java flagd provider
(opentelemetry-api/context/common in ad and fraud-detection), fastmcp in agent and mcp, Next.js vendored
`@opentelemetry/api`, the KIP-714 `opentelemetry-proto` in kafka and in fraud-detection's shaded kafka-clients.

## Memory

The peak demo total was about 2.1 GiB (15 samples). The highest services were load-generator at 538 MiB and kafka at 444 of 620 MiB.
checkout and product-catalog peaked at 18.8 and 18.6 of 20 MiB. That's the same limit as upstream, with GOMEMLIMIT set to 16MiB.

## Follow-up silence re-run, 2026-10-01 13:18-13:25 CEST

After the maintainer accepted flagd as non-silent (BREAKING.md #23), the
check was re-run with `notel/verify/silence-allowlist.txt`. It used the same
compose files, `ENVOY_PORT=8081`, and 5 minutes of load with sidecars
attached to every demo container.

- Every container was Up for the whole run.
- The report showed `flagd (allowlisted: 60 attempts)` and **SILENT** (exit 0).
- The positive control was not executed in this re-run, because the
  frontend image has no shell. The control from the main run above
  (load-generator -> `otel-collector:4318`) was recorded by both the canary
  and the sidecar. The skill now uses load-generator for the control.
- `silence_check.sh` was hardened: `report` exits with 3 ("NOT VERIFIED")
  when no sidecars or canary are running. A first re-run attempt failed to
  start the stack, and it had wrongly printed SILENT.
