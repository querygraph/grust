//! Local diagnostic control, not a Sail reproduction or qualification.
//! Both peers use exact Sail-locked HTTP/2 versions. A frame-aware in-memory
//! proxy deliberately drops PING ACKs, leaving all other traffic unchanged.
use bytes::Bytes;
use http_body::{Body, Frame};
use http_body_util::{BodyExt, Empty};
use hyper_util::rt::{TokioExecutor, TokioIo, TokioTimer};
use std::convert::Infallible;
use std::error::Error;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::Duration;
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tracing::Instrument;

type Failure = Box<dyn Error + Send + Sync>;

struct OpenBody(Option<Bytes>);
impl Body for OpenBody {
    type Data = Bytes;
    type Error = Infallible;
    fn poll_frame(mut self: Pin<&mut Self>, _: &mut Context<'_>)
        -> Poll<Option<Result<Frame<Bytes>, Infallible>>>
    {
        match self.0.take() {
            Some(bytes) => Poll::Ready(Some(Ok(Frame::data(bytes)))),
            None => Poll::Pending,
        }
    }
}

#[tokio::main]
async fn main() -> Result<(), Failure> {
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_ansi(false)
        .with_target(true)
        .with_thread_ids(true)
        .init();
    let mode = std::env::args().nth(1).unwrap_or_else(|| "keepalive".into());
    tracing::info!(%mode, hyper_tracing = cfg!(feature = "hyper-tracing"),
                   "CONTROL start; this is not Sail");
    tokio::time::timeout(Duration::from_secs(10), run(&mode)).await??;
    println!("PASS: induced {mode} failure produced the same outer Tonic body-read message");
    Ok(())
}

async fn run(mode: &str) -> Result<(), Failure> {
    let (client_io, proxy_client) = tokio::io::duplex(65536);
    let (proxy_server, server_io) = tokio::io::duplex(65536);
    let (mut from_client, mut to_client) = tokio::io::split(proxy_client);
    let (mut from_server, mut to_server) = tokio::io::split(proxy_server);
    let drop_ping_acks = mode == "keepalive";
    let upstream = tokio::spawn(async move {
        let mut preface = [0; 24];
        from_client.read_exact(&mut preface).await?;
        to_server.write_all(&preface).await?;
        loop {
            let mut header = [0u8; 9];
            if from_client.read_exact(&mut header).await.is_err() { break; }
            let len = (usize::from(header[0]) << 16)
                | (usize::from(header[1]) << 8) | usize::from(header[2]);
            let mut payload = vec![0; len];
            from_client.read_exact(&mut payload).await?;
            if drop_ping_acks && header[3] == 6 && header[4] & 1 != 0 {
                tracing::info!("CONTROL proxy deliberately dropped client PING ACK");
                continue;
            }
            to_server.write_all(&header).await?;
            to_server.write_all(&payload).await?;
        }
        Ok::<_, std::io::Error>(())
    }.instrument(tracing::info_span!("peer", side = "proxy-client-to-server")));
    let downstream = tokio::spawn(async move {
        let result = tokio::io::copy(&mut from_server, &mut to_client).await;
        // A split duplex write half does not signal EOF merely by dropping it
        // while its paired read half remains alive. Relay the server FIN.
        let _ = to_client.shutdown().await;
        result
    }.instrument(tracing::info_span!("peer", side = "proxy-server-to-client")));

    let (trigger, triggered) = tokio::sync::oneshot::channel::<()>();
    let server = if mode == "keepalive" {
        tokio::spawn(async move {
            let service = hyper::service::service_fn(|_| async {
                Ok::<_, Infallible>(http::Response::new(OpenBody(Some(Bytes::from_static(b"open")))))
            });
            let result = hyper::server::conn::http2::Builder::new(TokioExecutor::new())
                .timer(TokioTimer::new())
                .keep_alive_interval(Some(Duration::from_millis(100)))
                .keep_alive_timeout(Duration::from_millis(150))
                .serve_connection(TokioIo::new(server_io), service).await;
            tracing::info!(?result, "CONTROL server connection future completed");
            assert!(result.as_ref().is_err_and(hyper::Error::is_timeout),
                    "expected the deliberately induced keepalive timeout");
        }.instrument(tracing::info_span!("peer", side = "server")))
    } else {
        assert_eq!(mode, "reset");
        tokio::spawn(async move {
            let mut connection = h2::server::handshake(server_io).await.unwrap();
            let (_, mut respond) = connection.accept().await.unwrap().unwrap();
            let mut body = respond.send_response(http::Response::new(()), false).unwrap();
            body.send_data(Bytes::from_static(b"open"), false).unwrap();
            let reset = tokio::spawn(async move {
                triggered.await.unwrap();
                tracing::info!("CONTROL server deliberately resets the open body INTERNAL_ERROR");
                body.send_reset(h2::Reason::INTERNAL_ERROR);
            }.instrument(tracing::info_span!("peer", side = "server-reset")));
            while let Some(request) = connection.accept().await {
                if request.is_err() { break; }
            }
            let _ = reset.await;
        }.instrument(tracing::info_span!("peer", side = "server")))
    };

    let (mut client, connection) = hyper::client::conn::http2::Builder::new(TokioExecutor::new())
        .handshake::<_, Empty<Bytes>>(TokioIo::new(client_io)).await?;
    let driver = tokio::spawn(async move {
        let result = connection.await;
        tracing::info!(?result, "CONTROL client connection future completed");
    }.instrument(tracing::info_span!("peer", side = "client")));
    let request = http::Request::builder().uri("http://control.test/open")
        .body(Empty::<Bytes>::new())?;
    let response = client.send_request(request).await?;
    let mut body = response.into_body();
    let first = body.frame().await.expect("first frame")?;
    assert_eq!(first.into_data().unwrap(), Bytes::from_static(b"open"));
    if mode == "reset" { let _ = trigger.send(()); }
    let error = body.frame().await.expect("body must fail, not end").unwrap_err();
    let mut chain: &dyn Error = &error;
    loop {
        tracing::info!(display = %chain, debug = ?chain, "CONTROL body error chain");
        match chain.source() { Some(source) => chain = source, None => break }
    }
    let status = tonic::Status::from_error(Box::new(error));
    tracing::info!(code = ?status.code(), message = status.message(), debug = ?status,
                   "CONTROL Tonic conversion");
    assert_eq!(status.message(), "h2 protocol error: error reading a body from connection");
    if mode == "keepalive" { server.await?; } else { server.abort(); let _ = server.await; }
    driver.abort(); let _ = driver.await;
    upstream.abort(); let _ = upstream.await;
    downstream.abort(); let _ = downstream.await;
    Ok(())
}
