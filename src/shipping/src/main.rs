// Copyright The OpenTelemetry Authors
// SPDX-License-Identifier: Apache-2.0

use actix_web::{web, App, HttpResponse, HttpServer};
use open_feature::provider::FeatureProvider;
use open_feature_flagd::{FlagdOptions, FlagdProvider};
use std::env;
use std::sync::Arc;
use tracing::info;
use tracing_subscriber::EnvFilter;

mod shipping_service;
use shipping_service::{get_quote, ship_order};

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    tracing_subscriber::fmt()
        .with_writer(std::io::stdout)
        .with_env_filter(EnvFilter::new("info"))
        .init();

    let port: u16 = env::var("SHIPPING_PORT")
        .expect("$SHIPPING_PORT is not set")
        .parse()
        .expect("$SHIPPING_PORT is not a valid port");

    let mut ip = "0.0.0.0".to_string();

    if let Ok(ipv6_enabled) = env::var("IPV6_ENABLED") {
        if ipv6_enabled == "true" {
            ip = "[::]".to_string();
            info!("Overwriting Localhost IP:  {ip}");
        }
    }

    let addr = format!("{}:{}", ip, port);
    info!(
        name: "shipping.server.started",
        addr = addr.as_str(),
        message = "Shipping service is running"
    );

    let provider = FlagdProvider::new(FlagdOptions {
        cache_settings: None,
        ..Default::default()
    })
    .await
    .expect("Failed to initialize flagd provider");

    let flag_provider = web::Data::from(Arc::new(provider) as Arc<dyn FeatureProvider>);

    HttpServer::new(move || {
        App::new()
            .app_data(flag_provider.clone())
            .service(get_quote)
            .service(ship_order)
            .route(
                "/health",
                web::get().to(|| async { HttpResponse::Ok().finish() }),
            )
    })
    .bind(&addr)?
    .run()
    .await
}
