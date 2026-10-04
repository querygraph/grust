use std::sync::Arc;

use arrow_flight::decode::FlightRecordBatchStream;
use arrow_flight::flight_service_client::FlightServiceClient;
use datafusion::arrow::datatypes::SchemaRef;
use futures::TryStreamExt;
use prost::Message;
use sail_common_datafusion::array::record_batch::cast_record_batch_positionally;

use crate::diagnostics::{log_codec_failure, log_failure};
use crate::error::ExecutionResult;
use crate::id::{DriverId, TaskStreamKey};
use crate::rpc::{ClientHandle, ClientOptions, ClientService};
use crate::stream::error::TaskStreamError;
use crate::stream::r#gen::{DriverTaskStreamTicket, TaskStreamTicket};
use crate::stream::reader::TaskStreamSource;

#[derive(Clone, Copy, Debug)]
pub enum TaskStreamOwner {
    Driver { driver_id: DriverId },
    Worker,
}

#[derive(Clone)]
pub struct TaskStreamFlightClient {
    inner: ClientHandle<FlightServiceClient<ClientService>>,
    owner: TaskStreamOwner,
}

impl TaskStreamFlightClient {
    pub fn new(options: ClientOptions, owner: TaskStreamOwner) -> Self {
        Self {
            // TODO: share connection with driver/worker client
            inner: ClientHandle::new(options),
            owner,
        }
    }

    pub async fn fetch_task_stream(
        &self,
        key: TaskStreamKey,
        schema: SchemaRef,
    ) -> ExecutionResult<TaskStreamSource> {
        let ticket = TaskStreamTicket {
            job_id: key.job_id.into(),
            stage: key.stage as u64,
            partition: key.partition as u64,
            attempt: key.attempt as u64,
            channel: key.channel as u64,
        };
        let ticket = match self.owner {
            TaskStreamOwner::Driver { driver_id } => {
                let ticket = DriverTaskStreamTicket {
                    driver_id: driver_id.into(),
                    stream: Some(ticket),
                };
                ticket.encode_to_vec()
            }
            TaskStreamOwner::Worker => ticket.encode_to_vec(),
        };
        let request = arrow_flight::Ticket {
            ticket: ticket.into(),
        };
        let mut client = self.inner.get().await.inspect_err(|error| {
            log_failure(
                format_args!(
                    "event=flight_client_error phase=connect peer={} owner={:?} key={key:?}",
                    self.inner.options().to_url_string(),
                    self.owner
                ),
                error,
            );
        })?;
        let response = client.do_get(request).await.inspect_err(|error| {
            log_failure(
                format_args!(
                    "event=flight_client_error phase=do_get peer={} owner={:?} key={key:?}",
                    self.inner.options().to_url_string(),
                    self.owner
                ),
                error,
            );
        })?;
        let peer = self.inner.options();
        let owner = self.owner;
        let body_key = key.clone();
        let stream = response
            .into_inner()
            .inspect_err(move |error| {
                log_failure(
                    format_args!(
                        "event=flight_client_error phase=body peer={} owner={owner:?} key={body_key:?}",
                        peer.to_url_string()
                    ),
                    error,
                );
            })
            .map_err(|e| e.into());
        let peer = self.inner.options();
        let decode_key = key.clone();
        let stream = FlightRecordBatchStream::new_from_flight_data(stream)
            .inspect_err(move |error| {
                log_codec_failure(
                    format_args!(
                        "event=flight_client_error phase=decode peer={} owner={owner:?} key={decode_key:?}",
                        peer.to_url_string()
                    ),
                    error,
                );
            })
            .map_err(|e| e.into());
        // The Flight data encoder may have issue with the `LargeList` data type, causing
        // schema mismatch. As a workaround, here we cast the record batch to the expected schema.
        // https://github.com/apache/arrow-rs/issues/10291
        let peer = self.inner.options();
        let stream = stream.and_then(move |batch| {
            let result = if batch.schema().as_ref() == schema.as_ref() {
                Ok(batch)
            } else {
                cast_record_batch_positionally(batch, schema.clone())
                    .inspect_err(|error| {
                        log_failure(
                            format_args!(
                                "event=flight_client_error phase=cast peer={} owner={owner:?} key={key:?}",
                                peer.to_url_string()
                            ),
                            error,
                        );
                    })
                    .map_err(|e| TaskStreamError::External(Arc::new(e)))
            };
            futures::future::ready(result)
        });
        Ok(Box::pin(stream) as TaskStreamSource)
    }
}
