use async_trait::async_trait;
use grust_core::TypedGraphIndex;
use grust_core::prelude::*;
use grust_cypher::pushdown::{NoTypeHints, SqlDialect, StrOp, combine_union, plan_read};
use grust_cypher::{CypherParameters, CypherResultTable};
use grust_sql_core::{GraphSqlDialect, UniversalTableRefs};
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};

mod guarded_commit;

/// Journal/concurrency mode for a local Turso database.
#[derive(Clone, Copy, Debug, Default, Eq, PartialEq)]
pub enum TursoJournalMode {
    /// Write-ahead logging — Turso's default single-writer mode.
    #[default]
    Wal,
    /// Multi-version concurrency control (`PRAGMA journal_mode = mvcc`), which
    /// enables `BEGIN CONCURRENT` concurrent writers. MVCC is a database-*header*
    /// mode; Turso 0.7.2 converts an existing WAL database when it is opened
    /// in this mode, and a live store can switch between the two
    /// (`set_bulk_load_via_wal`). `connect` errors if the mode is not applied.
    Mvcc,
}

impl TursoJournalMode {
    /// The `PRAGMA journal_mode` value the engine reports/accepts.
    fn pragma_value(self) -> &'static str {
        match self {
            TursoJournalMode::Wal => "wal",
            TursoJournalMode::Mvcc => "mvcc",
        }
    }
}

/// `PRAGMA synchronous` for a connection. Turso's default is `Full`: every
/// commit fsyncs (under MVCC, while holding the global commit lock).
/// `Normal` skips the per-commit fsync and still fsyncs at checkpoints, so a
/// crash can lose the commits since the last checkpoint; `Off` never fsyncs.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum TursoSynchronous {
    Off,
    Normal,
    Full,
}

impl TursoSynchronous {
    fn pragma_value(self) -> &'static str {
        match self {
            TursoSynchronous::Off => "OFF",
            TursoSynchronous::Normal => "NORMAL",
            TursoSynchronous::Full => "FULL",
        }
    }
}

/// One statement waiting for a group commit, and where to send its outcome.
struct GroupJob {
    sql: String,
    reply: tokio::sync::oneshot::Sender<Result<()>>,
}

/// The MVCC group committer: a task that owns one connection and commits
/// whatever statements are waiting as one transaction.
struct GroupCommit {
    jobs: tokio::sync::mpsc::UnboundedSender<GroupJob>,
}

/// Most statements one group commit carries; a larger backlog waits for the
/// next commit.
const GROUP_COMMIT_MAX_STATEMENTS: usize = 256;

impl GroupCommit {
    fn spawn(committer: TursoGraphStore) -> Self {
        let (jobs, mut queue) = tokio::sync::mpsc::unbounded_channel::<GroupJob>();
        tokio::spawn(async move {
            while let Some(first) = queue.recv().await {
                let mut batch = vec![first];
                while batch.len() < GROUP_COMMIT_MAX_STATEMENTS {
                    match queue.try_recv() {
                        Ok(job) => batch.push(job),
                        Err(_) => break,
                    }
                }
                let statements: Vec<String> = batch.iter().map(|job| job.sql.clone()).collect();
                if batch.len() > 1
                    && committer
                        .execute_transaction(&statements, true)
                        .await
                        .is_ok()
                {
                    for job in batch {
                        let _ = job.reply.send(Ok(()));
                    }
                    continue;
                }
                // One statement, or a batch that failed as a whole: each job
                // runs as its own transaction with the usual conflict retry,
                // so only the failing statement's caller sees the error.
                for job in batch {
                    let outcome = committer
                        .execute_transaction(std::slice::from_ref(&job.sql), true)
                        .await;
                    let _ = job.reply.send(outcome);
                }
            }
        });
        Self { jobs }
    }

    async fn submit(&self, sql: String) -> Result<()> {
        let (reply, outcome) = tokio::sync::oneshot::channel();
        self.jobs
            .send(GroupJob { sql, reply })
            .map_err(|_| GrustError::Backend("Turso group committer has stopped".to_string()))?;
        outcome
            .await
            .map_err(|_| GrustError::Backend("Turso group committer dropped a write".to_string()))?
    }
}

#[derive(Clone, Debug)]
pub struct TursoConfig {
    pub path: String,
    pub table_prefix: String,
    pub batch_size: usize,
    /// Journal/concurrency mode for the local database (default `Wal`).
    pub journal_mode: TursoJournalMode,
}

impl Default for TursoConfig {
    fn default() -> Self {
        Self {
            path: ":memory:".to_string(),
            table_prefix: "grust".to_string(),
            batch_size: 500,
            journal_mode: TursoJournalMode::Wal,
        }
    }
}

#[cfg(feature = "sync")]
#[derive(Clone, Debug)]
pub struct TursoSyncConfig {
    pub local_path: String,
    pub remote_url: String,
    pub auth_token: Option<String>,
    pub table_prefix: String,
    pub batch_size: usize,
}

#[allow(dead_code)]
enum TursoDatabase {
    Local(turso::Database),
    #[cfg(feature = "sync")]
    Synced(turso::sync::Database),
}

pub struct TursoGraphStore {
    config: TursoConfig,
    _db: TursoDatabase,
    conn: turso::Connection,
    /// The resident typed snapshot, built on request from a full read of the
    /// store and dropped by every statement that could change it.
    index_cache: std::sync::Mutex<Option<Arc<TypedGraphIndex>>>,
    /// Serializes all operations on `conn` so an explicit guarded transaction
    /// cannot accidentally absorb a concurrent read or write on the same
    /// connection.
    connection_gate: tokio::sync::Mutex<()>,
    /// MVCC group commit shared by every handle opened with `connect_shared`
    /// from a store that called `with_group_commit`.
    group: Option<Arc<GroupCommit>>,
    /// When set, an MVCC `put_graph` switches the database to WAL for the
    /// load and back to MVCC afterwards (see `set_bulk_load_via_wal`).
    bulk_load_via_wal: AtomicBool,
    /// Concurrent writers an MVCC `put_graph` uses (see
    /// `set_mvcc_load_parallelism`); 1 loads on this connection alone.
    mvcc_load_parallelism: AtomicUsize,
    /// Set for the duration of a `put_graph` whose target tables were empty
    /// when it began: its batches insert without a conflict clause, and a
    /// batch that does collide is replayed as an upsert.
    loading_empty_tables: Arc<AtomicBool>,
    /// Set before an explicit transaction begins and cleared only after its
    /// commit or rollback finishes. If a future is cancelled while the gate is
    /// held, the next caller recovers the abandoned transaction first.
    transaction_needs_rollback: AtomicBool,
}

impl TursoGraphStore {
    pub async fn connect(config: TursoConfig) -> Result<Self> {
        validate_identifier(&config.table_prefix)?;
        let db = turso::Builder::new_local(&config.path)
            .build()
            .await
            .map_err(|err| {
                GrustError::Backend(format!(
                    "failed to open Turso database at {}: {err}",
                    config.path
                ))
            })?;
        let conn = db.connect().map_err(|err| {
            GrustError::Backend(format!("failed to connect to Turso database: {err}"))
        })?;
        let store = Self {
            config,
            _db: TursoDatabase::Local(db),
            conn,
            index_cache: std::sync::Mutex::new(None),
            connection_gate: tokio::sync::Mutex::new(()),
            transaction_needs_rollback: AtomicBool::new(false),
            group: None,
            bulk_load_via_wal: AtomicBool::new(false),
            mvcc_load_parallelism: AtomicUsize::new(1),
            loading_empty_tables: Arc::new(AtomicBool::new(false)),
        };
        store.apply_journal_mode().await?;
        store
            .execute_discarding_rows(&format!("PRAGMA cache_size = -{PAGE_CACHE_KIB}"))
            .await?;
        Ok(store)
    }

    /// Another handle on this store's open database: a new connection that
    /// shares the same `turso::Database` (its MVCC store and page cache)
    /// instead of opening the file again. Concurrent writers in one process
    /// should use this; `connect` on the same path builds a separate database
    /// object.
    pub async fn connect_shared(&self) -> Result<Self> {
        let db = match &self._db {
            TursoDatabase::Local(db) => db.clone(),
            #[cfg(feature = "sync")]
            TursoDatabase::Synced(_) => {
                return Err(GrustError::Unsupported(
                    "connect_shared is not available on a synced Turso store".to_string(),
                ));
            }
        };
        let conn = db.connect().map_err(|err| {
            GrustError::Backend(format!("failed to connect to Turso database: {err}"))
        })?;
        let store = Self {
            config: self.config.clone(),
            _db: TursoDatabase::Local(db),
            conn,
            index_cache: std::sync::Mutex::new(None),
            connection_gate: tokio::sync::Mutex::new(()),
            transaction_needs_rollback: AtomicBool::new(false),
            // Handles share the store's committer; the committer's own
            // connection is opened before it exists and so commits directly.
            group: self.group.clone(),
            bulk_load_via_wal: AtomicBool::new(self.bulk_load_via_wal.load(Ordering::Acquire)),
            mvcc_load_parallelism: AtomicUsize::new(
                self.mvcc_load_parallelism.load(Ordering::Acquire),
            ),
            // Shared, not copied: a parallel load sets the flag on the store
            // and its writer handles must see it.
            loading_empty_tables: self.loading_empty_tables.clone(),
        };
        store.apply_journal_mode().await?;
        store
            .execute_discarding_rows(&format!("PRAGMA cache_size = -{PAGE_CACHE_KIB}"))
            .await?;
        Ok(store)
    }

