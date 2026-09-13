# Conformance — `langsys-fastapi`

| | |
|---|---|
| **Spec revision read** | langsys2 5cff03a1…, docs/sdk-spec.mdx blob 5c5c0723f88fb8e6b13f58876c7adca8b6b35691 |
| **Profiles** | server, binding, all — derived: binding over langsys-python |
| **SDK** | `langsys-fastapi`, the FastAPI/Starlette binding |
| **specVersion** | 8.0.1 |
| **SDK revision** | `feature/838_write_key_gating`, cut from `main` `29bb650` |
| **Core revision** | `langsys-python` `c79fd57cc553d3bf420391d23b1f5e842fae6cfc`, as a clean `git archive` — see *Reproducing* |
| **Published** | Never |
| **Suite** | 74 passed and 2 strict `xfail` (SRV-3, red first) by default; 5 live under `pytest -m integration`, all passing against the local stack |

The spec revision was re-derived when this file was written, from the commit rather than a
branch: `git -C ~/Documents/dev/langsys2 rev-parse 5cff03a17751e7dae9dcf1af52a9454d027c9006:docs/sdk-spec.mdx`.
`_dev_/conformance_counts.py` refuses to count if that blob moves. The per-rule revision
column is omitted, following the fleet norm: the section hashes are served only from an MCP
resource that no SDK lane can reach.

**On the profile.** The spec never names FastAPI. Its server row covers Python "and [its]
framework variants", and its binding row describes a thin wrapper over a core. This file is
therefore filed `server, binding, all`, derived as a binding over `langsys-python`. Every
row is either delegated to the core with a probe showing this package does not take part,
or proven here. The Reviewer has flagged the naming gap to the operator.

**What surfaced while writing this.** Nine things. The first three were in the Reviewer's
survey of `29bb650`; each was measured here before it was fixed. The rest came from writing
the tests, and one was my own mistake, caught in review.

1. **The end-of-request branch discarded a queue the core holds.** With the write decision
   unknown, `29bb650` left the queue empty after 0 POSTs. The core's own flush, given the
   same state, kept it with reason `capability-unknown`. The binding branched on
   `can_write`, which folds "unknown" into "no".
2. **The binding's `auto_flush` meant the opposite of the core's.** Measured: with
   `auto_flush=False`, a write-enabled session discarded its queue after 0 POSTs. In the
   core, `auto_flush` means "flush at process exit".
3. **The write decision outlived the request.** At `29bb650` the observed decision was still
   `(4, True)` after the request ended. What that costs only showed up once the test
   existed. On the hot path (authorize payload warm, catalog cached), a "no" observed by one
   request made the next request silently register nothing.
4. **My first SRV-3 fix hid the defect instead of fixing it.** I built the shared client
   with `debounce=None`, which made a slow-handler order test pass. Review ruled that this is
   scheduling one layer too high (BIND-3). I reverted it. The reverted line is now the firing
   control for the BIND-3 probe, and restoring it is one of the mutations. It is recorded
   because the green test was real and the conformance was not.
5. **The binding's own flush sends other requests' misses.** I measured concurrency at the
   Reviewer's request. The end-of-request flush drains the whole process-wide queue. A quick
   request therefore registered a still-rendering request's miss at 0.027s, while that
   request's response did not start until 0.306s. No timer was involved. I sent this to the
   Reviewer for the core seam, which has to cover explicit flushes as well as the timer.
6. **`supported` only constrained `Accept-Language`.** Any `?locale=` or cookie value reached
   the API as a locale: a catalog fetch and a cache entry for every distinct string a visitor
   sends. All three candidates now go through the core's `detect_preferred_locale`.
7. **A single non-UTF-8 header byte failed the request.** Header bytes, which HTTP defines as
   latin-1, were decoded as UTF-8, and the error was raised before the app ran.
8. **`t()` has a keyword collision.** A `{category}` or `{phrase}` placeholder cannot be
   passed as a keyword, and `category=` is silently taken as the category.
   `langsys-python-django` has the same signature. This is documented rather than changed;
   see gaps.
9. **A linked working tree does not produce reproducible evidence.** The editable link
   follows `langsys-python`'s working tree, and that tree was being edited while this file
   was written. Two runs against it failed 2 tests and then 6 tests. Minutes later the same
   tests passed without any change here, and they pass at `c79fd57`. I did not diagnose the
   cause. Every result below is pinned to a clean archive of that commit.

