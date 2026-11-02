//! Unit 6 scenarios on a single pinned broker: committed readable frontier,
//! retention before the first acknowledgement, partition incarnation and
//! ownership, gaps, and request uncertainty. Each records observations; the
//! assertions pin only what the design review already states, and every
//! surprise is recorded rather than asserted away.

use std::collections::HashMap;
use std::str::FromStr;
use std::time::{Duration, Instant};

use fable_iggy_harness::{record, server_binary};
use iggy::prelude::*;
use integration::harness::{TestHarness, TestServerConfig};
use serde::Serialize;
use tokio::time::sleep;

const STREAM: &str = "fable-stream";
const TOPIC: &str = "fable-topic";

async fn harness(name: &str, extra_envs: HashMap<String, String>) -> TestHarness {
    let server = TestServerConfig::builder()
        .executable_path(server_binary())
        .quic_enabled(false)
        .websocket_enabled(false)
        .http_enabled(false)
        .extra_envs(extra_envs)
        .build();
    let mut harness = TestHarness::builder()
        .test_name(name)
        .server(server)
        .root_tcp_client()
        .build()
        .expect("harness");
    harness.start().await.expect("server start");
    harness
}

async fn create_topic(client: &IggyClient, options: TopicCreateOptions) {
    client
        .create_stream(STREAM, &StreamCreateOptions::default())
        .await
        .expect("stream");
    client
        .create_topic(&Identifier::named(STREAM).unwrap(), TOPIC, &options)
        .await
        .expect("topic");
}

fn ids() -> (Identifier, Identifier) {
    (Identifier::named(STREAM).unwrap(), Identifier::named(TOPIC).unwrap())
}

async fn send(client: &IggyClient, prefix: &str, count: u32) {
    let (stream, topic) = ids();
    let mut messages: Vec<IggyMessage> = (0..count)
        .map(|i| IggyMessage::from_str(&format!("{prefix}-{i}")).unwrap())
        .collect();
    client
        .send_messages(&stream, &topic, &Partitioning::partition_id(0), &mut messages)
        .await
        .expect("send");
}

async fn poll_from(client: &IggyClient, consumer: &Consumer, offset: u64, count: u32) -> PolledMessages {
    let (stream, topic) = ids();
    client
        .poll_messages(&stream, &topic, Some(0), consumer, &PollingStrategy::offset(offset), count, false)
        .await
        .expect("poll")
}

async fn partition_frontier(client: &IggyClient) -> (u64, u64) {
    let (stream, topic) = ids();
    let details = client.get_topic(&stream, &topic).await.expect("get topic").expect("topic exists");
    let partition = details.partitions.first().expect("partition 0");
    (partition.current_offset, partition.messages_count)
}

fn error_code(error: &IggyError) -> u32 {
    error.as_code()
}

#[derive(Serialize)]
struct Frontier {
    scenario: &'static str,
    sent: u32,
    partition_current_offset: u64,
    partition_messages_count: u64,
    polled_offsets_from_0: Vec<u64>,
    polled_current_offset: u64,
    polled_past_frontier: usize,
    stored_offset_before_any_ack: Option<u64>,
    context_incarnation: u64,
}

#[tokio::test]
async fn s1_committed_readable_frontier() {
    let mut harness = harness("s1_frontier", HashMap::new()).await;
    let client = harness.tcp_root_client().await.expect("client");
    create_topic(&client, TopicCreateOptions { partitions_count: Some(1), ..TopicCreateOptions::default() }).await;
    send(&client, "r", 5).await;
    let (current_offset, messages_count) = partition_frontier(&client).await;
    let consumer = Consumer::new(Identifier::named("fable").unwrap());
    let polled = poll_from(&client, &consumer, 0, 100).await;
    let offsets: Vec<u64> = polled.messages.iter().map(|m| m.header.offset).collect();
    let past = poll_from(&client, &consumer, current_offset + 1, 100).await;
    let (stream, topic) = ids();
    let stored = client
        .get_consumer_offset(&consumer, &stream, &topic, Some(0))
        .await
        .expect("get offset")
        .map(|o| o.stored_offset);
    let observation = Frontier {
        scenario: "committed readable frontier: every message up to the partition's current offset is readable before any acknowledgement, and nothing past it",
        sent: 5,
        partition_current_offset: current_offset,
        partition_messages_count: messages_count,
        polled_offsets_from_0: offsets.clone(),
        polled_current_offset: polled.current_offset,
        polled_past_frontier: past.messages.len(),
        stored_offset_before_any_ack: stored,
        context_incarnation: polled.context.incarnation,
    };
    record("s1_frontier", &observation);
    assert_eq!(offsets, (0..5).collect::<Vec<_>>());
    assert_eq!(past.messages.len(), 0);
    harness.stop().await.expect("stop");
}