    /// Apply the configured journal mode on a fresh connection. MVCC is set via
    /// `PRAGMA journal_mode = mvcc` (a database-header mode) and verified by
    /// reading the mode back, so a silently-unconverted existing WAL database
    /// surfaces as an error rather than running in the wrong mode.
    async fn apply_journal_mode(&self) -> Result<()> {
        if self.config.journal_mode == TursoJournalMode::Wal {
            // WAL is the engine default; nothing to enforce.
            return Ok(());
        }
        let want = self.config.journal_mode.pragma_value();
        let got = self
            .query_scalar_text(&format!("PRAGMA journal_mode = {want}"))
            .await?;
        if got.as_deref() != Some(want) {
            return Err(GrustError::Backend(format!(
                "requested Turso journal_mode = {want} but the database reports {got:?}"
            )));
        }
        Ok(())
    }

    /// Run a query expected to yield a single text cell in its first row.
    /// Run a statement whose result rows carry nothing the store needs, such
    /// as `PRAGMA wal_checkpoint`, draining them so the statement completes.
    async fn execute_discarding_rows(&self, sql: &str) -> Result<()> {
        let _gate = self.lock_connection().await?;
        let mut rows = self
            .conn
            .query(sql, ())
            .await
            .map_err(|err| GrustError::Backend(format!("Turso query failed: {err}: {sql}")))?;
        while rows
            .next()
            .await
            .map_err(|err| GrustError::Backend(format!("Turso row read failed: {err}: {sql}")))?
            .is_some()
        {}
        Ok(())
    }

    async fn query_scalar_text(&self, sql: &str) -> Result<Option<String>> {
        let _gate = self.lock_connection().await?;
        let mut rows = self
            .conn
            .query(sql, ())
            .await
            .map_err(|err| GrustError::Backend(format!("Turso query failed: {err}: {sql}")))?;
        match rows
            .next()
            .await
            .map_err(|err| GrustError::Backend(format!("Turso row read failed: {err}: {sql}")))?
        {
            Some(row) => row_optional_text(&row, 0, "pragma result"),
            None => Ok(None),
        }
    }

    /// The first column of the first row of `sql` as an integer.
    async fn query_scalar_i64(&self, sql: &str) -> Result<i64> {
        let _gate = self.lock_connection().await?;
        let mut rows = self
            .conn
            .query(sql, ())
            .await
            .map_err(|err| GrustError::Backend(format!("Turso query failed: {err}: {sql}")))?;
        let row = rows
            .next()
            .await
            .map_err(|err| GrustError::Backend(format!("Turso row read failed: {err}: {sql}")))?
            .ok_or_else(|| GrustError::Backend(format!("Turso returned no row: {sql}")))?;
        match row.get_value(0) {
            Ok(turso::Value::Integer(value)) => Ok(value),
            other => Err(GrustError::Backend(format!(
                "Turso returned {other:?} where an integer was expected: {sql}"
            ))),
        }
    }

    /// Turn on MVCC group commit for this store and every handle later opened
    /// from it with `connect_shared`. Single-statement writes (`put_node`,
    /// `put_edge`, and the other one-statement mutations) from all of those
    /// handles are handed to one committer, which runs whatever is waiting
    /// as one `BEGIN CONCURRENT … COMMIT`: under `synchronous = FULL` that
    /// is one fsync for the batch instead of one per write, and each caller
    /// returns only after the commit that carries its statement. A batch
    /// that fails is retried one statement at a time, so a failing or
    /// conflicting write fails only its own caller. WAL stores are returned
    /// unchanged. Must be called from within a Tokio runtime.
    pub async fn with_group_commit(mut self) -> Result<Self> {
        if self.config.journal_mode != TursoJournalMode::Mvcc || self.group.is_some() {
            return Ok(self);
        }
        let committer = self.connect_shared().await?;
        self.group = Some(Arc::new(GroupCommit::spawn(committer)));
        Ok(self)
    }

    /// Set `PRAGMA synchronous` on this store's connection. Each handle has
    /// its own connection, so set it on every handle that should use it.
    pub async fn set_synchronous(&self, mode: TursoSynchronous) -> Result<()> {
        self.execute_discarding_rows(&format!("PRAGMA synchronous = {}", mode.pragma_value()))
            .await
    }

    /// Run this MVCC store's `put_graph` calls through WAL: each switches the
    /// database to `journal_mode = wal`, loads in one transaction (WAL's load
    /// path, several times faster than MVCC's, which keeps every index entry
    /// of every row version in memory), checkpoints, and switches back to
    /// MVCC, also when the load fails. Journal mode is database-wide, so the
    /// caller must not run other writes on the database while a `put_graph`
    /// is in flight; a bulk load before serving is the intended use. A no-op
    /// for WAL stores. Handles opened later with `connect_shared` inherit it.
    pub fn set_bulk_load_via_wal(&self, enabled: bool) {
        self.bulk_load_via_wal.store(enabled, Ordering::Release);
    }

    /// Load an MVCC store's `put_graph` with `writers` concurrent connections
    /// (`BEGIN CONCURRENT` transactions on disjoint slices of the nodes, then
    /// of the edges), so the per-row MVCC index work runs on several cores;
    /// WAL allows one writer. 1 (the default) loads on this connection alone.
    /// Needs a multi-threaded Tokio runtime to use more than one core.
    pub fn set_mvcc_load_parallelism(&self, writers: usize) {
        self.mvcc_load_parallelism
            .store(writers.max(1), Ordering::Release);
    }

    pub async fn in_memory() -> Result<Self> {
        Self::connect(TursoConfig::default()).await
    }

    #[cfg(feature = "sync")]
    pub async fn connect_synced(config: TursoSyncConfig) -> Result<Self> {
        validate_identifier(&config.table_prefix)?;
        let mut builder = turso::sync::Builder::new_remote(&config.local_path)
            .with_remote_url(&config.remote_url);
        if let Some(token) = &config.auth_token {
            builder = builder.with_auth_token(token.clone());
        }
        let db = builder.build().await.map_err(|err| {
            GrustError::Backend(format!(
                "failed to open synced Turso database at {}: {err}",
                config.local_path
            ))
        })?;
        let conn = db.connect().await.map_err(|err| {
            GrustError::Backend(format!("failed to connect to synced Turso database: {err}"))
        })?;
        Ok(Self {
            config: TursoConfig {
                path: config.local_path,
                table_prefix: config.table_prefix,
                batch_size: config.batch_size,
                journal_mode: TursoJournalMode::Wal,
            },
            _db: TursoDatabase::Synced(db),
            conn,
            index_cache: std::sync::Mutex::new(None),
            connection_gate: tokio::sync::Mutex::new(()),
            transaction_needs_rollback: AtomicBool::new(false),
            group: None,
            bulk_load_via_wal: AtomicBool::new(false),
            mvcc_load_parallelism: AtomicUsize::new(1),
            loading_empty_tables: Arc::new(AtomicBool::new(false)),
        })
    }

    pub fn config(&self) -> &TursoConfig {
        &self.config
    }

    #[cfg(feature = "sync")]
    pub async fn push(&self) -> Result<()> {
        let _gate = self.lock_connection().await?;
        match &self._db {
            TursoDatabase::Synced(db) => db
                .push()
                .await
                .map_err(|err| GrustError::Backend(format!("Turso push failed: {err}"))),
            _ => Err(GrustError::Unsupported(
                "Turso push is only available for synced stores".to_string(),
            )),
        }
    }

    #[cfg(feature = "sync")]
    pub async fn pull(&self) -> Result<bool> {
        let _gate = self.lock_connection().await?;
        // Retire before polling: a failed or cancelled pull may already have
        // changed local data. Previously returned immutable snapshots stay valid.
        self.invalidate_snapshot();
        match &self._db {
            TursoDatabase::Synced(db) => db
                .pull()
                .await
                .map_err(|err| GrustError::Backend(format!("Turso pull failed: {err}"))),
            _ => Err(GrustError::Unsupported(
                "Turso pull is only available for synced stores".to_string(),
            )),
        }
    }

    async fn execute(&self, sql: &str) -> Result<()> {
        let _gate = self.lock_connection().await?;
        self.execute_unlocked(sql).await
    }

