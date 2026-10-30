        }
    }

    /// Get a new TaskContext to run in this session
    pub fn task_ctx(&self) -> Arc<TaskContext> {
        Arc::new(TaskContext::from(self))
    }

    /// Return a new  [`SessionState`] suitable for executing a single query.
    ///
    /// Notes:
    ///
    /// 1. `query_execution_start_time` is set to the current time for the
    ///    returned state.
    ///
    /// 2. The returned state is not shared with the current session state
    ///    and this changes to the returned `SessionState` such as changing
    ///    [`ConfigOptions`] will not be reflected in this `SessionContext`.
    ///
    /// [`ConfigOptions`]: crate::config::ConfigOptions
    pub fn state(&self) -> SessionState {
        let mut state = self.state.read().clone();
        state.mark_start_execution();
        state
    }

    /// Get reference to [`SessionState`]
/// Create a new task context instance from SessionContext
impl From<&SessionContext> for TaskContext {
    fn from(session: &SessionContext) -> Self {
        TaskContext::from(&*session.state.read())
    }
}

