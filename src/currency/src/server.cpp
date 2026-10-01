// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

#include <chrono>
#include <cerrno>
#include <csignal>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <math.h>
#include <pthread.h>
#include <string>
#include <unordered_map>
#include <demo.grpc.pb.h>
#include <grpc/health/v1/health.grpc.pb.h>

#include <grpcpp/grpcpp.h>
#include <grpcpp/server.h>
#include <grpcpp/server_builder.h>
#include <grpcpp/server_context.h>

using namespace std;

using oteldemo::Empty;
using oteldemo::GetSupportedCurrenciesResponse;
using oteldemo::CurrencyConversionRequest;
using oteldemo::Money;

using grpc::Status;
using grpc::ServerContext;
using grpc::ServerBuilder;
using grpc::Server;

namespace
{
  constexpr auto server_shutdown_timeout = std::chrono::seconds(4);

  void logInfo(const std::string& message)
  {
    std::cout << ("INFO: " + message + "\n") << std::flush;
  }

  void logError(const std::string& message)
  {
    std::cerr << ("ERROR: " + message + "\n") << std::flush;
  }

  std::unordered_map<std::string, double> currency_conversion
  {
    {"EUR", 1.0},
    {"USD", 1.1305},
    {"JPY", 126.40},
    {"BGN", 1.9558},
    {"CZK", 25.592},
    {"DKK", 7.4609},
    {"GBP", 0.85970},
    {"HUF", 315.51},
    {"PLN", 4.2996},
    {"RON", 4.7463},
    {"SEK", 10.5375},
    {"CHF", 1.1360},
    {"ISK", 136.80},
    {"NOK", 9.8040},
    {"HRK", 7.4210},
    {"RUB", 74.4208},
    {"TRY", 6.1247},
    {"AUD", 1.6072},
    {"BRL", 4.2682},
    {"CAD", 1.5128},
    {"CNY", 7.5857},
    {"HKD", 8.8743},
    {"IDR", 15999.40},
    {"ILS", 4.0875},
    {"INR", 79.4320},
    {"KRW", 1275.05},
    {"MXN", 21.7999},
    {"MYR", 4.6289},
    {"NZD", 1.6679},
    {"PHP", 59.083},
    {"SGD", 1.5349},
    {"THB", 36.012},
    {"ZAR", 16.0583},
  };

class HealthServer final : public grpc::health::v1::Health::Service
{
  Status Check(
    ServerContext* context,
    const grpc::health::v1::HealthCheckRequest* request,
    grpc::health::v1::HealthCheckResponse* response) override
  {
    response->set_status(grpc::health::v1::HealthCheckResponse::SERVING);
    return Status::OK;
  }
};

class CurrencyService final : public oteldemo::CurrencyService::Service
{
  Status GetSupportedCurrencies(ServerContext* context,
  	const Empty* request,
  	GetSupportedCurrenciesResponse* response) override
  {
    for (auto &code : currency_conversion) {
      response->add_currency_codes(code.first);
    }

    logInfo("GetSupportedCurrencies successful");
  	return Status::OK;
  }

  double getDouble(Money& money) {
    auto units = money.units();
    auto nanos = money.nanos();

    double decimal = 0.0;
    while (nanos != 0) {
      double t = (double)(nanos%10)/10;
      nanos = nanos/10;
      decimal = decimal/10 + t;
    }

    return double(units) + decimal;
  }

  void getUnitsAndNanos(Money& money, double value) {
    long unit = (long)value;
    double rem = value - unit;
    long nano = rem * pow(10, 9);
    money.set_units(unit);
    money.set_nanos(nano);
  }

  Status Convert(ServerContext* context,
  	const CurrencyConversionRequest* request,
  	Money* response) override
  {
    try {
      // Do the conversion work
      Money from = request->from();
      string from_code = from.currency_code();
      double rate = currency_conversion[from_code];
      double one_euro = getDouble(from) / rate ;

      string to_code = request->to_code();
      double to_rate = currency_conversion[to_code];

      double final = one_euro * to_rate;
      getUnitsAndNanos(*response, final);
      response->set_currency_code(to_code);

      logInfo("conversion successful currency.from=" + from_code + " currency.to=" + to_code);
      return Status::OK;

    } catch(...) {
      logError("conversion failure");
      return Status::CANCELLED;
    }
    return Status::OK;
  }
};

bool RunServer(uint16_t port, const sigset_t& shutdown_signals)
{
  std::string ip("0.0.0.0");

  const char* ipv6_enabled = std::getenv("IPV6_ENABLED");

  if (ipv6_enabled != nullptr && std::string(ipv6_enabled) == "true") {
    ip = "[::]";
    logInfo("Overwriting Localhost IP server.address=" + ip);
  }

  std::string address(ip + ":" +  std::to_string(port));

  CurrencyService currencyService;
  HealthServer healthService;
  ServerBuilder builder;

  builder.RegisterService(&currencyService);
  builder.RegisterService(&healthService);
  builder.AddListeningPort(address, grpc::InsecureServerCredentials());

  std::unique_ptr<Server> server(builder.BuildAndStart());
  if (server == nullptr) {
    std::cerr << "Failed to start Currency Server\n";
    return false;
  }

  logInfo("Currency Server started server.address=" + address);

  int received_signal = 0;
  const int signal_error = sigwait(&shutdown_signals, &received_signal);
  if (signal_error != 0) {
    std::cerr << "Failed to wait for shutdown signal: " << std::strerror(signal_error) << "\n";
  } else {
    const char* signal_name = received_signal == SIGTERM ? "SIGTERM" : "SIGINT";
    logInfo(std::string("Received ") + signal_name + ", shutting down Currency Server");
  }

  server->Shutdown(std::chrono::system_clock::now() + server_shutdown_timeout);
  server->Wait();
  return signal_error == 0;
}
}

int main(int argc, char **argv) {

  sigset_t shutdown_signals;
  if (sigemptyset(&shutdown_signals) == -1 ||
      sigaddset(&shutdown_signals, SIGINT) == -1 ||
      sigaddset(&shutdown_signals, SIGTERM) == -1) {
    std::cerr << "Failed to configure shutdown signals: " << std::strerror(errno) << "\n";
    return 1;
  }

  const int signal_mask_error = pthread_sigmask(SIG_BLOCK, &shutdown_signals, nullptr);
  if (signal_mask_error != 0) {
    std::cerr << "Failed to block shutdown signals: " << std::strerror(signal_mask_error) << "\n";
    return 1;
  }

  if (argc < 2) {
    std::cout << "Usage: currency <port>";
    return 0;
  }

  uint16_t port = atoi(argv[1]);

  return RunServer(port, shutdown_signals) ? 0 : 1;
}