    async fn lock_connection(&self) -> Result<tokio::sync::MutexGuard<'_, ()>> {
        let gate = self.connection_gate.lock().await;
        if self.transaction_needs_rollback.load(Ordering::Acquire) {
            // Cancellation may occur while BEGIN, a statement, or COMMIT is
            // being driven. If BEGIN never took effect the connection is
            // already in autocommit mode; otherwise resolve the transaction
            // before allowing another operation onto the shared connection.
            self.recover_transaction_unlocked().await?;
        }
        Ok(gate)
    }

    /// Resolve a transaction whose completion is uncertain. The marker stays
    /// set if state inspection or rollback fails, preventing later operations
    /// from silently joining the abandoned transaction.
    async fn recover_transaction_unlocked(&self) -> Result<()> {
        let autocommit = self.conn.is_autocommit().map_err(|err| {
            GrustError::Backend(format!(
                "failed to inspect Turso transaction state during cancellation recovery: {err}"
            ))
        })?;
        if !autocommit {
            self.execute_unlocked("ROLLBACK").await?;
        }
        self.transaction_needs_rollback
            .store(false, Ordering::Release);
        Ok(())
    }

    async fn execute_unlocked(&self, sql: &str) -> Result<()> {
        // Every statement that can change the store funnels through here
        // (writes, DDL, BEGIN/COMMIT); reads go through `conn.query` directly.
        self.invalidate_snapshot();
        self.conn
            .execute_batch(sql)
            .await
            .map_err(|err| GrustError::Backend(format!("Turso command failed: {err}: {sql}")))
    }

    /// Execute a single data-write statement. In WAL mode this is a plain
    /// auto-commit statement (unchanged); in MVCC mode it runs inside a
    /// `BEGIN CONCURRENT` transaction with conflict retry.
    async fn execute_data(&self, sql: &str) -> Result<()> {
        match self.config.journal_mode {
            TursoJournalMode::Wal => self.execute(sql).await,
            TursoJournalMode::Mvcc if self.group.is_some() => {
                self.invalidate_snapshot();
                let group = self.group.as_ref().expect("checked above");
                let result = group.submit(sql.to_string()).await;
                self.invalidate_snapshot();
                result
            }
            TursoJournalMode::Mvcc => {
                self.execute_concurrent(std::slice::from_ref(&sql.to_string()))
                    .await
            }
        }
    }

    /// Run `statements` as one MVCC `BEGIN CONCURRENT … COMMIT` transaction,
    /// retrying the whole transaction on a write-write / busy conflict (bounded).
    /// Only used when `journal_mode == Mvcc`.
    async fn execute_concurrent(&self, statements: &[String]) -> Result<()> {
        self.execute_transaction(statements, true).await
    }

    /// Execute already-lowered statements on the shared connection while
    /// holding its gate for the entire transaction, including rollback. This
    /// prevents another task from observing or joining a failed transaction.
    async fn execute_transaction(&self, statements: &[String], concurrent: bool) -> Result<()> {
        const MAX_ATTEMPTS: usize = 8;
        if statements
            .iter()
            .all(|statement| statement.trim().is_empty())
        {
            return Ok(());
        }
        let _gate = self.lock_connection().await?;
        let mut attempt = 0;
        loop {
            attempt += 1;
            self.transaction_needs_rollback
                .store(true, Ordering::Release);
            let result = async {
                self.execute_unlocked(if concurrent {
                    "BEGIN CONCURRENT"
                } else {
                    "BEGIN"
                })
                .await?;
                for statement in statements {
                    if !statement.trim().is_empty() {
                        self.execute_unlocked(statement).await?;
                    }
                }
                self.execute_unlocked("COMMIT").await
            }
            .await;
            match result {
                Ok(()) => {
                    self.transaction_needs_rollback
                        .store(false, Ordering::Release);
                    return Ok(());
                }
                Err(err) => {
                    // A conflict aborts the transaction; clear any residual state
                    // before retrying or surfacing the error. If rollback itself
                    // fails, keep the recovery marker set for the next caller.
                    if let Err(recovery_err) = self.recover_transaction_unlocked().await {
                        return Err(GrustError::Backend(format!(
                            "{err}; Turso transaction recovery failed: {recovery_err}"
                        )));
                    }
                    if concurrent && is_mvcc_conflict(&err) && attempt < MAX_ATTEMPTS {
                        continue;
                    }
                    return Err(err);
                }
            }
        }
    }

    async fn query_nodes(&self, sql: &str) -> Result<Vec<Node>> {
        let _gate = self.lock_connection().await?;
        self.query_nodes_unlocked(sql).await
    }

    async fn query_nodes_unlocked(&self, sql: &str) -> Result<Vec<Node>> {
        let mut rows =
            self.conn.query(sql, ()).await.map_err(|err| {
                GrustError::Backend(format!("Turso node query failed: {err}: {sql}"))
            })?;
        let mut nodes = Vec::new();
        while let Some(row) = rows.next().await.map_err(|err| {
            GrustError::Backend(format!("Turso node row read failed: {err}: {sql}"))
        })? {
            nodes.push(row_to_node(&row)?);
        }
        Ok(nodes)
    }

    async fn query_edges(&self, sql: &str) -> Result<Vec<Edge>> {
        let _gate = self.lock_connection().await?;
        self.query_edges_unlocked(sql).await
    }

    async fn query_edges_unlocked(&self, sql: &str) -> Result<Vec<Edge>> {
        let mut rows =
            self.conn.query(sql, ()).await.map_err(|err| {
                GrustError::Backend(format!("Turso edge query failed: {err}: {sql}"))
            })?;
        let mut edges = Vec::new();
        while let Some(row) = rows.next().await.map_err(|err| {
            GrustError::Backend(format!("Turso edge row read failed: {err}: {sql}"))
        })? {
            edges.push(row_to_edge(&row)?);
        }
        Ok(edges)
    }

    fn nodes_table(&self) -> String {
        quote_ident(&format!("{}_nodes", self.config.table_prefix))
    }

    /// Whether the edge table predates the encoded optional identity key.
    async fn edges_table_is_legacy_unlocked(&self) -> Result<bool> {
        let sql = format!("PRAGMA table_info({})", self.edges_table());
        let mut rows =
            self.conn.query(&sql, ()).await.map_err(|err| {
                GrustError::Backend(format!("Turso table_info failed: {err}: {sql}"))
            })?;
        let mut columns = Vec::new();
        while let Some(row) = rows.next().await.map_err(|err| {
            GrustError::Backend(format!("Turso table_info row read failed: {err}: {sql}"))
        })? {
            columns.push(row_text(&row, 1, "table_info name")?);
        }
        Ok(!columns.is_empty() && !columns.iter().any(|c| c == "identity_key"))
    }

    /// Whether the retired `<prefix>_edges_from_idx` is still in the schema.
    async fn edges_from_index_exists_unlocked(&self) -> Result<bool> {
        let sql = format!(
            "SELECT 1 FROM sqlite_schema WHERE type = 'index' AND name = {}",
            sql_str(&format!("{}_edges_from_idx", self.config.table_prefix))
        );
        let mut rows = self.conn.query(&sql, ()).await.map_err(|err| {
            GrustError::Backend(format!("Turso schema query failed: {err}: {sql}"))
        })?;
        Ok(rows
            .next()
            .await
            .map_err(|err| {
                GrustError::Backend(format!("Turso schema row read failed: {err}: {sql}"))
            })?
            .is_some())
    }

    /// Whether `table` (an already-quoted identifier) holds at least one row.
    /// `EXISTS` stops at the first row, where `COUNT(*)` would walk the table.
    async fn table_has_rows(&self, table: &str) -> Result<bool> {
        Ok(self
            .query_scalar_i64(&format!("SELECT EXISTS(SELECT 1 FROM {table})"))
            .await?
            != 0)
    }

    fn edges_table(&self) -> String {
        quote_ident(&format!("{}_edges", self.config.table_prefix))
    }

    fn commits_table(&self) -> String {
        quote_ident(&format!("{}_commits", self.config.table_prefix))
    }
}

/// The encoded edge identity the SQL-text upsert writes: empty for an edge
/// without an id, `id:` followed by the id otherwise. The two must agree;
/// `prepared_bulk_load_writes_exactly_the_rows_of_the_sql_text_upserts`
/// compares the stored rows of both paths.
fn edge_identity_key(edge: &Edge) -> String {
    edge.id
        .as_ref()
        .map_or_else(String::new, |id| format!("id:{}", id.as_str()))
}

fn prepared_upsert_nodes_sql(table: &str, rows: usize) -> String {
    let values = vec!["(?, ?, ?)"; rows].join(", ");
    format!(
        "INSERT INTO {table} (id, label, props) VALUES {values}
         ON CONFLICT(id) DO UPDATE SET
            label = excluded.label,
            props = excluded.props"
    )
}

fn prepared_upsert_edges_sql(table: &str, rows: usize) -> String {
    let values = vec!["(?, ?, ?, ?, ?, ?)"; rows].join(", ");
    format!(
        "INSERT INTO {table} (id, from_id, to_id, label, props, identity_key) VALUES {values}
         ON CONFLICT(from_id, label, to_id, identity_key) DO UPDATE SET
            id = excluded.id,
            props = excluded.props"
    )
}

/// The same rows as [`prepared_upsert_nodes_sql`] without the conflict
/// clause: on a table that was empty when the load began there is nothing to
/// conflict with, and the upsert's index probe per row is pure cost.
fn prepared_insert_nodes_sql(table: &str, rows: usize) -> String {
    let values = vec!["(?, ?, ?)"; rows].join(", ");
    format!("INSERT INTO {table} (id, label, props) VALUES {values}")
}

/// The same rows as [`prepared_upsert_edges_sql`] without the conflict clause.
fn prepared_insert_edges_sql(table: &str, rows: usize) -> String {
    let values = vec!["(?, ?, ?, ?, ?, ?)"; rows].join(", ");
    format!("INSERT INTO {table} (id, from_id, to_id, label, props, identity_key) VALUES {values}")
}

