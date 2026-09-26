# Conformance — `langsys-fastapi`

| | |
|---|---|
| **Spec revision read** | langsys2 a95af2c2…, docs/sdk-spec.mdx blob 5d7e6890b733a50fb6f5f5c30e0056c6ef7bcf45 |
| **Profiles** | server, binding — derived: binding over langsys-python |
| **SDK** | `langsys-fastapi`, the FastAPI/Starlette binding |
| **specVersion** | 8.2.18 |
| **SDK revision** | `feature/838_write_key_gating`, cut from `main` `29bb650` |
| **Core revision** | `langsys-python` `e834170e0830475f8d4640f33f0e5ac8ec31d0ca`, as a clean `git archive` — see *Reproducing* |
| **Message vectors** | `tests/fixtures/server-message-vectors.json`, blob `7333e3919dac43af81c6c20bfdba974efd79725b`, vendored from the core |
| **Contract fixture** | `tests/contract-fixture/`, tree `542f57f5ffcb9038db1b7411152b7e31b96cb269`, vendored byte-exact with the core's harness `tests/contract.py` |
| **Published** | Never — PyPI and TestPyPI both 404 (positive control: `httpx` → 200) |
| **Suite** | 121 passed by default, the contract tests included; 5 live under `pytest -m integration`, all passing against the local stack |

Spec version implemented: **v8.2.18**, blob `5d7e6890b733a50fb6f5f5c30e0056c6ef7bcf45`. The blob is
re-derived on every write of this file, from the commit rather than a branch:
`git -C ~/Documents/dev/langsys2 rev-parse a95af2c2596d5a882473d9ef09d232eb5c1d7a12:docs/sdk-spec.mdx`.
`_dev_/conformance_counts.py` refuses to count if it moves. No per-rule revision is recorded:
the blob citation is complete without one.

**On the profile.** The spec's per-SDK table gives `langsys-python-fastapi` the profile
`server, binding` over `langsys-python`, with SRV-4 `n/a (architecture)` because the output is
terminal. Every row is either proven here or delegated to the core with a probe showing this
package takes no part.

**What surfaced while writing this.** Checking `29bb650` rule by rule against running code found
five defects, each measured before it was fixed:

1. **Capability unknown discarded the queue.** The end-of-request branch tested `can_write`,
   which folds "could not ask" into "no", and cleared the queue: 0 POSTs where the core on its
   own holds with reason `capability-unknown`. The middleware now hands every queue to the
   core's `flush_pending()` and branches on nothing.
2. **The middleware's `auto_flush` meant the opposite of the core's.** Turned off, it discarded a
   write-enabled session's queue; the core's `auto_flush` means "flush at process exit". The
   middleware now takes no option the core defines.
3. **The write decision outlived the request.** On the hot path — authorize payload warm,
   catalog cached — a "no" observed by one request silenced the next request's registration. The
   decision is now reset at the end of every request.
4. **An explicit locale reached the API unvalidated.** Any `?locale=` or cookie value was used as
   the locale, costing a catalog fetch and a cache entry per distinct string. Every candidate is
   now validated against the project's own locales by the core's resolver.
5. **One non-UTF-8 header byte failed the request.** Header bytes, latin-1 on the wire, were
   decoded as UTF-8 before the app ran. They are now decoded as latin-1.

**Tiers.** `live`: a real Langsys stack, asserting the server's answers as recorded from its
responses. `contract`: the shared contract double, asserting only the state it accepted — and,
for an absence, after drifting the capability so the double would have accepted (CONF-2).
`n/a (pure)`: in-process behaviour, isolation a stateful fixture could neither prove nor
disprove, or artifact inspection with a positive control. A `delegated` row carries `-`: the
tier of the behaviour lives on the core's row.

**The `live` fixture is seeded on demand.** langsys2's committed
`database/seeders/SdkIntegrationSeeder.php` gives this binding slot 15 — project
`c0de0000-5d10-4000-8000-000000000015` with write, read and `ip_write` keys, and the
`Technical Support` → `Soporte Técnico` es-es row the tests read. `DatabaseSeeder` runs it
outside production, after `OrganizationsTableSeeder`; every id and raw key is a fixed constant
and the seeder upserts, so `php artisan db:seed` recreates the fixture exactly. Registration
asserts HTTP acceptance only: the local stack runs with queue workers down.