**Tiers.** `live`: a real Langsys stack, asserting the server's answers as recorded from its
responses. `n/a (pure)`: in-process behaviour, isolation that a stateful fixture could
neither prove nor disprove, or artifact inspection with a positive control. A `delegated`
row carries `-`: the tier of the behaviour lives on the core's row, and the absence probe in
its Evidence proves only that this package does not take part. `mock` grades nothing here.
No row claims `contract`, because the shared fixture does not exist.

**The `live` fixture is seeded on demand, not by hand.** langsys2's committed
`database/seeders/SdkIntegrationSeeder.php` gives this binding slot 15 — project
`c0de0000-5d10-4000-8000-000000000015` with write, read and `ip_write` keys, and the
`Technical Support` → `Soporte Técnico` es-es row the tests read. Slot 15 was added in
langsys2 `f8e499d1` and is present at the spec commit `5cff03a`, where `DatabaseSeeder` runs
it outside production, last in its chain and after `OrganizationsTableSeeder`. Every id and raw key is a fixed constant and the seeder
upserts, so `php artisan db:seed` (or `php artisan db:seed --class=SdkIntegrationSeeder` on a
database that already has organizations) recreates the fixture exactly. Registration asserts
HTTP acceptance only: the local stack runs with queue workers down.

**Delegation.** A `delegated` row cites the core's row in `langsys-python`'s
`CONFORMANCE.md` at `c79fd57`, graded as that file grades it, together with an absence
probe in `tests/test_probes.py::test_ABSENCE`, and takes tier `-`. A probe reads this package's code only
(docstrings and comments blanked), asserts that it read all 5 files, and carries a firing
control: a snippet the same filter must catch. The count beside each probe is the same
pattern run over the core at `c79fd57`. A core count of 0 means the core has no such code
either, and the firing control alone carries the proof.

---

## Summary

Counted by `_dev_/conformance_counts.py`, which exits non-zero if a rule id is unaccounted
for, unknown or graded twice, or if a status or tier falls outside the vocabulary.

| Status | Count | |
|---|---|---|
| `implemented` | 14 | 3 `live` (REG-3, SRV-1, CONF-1) · 11 `n/a (pure)` |
| `delegated` | 42 | |
| `partial` | 1 | SRV-3 — waits on a `langsys-python` seam |
| `n/a (profile: browser)` | 20 | |
| `n/a (architecture: …)` | 2 | SRV-4, SRV-5 |
| **total** | **79** | |

**Not green: SRV-3 is `partial`.**

## Status