/// Whether an error is a key collision, so a batch that took the plain-INSERT
/// path can be replayed as an upsert. Deliberately broad: Turso's wording is
/// not pinned down here, and replaying a batch as an upsert is always correct.
fn is_key_collision(err: &GrustError) -> bool {
    let msg = err.to_string().to_ascii_lowercase();
    msg.contains("constraint") || msg.contains("unique") || msg.contains("duplicate")
}

impl TursoGraphStore {
    /// `put_graph`: the rows of `graph` as prepared multi-row upserts.
    async fn put_graph_rows(&self, graph: &Graph) -> Result<LoadReport> {
        let rows = self.config.batch_size.max(1);
        // A load whose target tables are empty right now cannot collide, so
        // its batches insert without the upsert's conflict clause (and its
        // index probe per row). The flag covers this call only, and is cleared
        // on every exit so an ordinary later write never takes that path. Each
        // side is only checked when the graph has rows for it.
        let fresh = (graph.nodes.is_empty() || !self.table_has_rows(&self.nodes_table()).await?)
            && (graph.edges.is_empty() || !self.table_has_rows(&self.edges_table()).await?);
        self.loading_empty_tables.store(fresh, Ordering::Release);
        let loaded = self.put_graph_rows_inner(graph, rows).await;
        self.loading_empty_tables.store(false, Ordering::Release);
        loaded
    }

    async fn put_graph_rows_inner(&self, graph: &Graph, rows: usize) -> Result<LoadReport> {
        if self.config.journal_mode == TursoJournalMode::Mvcc
            && self.bulk_load_via_wal.load(Ordering::Acquire)
        {
            return self.put_graph_rows_via_wal(graph, rows).await;
        }
        if self.config.journal_mode == TursoJournalMode::Mvcc {
            // MVCC keeps every row version of an open transaction in memory
            // until it commits, so one BEGIN CONCURRENT around a whole load
            // grows with the load and a conflict retries all of it: the
            // adversarial-graph strain benchmark measured about 1,500 edges/s
            // this way. Committing every MVCC_LOAD_COMMIT_STATEMENTS batches
            // keeps each transaction small; a load is no longer all-or-nothing
            // under MVCC, and a failure leaves the groups committed before it.
            //
            // Under the default synchronous = FULL every MVCC commit fsyncs
            // the logical log while holding Turso's global commit lock. The
            // load runs at NORMAL, which skips the per-commit fsync; the
            // TRUNCATE checkpoint below still fsyncs, so the load is durable
            // when put_graph returns. The connection's previous setting is
            // restored whether or not the load succeeds.
            let synchronous = self.query_scalar_i64("PRAGMA synchronous").await?;
            self.execute_discarding_rows("PRAGMA synchronous = NORMAL")
                .await?;
            let loaded = self.put_mvcc_parallel(graph, rows).await;
            self.execute_discarding_rows(&format!("PRAGMA synchronous = {synchronous}"))
                .await?;
            loaded?;
        } else {
            self.load_transaction(&graph.nodes, &graph.edges, false, rows)
                .await?;
        }
        // End every load in a TRUNCATE checkpoint, inside the load interval.
        // WAL: one transaction leaves the whole load in the write-ahead log,
        // and every read until the next checkpoint pays to look through it.
        // MVCC: the automatic checkpoints leave up to a threshold's worth of
        // the load in the logical log and its row versions in memory; this
        // folds them into the database file, so the load returns durable in
        // the B-tree and with the in-memory store drained.
        self.execute_discarding_rows("PRAGMA wal_checkpoint(TRUNCATE)")
            .await?;
        Ok(LoadReport {
            nodes: graph.nodes.len(),
            edges: graph.edges.len(),
        })
    }

    /// An MVCC store's `put_graph` run through WAL (`set_bulk_load_via_wal`):
    /// switch to WAL, load everything in one transaction, checkpoint, switch
    /// back to MVCC whether or not the load succeeded.
    async fn put_graph_rows_via_wal(&self, graph: &Graph, rows: usize) -> Result<LoadReport> {
        self.switch_journal_mode("wal").await?;
        let loaded = async {
            self.load_transaction(&graph.nodes, &graph.edges, false, rows)
                .await?;
            self.execute_discarding_rows("PRAGMA wal_checkpoint(TRUNCATE)")
                .await
        }
        .await;
        let back = self.switch_journal_mode("mvcc").await;
        loaded?;
        back?;
        Ok(LoadReport {
            nodes: graph.nodes.len(),
            edges: graph.edges.len(),
        })
    }

    /// Set the database's journal mode and confirm the engine reports it.
    async fn switch_journal_mode(&self, want: &str) -> Result<()> {
        let got = self
            .query_scalar_text(&format!("PRAGMA journal_mode = {want}"))
            .await?;
        if got.as_deref() == Some(want) {
            Ok(())
        } else {
            Err(GrustError::Backend(format!(
                "Turso did not switch journal_mode to {want}; it reports {got:?}"
            )))
        }
    }

    /// The MVCC load with `mvcc_load_parallelism` writers: nodes, then
    /// edges, each split into that many contiguous slices, every slice loaded
    /// on its own shared connection and task.
    ///
    /// Automatic checkpoints cannot run while another writer's transaction
    /// is open (they fail Busy and are skipped), so free-running writers kept
    /// every row version resident: 14–15 GB at 5 M edges against 1.7 GB for
    /// one writer. The writers therefore advance in rounds of at most
    /// `MVCC_PARALLEL_ROUND_GROUPS` commit groups each; after every round,
    /// with nothing in flight, one TRUNCATE checkpoint folds the round into
    /// the database file. The first error is returned after its round ends.
    async fn put_mvcc_parallel(&self, graph: &Graph, rows: usize) -> Result<()> {
        let writers = self.mvcc_load_parallelism.load(Ordering::Acquire);
        if writers <= 1 || graph.nodes.len() + graph.edges.len() < 2 * rows {
            return self.put_mvcc_groups(graph, rows).await;
        }
        let mut handles = Vec::with_capacity(writers);
        for _ in 0..writers {
            let handle = self.connect_shared().await?;
            handle
                .execute_discarding_rows("PRAGMA synchronous = NORMAL")
                .await?;
            handle
                .execute_discarding_rows(&format!(
                    "PRAGMA cache_size = -{MVCC_LOAD_WRITER_CACHE_KIB}"
                ))
                .await?;
            handles.push(Arc::new(handle));
        }
        // Turso runs an inline garbage-collection pass on the commit path
        // every mvcc_gc_threshold new row versions; a bulk load leaves nothing
        // worth collecting, and the round checkpoints below drain the versions
        // anyway. The store's own threshold is restored after the load.
        let gc = self.query_scalar_i64("PRAGMA mvcc_gc_threshold").await?;
        self.execute_discarding_rows("PRAGMA mvcc_gc_threshold = -1")
            .await?;
        let loaded = self.put_mvcc_parallel_phases(graph, rows, &handles).await;
        self.execute_discarding_rows(&format!("PRAGMA mvcc_gc_threshold = {gc}"))
            .await?;
        loaded
    }

    /// The rounds of a parallel MVCC load: nodes, then edges, each writer
    /// taking one slice per round, with a checkpoint between rounds.
    async fn put_mvcc_parallel_phases(
        &self,
        graph: &Graph,
        rows: usize,
        handles: &[Arc<TursoGraphStore>],
    ) -> Result<()> {
        let writers = handles.len();
        let slices = |len: usize| -> Vec<std::ops::Range<usize>> {
            let per = len.div_ceil(writers).max(1);
            (0..len)
                .step_by(per)
                .map(|s| s..(s + per).min(len))
                .collect()
        };
        let round = MVCC_PARALLEL_ROUND_GROUPS * MVCC_LOAD_COMMIT_STATEMENTS * rows;
        for phase in [false, true] {
            let len = if phase {
                graph.edges.len()
            } else {
                graph.nodes.len()
            };
            let ranges = slices(len);
            let mut offset = 0;
            loop {
                let mut tasks = Vec::new();
                for (range, handle) in ranges.iter().zip(handles.iter().cloned()) {
                    let start = range.start + offset;
                    if start >= range.end {
                        continue;
                    }
                    let part_range = start..(start + round).min(range.end);
                    let part = if phase {
                        Graph::new(Vec::new(), graph.edges[part_range].to_vec())
                    } else {
                        Graph::new(graph.nodes[part_range].to_vec(), Vec::new())
                    };
                    tasks.push(tokio::spawn(async move {
                        handle.put_mvcc_groups(&part, rows).await
                    }));
                }
                if tasks.is_empty() {
                    break;
                }
                let mut first_err = None;
                for task in tasks {
                    let outcome = task.await.map_err(|err| {
                        GrustError::Backend(format!("Turso parallel load task failed: {err}"))
                    });
                    if let Err(err) = outcome.and_then(|r| r) {
                        first_err.get_or_insert(err);
                    }
                }
                if let Some(err) = first_err {
                    return Err(err);
                }
                self.execute_discarding_rows("PRAGMA wal_checkpoint(TRUNCATE)")
                    .await?;
                offset += round;
            }
        }
        Ok(())
    }

