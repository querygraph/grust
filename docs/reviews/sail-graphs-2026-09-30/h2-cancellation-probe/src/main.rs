//! A narrow control for the handoff's local-reset-limit hypothesis.
//! This does not reproduce a Sail failure or qualify its transport.
use bytes::Bytes;
use std::error::Error;
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Arc;
use std::time::Duration;

#[tokio::main]
async fn main() -> Result<(), Box<dyn Error>> {
    tokio::time::timeout(Duration::from_secs(30), run()).await??;
    Ok(())
}

async fn run() -> Result<(), Box<dyn Error>> {
    const REQUESTS: usize = 1100;
    let (client_io, server_io) = tokio::io::duplex(65536);
    let observed_cancellations = Arc::new(AtomicUsize::new(0));
    let counted = observed_cancellations.clone();
    let server = tokio::spawn(async move {
        let mut connection = h2::server::Builder::new()
            .max_local_error_reset_streams(Some(1))
            .handshake::<_, Bytes>(server_io)
            .await
            .unwrap();
        let mut cancellations = tokio::task::JoinSet::new();
        while let Some(request) = connection.accept().await {
            let (_, mut respond) = request.unwrap();
            let response = http::Response::new(());
            // Keep the response open until the client cancels it.
            let mut body = respond.send_response(response, false).unwrap();
            let counted = counted.clone();
            cancellations.spawn(async move {
                let reason = std::future::poll_fn(|cx| body.poll_reset(cx)).await;
                if matches!(reason, Ok(h2::Reason::CANCEL)) {
                    counted.fetch_add(1, Ordering::SeqCst);
                }
            });
        }
    });
    let (mut client, connection) = h2::client::Builder::new()
        .max_local_error_reset_streams(Some(1))
        .handshake::<_, Bytes>(client_io)
        .await?;
    let driver = tokio::spawn(connection);
    for _ in 0..REQUESTS {
        client = client.ready().await?;
        let (response, request_body) = client.send_request(http::Request::new(()), true)?;
        let response = response.await?;
        drop(response);
        drop(request_body);
        tokio::task::yield_now().await;
    }
    client = client.ready().await?;
    let (response, _) = client.send_request(http::Request::new(()), true)?;
    let final_response = response.await?;
    assert_eq!(final_response.status(), http::StatusCode::OK);
    while observed_cancellations.load(Ordering::SeqCst) < REQUESTS {
        tokio::task::yield_now().await;
    }
    println!("PASS: {REQUESTS} accepted response-body cancellations observed by peer, then another response, on one connection; local error-reset cap=1 on both peers");
    server.abort();
    driver.abort();
    Ok(())
}
