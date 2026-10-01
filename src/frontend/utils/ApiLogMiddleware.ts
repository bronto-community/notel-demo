// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

import { NextApiHandler } from 'next';
import logger from './logger';

const ApiLogMiddleware = (handler: NextApiHandler): NextApiHandler => {
  return async (request, response) => {
    const urlPath = request.url?.split('?', 1)[0];

    try {
      await handler(request, response);
      logger.info(
        {
          'http.request.method': request.method,
          'url.path': urlPath,
          'http.response.status_code': response.statusCode,
        },
        'API request completed'
      );
    } catch (error) {
      logger.error(
        {
          err: error,
          'http.request.method': request.method,
          'url.path': urlPath,
          'http.response.status_code': 500,
        },
        'API request failed'
      );
      throw error;
    }
  };
};

export default ApiLogMiddleware;
