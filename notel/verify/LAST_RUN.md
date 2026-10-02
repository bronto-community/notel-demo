# notel verification: last run

- Date: 2026-10-02
- Upstream sha: `7ea09b86` (chore(deps): bump the src-frontend group across 1 directory with 2 updates (#4056))
- notel HEAD: `ac7ecc77` (branch `sync/7ea09b86`, 23 notel commits on top of upstream)
- Compose: `compose.yaml compose.full.yaml compose.extras.yaml compose.agent.yaml notel/verify/compose.canary.yaml`, `--env-file .env --env-file .env.override`
- Images were built and run with `DEMO_VERSION=sync` (tags `sync-<svc>`), so the `latest-*` images were not touched.
- Host port 8080 was taken, so the run used `ENVOY_PORT=8081` set in the shell. No files were changed.
- Browser (Playwright) traffic: on (the default).
- Stack up at 16:10:57 CEST. Silence sidecars were attached at 16:12:10 and the first report ran at 16:25:24, which gives 13 minutes of load.

## Results

| Step | Result |
| --- | --- |
| 1. Static checks | PASS. `check_residuals.py --show-unused` reports no unallowed residuals (exit 0). `strip_infra.py --check`: 0 pending deletions or edits. All eight compose file combinations pass `config -q`. `check_render.sh` prints CLEAN (chart 0.42.1). `gen_helm_values.py --check` exits with 0 (python:3.13-alpine). markdownlint passes on the 42 changed markdown files. Manifests have no direct observability dependencies (`opentelemetry-api` appears only via fastmcp-slim in agent and mcp) |
| 2. Build | PASS. All 21 service images and `frontend-tests` built. Two parallel `compose build` attempts failed on network TLS handshake timeouts (the Gradle download in ad, then `proxy.golang.org` in checkout and product-catalog). A serial per-service build passed on the first attempt for every service |
| 3. Stop main stack | PASS (`down` without `-v`) |
| 4. Run and smoke test | PASS. `/`, `/api/products`, `/feature/`, `/loadgen/` and `/chatbot/` return 200, and the storefront title is "Notel Demo - Home". API checkout order `5c8ce6ae-be6b-11f1-a085-4e6199b0a3e7` appears in the checkout, accounting, email and fraud-detection logs. The payment log shows the matching charge (USD 221.89, card ending 0454). The confirmation page renders "Your order is complete" when it gets the `order` query, as the UI passes it. All 24 containers stayed up with no restarts and no OOM kills. Locust: 881 requests, 7 failures (see open issues) |
| 4. paymentFailure | PASS. With the flag at 100%, checkout returned 422 `PAYMENT_FAILED`. The payment log shows "Payment request failed. Invalid token", and the frontend log shows "Checkout payment declined". Afterwards the flag was set back to off and the flag file was restored byte for byte (sha1 `dfd6e605`, git clean) |
| 4. Cypress | 5 of 9 failed, the same specs and causes as listed in BREAKING.md: `Checkout` (`data-cy=checkout-item`), `CheckoutPaymentFailure` x2 (`frontend:8080/feature/api/read` 404 in the before/after hooks), `Home` (corrupted session), `ProductDetail` (picture missing) |
| 5. Silence report | PASS. SILENT (exit 0). flagd is allowlisted (161 attempts). The positive control was recorded by both the canary and the load-generator sidecar, and the second report exited with 1 |
| 5. Log grep | PASS. The only hits are the ad install path `opentelemetry-demo-ad` (project naming) and Envoy's startup list of built-in extensions |
| 6. Image scan | PASS. One new dormant case needs review (starlette) |
| 7. Tear down | PASS (`down -v`, sync project only) |
| 8. Kubernetes | Not run. Only the static `check_render.sh` and `gen_helm_values.py --check` were run (step 1) |
| Main stack restore | PASS. 21 `latest-*` containers are up, and `localhost:8081/` returns 200 with "Notel Demo - Home" |

## Silence report

```text
== flagd (allowlisted: 161 attempts) ==
14:12:01.626495 lo    In  IP 127.0.0.1.40706 > 127.0.0.1.4318: Flags [S] ...
SILENT: no unallowlisted telemetry connection attempts recorded
```

After the positive control:

```text
== load-generator ==
14:25:44.172689 eth0  Out IP 172.23.0.25.51792 > 172.23.0.3.4318: Flags [S] ...
14:25:44.174832 lo    In  IP 127.0.0.1.36436 > 127.0.0.1.4318: Flags [S] ...
== notel-canary ==
CANARY_HIT proto=tcp port=4318 peer=('172.23.0.25', 51792)
exit=1
```

## New dormant cases (need maintainer review)

- agent, chatbot and mcp: `starlette` 1.7.0 ships `starlette/middleware/opentelemetry.py`
  (`OpenTelemetryMiddleware`, experimental and opt-in). Nothing in site-packages or the app
  imports it. In chatbot it can't even be imported, because `opentelemetry-api` is absent.
  It is inert.
- recommendation: grpcio's `cygrpc` extension embeds xDS `opentelemetry.proto` descriptors.
  This is the same pattern as the known Alpine `libgrpc` case in currency, and no OTel plugin is installed.

Known cases confirmed: the Go flagd provider (otel, otel/metric, otel/trace, auto/sdk and
otelconnect in checkout and product-catalog), the Java flagd provider (opentelemetry-api,
context and common in ad), fastmcp-slim `opentelemetry-api` in agent and mcp, Next.js vendored
`@opentelemetry/api`, langsmith in agent, Locust `opentelemetry.py`, Cypress in
frontend-tests, Envoy, the KIP-714 protos (the kafka broker jar, fraud-detection's shaded
kafka-clients, and librdkafka in accounting) and currency `libgrpc`. Text-only mentions
(doc URLs in pino, OpenFeature and Monolog; quote's `install-php-extensions` script, with no
OTel PHP extension loaded) are not packages.

## Memory

The demo-only peak was about 3.0 GiB (16:14:41, 30 samples). The peak was 3.4 GiB while the
Cypress container ran. load-generator peaked at 989 of 1500 MiB during the first 3 minutes,
then settled at 360-770 MiB, and kafka reached 494 of 620 MiB. checkout peaked at 20.0 of 20 MiB,
product-catalog at 18.2 of 20 MiB and flagd at 74.9 of 75 MiB. These are upstream's limits and
are kept on purpose (DECISIONS, "Memory limits").

## Open issues

1. Locust recorded 7 failures in 881 requests with all flags off. Five were 504s
   (`response_timeout` after 15 s, 4 on `/api/checkout`, 1 on `/api/recommendations`). Four of
   them came in the first 90 s after startup, when checkout also logged "failed to send order
   confirmation ... context deadline exceeded" to email. The other was at 14:14:52. There was also
   one 503 on `/api/products` (14:15:49) and one agent `/prompt` 500. checkout sits at its 20 MiB
   limit, which matches the known upstream memory-limit issue. Nothing points to a notel change.
2. The agent `/prompt` 500 came from a request with no cassette match. Because of
   `record_mode="new_episodes"` (upstream `patch_vcr.py`, unchanged by notel), that request was
   sent to the real `https://local-llm.com`, which answered 301. This is upstream behavior and not
   telemetry, but it is real outbound traffic.
3. Build: `cache_from` points to `ghcr.io/bronto-community/notel-demo:3.1.0-<svc>`, which answers
   401 without a login. The error doesn't block the build, but it fills the build log. Parallel builds are
   also prone to network timeouts on this machine.
4. The silence tooling gap is unchanged: sidecars attach after `up -d`, and the one-off
   `frontend-tests` container is not covered.