    /// The MVCC load body: nodes, then edges, each committed in groups of
    /// `MVCC_LOAD_COMMIT_STATEMENTS` batches.
    async fn put_mvcc_groups(&self, graph: &Graph, rows: usize) -> Result<()> {
        let group = MVCC_LOAD_COMMIT_STATEMENTS * rows;
        for chunk in graph.nodes.chunks(group) {
            self.load_transaction(chunk, &[], true, rows).await?;
        }
        for chunk in graph.edges.chunks(group) {
            self.load_transaction(&[], chunk, true, rows).await?;
        }
        Ok(())
    }

    /// Upsert `nodes` then `edges` in one transaction on the shared
    /// connection, with the same gate, rollback and MVCC retry handling as
    /// [`Self::execute_transaction`].
    async fn load_transaction(
        &self,
        nodes: &[Node],
        edges: &[Edge],
        concurrent: bool,
        rows: usize,
    ) -> Result<()> {
        const MAX_ATTEMPTS: usize = 8;
        if nodes.is_empty() && edges.is_empty() {
            return Ok(());
        }
        let _gate = self.lock_connection().await?;
        let mut attempt = 0;
        loop {
            attempt += 1;
            self.transaction_needs_rollback
                .store(true, Ordering::Release);
            let result = async {
                self.execute_unlocked(if concurrent {
                    "BEGIN CONCURRENT"
                } else {
                    "BEGIN"
                })
                .await?;
                self.upsert_rows_unlocked(nodes, edges, rows).await?;
                self.execute_unlocked("COMMIT").await
            }
            .await;
            match result {
                Ok(()) => {
                    self.transaction_needs_rollback
                        .store(false, Ordering::Release);
                    return Ok(());
                }
                Err(err) => {
                    if let Err(recovery_err) = self.recover_transaction_unlocked().await {
                        return Err(GrustError::Backend(format!(
                            "{err}; Turso transaction recovery failed: {recovery_err}"
                        )));
                    }
                    if concurrent && is_mvcc_conflict(&err) && attempt < MAX_ATTEMPTS {
                        continue;
                    }
                    return Err(err);
                }
            }
        }
    }

    /// Multi-row upserts of `rows` rows each through prepared statements
    /// with bound values: the statement is parsed once per row count instead
    /// of once per batch, and no row is rendered into SQL text.
    async fn upsert_rows_unlocked(
        &self,
        nodes: &[Node],
        edges: &[Edge],
        rows: usize,
    ) -> Result<()> {
        self.invalidate_snapshot();
        // A load into tables that were empty when it began cannot collide, so
        // its batches skip the upsert's conflict clause (and its index probe
        // per row). A batch that collides anyway — duplicate keys inside the
        // same load — is replayed as an upsert, which is always correct.
        let fresh = self.loading_empty_tables.load(Ordering::Acquire);
        let nodes_table = self.nodes_table();
        for chunk in nodes.chunks(rows) {
            let mut params = Vec::with_capacity(chunk.len() * 3);
            for node in chunk {
                params.push(turso::Value::Text(node.id.as_str().to_string()));
                params.push(turso::Value::Text(node.label.as_str().to_string()));
                params.push(turso::Value::Text(grust_sql_core::props_to_json(
                    &node.props,
                )?));
            }
            let upsert = prepared_upsert_nodes_sql(&nodes_table, chunk.len());
            if fresh {
                let insert = prepared_insert_nodes_sql(&nodes_table, chunk.len());
                match self
                    .execute_prepared_unlocked(&insert, params.clone())
                    .await
                {
                    Ok(()) => continue,
                    Err(err) if is_key_collision(&err) => {}
                    Err(err) => return Err(err),
                }
            }
            self.execute_prepared_unlocked(&upsert, params).await?;
        }
        let edges_table = self.edges_table();
        for chunk in edges.chunks(rows) {
            let mut params = Vec::with_capacity(chunk.len() * 6);
            for edge in chunk {
                params.push(match &edge.id {
                    Some(id) => turso::Value::Text(id.as_str().to_string()),
                    None => turso::Value::Null,
                });
                params.push(turso::Value::Text(edge.from.as_str().to_string()));
                params.push(turso::Value::Text(edge.to.as_str().to_string()));
                params.push(turso::Value::Text(edge.label.as_str().to_string()));
                params.push(turso::Value::Text(grust_sql_core::props_to_json(
                    &edge.props,
                )?));
                params.push(turso::Value::Text(edge_identity_key(edge)));
            }
            let upsert = prepared_upsert_edges_sql(&edges_table, chunk.len());
            if fresh {
                let insert = prepared_insert_edges_sql(&edges_table, chunk.len());
                match self
                    .execute_prepared_unlocked(&insert, params.clone())
                    .await
                {
                    Ok(()) => continue,
                    Err(err) if is_key_collision(&err) => {}
                    Err(err) => return Err(err),
                }
            }
            self.execute_prepared_unlocked(&upsert, params).await?;
        }
        Ok(())
    }

    async fn execute_prepared_unlocked(&self, sql: &str, params: Vec<turso::Value>) -> Result<()> {
        let mut statement =
            self.conn.prepare_cached(sql).await.map_err(|err| {
                GrustError::Backend(format!("Turso prepare failed: {err}: {sql}"))
            })?;
        statement
            .execute(params)
            .await
            .map_err(|err| GrustError::Backend(format!("Turso command failed: {err}: {sql}")))?;
        Ok(())
    }
}

#[async_trait]
impl GraphStore for TursoGraphStore {
    async fn apply_schema(&self, schema: &GraphSchema) -> Result<()> {
        self.bootstrap().await?;
        self.execute(&turso_schema_sql(
            &self.config,
            &self.nodes_table(),
            &self.edges_table(),
            schema,
        )?)
        .await
    }

    async fn put_node(&self, node: &Node) -> Result<PutOutcome> {
        self.execute_data(&upsert_nodes_sql(
            &self.nodes_table(),
            std::slice::from_ref(node),
        )?)
        .await?;
        Ok(PutOutcome::Upserted)
    }

    async fn put_edge(&self, edge: &Edge) -> Result<PutOutcome> {
        self.execute_data(&upsert_edges_sql(
            &self.edges_table(),
            std::slice::from_ref(edge),
        )?)
        .await?;
        Ok(PutOutcome::Upserted)
    }

    /// Load the whole graph: in WAL mode one transaction, so one durable
    /// commit for all of its rows and either every row lands or none does.
    ///
    /// Rows go in as multi-row upserts of `batch_size` rows through prepared
    /// statements with bound values:
    /// each statement shape is parsed once per load, not once per batch, and
    /// only one batch of bound values is alive at a time instead of the SQL
    /// text of the whole load. The upserts are the same `ON CONFLICT DO
    /// UPDATE` statements as [`upsert_nodes_sql`] and [`upsert_edges_sql`], so
    /// a repeated key keeps its last row, as before.
    async fn put_graph(&self, graph: &Graph) -> Result<LoadReport> {
        self.put_graph_rows(graph).await
    }

    async fn get_node(&self, id: &NodeId) -> Result<Option<Node>> {
        let sql = grust_sql_core::select_node_sql(&TursoDialect, &self.nodes_table(), id, sql_str);
        Ok(self.query_nodes(&sql).await?.into_iter().next())
    }

    async fn get_nodes(&self, ids: &[NodeId]) -> Result<Vec<Node>> {
        match grust_sql_core::select_nodes_sql(&TursoDialect, &self.nodes_table(), ids, sql_str) {
            Some(sql) => self.query_nodes(&sql).await,
            None => Ok(Vec::new()),
        }
    }

    async fn get_edges(&self, query: EdgeQuery) -> Result<Vec<Edge>> {
        let sql =
            grust_sql_core::select_edges_sql(&TursoDialect, &self.edges_table(), query, sql_str);
        self.query_edges(&sql).await
    }

    async fn traverse(&self, traversal: Traversal) -> Result<Vec<Node>> {
        let sql = traversal_sql(&self.nodes_table(), &self.edges_table(), &traversal)?;
        self.query_nodes(&sql).await
    }
}

#[async_trait]
impl GraphAdminStore for TursoGraphStore {
    async fn bootstrap(&self) -> Result<()> {
        let sql = bootstrap_sql(&self.config, &self.nodes_table(), &self.edges_table())?;
        let _gate = self.lock_connection().await?;
        if self.edges_table_is_legacy_unlocked().await? {
            // Both the endpoint-only key and the unreleased raw id_key need
            // migration to the encoded optional identity.
            // Rebuild once in one transaction. Encoding the stored optional ID
            // preserves update identity and distinguishes None from Some("").
            // Old indexes leave with the old table; the second bootstrap below
            // recreates them.
            let edges = self.edges_table();
            let old = quote_ident(&format!("{}_edges_v1", self.config.table_prefix));
            self.execute_unlocked(&format!(
                "BEGIN;
                 ALTER TABLE {edges} RENAME TO {old};
                 {sql};
                 INSERT INTO {edges} (id, from_id, to_id, label, props, identity_key)
                     SELECT id, from_id, to_id, label, props,
                         CASE WHEN id IS NULL THEN '' ELSE 'id:' || id END FROM {old};
                 DROP TABLE {old};
                 COMMIT;"
            ))
            .await?;
        }
        self.execute_unlocked(&sql).await?;
        // Stores bootstrapped before the edge-source index was retired still
        // carry it: every plan already reads source lookups from the edge
        // primary key, so dropping it changes no answer and ends its cost.
        if self.edges_from_index_exists_unlocked().await? {
            let idx = quote_ident(&format!("{}_edges_from_idx", self.config.table_prefix));
            self.execute_unlocked(&format!("DROP INDEX IF EXISTS {idx}"))
                .await?;
        }
        Ok(())
    }

