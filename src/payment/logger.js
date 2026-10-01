// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

const pino = require('pino')

const logger = pino({
  mixin() {
    return {
      'service.name': 'payment',
    }
  },
  formatters: {
    level: (label) => {
      return { 'level': label };
    },
  },
});

module.exports = logger;
