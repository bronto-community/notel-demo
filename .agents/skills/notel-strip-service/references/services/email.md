# email (Ruby)

## Observability removed

- `email_server.rb`: the 7 `opentelemetry*` requires, `OpenTelemetry::SDK.configure`
  with the Sinatra instrumentation, the OTel logger (`$logger`) and its
  `on_emit` call (`email.confirmation_sent`), the OTLP metric exporter and the
  `demo.notification.confirmations` counter, the `demo.order.id` attributes on
  the current span and the manual span, `record_exception` in the `error`
  block, and the `tracer.in_span("send_email")` wrapper (unwrapped and
  dedented).
- `Gemfile`: the 8 `opentelemetry-*` gems (sdk, common, logs-sdk,
  metrics-sdk, exporter-otlp, exporter-otlp-metrics, exporter-otlp-logs,
  instrumentation-all).
- `Gemfile.lock`: regenerated with `bundle lock` in
  `ruby:4.0.5-alpine3.22`. The result is deletions only.

## Behavior-preserving replacements

- `error do "" end` (BREAKING.md #15). With `APP_ENV=production`, the error
  block's return value becomes the response body. Upstream returned the span
  from `record_exception`, which Sinatra ignores, so the 500 body was empty
  (`content-length: 0`). Without an error block, Sinatra would return
  `<h1>Internal Server Error</h1>` instead. The explicit `""` keeps the body
  empty. Checked against the upstream image.
- The success response is still empty, because `send_email` still returns
  the value of `puts` (nil).
- No new logger. The existing `puts "Order confirmation email sent for order
  ..."` already covers the `email.confirmation_sent` log record, so only the
  OTel copy went away.

## Traps

- `bundle lock` with the image's bundler rewrites `BUNDLED WITH` from 2.6.7 to
  4.0.10. Restore `2.6.7` (three spaces) so the lockfile diff stays
  deletions only.
- `googleapis-common-protos-types` and `logger` stay in the lock because grpc
  (through the flagd provider), mail, sinatra and rack-protection need them.
  Keep `google-protobuf`.
- `JSON` still resolves without the OTel gems, since Sinatra and the flagd
  provider load it.
- Use `docker build --load` with the docker-container buildx driver.
  Otherwise the image is not loaded and cannot be run.

## Dormant transitive OTel

- none (`gem list` in the image has no opentelemetry gems)

## Verify

- `docker build --load -t notel-test/email -f src/email/Dockerfile .`
- `docker run -e APP_ENV=production -e EMAIL_PORT=6060 -p 16061:6060 notel-test/email`, then:
  - invalid JSON POST to `/send_order_confirmation` returns 500 with
    `content-length: 0`;
  - a full order JSON returns 200 with an empty body and the log line
    `Order confirmation email sent for order <id>`.
- `docker exec <c> gem list | grep -i opentelemetry` prints nothing.