    async fn clear(&self) -> Result<()> {
        self.execute(&format!(
            "DELETE FROM {};
             DELETE FROM {};
             DELETE FROM {};",
            self.edges_table(),
            self.nodes_table(),
            self.commits_table()
        ))
        .await
    }
}

#[async_trait]
impl GraphMutationStore for TursoGraphStore {
    fn mutation_atomicity(&self) -> GraphMutationAtomicity {
        GraphMutationAtomicity::Transactional
    }

    async fn delete_node(&self, id: &NodeId) -> Result<()> {
        self.execute_data(&delete_node_sql(&self.nodes_table(), id))
            .await
    }

    async fn delete_edge(&self, from: &NodeId, label: &Label, to: &NodeId) -> Result<()> {
        self.execute_data(&delete_edge_sql(&self.edges_table(), from, label, to))
            .await
    }

    async fn apply_mutations(&self, mutations: &[GraphMutation]) -> Result<()> {
        if mutations.is_empty() {
            return Ok(());
        }
        let nodes = self.nodes_table();
        let edges = self.edges_table();
        let statements = mutations
            .iter()
            .map(|mutation| {
                grust_sql_core::mutation_sql(&TursoDialect, &nodes, &edges, mutation, sql_str)
            })
            .collect::<Result<Vec<_>>>()?;
        match self.config.journal_mode {
            TursoJournalMode::Wal => self.execute_transaction(&statements, false).await,
            TursoJournalMode::Mvcc => self.execute_concurrent(&statements).await,
        }
    }
}

#[async_trait]
impl CypherMutationExecutor for TursoGraphStore {
    async fn execute_cypher_mutation_plan(
        &self,
        plan: &GraphMutationPlan,
    ) -> Result<GraphMutationReport> {
        // Lower every fixed operation before opening the transaction so an
        // unsupported trailing operation cannot commit a valid prefix.
        let prepared = plan
            .operations
            .iter()
            .map(|operation| match operation {
                GraphMutationPlanOp::PatchMatchingNodes { .. } => Ok(None),
                other => mutation_sql(
                    &self.nodes_table(),
                    &self.edges_table(),
                    &GraphMutation::from(other.clone()),
                )
                .map(Some),
            })
            .collect::<Result<Vec<_>>>()?;

        const MAX_ATTEMPTS: usize = 8;
        let concurrent = self.config.journal_mode == TursoJournalMode::Mvcc;
        let _gate = self.lock_connection().await?;
        let mut attempt = 0;
        loop {
            attempt += 1;
            let mut report = plan.report();
            self.transaction_needs_rollback
                .store(true, Ordering::Release);
            let execution = async {
                self.execute_unlocked(if concurrent {
                    "BEGIN CONCURRENT"
                } else {
                    "BEGIN"
                })
                .await?;
                for (operation, prepared_sql) in plan.operations.iter().zip(&prepared) {
                    match operation {
                        GraphMutationPlanOp::PatchMatchingNodes {
                            label,
                            props,
                            predicates,
                            patch,
                            ..
                        } => {
                            let nodes = self
                                .matching_nodes_unlocked(label.as_ref(), props, predicates)
                                .await?;
                            report.matched_rows += nodes.len();
                            report.node_patches += nodes.len();
                            report.changed_nodes += nodes.len();
                            for node in nodes {
                                let sql = patch_node_sql(&self.nodes_table(), &node.id, patch)?;
                                self.execute_unlocked(&sql).await?;
                            }
                        }
                        _ => {
                            self.execute_unlocked(
                                prepared_sql
                                    .as_deref()
                                    .expect("fixed mutation SQL was precomputed"),
                            )
                            .await?;
                        }
                    }
                }
                self.execute_unlocked("COMMIT").await?;
                Ok::<_, GrustError>(report)
            }
            .await;

            match execution {
                Ok(report) => {
                    self.transaction_needs_rollback
                        .store(false, Ordering::Release);
                    return Ok(report);
                }
                Err(err) => {
                    if let Err(recovery_err) = self.recover_transaction_unlocked().await {
                        return Err(GrustError::Backend(format!(
                            "{err}; Turso transaction recovery failed: {recovery_err}"
                        )));
                    }
                    if concurrent && is_mvcc_conflict(&err) && attempt < MAX_ATTEMPTS {
                        continue;
                    }
                    return Err(err);
                }
            }
        }
    }
}

pub fn bootstrap_sql(config: &TursoConfig, nodes_table: &str, edges_table: &str) -> Result<String> {
    let graph_sql = grust_sql_core::universal_bootstrap_sql(
        &TursoDialect,
        &config.table_prefix,
        &UniversalTableRefs {
            nodes: nodes_table.to_string(),
            edges: edges_table.to_string(),
        },
        Some("PRAGMA foreign_keys = ON"),
        quote_ident,
    );
    Ok(format!(
        "{graph_sql}\n{}",
        guarded_commit::ledger_bootstrap_sql(config)
    ))
}

pub fn turso_schema_sql(
    config: &TursoConfig,
    nodes_table: &str,
    edges_table: &str,
    schema: &GraphSchema,
) -> Result<String> {
    grust_sql_core::schema_sql(
        &TursoDialect,
        grust_sql_core::GraphSqlSchemaLayout {
            table_prefix: &config.table_prefix,
            nodes_table,
            edges_table,
        },
        schema,
        quote_ident,
        quote_ident,
        sql_str,
        turso_prop_expr,
    )
}

fn turso_prop_expr(field: &Field) -> String {
    let value = format!(
        "json_extract(props, '$.{}.value')",
        json_path_key(&field.name)
    );
    match field.ty {
        FieldType::String
        | FieldType::DateTime
        | FieldType::StringArray
        | FieldType::IntArray
        | FieldType::FloatArray
        | FieldType::Json => value,
        FieldType::Int => format!("CAST({value} AS INTEGER)"),
        FieldType::Float => format!("CAST({value} AS REAL)"),
        FieldType::Bool => format!("CAST({value} AS INTEGER)"),
    }
}

/// Page cache per connection, in KiB (`PRAGMA cache_size = -1048576`).
///
/// The engine's native default is 2,000 pages, about 8 MB: a load outgrows
/// it within the first million edges, and from then on every insert into
/// the edge key, the two edge indexes and the foreign-key probes of the node
/// key is a page read. At 1 GiB a 2M-edge load runs at 42k edges/s instead
/// of 24k, and a 30M-edge load holds 27-37k edges/s per 5M-edge batch.
/// The cache fills lazily, so a small store never holds more than its pages.
pub const PAGE_CACHE_KIB: u64 = 1024 * 1024;

/// Batches per MVCC transaction in `put_graph`: each transaction commits this
/// many `batch_size`-row statements, so with the default batch size of 500
/// rows about ten thousand rows at a time.
pub const MVCC_LOAD_COMMIT_STATEMENTS: usize = 20;

/// Commit groups each parallel MVCC load writer runs between the checkpoints
/// that bound the load's resident row versions (see `put_mvcc_parallel`).
pub const MVCC_PARALLEL_ROUND_GROUPS: usize = 5;

/// Page cache for one parallel load writer's connection. A writer streams
/// rows in and re-reads almost nothing, so it does not need the store's
/// `PAGE_CACHE_KIB`; eight writers at that size budget 8 GiB of cache alone.
pub const MVCC_LOAD_WRITER_CACHE_KIB: u64 = 128 * 1024;

pub fn upsert_nodes_sql(table: &str, nodes: &[Node]) -> Result<String> {
    TursoDialect.upsert_nodes_sql(table, nodes)
}

pub fn upsert_edges_sql(table: &str, edges: &[Edge]) -> Result<String> {
    TursoDialect.upsert_edges_sql(table, edges)
}

pub fn delete_node_sql(nodes_table: &str, id: &NodeId) -> String {
    grust_sql_core::delete_node_sql(nodes_table, id, sql_str)
}

pub fn patch_node_sql(nodes_table: &str, id: &NodeId, props: &Props) -> Result<String> {
    TursoDialect.patch_node_sql(nodes_table, id, props)
}

pub fn delete_edge_sql(edges_table: &str, from: &NodeId, label: &Label, to: &NodeId) -> String {
    grust_sql_core::delete_edge_sql(edges_table, from, label, to, sql_str)
}

pub fn mutation_sql(
    nodes_table: &str,
    edges_table: &str,
    mutation: &GraphMutation,
) -> Result<String> {
    grust_sql_core::mutation_sql(&TursoDialect, nodes_table, edges_table, mutation, sql_str)
}

pub fn apply_mutations_sql(
    nodes_table: &str,
    edges_table: &str,
    mutations: &[GraphMutation],
) -> Result<String> {
    grust_sql_core::apply_mutations_sql(&TursoDialect, nodes_table, edges_table, mutations, sql_str)
}