**Delegation.** A `delegated` row cites the core's row in `langsys-python`'s `CONFORMANCE.md` at
`e834170`, graded as that file grades it; that file grades spec 8.2.18. Each delegated row carries an
absence probe, `tests/test_probes.py::test_ABSENCE[<rule>]`: it reads this package's code only
(docstrings and comments blanked), asserts it read all 6 files, and carries a firing control, a
snippet the same filter must catch. The count beside each probe is the same pattern run over the
core at `e834170`; a core count of 0 means the core has no such code either, and the firing
control alone carries the proof.

---

## Summary

Counted by `_dev_/conformance_counts.py`, which exits non-zero if a rule id is unaccounted for,
unknown or graded twice, or if a status or tier falls outside the vocabulary.

| Status | Count | |
|---|---|---|
| `implemented` | 23 | 3 `live` (REG-3, SRV-1, CONF-1) · 2 `contract` (SRV-3, SRV-6) · 18 `n/a (pure)` |
| `delegated` | 63 | graded on the core's rows — see gaps |
| `n/a (profile: browser)` | 21 | |
| `n/a (architecture: …)` | 6 | GATE-10, HINT-13, SRV-4, SRV-5, MSG-10, MSG-12 |
| **total** | **113** | |

## Status

| Rule | Status | Tier | Evidence |
|---|---|---|---|
| GATE-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[GATE-1]`: key type named 0 times here, 27 in core; control `if client.key_type == "write"` fires |
| GATE-2 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[GATE-2]`: 0 here, 8 in core; the firing control is the `29bb650` end-of-request branch verbatim. The end-of-request flush calls the core's `flush_pending()` unconditionally, so hold-on-unknown is decided in the core. Through the middleware: `test_request_boundary.py::test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`, with control `test_GATE2_CONTROL_a_server_no_still_discards_through_the_middleware` |
| GATE-3 | implemented | n/a (pure) | The middleware calls the core's `reset_write_decision()` at the end of every request, in a `finally`, discharging the obligation the core declares for wrappers. `test_request_boundary.py::test_GATE3_a_no_observed_in_one_request_does_not_silence_the_next`: one request is told no; the next has a warm plain write key and a cached catalog, and still registers. Mutation: dropping the reset reddens it. No carve-out is taken |
| GATE-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[GATE-4]`: nothing cached and no decision named here, 0 here, 29 in core |
| GATE-5 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[GATE-5]`: 0 here, 0 in core. The core keeps no "already registered" store either; control `self._registered.add(key)` fires |
| GATE-6 | delegated | - | Core: n/a (architecture: no report lane exists, per HINT-2; live if one is ever added). Probe `test_ABSENCE[GATE-6]`: no report lane, 0 here, 0 in core; control `http.post("discovery/hint", …)` fires |
| GATE-7 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[GATE-7]`: 0 here, 8 in core. Every entry point here (`t()`, `at()`, DI, the validation handler) reaches the core, and the end-of-request flush feeds only the core's register lane |
| GATE-8 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[GATE-8]`: 0 here, 59 in core |
| GATE-9 | n/a (profile: browser) | - | The base-locale discovery gate is a browser client's |
| GATE-10 | n/a (architecture: this binding renders no HTML of its own, so it has no root or element to mark and no DOM host that reads a mark, live if it adds a template integration) | - | The core's `translate_page()`, reachable through the DI client, is the producer on this stack and marks its root off the base locale |
| CAT-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-1]`: no catalog read here, 0 here, 94 in core |
| CAT-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-2]`: 0 here, 94 in core |
| CAT-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-3]`: 0 here, 123 in core |
| REG-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-1]`: no registration call or POST here, 0 here, 10 in core |
| REG-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-2]`: no debounce, timer or task here, 0 here, 13 in core. `test_REG2_everything_one_request_found_goes_out_as_one_request` shows a five-miss request going out as one request with no flush in the app |
| REG-3 | implemented | live | The execution context this binding owns is the request: once the response is out, the middleware hands the queue to the core's public `flush_pending()`, and `reset_client()` and `configure()` flush a retired client before closing it. Live: `tests/test_live.py::test_LIVE_SRV3_REG3_accepted_after_the_response_and_never_from_a_read_key[CONTROL-write-key-on-the-same-render-pushes]` — the stack answered the POST 2xx and the queue is empty. Also `test_REG3_reconfiguring_hands_the_retired_client_s_queue_to_the_core_first`. Mutations: dropping the end-of-request flush reddens 3 named tests; closing without flushing reddens 1. The manual flush is the core's, reachable as `get_langsys().flush_pending()` and documented in the README |
| REG-4 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-5 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-6 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-6]`: the private queue is never touched here, 0 here, 33 in core |
| REG-7 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-7]`: 0 here, 3 in core. The lock here guards building the client, not sending |
| REG-8 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[REG-8]`: no retry or backoff here, 0 here, 20 in core. The shared client outlives every request, so the core's failure clock does too |
| REG-9 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[REG-9]`: 0 here, 13 in core |
| REG-10 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[REG-10]`: this package returns no flush result, 0 here, 14 in core. Its end-of-request guard logs and never raises past a response already sent |
| REG-11 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-11]`: 0 here, 14 in core |
| REG-12 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-12]`: 0 here, 30 in core |
| REG-13 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-13]`: no catalog-load state here, 0 here, 0 in core |
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
| HINT-13 | n/a (architecture: FastAPI has no client-side router, and every navigation is a new request that enters through the middleware, live if the binding ships a client entry) | - | No navigation hook exists to wire |
| ICU-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-1]`: no interpolation here, 0 here, 22 in core. `test_BIND1_…` runs an ICU plural through `t()`, `at()` and the core and gets identical output |
| ICU-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-2]`: 0 here, 22 in core. The `test_BIND1_…` vectors include a null count |
| ICU-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-3]`: 0 here, 22 in core |
| ICU-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-4]`: 0 here, 22 in core |
| ICU-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-5]`: 0 here, 22 in core |
| ICU-6 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-6]`: no formatter here, 0 here, 23 in core |
| CID-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-1]`: no hashing or ids here, 0 here, 78 in core |
| CID-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-2]`: 0 here, 78 in core |
| CID-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-3]`: 0 here, 78 in core |
| CID-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-4]`: 0 here, 78 in core |
| TOK-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-1]`: no parser or tokenizer here, 0 here, 66 in core. HTML paths are reachable only through the DI client, which is the core itself (BIND-6) |
| TOK-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-2]`: 0 here, 66 in core |
| TOK-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-3]`: 0 here, 66 in core |
| TOK-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-4]`: 0 here, 66 in core |
| TOK-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-5]`: 0 here, 66 in core |
| TOK-6 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-6]`: 0 here, 66 in core |
| MARK-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-1]`: no identity or resolved attribute here, 0 here, 27 in core |
| MARK-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-2]`: 0 here, 27 in core |
| MARK-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-3]`: 0 here, 27 in core |
| MARK-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-4]`: 0 here, 27 in core |
| SSR-1 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-2 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-3 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SRV-1 | implemented | live | Asserted on the served bytes, on every route this binding exposes: `tests/test_live.py::test_LIVE_SRV1_the_served_bytes_carry_the_request_locale[/sync]`, `[/async]` and `[/di]`. The response body carries `Soporte Técnico` from the live es-es catalog, and a control phrase absent from it, in the same render, emits the base language and is queued as a miss. Unit twins are in `test_request_boundary.py`. Mutation: never exposing the resolved locale reddens all three |
| SRV-2 | implemented | n/a (pure) | `test_SRV2_concurrent_requests_in_different_locales_see_only_their_own[/srv2/async]` and `[/srv2/sync]`: an es request and a de request are both inside their scope before either translates, held there by asyncio events on the async path and a thread barrier on the threadpool path. Mutation: holding the locale in a process global reddens both |
| SRV-3 | implemented | contract | The middleware opens the core's request scope at request start and ends it once the final response body has been sent, then flushes; while the scope is open, no flush sends the request's misses. Order of events: `test_SRV3_REG3_registration_happens_after_the_response_is_sent`; `test_SRV3_a_slow_handler_sends_nothing_before_its_response`, whose handler outlives the core's 400ms debounce; `test_SRV3_another_request_s_flush_sends_nothing_before_this_response`, where a concurrent request finishes first; `test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response`, ordered by the core's debounce. Read-only half, with CONF-2's drift: `test_contract.py::test_SRV3_a_session_that_may_not_write_pushes_nothing_even_once_the_world_would_accept` — an `ip_write` session not allow-listed pushes nothing, the double's allow-list then widens and the state stays empty, and in the drifted world a request that may write registers its own miss. Write acceptance, live: `test_LIVE_SRV3_REG3_…[CONTROL-write-key-on-the-same-render-pushes]`. Mutations: releasing and flushing before the body, never opening the scope, and leaving a raised request's scope open each redden their named tests |
| SRV-4 | n/a (architecture: this binding performs no hydration hand-off because FastAPI responses are terminal, as the spec's per-SDK table records, live if the binding ships a client entry or template integration that hydrates) | - | No client renders against a FastAPI response |
| SRV-5 | n/a (architecture: FastAPI has no component model, so this binding renders no children to capture, live if a template-component integration is added) | - | The core's DOM walker is reachable only through the DI client, where it is the core's row |
| SRV-6 | implemented | contract | **A locale the app resolved is served as it resolved it.** An app's own middleware, running before this one, sets `request.state.locale` (the attribute is the `state_key` wiring); the middleware hands it to the core's `resolve_request_locale(framework=…)`, which validates it and maps it to the project's form, and nothing else is consulted and no `Vary` added. `test_contract.py::test_SRV6_a_locale_the_app_resolved_is_served_whatever_else_the_request_says`: `es-ES` is served as `es-es`, a bare `es` as the project's default Spanish, and an unsupported `fr-FR` as the base — each against a conflicting URL, cookie and header. **Where nothing has resolved it,** the middleware asks the core's `resolve_request_locale` for the locale — the URL, then the locale cookie, then `Accept-Language`, then the project's base locale, each validated against the project's locales — merges the returned `Vary` into the app's own, and never writes a cookie. The URL step is whichever the app routes by: a path segment (`path_segment=`), the subdomain (`subdomain=True`) or the query parameter, the first present; with the cookie name these are wiring, and `cookie_name=None` declares that the app keeps no locale cookie. Against the double serving en-us, it-it and es-es: `test_contract.py::test_SRV6_one_url_resolves_url_then_cookie_then_header_each_validated` — the URL wins over a conflicting cookie and header with no `Vary`; a cookie wins with `Vary: Cookie`; a header alone is negotiated with `Vary` naming `Accept-Language`; an unsupported cookie falls through to the header and is not re-set; an unsupported URL locale falls through to the base. `test_SRV6_a_path_segment_the_app_routes_by_is_the_url_step` and `test_SRV6_a_subdomain_the_app_routes_by_is_the_url_step`, each against a conflicting cookie and header; `test_SRV6_vary_is_merged_into_the_apps_own`; `test_SRV6_an_app_with_no_locale_cookie_does_not_vary_on_one`. Mutations: never sending `Vary`, replacing the app's `Vary`, ignoring the path segment, ignoring the subdomain and never offering the cookie each redden their named tests. Mutation: ignoring the app's locale reddens the first case |
| MSG-1 | implemented | n/a (pure) | `install(app)` keeps FastAPI's own 422 body — its default handler writes it — and attaches one entry per error beside `detail`, under a configurable key — the core's `langsys_errors` by default — through the core's `attach_server_messages`. `test_messages.py::test_MSG1_fastapis_own_body_is_unchanged_and_the_entries_ride_beside_it` compares the body, request for request, with the same app answering through FastAPI's default handler; `test_MSG1_the_key_the_entries_sit_under_is_configurable`. Mutation: replacing the body with the entries alone reddens it |
| MSG-2 | implemented | n/a (pure) | Each entry's `code` is Pydantic's own error `type` — a custom `PydanticCustomError`'s type included — passed through unchanged. `test_MSG2_code_field_and_message_are_pydantics_own`: every entry's `code`, `field` and `message` are the `type`, `loc` and `msg` of the error beside it in `detail`. `test_probes.py::test_MSG2_no_vocabulary_or_wording_of_ours_stands_in_for_pydantics` finds no code vocabulary or wording table here, with a firing control. Mutation: mapping the type onto a code of ours reddens it |
| MSG-3 | implemented | n/a (pure) | The template is Pydantic's own sentence for the error type, from `pydantic_core`'s message templates, never reworded. A number or a date in it stays a `{name}` marker; text Pydantic writes into it — the plural `s`, a `Literal`'s choices, a pattern, a validator's own message — is written in, so it is translated with its sentence. Pydantic's sentences never name the field, so no label is written in (MSG-10). `test_MSG3_MSG9_each_template_is_pydantics_sentence_before_its_values_are_filled` (eleven failures, each its exact template and params) and `test_MSG3_text_pydantic_writes_into_its_sentence_is_written_in_so_it_is_translated_whole`. Mutation: writing numbers in instead of leaving them markers reddens 2 named tests |
| MSG-4 | implemented | n/a (pure) | `test_MSG4_numbers_are_params_and_the_filled_template_is_the_message`: `fill(template, params)` reproduces `message` for every entry — Pydantic's own `msg` — numbers are JSON numbers, and `params` is present exactly when the template has markers. `test_MSG1_MSG4_the_measured_pydantic_entries_in_the_shared_vectors_are_what_this_builds`: the vector file's two measured Pydantic entries are exactly what this package builds from the same failures |
| MSG-5 | delegated | - | Core: n/a (profile: browser, binding). Probe `test_ABSENCE[MSG-5]`: this package renders no entry, 0 here, 1 in core. An app renders an entry through the core client's `render_server_message`, reachable through DI |
| MSG-6 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[MSG-6]`: no category chosen here, 0 here, 7 in core. Entries are built through the core client, under its `message_category`; `configure(message_category=…)` passes the core's option through unchanged |
| MSG-7 | implemented | n/a (pure) | `declared_templates(app)` is the provider the core's listing command runs. It walks every route's parameters and body models and lists each Pydantic sentence a field can produce, its constraints' values settled as at runtime, plus the `PydanticCustomError` templates a validator declares with `@declares`. A sentence Pydantic fills with its parser's text at runtime, and an undeclared validator, are reported with where and what would make them listable; they register when first emitted (MSG-8). `test_MSG7_the_listing_covers_every_template_the_app_emits_ahead_of_time` and `test_MSG7_what_cannot_be_listed_is_reported_with_where_and_what_to_do`. Through the core's command, `test_MSG7_the_command_reports_what_it_cannot_list_and_fails_only_under_strict` exits 0 on a report and 1 under `strict`. Mutation: ignoring a validator's declared templates reddens the second |
| MSG-8 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[MSG-8]`: 0 here, 5 in core. The handler builds entries through the core client inside the request scope, so an unlisted template is registered after the response: `test_contract.py::test_MSG8_a_template_the_catalog_lacks_is_registered_after_the_failed_response` reads the template back from the double |
| MSG-9 | implemented | n/a (pure) | Entries are built from Pydantic's own unfilled sentence for the failure and its context values. Pydantic's rendered `msg` is only compared against, never parsed: a template that would not fill to it registers Pydantic's words as they stand, with no params. A custom error takes the template its validator declares; one with none registers as its text with no params, and the listing reports it. `test_MSG3_MSG9_each_template_is_pydantics_sentence_before_its_values_are_filled`; `test_MSG9_a_custom_error_with_no_declared_template_registers_as_its_text` |
| MSG-10 | n/a (architecture: Pydantic's validation messages never reference the field, so there is no label to write in, live if a template this binding emits names its field) | - | Pydantic prints no label; the field travels as Pydantic's own `loc` in each entry's `field` |
| MSG-11 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MSG-11]`: 0 here, 3 in core. This package feeds both halves: the listing's templates go through the core's `TemplateList`, and runtime entries through the core client's `server_message` |
| MSG-12 | n/a (architecture: FastAPI has no redirect-after-failure hand-off such as Inertia's, so there is no next page to carry entries to, live if the binding adds one) | - | A failed request answers its entries in the response itself |
| MIG-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-1]`: no legacy-key handling here, 0 here, 51 in core |
| MIG-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-2]`: 0 here, 51 in core |
| MIG-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-3]`: 0 here, 51 in core |
| MIG-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-4]`: 0 here, 51 in core |
| MIG-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-5]`: 0 here, 51 in core |
| MIG-6 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-6]`: 0 here, 51 in core |
| MIG-7 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-7]`: 0 here, 51 in core |
| MIG-8 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MIG-8]`: 0 here, 51 in core |
| MIG-9 | delegated | - | Core: not implemented. Probe `test_ABSENCE[MIG-9]`: 0 here, 51 in core |
| SNAP-1 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[SNAP-1]`: no export here, 0 here, 1 in core |
| SNAP-2 | implemented | n/a (pure) | `configure(snapshot=…)` seeds the shared client from an exported snapshot when it is built, through the core's `load_snapshot`: this binding decides to seed at boot. `test_request_boundary.py::test_SNAP2_a_snapshot_given_to_configure_seeds_the_client_and_answers_with_no_network`: with the API unreachable, a phrase the snapshot holds is translated and one it lacks falls back to its source text. Mutation: never seeding reddens it |
| SNAP-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[SNAP-3]`: no snapshot is read or written here, 0 here, 10 in core |
| BIND-1 | implemented | n/a (pure) | Shape and timing only, tested by running the spec's first heuristic. `test_BIND1_deleting_the_binding_changes_nothing_but_shape`: the same vectors through `t()`, through `at()` and directly through the core give identical text and identical queues. `at()` is a threadpool shape adapter; the validation handler is framework adaptation — Pydantic's failed rules and labels into the core's entry. Mutation: `t()` dropping the category reddens it. Known shape limit: see gaps |
| BIND-2 | implemented | n/a (pure) | `test_ABSENCE[BIND-2]`: no capability name in this package's code, 0 here, 59 in core; the firing control is the `29bb650` end-of-request branch verbatim. Behaviour: `test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`. Mutation: restoring the branch reddens 3 named tests |
| BIND-3 | implemented | n/a (pure) | `test_ABSENCE[BIND-3]`: no transport, timer, sleep, retry, backoff, header or `debounce` in this package's code, 0 here, 35 in core. The end-of-request flush and the request scope are lifecycle calls into the core, not schedules. Firing control: a client built with `debounce=None`. Mutation: building the shared client that way reddens this probe and REG-2's |
| BIND-4 | implemented | n/a (pure) | `test_BIND4_configure_introduces_no_option_the_core_does_not_define`: every `configure()` option is a `LangsysClient` option. `test_BIND4_the_middleware_introduces_only_request_shape_options`: the middleware takes only `path_segment`, `subdomain`, `query_param` and `cookie_name` — SRV-6's wiring, where the app keeps a value the core defines. Firing controls: the `29bb650` signature with `auto_flush` and `supported`, and a `discovery` option. Mutation: restoring `auto_flush` reddens it |
| BIND-5 | implemented | n/a (pure) | `test_ABSENCE[BIND-5]`: nothing memoized in front of `t()`, 0 here, 10 in core. Mutation: `lru_cache` on `t()` reddens it |
| BIND-6 | implemented | n/a (pure) | `test_BIND6_nothing_exported_shadows_a_core_name_with_something_else` and `test_BIND6_DI_hands_out_the_core_client_itself`: DI returns the core `LangsysClient` itself. The other exported names are framework idioms — the middleware, `t`/`at` over the shared client, DI providers, request-locale accessors — and `langsys_fastapi.messages` adds only the Pydantic side of the entry the core defines. Mutation: exporting a reimplemented core name reddens it |
| GRANT-1 | n/a (profile: browser) | - | A server binding holds a key, not a grant. No header is set here (`test_ABSENCE[WIRE-1]`) |
| GRANT-2 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-3 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-4 | n/a (profile: browser) | - | A server binding holds a key, not a grant. The core asserts, live, that it never sends `X-Write-Grant` |
| CACHE-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CACHE-1]`: no cache key built here, 0 here, 11 in core. `configure(cache=…)` passes the backend through unchanged |
| CACHE-2 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[CACHE-2]`: no failure window here, 0 here, 3 in core. The shared client outlives every request, so the core's window does too |
| OBS-1 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[OBS-1]`: 0 here, 11 in core. The core re-arms its once-per-session notice on `reset_write_decision()`; called per request here, the request is the session |
| WIRE-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-1]`: no auth header here, 0 here, 8 in core |
| WIRE-2 | delegated | - | Core: implemented, contract. Probe `test_ABSENCE[WIRE-2]`: no response parsing here, 0 here, 1 in core |
| WIRE-3 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-3]`: 0 here, 35 in core. The locale this package hands the core is the core resolver's own answer; lowercasing for the wire happens in the core |
| WIRE-4 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-4]`: no API call of this package's own, 0 here, 13 in core. When the project's locales cannot be read, the core's resolver serves the configured base locale rather than raising |
| WIRE-5 | implemented | n/a (pure) | `test_WIRE5_configure_redirects_the_api_base_even_after_first_use`: requests arrive at one double, then at a second after `configure()` is called again once the client has been used. `test_WIRE5_the_seam_is_findable_where_an_integrator_looks`: the README's Configuration section names `api_url` and `LANGSYS_API_URL`, and so does the `configure()` docstring. The contract tests reach the shared double through this seam. Mutation: `configure()` not rebuilding the client reddens the first |
| CONF-1 | implemented | live | Every row whose property depends on what the API answers is proven against a server that can say no, asserting what it accepted: REG-3 and SRV-1 live; SRV-3, SRV-6 and MSG-8's evidence against the contract double, with drift for the absence. Every path: SRV-1 is proven on sync `t()`, async `at()` and DI. The mock-backed unit tests beside them are supporting evidence, not the grade |
| CONF-2 | implemented | n/a (pure) | Every row carries a tier, and `_dev_/conformance_counts.py` rejects a tier its status cannot carry, including anything but `-` on a delegated row. The shared contract fixture is vendored by tree id (`542f57f5`) and reached through WIRE-5's seam; the one absence proven here drifts the capability and carries its control (SRV-3). `live` evidence comes from a committed, idempotent seeder |
| CONF-3 | implemented | n/a (pure) | `_dev_/mutations.py`: 26 mutations across every implemented row that running something can break. Each must redden its named tests against a green baseline, and the tree is restored byte-for-byte afterwards; all 26 redden against core `e834170`. For delegated rows, each probe's firing control is the mutation |

