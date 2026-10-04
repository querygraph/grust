# Jev is built into Sail

*Draft blog post, 2026-09-29. Facts from the Sail 0.7.2 release, its Jev
guide and lakehq/sail#2653; numbers are the shipped defaults.*

Sail 0.7.2, released today, is the first query engine with Jev built in.
Five SQL functions call TypeSafe's System One API from inside the engine,
so a Spark Connect client can ask a question of every row of a table and
get a typed answer back as a column, with no UDF, no Python, and no
service of your own in between.

```sql
SELECT
  ticket_id,
  jev_noul(body, 'Is this about billing?').noul            AS billing_probability,
  jev_choice(body, 'Which team owns this?',
             map('billing', 'invoices and refunds',
                 'access',  'logins and permissions',
                 'product', 'features and bugs')).choice    AS owner
FROM support_tickets;
```

## What you get

| Function | Answers |
|---|---|
| `jev_noul(state, instructions [, criteria [, options]])` | the probability of yes, as a `DOUBLE` in [0, 1]; it is not rounded to a boolean |
| `jev_choice(state, instructions, criteria [, options])` | the chosen option, a `MAP` of probabilities over all options, and a confidence |
| `jev_score(state, instructions, criteria [, options])` | a probability-weighted position on a rubric, with the probabilities and a legend |
| `jev_system_one(state, questions [, options])` | several questions at once, answered under their own ids |
| `jev_models([options])` | the models and aliases available to the account |

Every result is one `STRUCT` per input row, and every inference result
also carries the model that answered, the service's request id, Sail's
batch id and the token usage. `state` and `instructions` can be a string or
a `VARIANT`, so JSON goes in with `parse_json` and comes out with its
structure intact; legends and answers come back as `VARIANT`. These
functions are Sail's own: Apache Spark has nothing like them.

## How it runs

The functions are asynchronous inside the engine, not wrappers around a
blocking call. Each one is a DataFusion async scalar function; Sail's
planner moves the call into an asynchronous execution step, and in cluster
mode the plan carries only the function's kind, so workers rebuild the
call without ever receiving a client or a credential.

Rows are batched into requests, up to 64 questions or 256 KiB per request
by default with a 1 MiB hard cap that is measured before any body is
allocated. A per-process runtime bounds the work in flight: 8 concurrent
HTTP attempts, 16 admitted request groups and 16 MiB of reserved request
bytes, all adjustable per worker. Each attempt has a 10 s deadline, retries
are limited by count and by a 30 s time budget, and `Retry-After` is
honored. The API key is read from the environment of the server and of
every worker, never from SQL, and is scrubbed from error messages; SQL can
choose only the model, the deadline, the retry budget and the retry count.

## Why it matters

Row-level inference has lived outside the engine: a UDF, a notebook loop,
a sidecar service, each with its own batching, retries and secrets. Jev in
Sail puts that inside the plan, where the optimizer, the workers and the
memory accounting already are, and where the answer is a typed column
that the next join or aggregate can use. That is the same reason we built
graph execution into Sail through its extension mechanism: the plan is the
right place for the work.

Sail 0.7.2 is on PyPI as `pysail`. The Jev guide is at
`docs/guide/integrations/jev.md` in the Sail repository, and the
implementation is lakehq/sail#2653. Set `TYPESAFE_API_KEY`, start Sail,
and ask your data a question.
