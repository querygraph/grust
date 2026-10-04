# F2 native client Arrow bridge evidence

Four int64 conditions, eight full outputs, plus a separate three-output signed tiny control. All eleven outputs passed the closed full physical original-domain/partition oracle after engine closure. All eight main Parquets (217948036 bytes) were preserved on Apo with full matching SHA.

The benchmark JSONs describe chunk_checkpoint_arrow_client_four_phase: full client Parquet-to-Arrow read; bounded inline IPC, eager unsorted checkpoint, balanced cached-reference unions, asStaged and projectionStats; all WCC calls with full Arrow result transport; all client Parquet writes. It is a separate profile, with n1/null standard deviation and raw shared-host phase observations, not a dedicated-host absolute benchmark or a native CSR-only/kernel-only or Sem resource/work parity claim. Parent Popen-to-wait is distinct.

Original artifact-status and unset-checkpoint-path failures, original failed receipts and root manual closure records are included unchanged. Historical report01 was unvalidated when written; qualified report02 binds the later actual oracle receipts. The prior ordinary native-Parquet Grust0.24 int64/text one/three-call baseline is retained separately under prior-evidence; its exclusive four Sem phases are unavailable/null and it is not relabelled as this bridge.

The manifest inventories every copied JSON/log/helper and declared excluded binary/wheel/venv/Parquet payload pin. Packaging opens only metadata/source files; it does not rerun numerics, engines or process probes.