#[derive(Serialize)]
struct Retention {
    scenario: &'static str,
    sent_total: u32,
    max_topic_size: String,
    segment_size: String,
    waited_secs: u64,
    partition_current_offset: u64,
    partition_messages_count: u64,
    segments_count: u32,
    first_offset_polled_from_0: Option<u64>,
    poll_from_0_error: Option<String>,
    gap_detected_only_by_first_offset_check: bool,
    stored_offset_before_any_ack: Option<u64>,
}

#[tokio::test]
async fn s2_retention_before_the_first_ack_and_s4_gap() {
    // As in the pinned message_cleanup test: the cleaner runs every 100 ms,
    // and size retention floors each partition's budget at one sealed
    // segment plus the bus message cap, so the 64 MiB default cap would keep
    // every segment; 2 MiB puts the floor under the topic cap.
    let envs = HashMap::from([
        ("IGGY_DATA_MAINTENANCE_MESSAGES_CLEANER_ENABLED".to_string(), "true".to_string()),
        ("IGGY_DATA_MAINTENANCE_MESSAGES_INTERVAL".to_string(), "100ms".to_string()),
        ("IGGY_MESSAGE_BUS_MAX_MESSAGE_SIZE".to_string(), (2 * 1024 * 1024).to_string()),
    ]);
    let mut harness = harness("s2_retention", envs).await;
    let client = harness.tcp_root_client().await.expect("client");
    // The server floor is a 1 MiB segment (MIN_TOPIC_SEGMENT_SIZE) and a cap
    // of at least one segment; four segments of 1 MiB roll quickly.
    let segment = IggyByteSize::from(1024 * 1024_u64);
    let max_size = IggyByteSize::from(4 * 1024 * 1024_u64);
    create_topic(
        &client,
        TopicCreateOptions {
            partitions_count: Some(1),
            max_topic_size: Some(MaxTopicSize::Custom(max_size)),
            segment_size: Some(segment),
            ..TopicCreateOptions::default()
        },
    )
    .await;
    // 1 KiB payloads, 100 per batch: ~100 KiB per batch, 120 batches ~ 12 MiB,
    // three times the cap, so the cleaner has sealed segments to delete.
    let mut sent = 0;
    let payload = "x".repeat(1024);
    for batch in 0..120 {
        send(&client, &format!("b{batch}-{payload}"), 100).await;
        sent += 100;
    }
    let consumer = Consumer::new(Identifier::named("fable").unwrap());
    let started = Instant::now();
    let mut first: Option<u64> = None;
    let mut error: Option<String> = None;
    while started.elapsed() < Duration::from_secs(30) {
        let (stream, topic) = ids();
        match client
            .poll_messages(&stream, &topic, Some(0), &consumer, &PollingStrategy::offset(0), 10, false)
            .await
        {
            Ok(polled) => {
                first = polled.messages.first().map(|m| m.header.offset);
                if first.is_some_and(|f| f > 0) {
                    break;
                }
            }
            Err(e) => {
                error = Some(format!("{e:?} code={}", error_code(&e)));
                break;
            }
        }
        sleep(Duration::from_secs(1)).await;
    }
    let (current_offset, messages_count) = partition_frontier(&client).await;
    let (stream, topic) = ids();
    let details = client.get_topic(&stream, &topic).await.expect("topic").expect("exists");
    let segments = details.partitions.first().map(|p| p.segments_count).unwrap_or(0);
    let stored = client
        .get_consumer_offset(&consumer, &stream, &topic, Some(0))
        .await
        .expect("get offset")
        .map(|o| o.stored_offset);
    let observation = Retention {
        scenario: "retention before the first acknowledgement: polling offset 0 after the cleaner removed sealed segments resumes at the first retained offset without an error; the only gap detector is first offset > expected start",
        sent_total: sent,
        max_topic_size: max_size.to_string(),
        segment_size: segment.to_string(),
        waited_secs: started.elapsed().as_secs(),
        partition_current_offset: current_offset,
        partition_messages_count: messages_count,
        segments_count: segments,
        first_offset_polled_from_0: first,
        poll_from_0_error: error.clone(),
        gap_detected_only_by_first_offset_check: error.is_none() && first.is_some_and(|f| f > 0),
        stored_offset_before_any_ack: stored,
    };
    record("s2_retention_s4_gap", &observation);
    harness.stop().await.expect("stop");
}