---

## Gaps, ranked by cost

1. **Delegated rows are only as good as the core rows they cite.** At `e834170` the core grades
   MIG-9 `not implemented`. Those are the core's to close; these rows follow its grades.
2. **A `{category}` or `{phrase}` placeholder cannot be passed to `t()` or `at()` as a keyword,**
   and `category=` is silently taken as the category — the placeholder stays unfilled and the
   phrase is queued under that category. The core takes placeholders only through a `params`
   mapping; the matching shape here is a `params=` mapping on `t()` and `at()`, decided together
   with `langsys-python-django`, which shares the signature. Until then the README documents the
   DI client as the way to pass those names.
3. **A raised request's send timing rests on the core's debounce.** Its scope ends as the
   exception leaves the middleware, before Starlette's error middleware sends the 500, and the
   core's debounce sends its misses 400ms later — after the error response, as
   `test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response` asserts, but by
   timing rather than by an event.
4. **The declared dependency does not express what the middleware needs.** `pyproject.toml` says
   `langsys>=0.1.0`; the middleware needs the core's request scope, request-locale resolver and
   snapshot seam. The floor moves with the core's first release that includes them.

## Reproducing

```bash
.venv/bin/pytest                          # 121 passed, the contract double included; live tests skip
php artisan db:seed                       # in langsys2: (re)creates the slot-15 fixture
.venv/bin/pytest -m integration           # 5 live; environment in tests/test_live.py
.venv/bin/python _dev_/mutations.py       # CONF-3: every mutation must redden its named tests
python3 _dev_/conformance_counts.py       # this file's tally, against the pinned spec blob
```

The contract tests need Node 18 or later. The editable link follows `langsys-python`'s working
tree; to run against the commit this file cites, prefix any command above with `PYTHONPATH`:

```bash
mkdir -p /tmp/langsys-core && git -C ../langsys-python archive e834170 src | tar -x -C /tmp/langsys-core
PYTHONPATH=/tmp/langsys-core/src .venv/bin/pytest
```