pub fn traversal_sql(
    nodes_table: &str,
    edges_table: &str,
    traversal: &Traversal,
) -> Result<String> {
    grust_sql_core::traversal_sql(&TursoDialect, nodes_table, edges_table, traversal, sql_str)
}

fn json_predicate(alias: &str, key: &str, value: &Value) -> Result<String> {
    validate_identifier(key)?;
    let path = format!("$.{}.value", json_path_key(key));
    let prop = format!("json_extract({alias}.props, {})", sql_str(&path));
    Ok(match value {
        Value::Null => format!("json_type({alias}.props, {}) = 'null'", sql_str(&path)),
        Value::Bool(value) => format!("{prop} = {}", if *value { 1 } else { 0 }),
        Value::Int(value) => format!("CAST({prop} AS INTEGER) = {value}"),
        Value::Float(value) => format!("CAST({prop} AS REAL) = {value}"),
        Value::String(value) => format!("{prop} = {}", sql_str(value)),
        other => {
            let json = serde_json::to_string(other)
                .map_err(|err| GrustError::Serialization(err.to_string()))?;
            format!("{prop} = {}", sql_str(&json))
        }
    })
}

impl TursoGraphStore {
    async fn matching_nodes_unlocked(
        &self,
        label: Option<&Label>,
        props: &Props,
        predicates: &[GraphPropertyPredicate],
    ) -> Result<Vec<Node>> {
        let mut clauses = Vec::new();
        if let Some(label) = label {
            clauses.push(format!("n.label = {}", sql_str(label.as_str())));
        }
        for (key, value) in props {
            if key == "id" {
                let Some(id) = value.as_str() else {
                    return Ok(Vec::new());
                };
                clauses.push(format!("n.id = {}", sql_str(id)));
            } else {
                clauses.push(json_predicate("n", key, value)?);
            }
        }
        let where_clause = if clauses.is_empty() {
            String::new()
        } else {
            format!(" WHERE {}", clauses.join(" AND "))
        };
        let sql = format!(
            "SELECT n.id, n.label, {} AS props FROM {} n{where_clause}",
            TursoDialect.node_props_select("n"),
            self.nodes_table()
        );
        let mut nodes = self.query_nodes_unlocked(&sql).await?;
        if !predicates.is_empty() {
            nodes.retain(|node| {
                predicates
                    .iter()
                    .all(|predicate| predicate.matches(node.props.get(&predicate.key)))
            });
        }
        Ok(nodes)
    }
}

fn row_to_node(row: &turso::Row) -> Result<Node> {
    let id = row_text(row, 0, "node id")?;
    let label = row_text(row, 1, "node label")?;
    let props_json = row_text(row, 2, "node props")?;
    let props: Props = serde_json::from_str(&props_json)
        .map_err(|err| GrustError::Serialization(format!("node props JSON parse failed: {err}")))?;
    Ok(Node {
        id: NodeId::new(id),
        label: Label::new(label),
        props,
    })
}

fn row_to_edge(row: &turso::Row) -> Result<Edge> {
    let id = row_optional_text(row, 0, "edge id")?;
    let from_id = row_text(row, 1, "edge from_id")?;
    let to_id = row_text(row, 2, "edge to_id")?;
    let label = row_text(row, 3, "edge label")?;
    let props_json = row_text(row, 4, "edge props")?;
    let props: Props = serde_json::from_str(&props_json)
        .map_err(|err| GrustError::Serialization(format!("edge props JSON parse failed: {err}")))?;
    let mut edge = Edge::new(label, from_id, to_id, props);
    edge.id = id.map(EdgeId::new);
    Ok(edge)
}

fn row_text(row: &turso::Row, idx: usize, name: &str) -> Result<String> {
    row_optional_text(row, idx, name)?.ok_or_else(|| {
        GrustError::Backend(format!("Turso {name} column unexpectedly contained NULL"))
    })
}

fn row_optional_text(row: &turso::Row, idx: usize, name: &str) -> Result<Option<String>> {
    match row
        .get_value(idx)
        .map_err(|err| GrustError::Backend(format!("failed to read Turso {name}: {err}")))?
    {
        turso::Value::Text(value) => Ok(Some(value)),
        turso::Value::Null => Ok(None),
        other => Err(GrustError::Backend(format!(
            "Turso {name} column had unexpected value {other:?}"
        ))),
    }
}

/// Whether a backend error is a retryable MVCC conflict (write-write conflict,
/// busy / busy-snapshot, or a generic conflict) — the engine aborts the
/// `BEGIN CONCURRENT` transaction in these cases and the write can be retried.
fn is_mvcc_conflict(err: &GrustError) -> bool {
    let msg = err.to_string().to_ascii_lowercase();
    msg.contains("conflict") || msg.contains("busy") || msg.contains("snapshot")
}

// ---------------------------------------------------------------------------
// Portable read pushdown (PUSHDOWN2 follow-on: Turso joins the consumers)
// ---------------------------------------------------------------------------

/// The pushdown [`SqlDialect`] for Turso's universal tables: **tagged-JSON**
/// props (each property is stored as `{"type": t, "value": v}`, so scalar
/// extraction is `$.key.value`), `from_id`/`to_id`/`label` edge columns, and
/// no recursive CTEs or JSON table functions in the embedded engine — those
/// leaves report unsupported and the store falls back to the reference.
#[derive(Clone, Debug)]
pub struct TursoReadDialect {
    nodes: String,
    edges: String,
}

impl TursoReadDialect {
    pub fn new(table_prefix: &str) -> Self {
        Self {
            nodes: format!("{table_prefix}_nodes"),
            edges: format!("{table_prefix}_edges"),
        }
    }
}

impl SqlDialect for TursoReadDialect {
    fn nodes_table(&self) -> &str {
        &self.nodes
    }
    fn edges_table(&self) -> &str {
        &self.edges
    }
    fn quote_ident(&self, ident: &str) -> String {
        quote_ident(ident)
    }
    fn json_property(&self, props_column: &str, key: &str) -> String {
        // Tagged storage: extract the scalar payload under the type tag.
        format!("json_extract({props_column}, '$.{key}.value')")
    }
    fn exact_string_property_eq(
        &self,
        props_column: &str,
        key: &str,
        value: &str,
    ) -> Option<String> {
        if value.contains('\0') {
            return None;
        }
        let path = self.string_literal(&format!("$.{key}.value"));
        let value = self.string_literal(value);
        Some(format!(
            "(json_type({props_column}, {path}) = 'text' AND \
             json_extract({props_column}, {path}) COLLATE BINARY = {value})"
        ))
    }
    fn cast_int(&self, expr: &str) -> String {
        format!("CAST({expr} AS INTEGER)")
    }
    fn cast_float(&self, expr: &str) -> String {
        format!("CAST({expr} AS REAL)")
    }
    fn string_literal(&self, value: &str) -> String {
        sql_str(value)
    }
    fn string_predicate(&self, expr: &str, op: StrOp, needle: &str) -> String {
        // Mirrors `SqliteDialect`: literal (non-LIKE) matching, NULL-propagating.
        let n = self.string_literal(needle);
        match op {
            StrOp::StartsWith => format!("instr({expr}, {n}) = 1"),
            StrOp::Contains => format!("instr({expr}, {n}) > 0"),
            StrOp::EndsWith => format!("substr({expr}, -{}) = {n}", needle.chars().count()),
        }
    }
    fn bool_literal_sql(&self, value: bool) -> String {
        // json_extract returns the tagged JSON boolean as integer 1/0.
        if value {
            "1".to_string()
        } else {
            "0".to_string()
        }
    }
    fn orders_json_typed(&self) -> bool {
        // json_extract of the tagged `.value` yields INTEGER/REAL/TEXT.
        true
    }
    fn recursive_cte_supported(&self) -> bool {
        // The embedded turso (limbo) engine does not execute WITH RECURSIVE.
        false
    }
    fn edge_src_col(&self) -> &str {
        "from_id"
    }
    fn edge_dst_col(&self) -> &str {
        "to_id"
    }
    fn edge_type_col(&self) -> &str {
        "label"
    }
}

impl TursoGraphStore {
    fn read_dialect(&self) -> TursoReadDialect {
        TursoReadDialect::new(&self.config.table_prefix)
    }

    /// The resident typed snapshot of this store: an immutable `TypedGraphIndex`
    /// over a full read of the node and edge tables, built on the first call
    /// after any write and shared by every later call until the next write.
    ///
    /// The build is a full scan of the store plus index construction, and is
    /// meant to happen once after a load, outside any query's timing. Reads
    /// through `GraphStore` are unaffected; the snapshot serves the indexed
    /// Cypher entrypoints (`grust_cypher::read::run_read_query_indexed`).
    pub async fn indexed_snapshot(&self) -> Result<Arc<TypedGraphIndex>> {
        // Hold the connection gate from the read through publication: every
        // write needs the gate too, so nothing can change the store between
        // the scan the index is built from and the moment it is cached.
        let _gate = self.lock_connection().await?;
        if let Some(index) = self.cached_snapshot() {
            return Ok(index);
        }
        let graph = Arc::new(self.read_graph_unlocked().await?);
        let index = Arc::new(TypedGraphIndex::new(graph)?);
        *self
            .index_cache
            .lock()
            .expect("turso index cache lock poisoned") = Some(Arc::clone(&index));
        Ok(index)
    }

