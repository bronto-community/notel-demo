# payment (Node.js)

## Observability removed
- `charge.js`: tracer, meter and the `demo.payment.transactions` counter; the
  `charge` span with its attributes, `recordException`, `setStatus`,
  `error.type` and `span.end`; the `synthetic_request` baggage read and
  `demo.payment.charged`; the `enduser.id` baggage read; the `emitRawPii` flag
  read and the PII span attributes (and the then-unused `cvv` destructure).
  The `try/catch/finally` only served the span, so it was dropped and the body
  was dedented.
- `index.js`: active span lookup, `demo.payment.amount` attribute,
  `setStatus` and `error.type` in the catch. The catch (`logger.warn`,
  `callback(err)`) is kept.
- `package.json`: `@opentelemetry/api`, `@opentelemetry/semantic-conventions`,
  `@opentelemetry/auto-instrumentations-node` (devDependency, so the
  `devDependencies` block is gone), and the `--require` in `start`.
- `package-lock.json`: regenerated with `npm uninstall --package-lock-only`
  in `node:26.4.0-slim` (builder image). No remaining package changed version
  (222 -> 66 entries).
- `Dockerfile`: `otelagent` stage (operator autoinstrumentation image), the
  COPY of `/autoinstrumentation` and `NODE_OPTIONS`.

## Behavior-preserving replacements
- `logger.js` (BREAKING.md #16): the pino mixin hardcodes
  `'service.name': 'payment'` instead of reading `OTEL_SERVICE_NAME`, so the
  log shape is unchanged.
- The `paymentFailure` path still throws the error containing
  `demo.user_context.loyalty_level=gold`. Only the span attribute is gone.
  The `Transaction complete.` log still carries `loyalty_level`.

## Traps
- The Node agent was injected by the Dockerfile (`NODE_OPTIONS`), not by
  `package.json`. Both must go.
- The "Do not charge synthetic requests" branch only set a span attribute. No
  charge logic depended on it.

## Dormant transitive OTel
- none (`npm ls --all | grep -i opentelemetry` is empty, and there is no
  `node_modules/@opentelemetry`).

## Verify
- `docker build -f src/payment/Dockerfile .`
- `docker build --load --target builder -f src/payment/Dockerfile -t pay-b .`
  then `docker run --rm pay-b sh -c 'npm ls --all | grep -i opentelemetry'`
  (expect no output).
- Run the image with `-e PAYMENT_PORT=50051` and check for the
  `payment gRPC server started` log with `"service.name":"payment"`.
- There are no unit tests.