#[derive(Serialize)]
struct Incarnation {
    scenario: &'static str,
    incarnation_before: u64,
    owner_generation_before: u64,
    stored_offset_after_ack: Option<u64>,
    recreate_result: String,
    incarnation_after: Option<u64>,
    messages_after_recreate: Option<usize>,
    first_offset_after_recreate: Option<u64>,
    store_with_old_context: String,
    stored_offset_after_old_context_store: Option<u64>,
}

#[tokio::test]
async fn s3_incarnation_and_ownership_with_s4_offset_restart() {
    let mut harness = harness("s3_incarnation", HashMap::new()).await;
    let client = harness.tcp_root_client().await.expect("client");
    create_topic(&client, TopicCreateOptions { partitions_count: Some(1), ..TopicCreateOptions::default() }).await;
    send(&client, "r", 4).await;
    let consumer = Consumer::new(Identifier::named("fable").unwrap());
    let polled = poll_from(&client, &consumer, 0, 10).await;
    let before = polled.context;
    let (stream, topic) = ids();
    let position = ConsumerPosition { partition_id: 0, offset: 2, context: before };
    client
        .store_consumer_position(&consumer, &stream, &topic, position)
        .await
        .expect("store position");
    let stored = client.get_consumer_offset(&consumer, &stream, &topic, Some(0)).await.expect("get").map(|o| o.stored_offset);
    // Recreate the partition: delete then create one partition, reusing id 0.
    let recreate = match client.delete_partitions(&stream, &topic, 1).await {
        Ok(()) => match client.create_partitions(&stream, &topic, 1).await {
            Ok(()) => "deleted and created one partition".to_string(),
            Err(e) => format!("create failed: {e:?} code={}", error_code(&e)),
        },
        Err(e) => format!("delete failed: {e:?} code={}", error_code(&e)),
    };
    send(&client, "n", 2).await;
    let after = client
        .poll_messages(&stream, &topic, Some(0), &consumer, &PollingStrategy::offset(0), 10, false)
        .await;
    let (incarnation_after, count_after, first_after) = match &after {
        Ok(p) => (Some(p.context.incarnation), Some(p.messages.len()), p.messages.first().map(|m| m.header.offset)),
        Err(_) => (None, None, None),
    };
    let old_store = client
        .store_consumer_position(&consumer, &stream, &topic, ConsumerPosition { partition_id: 0, offset: 3, context: before })
        .await;
    let old_store_text = match &old_store {
        Ok(()) => "accepted".to_string(),
        Err(e) => format!("{e:?} code={}", error_code(e)),
    };
    let stored_after = client.get_consumer_offset(&consumer, &stream, &topic, Some(0)).await.ok().flatten().map(|o| o.stored_offset);
    let observation = Incarnation {
        scenario: "partition incarnation: a recreated partition id carries a new incarnation and restarts offsets; a position captured under the old incarnation is refused (expected HistoryUnavailable 87) and does not move the stored offset",
        incarnation_before: before.incarnation,
        owner_generation_before: before.owner_generation,
        stored_offset_after_ack: stored,
        recreate_result: recreate,
        incarnation_after,
        messages_after_recreate: count_after,
        first_offset_after_recreate: first_after,
        store_with_old_context: old_store_text,
        stored_offset_after_old_context_store: stored_after,
    };
    record("s3_incarnation_s4_restart", &observation);
    harness.stop().await.expect("stop");
}