    fn cached_snapshot(&self) -> Option<Arc<TypedGraphIndex>> {
        self.index_cache
            .lock()
            .expect("turso index cache lock poisoned")
            .clone()
    }

    fn invalidate_snapshot(&self) {
        self.index_cache
            .lock()
            .expect("turso index cache lock poisoned")
            .take();
    }

    /// Materialize the full graph — the reference-executor fallback input.
    pub async fn read_graph(&self) -> Result<Graph> {
        let _gate = self.lock_connection().await?;
        self.read_graph_unlocked().await
    }

    async fn read_graph_unlocked(&self) -> Result<Graph> {
        let nodes = self
            .query_nodes_unlocked(&format!(
                "SELECT id, label, props FROM {}",
                self.nodes_table()
            ))
            .await?;
        let edges = self
            .query_edges_unlocked(&format!(
                "SELECT id, from_id, to_id, label, props FROM {}",
                self.edges_table()
            ))
            .await?;
        Ok(Graph::new(nodes, edges))
    }

    /// Execute pushdown SQL whose result cells decode as optional text.
    async fn run_text_rows(&self, sql: &str, columns: usize) -> Result<Vec<Vec<Option<String>>>> {
        let _gate = self.lock_connection().await?;
        let mut rows = self.conn.query(sql, ()).await.map_err(|err| {
            GrustError::Backend(format!("Turso read pushdown query failed: {err}: {sql}"))
        })?;
        let mut out = Vec::new();
        while let Some(row) = rows.next().await.map_err(|err| {
            GrustError::Backend(format!("Turso read pushdown row failed: {err}: {sql}"))
        })? {
            let mut cells = Vec::with_capacity(columns);
            for i in 0..columns {
                let cell = match row.get_value(i).map_err(|err| {
                    GrustError::Backend(format!("Turso read pushdown cell failed: {err}"))
                })? {
                    turso::Value::Null => None,
                    turso::Value::Text(v) => Some(v),
                    turso::Value::Integer(v) => Some(v.to_string()),
                    turso::Value::Real(v) => Some(v.to_string()),
                    turso::Value::Blob(_) => None,
                };
                cells.push(cell);
            }
            out.push(cells);
        }
        Ok(out)
    }

    /// Portable read entrypoint: the query's `MATCH`/`WHERE`/row-source part
    /// is pushed into SQL over the universal tables where the plan supports
    /// this dialect (node scans, fixed segments, `OPTIONAL MATCH`,
    /// multi-pattern, `UNION`, `WITH` pipelines, subqueries, and the
    /// non-recursive catalog procedures); everything else falls back to the
    /// Memory reference over [`Self::read_graph`]. Eligible single `COUNT(*)`
    /// projections aggregate in SQL and transport only one scalar; final
    /// pagination remains in the shared Rust projection. Results are identical to
    /// [`grust_cypher::read::run_read_query`] by construction.
    pub async fn run_read_query(
        &self,
        cypher: &str,
        params: &CypherParameters,
    ) -> Result<CypherResultTable> {
        let dialect = self.read_dialect();
        if let Some(plan) = plan_read(cypher, params, &NoTypeHints)?
            && plan.supported_by(&dialect)
        {
            if let Some(count) = plan.scalar_count_read()
                && count.supported_by(&dialect)
            {
                let sql = count.to_sql(&dialect)?;
                let rows = self.run_text_rows(&sql, count.column_count()).await?;
                return count.project_text_rows(rows, params);
            }
            if let Some((arms, distinct)) = plan.union_arms() {
                let mut tables = Vec::with_capacity(arms.len());
                for arm in arms {
                    let rows = self
                        .run_text_rows(&arm.to_sql(&dialect), arm.column_count())
                        .await?;
                    tables.push(arm.project_text_rows(&dialect, rows, params)?);
                }
                return combine_union(tables, distinct);
            }
            let rows = self
                .run_text_rows(&plan.to_sql(&dialect), plan.column_count())
                .await?;
            return plan.project_text_rows(&dialect, rows, params);
        }
        let graph = self.read_graph().await?;
        grust_cypher::read::run_read_query(&graph, cypher, params)
    }
}

fn quote_ident(value: &str) -> String {
    grust_sql_core::quote_ident(value)
}

fn sql_str(value: &str) -> String {
    grust_sql_core::sql_str(value)
}

fn validate_identifier(value: &str) -> Result<()> {
    grust_sql_core::validate_identifier("Turso", value)
}

fn json_path_key(value: &str) -> String {
    grust_sql_core::json_path_key(value)
}

#[cfg(test)]
mod tests;

#[derive(Clone, Copy, Debug)]
struct TursoDialect;

impl GraphSqlDialect for TursoDialect {
    fn name(&self) -> &'static str {
        "Turso"
    }

    fn props_column_type(&self) -> &'static str {
        "TEXT"
    }

    fn empty_props_default(&self) -> &'static str {
        "'{}'"
    }

    fn node_props_select(&self, alias: &str) -> String {
        if alias.is_empty() {
            "props".to_string()
        } else {
            format!("{alias}.props")
        }
    }

    fn edge_props_select(&self, alias: &str) -> String {
        self.node_props_select(alias)
    }

    fn json_property_predicate(&self, alias: &str, key: &str, value: &Value) -> Result<String> {
        json_predicate(alias, key, value)
    }

    fn both_direction_join(
        &self,
        edges_table: &str,
        edge_alias: &str,
        prev_alias: &str,
        edge_label: &str,
    ) -> String {
        format!(
            "JOIN (
                SELECT to_id AS next_id, from_id AS current_id, label FROM {edges_table}
                UNION ALL
                SELECT from_id AS next_id, to_id AS current_id, label FROM {edges_table}
            ) {edge_alias} ON {edge_alias}.current_id = {prev_alias}.id{edge_label}"
        )
    }

    fn upsert_nodes_sql(&self, table: &str, nodes: &[Node]) -> Result<String> {
        if nodes.is_empty() {
            return Ok(String::new());
        }
        let rows = nodes
            .iter()
            .map(|node| {
                let props = grust_sql_core::props_to_json(&node.props)?;
                Ok(format!(
                    "({}, {}, {})",
                    sql_str(node.id.as_str()),
                    sql_str(node.label.as_str()),
                    sql_str(&props)
                ))
            })
            .collect::<Result<Vec<_>>>()?
            .join(", ");
        Ok(format!(
            "INSERT INTO {table} (id, label, props) VALUES {rows}
             ON CONFLICT(id) DO UPDATE SET
                label = excluded.label,
                props = excluded.props"
        ))
    }

    /// Edges are keyed by `(from_id, label, to_id, identity_key)`. The key is
    /// empty for no ID and `id:` followed by a present ID (including an empty
    /// ID), so these identities never collide. An edge without an id replaces
    /// the earlier edge between the same endpoints with the same label, while edges
    /// with distinct ids are kept apart, so a multigraph keeps every parallel
    /// edge (as grust-memory and LanceDB already do). Re-putting an id updates
    /// that edge in place.
    fn upsert_edges_sql(&self, table: &str, edges: &[Edge]) -> Result<String> {
        if edges.is_empty() {
            return Ok(String::new());
        }
        let rows = edges
            .iter()
            .map(|edge| {
                let props = grust_sql_core::props_to_json(&edge.props)?;
                let id = edge.id.as_ref().map(|id| sql_str(id.as_str()));
                let identity_key = edge.id.as_ref().map_or_else(
                    || "''".to_string(),
                    |id| sql_str(&format!("id:{}", id.as_str())),
                );
                Ok(format!(
                    "({}, {}, {}, {}, {}, {})",
                    id.unwrap_or_else(|| "NULL".to_string()),
                    sql_str(edge.from.as_str()),
                    sql_str(edge.to.as_str()),
                    sql_str(edge.label.as_str()),
                    sql_str(&props),
                    identity_key
                ))
            })
            .collect::<Result<Vec<_>>>()?
            .join(", ");
        Ok(format!(
            "INSERT INTO {table} (id, from_id, to_id, label, props, identity_key) VALUES {rows}
             ON CONFLICT(from_id, label, to_id, identity_key) DO UPDATE SET
                id = excluded.id,
                props = excluded.props"
        ))
    }

    /// The edge primary key `(from_id, label, to_id, identity_key)` leads with
    /// `from_id`, and Turso's planner reads every source lookup and traversal
    /// hop from it even when `<prefix>_edges_from_idx` exists; that index
    /// only cost a write per edge (a quarter of an MVCC load, a sixth of WAL).
    fn edge_source_index(&self) -> bool {
        false
    }

    fn edge_identity_column(&self) -> Option<&'static str> {
        Some("identity_key")
    }

    fn patch_node_sql(&self, nodes_table: &str, id: &NodeId, props: &Props) -> Result<String> {
        let props = grust_sql_core::props_to_json(props)?;
        Ok(format!(
            "UPDATE {nodes_table} SET props = json_patch(props, {}) WHERE id = {}",
            sql_str(&props),
            sql_str(id.as_str())
        ))
    }
}
