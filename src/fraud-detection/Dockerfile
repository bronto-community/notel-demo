# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0


FROM --platform=${BUILDPLATFORM} docker.io/library/gradle:9.8.0-jdk17@sha256:e5c0087b1bfc5da783fb514f78a7944d605bfbcd789fa644d0cd1c111d40572c AS builder

WORKDIR /usr/src/app/

COPY ./src/fraud-detection/ ./
COPY ./pb/ ./src/main/proto/

RUN gradle shadowJar

# -----------------------------------------------------------------------------

FROM gcr.io/distroless/java17-debian12:nonroot@sha256:06484c2a9dcc9070aeafbc0fe752cb9f73bc0cea5c311f6a516e9010061998ad

WORKDIR /usr/src/app/

ENV JAVA_TOOL_OPTIONS="-Xmx180m"

COPY --from=builder /usr/src/app/build/libs/fraud-detection-1.0-all.jar fraud-detection-1.0-all.jar

ENTRYPOINT [ "java", "-jar", "fraud-detection-1.0-all.jar" ]