#[derive(Serialize)]
struct Uncertainty {
    scenario: &'static str,
    stored_before_kill: Option<u64>,
    server_running_after_kill: bool,
    get_while_down: String,
    get_while_down_ms: u128,
    store_while_down: String,
    store_while_down_ms: u128,
    stored_after_restart_before_new_store: Option<u64>,
    store_after_restart: String,
    stored_after_restart: Option<u64>,
    poll_after_restart_offsets: Vec<u64>,
}

#[tokio::test]
async fn s5_request_uncertainty_across_a_broker_restart() {
    let mut harness = harness("s5_uncertainty", HashMap::new()).await;
    let client = harness.tcp_root_client().await.expect("client");
    create_topic(&client, TopicCreateOptions { partitions_count: Some(1), ..TopicCreateOptions::default() }).await;
    send(&client, "r", 3).await;
    let consumer = Consumer::new(Identifier::named("fable").unwrap());
    let polled = poll_from(&client, &consumer, 0, 10).await;
    let (stream, topic) = ids();
    client
        .store_consumer_position(&consumer, &stream, &topic, ConsumerPosition { partition_id: 0, offset: 0, context: polled.context })
        .await
        .expect("store");
    let stored_before = client.get_consumer_offset(&consumer, &stream, &topic, Some(0)).await.expect("get").map(|o| o.stored_offset);
    harness.kill_node(0).expect("kill");
    let server_running_after_kill = harness.running_server().is_ok();
    let probe_started = Instant::now();
    let get_while_down = match tokio::time::timeout(
        Duration::from_secs(5),
        client.get_consumer_offset(&consumer, &stream, &topic, Some(0)),
    )
    .await
    {
        Ok(Ok(offset)) => format!("ok: {:?}", offset.map(|o| o.stored_offset)),
        Ok(Err(e)) => format!("{e:?} code={}", error_code(&e)),
        Err(_) => "timed out after 5s (client reconnecting with unlimited retries)".to_string(),
    };
    let get_while_down_ms = probe_started.elapsed().as_millis();
    let store_started = Instant::now();
    let while_down = match tokio::time::timeout(
        Duration::from_secs(5),
        client.store_consumer_position(&consumer, &stream, &topic, ConsumerPosition { partition_id: 0, offset: 1, context: polled.context }),
    )
    .await
    {
        Ok(Ok(())) => "accepted".to_string(),
        Ok(Err(e)) => format!("{e:?} code={}", error_code(&e)),
        Err(_) => "timed out after 5s (not confirmed while down)".to_string(),
    };
    let store_while_down_ms = store_started.elapsed().as_millis();
    harness.restart_server().await.expect("restart");
    let client = harness.tcp_root_client().await.expect("client after restart");
    // Read back before any new acknowledgement: did the store issued while
    // the broker was down land (retained and replayed) or not?
    let stored_after_restart_before_new_store = client
        .get_consumer_offset(&consumer, &stream, &topic, Some(0))
        .await
        .expect("get")
        .map(|o| o.stored_offset);
    let polled = poll_from(&client, &consumer, 0, 10).await;
    let after = match client
        .store_consumer_position(&consumer, &stream, &topic, ConsumerPosition { partition_id: 0, offset: 2, context: polled.context })
        .await
    {
        Ok(()) => "accepted".to_string(),
        Err(e) => format!("{e:?} code={}", error_code(&e)),
    };
    let stored_after = client.get_consumer_offset(&consumer, &stream, &topic, Some(0)).await.expect("get").map(|o| o.stored_offset);
    let observation = Uncertainty {
        scenario: "request uncertainty: what an acknowledgement attempted while the broker is down returns (the SDK reconnects with unlimited retries by default and may retain and replay the request), whether the stored offset moved, and what a fresh-context acknowledgement after restart yields",
        stored_before_kill: stored_before,
        server_running_after_kill,
        get_while_down,
        get_while_down_ms,
        store_while_down: while_down,
        store_while_down_ms,
        stored_after_restart_before_new_store,
        store_after_restart: after,
        stored_after_restart: stored_after,
        poll_after_restart_offsets: polled.messages.iter().map(|m| m.header.offset).collect(),
    };
    record("s5_uncertainty", &observation);
    harness.stop().await.expect("stop");
}