| Rule | Status | Tier | Evidence |
|---|---|---|---|
| GATE-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[GATE-1]`: key type named 0 times here, 27 in core; control `if client.key_type == "write"` fires |
| GATE-2 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[GATE-2]`: 0 here, 8 in core; the firing control is the `29bb650` branch verbatim. The end-of-request flush now calls the core's `flush_pending()` unconditionally, so hold-on-unknown is decided in the core. Regression through the middleware: `tests/test_request_boundary.py::test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`, with control `test_GATE2_CONTROL_a_server_no_still_discards_through_the_middleware` |
| GATE-3 | implemented | n/a (pure) | The middleware calls the core's `reset_write_decision()` at the end of every request, in a `finally`, discharging the obligation the core declares for wrappers. `tests/test_request_boundary.py::test_GATE3_a_no_observed_in_one_request_does_not_silence_the_next`: one request is told no; the next has a warm plain write key and a cached catalog, and must still register. Mutation: dropping the reset reddens it. No carve-out is taken |
| GATE-4 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[GATE-4]`: nothing cached and no decision named here, 0 here, 28 in core |
| GATE-5 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[GATE-5]`: 0 here, 0 in core. The core has no "already registered" store either; control `self._registered.add(key)` fires |
| GATE-6 | delegated | - | Core: partial, mock. Probe `test_ABSENCE[GATE-6]`: no report lane, 0 here, 0 in core; control `http.post("discovery/hint", …)` fires |
| GATE-7 | delegated | - | Core: partial, mock. Probe `test_ABSENCE[GATE-7]`: 0 here, 7 in core. Every entry point here (`t()`, `at()`, DI) reaches the core's `translate`, and the end-of-request flush feeds only the core's register lane |
| GATE-8 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[GATE-8]`: 0 here, 58 in core |
| CAT-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-1]`: no catalog read here, 0 here, 57 in core |
| CAT-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-2]`: 0 here, 57 in core |
| CAT-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-3]`: 0 here, 73 in core |
| REG-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[REG-1]`: no registration call or POST here, 0 here, 9 in core |
| REG-2 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-2]`: no debounce, timer or task here, 0 here, 10 in core. This binding schedules nothing (see *What surfaced*, item 4). `test_REG2_everything_one_request_found_goes_out_as_one_request` shows a five-miss request going out as one request with no flush in the app |
| REG-3 | implemented | live | The execution context this binding owns is the request. Once the response is sent, the middleware hands the queue to the core's public `flush_pending()`; `reset_client()` and `configure()` flush a retired client before closing it. Live: `tests/test_live.py::test_LIVE_SRV3_REG3_accepted_after_the_response_and_never_from_a_read_key[CONTROL-write-key-on-the-same-render-pushes]`: the stack answered the POST 2xx, and the queue is empty. Also `test_REG3_reconfiguring_hands_the_retired_client_s_queue_to_the_core_first`. Mutations: dropping the end-of-request flush reddens 3 named tests; closing without flushing reddens 1. The manual flush is the core's, reachable as `get_langsys().flush_pending()` and documented in the README |
| REG-4 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-5 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-6 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-6]`: the private queue is never touched here, 0 here, 27 in core |
| REG-7 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-7]`: 0 here, 3 in core. The lock here guards building the client, not sending |
| REG-8 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-8]`: no retry or backoff here, 0 here, 20 in core |
| REG-9 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-9]`: 0 here, 13 in core |
| REG-10 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[REG-10]`: this package returns no flush result, 0 here, 12 in core. Its end-of-request guard logs and never raises past a response already sent |
| REG-11 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[REG-11]`: 0 here, 13 in core |
| REG-12 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-12]`: 0 here, 17 in core |
| HINT-1 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[HINT-2]`: 0 here, 0 in core. Neither has a report lane; control `http.post("discovery/hint", …)` fires |
| HINT-3 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-4 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-5 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-6 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-7 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-8 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-9 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-10 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-11 | n/a (profile: browser) | - | A server SDK has no page URL to report |
| HINT-12 | n/a (profile: browser) | - | The server mirror is the Langsys backend, not an SDK |
| ICU-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-1]`: no interpolation here, 0 here, 35 in core. `test_BIND1_…` runs an ICU plural through `t()`, `at()` and the core and gets identical output |
| ICU-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-2]`: 0 here, 35 in core. The `test_BIND1_…` vectors include a null count |
| ICU-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-3]`: 0 here, 35 in core |
| ICU-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-4]`: 0 here, 35 in core |
| ICU-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-5]`: 0 here, 35 in core |
| CID-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-1]`: no hashing or ids here, 0 here, 54 in core |
| CID-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-2]`: 0 here, 54 in core |
| CID-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-3]`: 0 here, 54 in core |
| CID-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-4]`: 0 here, 54 in core |
| TOK-1 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[TOK-1]`: no parser or tokenizer here, 0 here, 47 in core. HTML paths are reachable only through the DI client, which is the core itself (BIND-6) |
| TOK-2 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[TOK-2]`: 0 here, 47 in core |
| TOK-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-3]`: 0 here, 47 in core |
| TOK-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-4]`: 0 here, 47 in core |
| TOK-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-5]`: 0 here, 47 in core |
| MARK-1 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[MARK-1]`: no identity attribute here, 0 here, 18 in core |
| MARK-2 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[MARK-2]`: 0 here, 18 in core |
| SSR-1 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-2 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-3 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SRV-1 | implemented | live | Asserted on the served bytes, on every route this binding exposes: `tests/test_live.py::test_LIVE_SRV1_the_served_bytes_carry_the_request_locale[/sync]`, `[/async]` and `[/di]`. The response body carries `Soporte Técnico` from the live es-es catalog. A control phrase absent from that catalog, in the same render, emits the base language and is queued as a miss. Unit twins are in `test_request_boundary.py`. Mutation: never exposing the resolved locale reddens all three |
| SRV-2 | implemented | n/a (pure) | `test_SRV2_concurrent_requests_in_different_locales_see_only_their_own[/srv2/async]` and `[/srv2/sync]`: an es request and a de request are both inside their scope before either translates, held there by asyncio events on the async path and a thread barrier on the threadpool path. Mutation: holding the locale in a process global reddens both |
| SRV-3 | partial | live | **Holds.** A read-only key pushes nothing, with a write key on the same render as the positive control: `test_LIVE_SRV3_REG3_…[read-only-key-pushes-nothing]` and `[CONTROL-write-key-on-the-same-render-pushes]`. A request that finishes inside the core's debounce window, with no concurrent request finishing first, registers after its body: `test_SRV3_REG3_registration_happens_after_the_response_is_sent`; mutation: flushing before the body reddens it. **Does not hold, measured.** A handler slower than the core's 400ms debounce has its miss sent by the core's timer mid-render: sync, POST at 0.449s vs response start at 0.851s; async, 0.408s vs 0.804s. A concurrent request's end-of-request flush sends a still-rendering request's miss: 0.027s vs 0.306s, with no timer involved. **Waits on** a `langsys-python` seam: a miss recorded in a request scope is sent by no flush until that scope's own response has been flushed. Red first, as strict xfail: `test_SRV3_a_slow_handler_sends_nothing_before_its_response` and `test_SRV3_another_request_s_flush_sends_nothing_before_this_response` |
| SRV-4 | n/a (architecture: this binding performs no hydration hand-off because FastAPI responses are terminal and no client renders against them, live if the binding ships a client entry or template integration that hydrates) | - | The core rows SRV-4 separately; a terminal-HTML server SDK rows it n/a under 8.0.1's wording |
| SRV-5 | n/a (architecture: FastAPI has no component model, so this binding renders no children to capture, live if a template-component integration is added) | - | The core's DOM walker is reachable only through the DI client, where it is the core's row |
| BIND-1 | implemented | n/a (pure) | Shape and timing only, tested by running the spec's first heuristic. `test_BIND1_deleting_the_binding_changes_nothing_but_shape`: the same vectors through `t()`, through `at()` and directly through the core give identical text and identical queues. The vectors cover a hit, a miss, interpolation, an ICU plural with a supplied count and with a null count, and the uncategorized case. `at()` is a threadpool shape adapter. Mutation: `t()` dropping the category reddens it. Known shape limit: see gaps |
| BIND-2 | implemented | n/a (pure) | `test_ABSENCE[BIND-2]`: no capability name in this package's code, 0 here, 58 in core; the firing control is the `29bb650` branch verbatim. Behaviour: `test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`. Mutation: restoring the branch reddens 3 named tests |
| BIND-3 | implemented | n/a (pure) | `test_ABSENCE[BIND-3]`: no transport, timer, sleep, retry, backoff, header or `debounce` in this package's code, 0 here, 33 in core. The end-of-request flush is a lifecycle call to the core's public flush, not a schedule. The firing control is this binding's own reverted `debounce=None` line. Mutation: restoring that line reddens the probe and flips the red-first slow-handler test |
| BIND-4 | implemented | n/a (pure) | `test_BIND4_configure_introduces_no_option_the_core_does_not_define`: every `configure()` option is a `LangsysClient` option. `test_BIND4_the_middleware_introduces_only_request_shape_options`: the middleware takes no client option name, only `query_param` and `cookie_name` (where in a request the locale lives, which the core cannot define) and `supported` (a parameter of the core's own matcher). Firing controls: the `29bb650` signature with `auto_flush`, and a `discovery` option. Mutation: restoring `auto_flush` reddens it |
| BIND-5 | implemented | n/a (pure) | `test_ABSENCE[BIND-5]`: nothing memoized in front of `t()`, 0 here, 7 in core. Mutation: `lru_cache` on `t()` reddens it |
| BIND-6 | implemented | n/a (pure) | `test_BIND6_nothing_exported_shadows_a_core_name_with_something_else` and `test_BIND6_DI_hands_out_the_core_client_itself`: DI returns the core `LangsysClient` itself, not a wrapper. The other exported names are framework idioms: the middleware, `t`/`at` over the shared client, DI providers and request-locale accessors. Mutation: exporting a reimplemented core name reddens it |
| GRANT-1 | n/a (profile: browser) | - | A server binding holds a key, not a grant. No header is set here (`test_ABSENCE[WIRE-1]`) |
| GRANT-2 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-3 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-4 | n/a (profile: browser) | - | A server binding holds a key, not a grant. The core asserts, live, that it never sends `X-Write-Grant` |
| CACHE-1 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[CACHE-1]`: no cache key built here, 0 here, 11 in core. `configure(cache=…)` passes the backend through unchanged |
| OBS-1 | delegated | - | Core: implemented, mock. Probe `test_ABSENCE[OBS-1]`: 0 here, 11 in core. The core re-arms its once-per-session notice on `reset_write_decision()`; called per request here, the request is the session |
| WIRE-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[WIRE-1]`: no auth header here, 0 here, 8 in core |
| WIRE-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[WIRE-2]`: no response parsing here, 0 here, 17 in core |
| WIRE-3 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-3]`: 0 here, 17 in core. This package hands the core canonical BCP 47 (`es-ES`) from the core's own matcher; lowercasing for the wire happens in the core |
| WIRE-4 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-4]`: no API call of this package's own, 0 here, 10 in core. Locale resolution in the middleware is in-process, and its flush runs after the response and never raises past it |
| WIRE-5 | implemented | n/a (pure) | `test_WIRE5_configure_redirects_the_api_base_even_after_first_use`: requests arrive at one double, then at a second after `configure()` is called again once the client has been used, which is the late-redirect ordering the rule names. `test_WIRE5_the_seam_is_findable_where_an_integrator_looks`: the README's Configuration section names `api_url` and `LANGSYS_API_URL`, and so does the `configure()` docstring. Mutation: `configure()` not rebuilding the client reddens the first |
| CONF-1 | implemented | live | Every row whose property depends on what the API answers is proven live, asserting the server's answers as recorded from its responses: REG-3, SRV-1, and SRV-3's key halves. The fixture is re-creatable on demand from langsys2's committed `SdkIntegrationSeeder` (see *Tiers*). Every path: SRV-1 is proven on sync `t()`, async `at()` and DI. The mock-backed unit tests beside them are supporting evidence, not the grade |
| CONF-2 | implemented | n/a (pure) | Every row carries a tier, and `_dev_/conformance_counts.py` rejects a tier its status cannot carry, including anything but `-` on a delegated row. `live` evidence is reproducible: its fixture comes from a committed, idempotent seeder (see *Tiers*). No row claims `contract` |
| CONF-3 | implemented | n/a (pure) | `_dev_/mutations.py`: 13 mutations across every implemented or partial row that running something can break. Each must redden its named tests against a green baseline, and the tree is restored byte-for-byte afterwards. All 13 redden against core `c79fd57`. For delegated rows, each probe's firing control is the mutation |

---

## Gaps, ranked by cost

1. **SRV-3: registration can go out before the response.** It happens from the core's
   debounce on any handler slower than 400ms, and from a concurrent request's end-of-request
   flush. The cost lands on the visitor's request path, and content gets registered before
   its page has been served. The fix waits on a `langsys-python` seam; once it lands, this
   binding marks the request scope and flushes after the response. Both order tests are
   strict `xfail`, so the seam landing turns them into failures and the row has to flip.
2. **Delegated rows are only as good as the core rows they cite.** At `c79fd57` the core
   grades GATE-6 and GATE-7 `partial`. It grades GATE-2, GATE-5, GATE-8, REG-2, REG-6 to
   REG-9, REG-11, TOK-1, TOK-2, MARK-1, MARK-2, CACHE-1 and OBS-1 on mock evidence. Its file
   is still filed against blob `b657b490`, and the core lane is re-filing against
   `5c5c0723`.
3. **A `{category}` or `{phrase}` placeholder cannot be passed to `t()` or `at()` as a
   keyword,** and `category=` is silently taken as the category. `langsys-python-django`'s
   `t()` shares the signature. This is documented, with the DI client as the workaround.
   Making the arguments positional-only would silently reroute `t("Save", category="UI")`,
   which is worse.
4. **A request whose handler raised is not flushed at its own end.** Its misses go out with
   the next request or at process exit, and REG-3 already calls the exit path best-effort.
   This is deliberate: flushing there would run before the outer error response is sent.

## Reproducing

```bash
.venv/bin/pytest                          # 74 passed, 2 strict xfail; live tests skip
php artisan db:seed                       # in langsys2: (re)creates the slot-15 fixture
.venv/bin/pytest -m integration           # 5 live; environment in tests/test_live.py
.venv/bin/python _dev_/mutations.py       # CONF-3: every mutation must redden its named tests
python3 _dev_/conformance_counts.py       # this file's tally, against the pinned spec blob
```

The editable link follows `langsys-python`'s working tree, which moves (see *What
surfaced*, item 9). To pin the core at the commit this file cites, prefix any of the
commands above with `PYTHONPATH`:

```bash
mkdir -p /tmp/langsys-core && git -C ../langsys-python archive c79fd57 src | tar -x -C /tmp/langsys-core
PYTHONPATH=/tmp/langsys-core/src .venv/bin/pytest
```
