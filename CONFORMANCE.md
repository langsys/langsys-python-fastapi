# Conformance — `langsys-fastapi`

| | |
|---|---|
| **Spec revision read** | langsys2 a1b7568c…, docs/sdk-spec.mdx blob b0474afba2c9c1639baa8da219fa6a441b3e1c2f |
| **Profiles** | server, binding — the spec's per-SDK table row for `langsys-python-fastapi`, over core `langsys-python` |
| **SDK** | `langsys-fastapi`, the FastAPI/Starlette binding |
| **specVersion** | 8.2.12 |
| **SDK revision** | `feature/838_write_key_gating`, cut from `main` `29bb650` |
| **Core revision** | `langsys-python` `8575631a1296e7ca694c9badd786aa880829a4a3`, as a clean `git archive` — see *Reproducing* |
| **Contract fixture** | `tests/contract-fixture/`, tree `542f57f5ffcb9038db1b7411152b7e31b96cb269`, vendored byte-exact with the core's harness `tests/contract.py` |
| **Published** | Never — PyPI and TestPyPI both 404 (positive control: `httpx` → 200) |
| **Suite** | 114 passed by default, the contract tests included; 5 live under `pytest -m integration`, all passing against the local stack |

Spec version implemented: **v8.2.12**, blob `b0474afba2c9c1639baa8da219fa6a441b3e1c2f`. The blob is
re-derived on every write of this file, from the commit rather than a branch:
`git -C ~/Documents/dev/langsys2 rev-parse a1b7568c7ebcc53d074d30665e2195c122ea6978:docs/sdk-spec.mdx`.
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
`8575631`, graded as that file grades it. That file still grades spec 8.0.1's 79 rules, so a rule
new since then reads "no core row yet" until the core re-rows. Each delegated row carries an
absence probe, `tests/test_probes.py::test_ABSENCE[<rule>]`: it reads this package's code only
(docstrings and comments blanked), asserts it read all 6 files, and carries a firing control, a
snippet the same filter must catch. The count beside each probe is the same pattern run over the
core at `8575631`; a core count of 0 means the core has no such code either, and the firing
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
| `n/a (architecture: …)` | 6 | GATE-10, HINT-13, SRV-4, SRV-5, MSG-12, SNAP-2 |
| **total** | **113** | |

## Status

| Rule | Status | Tier | Evidence |
|---|---|---|---|
| GATE-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[GATE-1]`: key type named 0 times here, 27 in core; control `if client.key_type == "write"` fires |
| GATE-2 | delegated | - | Core: provisional, mock. Probe `test_ABSENCE[GATE-2]`: 0 here, 8 in core; the firing control is the `29bb650` end-of-request branch verbatim. The end-of-request flush calls the core's `flush_pending()` unconditionally, so hold-on-unknown is decided in the core. Through the middleware: `test_request_boundary.py::test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`, with control `test_GATE2_CONTROL_a_server_no_still_discards_through_the_middleware` |
| GATE-3 | implemented | n/a (pure) | The middleware calls the core's `reset_write_decision()` at the end of every request, in a `finally`, discharging the obligation the core declares for wrappers. `test_request_boundary.py::test_GATE3_a_no_observed_in_one_request_does_not_silence_the_next`: one request is told no; the next has a warm plain write key and a cached catalog, and still registers. Mutation: dropping the reset reddens it. No carve-out is taken |
| GATE-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[GATE-4]`: nothing cached and no decision named here, 0 here, 29 in core |
| GATE-5 | delegated | - | Core: provisional, mock. Probe `test_ABSENCE[GATE-5]`: 0 here, 0 in core. The core keeps no "already registered" store either; control `self._registered.add(key)` fires |
| GATE-6 | delegated | - | Core: n/a (architecture: no report lane exists, per HINT-2; live if one is ever added). Probe `test_ABSENCE[GATE-6]`: no report lane, 0 here, 0 in core; control `http.post("discovery/hint", …)` fires |
| GATE-7 | delegated | - | Core: partial, n/a (pure). Probe `test_ABSENCE[GATE-7]`: 0 here, 8 in core. Every entry point here (`t()`, `at()`, DI, the validation handler) reaches the core, and the end-of-request flush feeds only the core's register lane |
| GATE-8 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[GATE-8]`: 0 here, 59 in core |
| GATE-9 | n/a (profile: browser) | - | The base-locale discovery gate is a browser client's |
| GATE-10 | n/a (architecture: this binding renders no HTML of its own, so it has no root or element to mark and no DOM host that reads a mark, live if it adds a template integration) | - | The core's `translate_page()`, reachable through the DI client, is the producer on this stack and marks its root off the base locale |
| CAT-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-1]`: no catalog read here, 0 here, 72 in core |
| CAT-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-2]`: 0 here, 72 in core |
| CAT-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CAT-3]`: 0 here, 93 in core |
| REG-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[REG-1]`: no registration call or POST here, 0 here, 10 in core |
| REG-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-2]`: no debounce, timer or task here, 0 here, 12 in core. `test_REG2_everything_one_request_found_goes_out_as_one_request` shows a five-miss request going out as one request with no flush in the app |
| REG-3 | implemented | live | The execution context this binding owns is the request: once the response is out, the middleware hands the queue to the core's public `flush_pending()`, and `reset_client()` and `configure()` flush a retired client before closing it. Live: `tests/test_live.py::test_LIVE_SRV3_REG3_accepted_after_the_response_and_never_from_a_read_key[CONTROL-write-key-on-the-same-render-pushes]` — the stack answered the POST 2xx and the queue is empty. Also `test_REG3_reconfiguring_hands_the_retired_client_s_queue_to_the_core_first`. Mutations: dropping the end-of-request flush reddens 3 named tests; closing without flushing reddens 1. The manual flush is the core's, reachable as `get_langsys().flush_pending()` and documented in the README |
| REG-4 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-5 | n/a (profile: browser) | - | No page teardown exists on a server |
| REG-6 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-6]`: the private queue is never touched here, 0 here, 33 in core |
| REG-7 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-7]`: 0 here, 3 in core. The lock here guards building the client, not sending |
| REG-8 | delegated | - | Core: provisional, mock. Probe `test_ABSENCE[REG-8]`: no retry or backoff here, 0 here, 20 in core. The shared client outlives every request, so the core's failure clock does too |
| REG-9 | delegated | - | Core: provisional, mock. Probe `test_ABSENCE[REG-9]`: 0 here, 13 in core |
| REG-10 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[REG-10]`: this package returns no flush result, 0 here, 14 in core. Its end-of-request guard logs and never raises past a response already sent |
| REG-11 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-11]`: 0 here, 14 in core |
| REG-12 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[REG-12]`: 0 here, 22 in core |
| REG-13 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[REG-13]`: no catalog-load state here, 0 here, 0 in core |
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
| ICU-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-1]`: no interpolation here, 0 here, 37 in core. `test_BIND1_…` runs an ICU plural through `t()`, `at()` and the core and gets identical output |
| ICU-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-2]`: 0 here, 37 in core. The `test_BIND1_…` vectors include a null count |
| ICU-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-3]`: 0 here, 37 in core |
| ICU-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-4]`: 0 here, 37 in core |
| ICU-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[ICU-5]`: 0 here, 37 in core |
| ICU-6 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[ICU-6]`: no formatter here, 0 here, 37 in core |
| CID-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-1]`: no hashing or ids here, 0 here, 56 in core |
| CID-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-2]`: 0 here, 56 in core |
| CID-3 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-3]`: 0 here, 56 in core |
| CID-4 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CID-4]`: 0 here, 56 in core |
| TOK-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-1]`: no parser or tokenizer here, 0 here, 52 in core. HTML paths are reachable only through the DI client, which is the core itself (BIND-6) |
| TOK-2 | delegated | - | Core: held (strip ruling), n/a (pure). Probe `test_ABSENCE[TOK-2]`: 0 here, 52 in core |
| TOK-3 | delegated | - | Core: partial, n/a (pure). Probe `test_ABSENCE[TOK-3]`: 0 here, 52 in core |
| TOK-4 | delegated | - | Core: partial, n/a (pure). Probe `test_ABSENCE[TOK-4]`: 0 here, 52 in core |
| TOK-5 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[TOK-5]`: 0 here, 52 in core |
| TOK-6 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[TOK-6]`: 0 here, 52 in core |
| MARK-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-1]`: no identity or resolved attribute here, 0 here, 29 in core |
| MARK-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[MARK-2]`: 0 here, 29 in core |
| MARK-3 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MARK-3]`: 0 here, 29 in core |
| MARK-4 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MARK-4]`: 0 here, 29 in core |
| SSR-1 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-2 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SSR-3 | n/a (profile: browser) | - | These rules constrain a browser SDK running under server rendering |
| SRV-1 | implemented | live | Asserted on the served bytes, on every route this binding exposes: `tests/test_live.py::test_LIVE_SRV1_the_served_bytes_carry_the_request_locale[/sync]`, `[/async]` and `[/di]`. The response body carries `Soporte Técnico` from the live es-es catalog, and a control phrase absent from it, in the same render, emits the base language and is queued as a miss. Unit twins are in `test_request_boundary.py`. Mutation: never exposing the resolved locale reddens all three |
| SRV-2 | implemented | n/a (pure) | `test_SRV2_concurrent_requests_in_different_locales_see_only_their_own[/srv2/async]` and `[/srv2/sync]`: an es request and a de request are both inside their scope before either translates, held there by asyncio events on the async path and a thread barrier on the threadpool path. Mutation: holding the locale in a process global reddens both |
| SRV-3 | implemented | contract | The middleware opens the core's request scope at request start and ends it once the final response body has been sent, then flushes; while the scope is open, no flush sends the request's misses. Order of events: `test_SRV3_REG3_registration_happens_after_the_response_is_sent`; `test_SRV3_a_slow_handler_sends_nothing_before_its_response`, whose handler outlives the core's 400ms debounce; `test_SRV3_another_request_s_flush_sends_nothing_before_this_response`, where a concurrent request finishes first; `test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response`, ordered by the core's debounce. Read-only half, with CONF-2's drift: `test_contract.py::test_SRV3_a_session_that_may_not_write_pushes_nothing_even_once_the_world_would_accept` — an `ip_write` session not allow-listed pushes nothing, the double's allow-list then widens and the state stays empty, and in the drifted world a request that may write registers its own miss. Write acceptance, live: `test_LIVE_SRV3_REG3_…[CONTROL-write-key-on-the-same-render-pushes]`. Mutations: releasing and flushing before the body, never opening the scope, and leaving a raised request's scope open each redden their named tests |
| SRV-4 | n/a (architecture: this binding performs no hydration hand-off because FastAPI responses are terminal, as the spec's per-SDK table records, live if the binding ships a client entry or template integration that hydrates) | - | No client renders against a FastAPI response |
| SRV-5 | n/a (architecture: FastAPI has no component model, so this binding renders no children to capture, live if a template-component integration is added) | - | The core's DOM walker is reachable only through the DI client, where it is the core's row |
| SRV-6 | implemented | contract | The middleware asks the core's `resolve_request_locale` for the locale — the URL's `?locale=`, then the locale cookie, then `Accept-Language`, then the project's base locale, each validated against the project's locales — merges the returned `Vary` into the app's own, and never writes a cookie. The query-parameter and cookie names are wiring; `cookie_name=None` declares that the app keeps no locale cookie. Against the double serving en-us, it-it and es-es: `test_contract.py::test_SRV6_one_url_resolves_url_then_cookie_then_header_each_validated` — the URL wins over a conflicting cookie and header with no `Vary`; a cookie wins with `Vary: Cookie`; a header alone is negotiated with `Vary` naming `Accept-Language`; an unsupported cookie falls through to the header and is not re-set; an unsupported URL locale falls through to the base. `test_SRV6_vary_is_merged_into_the_apps_own` and `test_SRV6_an_app_with_no_locale_cookie_does_not_vary_on_one`. Mutations: never sending `Vary`, replacing the app's `Vary`, and never offering the cookie each redden their named tests |
| MSG-1 | implemented | n/a (pure) | `install(app)` answers a failed validation with the default langsys envelope, `{status: false, error: {code, message, template, errors: [entry, …]}}`, each entry `{field?, code, message, template, params?}` built by the core's constructor. `test_messages.py::test_MSG1_the_default_envelope_resolves_through_the_core_as_the_reference_does` resolves it through the core's `resolve_server_messages` exactly as the vector file's `langsys-envelope-validation` resolves; `test_MSG1_MSG4_every_entry_has_the_canonical_shape_and_message_is_the_filled_template` checks key order |
| MSG-2 | implemented | n/a (pure) | Codes come from the wording table, each in the shared vocabulary, and a size rule's code is the core's `size_code` for the field's type. `test_MSG2_codes_come_from_the_vocabulary_and_size_codes_follow_the_field_type`: text `too_short`, number `too_small`, list `too_many` |
| MSG-3 | implemented | n/a (pure) | Every template is a whole sentence with the field's label written in, worded as the langsys4 reference's `RuleWording`; markers carry only numbers and dates. `test_MSG3_labels_are_written_in_and_markers_hold_only_values` runs each emitted template through the core's `check_template` |
| MSG-4 | implemented | n/a (pure) | `test_MSG1_MSG4_every_entry_has_the_canonical_shape_and_message_is_the_filled_template`: `fill(template, params)` reproduces `message` for every entry, numbers are JSON numbers, and `params` is present exactly when the template has markers. `test_MSG9_the_canonical_reference_entry_is_what_a_failed_min_length_produces`: a failed `min_length=12` yields the vector file's canonical `too_short` entry byte for byte |
| MSG-5 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MSG-5]`: this package renders no entry, 0 here, 1 in core. An app renders an entry through the core client's `render_server_message`, reachable through DI |
| MSG-6 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MSG-6]`: no category chosen here, 0 here, 7 in core. Entries are built through the core client, under its `message_category`; `configure(message_category=…)` passes the core's option through unchanged |
| MSG-7 | implemented | n/a (pure) | `declared_templates(app)` is the provider the core's `python -m langsys.messages` command runs: it walks every route's parameters and body models and lists each template the wording table can produce, and names every untitled field and every validator that declares no templates, so the command exits non-zero. `test_MSG7_the_listing_covers_every_runtime_template_with_zero_problems` — every template a failed request emits is listed, with zero problems; `test_MSG7_MSG10_a_validated_field_with_no_label_fails_the_listing_by_name`; `test_MSG7_a_validator_that_declares_no_templates_fails_the_listing`. Mutation: listing an untitled field under its key instead of reporting it reddens the second |
| MSG-8 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MSG-8]`: 0 here, 5 in core. The handler builds entries through the core client inside the request scope, so an unlisted template is registered after the response: `test_contract.py::test_MSG8_a_template_the_catalog_lacks_is_registered_after_the_failed_response` reads both templates back from the double |
| MSG-9 | implemented | n/a (pure) | Entries come from the failed rule's type and context, never from Pydantic's rendered text; a date bound takes the date wording from the field's type. `test_MSG9_entries_are_built_from_the_failed_rules` — nine failures on one request, each the exact code, template and params expected, with no Pydantic sentence reaching a template; `test_MSG9_a_text_only_failure_becomes_invalid_with_its_own_text`; a validator's `message_error` declares its template and code. Mutation: building the template from Pydantic's rendered text reddens 3 named tests |
| MSG-10 | implemented | n/a (pure) | The label is the field's declared `Field(title=…)` or `Query(title=…)`, found by walking the error's location through nested models and lists. `test_MSG10_the_declared_title_is_the_label_not_the_key` (`items.0.label` is labelled `item label`); an untitled field is named by the listing (`test_MSG7_MSG10_…`). Mutation: labelling by the key reddens it |
| MSG-11 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MSG-11]`: 0 here, 10 in core. This package feeds both halves: the listing's templates go through the core's `TemplateList`, and runtime entries through the core client's `server_message` |
| MSG-12 | n/a (architecture: FastAPI has no redirect-after-failure hand-off such as Inertia's, so there is no next page to carry entries to, live if the binding adds one) | - | A failed request answers its entries in the response itself |
| MIG-1 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-1]`: no legacy-key handling here, 0 here, 7 in core |
| MIG-2 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-2]`: 0 here, 7 in core |
| MIG-3 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-3]`: 0 here, 7 in core |
| MIG-4 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-4]`: 0 here, 7 in core |
| MIG-5 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-5]`: 0 here, 7 in core |
| MIG-6 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-6]`: 0 here, 7 in core |
| MIG-7 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-7]`: 0 here, 7 in core |
| MIG-8 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-8]`: 0 here, 7 in core |
| MIG-9 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[MIG-9]`: 0 here, 7 in core |
| SNAP-1 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[SNAP-1]`: no export here, 0 here, 0 in core |
| SNAP-2 | n/a (architecture: a FastAPI response is rendered on the server per request, and nothing in this binding seeds a client before a first render, live if the binding adds a preload hook) | - | The core's catalog cache is what a server render reads |
| SNAP-3 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[SNAP-3]`: no snapshot is read or written here, 0 here, 0 in core |
| BIND-1 | implemented | n/a (pure) | Shape and timing only, tested by running the spec's first heuristic. `test_BIND1_deleting_the_binding_changes_nothing_but_shape`: the same vectors through `t()`, through `at()` and directly through the core give identical text and identical queues. `at()` is a threadpool shape adapter; the validation handler is framework adaptation — Pydantic's failed rules and labels into the core's entry. Mutation: `t()` dropping the category reddens it. Known shape limit: see gaps |
| BIND-2 | implemented | n/a (pure) | `test_ABSENCE[BIND-2]`: no capability name in this package's code, 0 here, 59 in core; the firing control is the `29bb650` end-of-request branch verbatim. Behaviour: `test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware`. Mutation: restoring the branch reddens 3 named tests |
| BIND-3 | implemented | n/a (pure) | `test_ABSENCE[BIND-3]`: no transport, timer, sleep, retry, backoff, header or `debounce` in this package's code, 0 here, 34 in core. The end-of-request flush and the request scope are lifecycle calls into the core, not schedules. Firing control: a client built with `debounce=None`. Mutation: building the shared client that way reddens this probe and REG-2's |
| BIND-4 | implemented | n/a (pure) | `test_BIND4_configure_introduces_no_option_the_core_does_not_define`: every `configure()` option is a `LangsysClient` option. `test_BIND4_the_middleware_introduces_only_request_shape_options`: the middleware takes only `query_param` and `cookie_name` — SRV-6's wiring, where the app keeps a value the core defines. Firing controls: the `29bb650` signature with `auto_flush` and `supported`, and a `discovery` option. Mutation: restoring `auto_flush` reddens it |
| BIND-5 | implemented | n/a (pure) | `test_ABSENCE[BIND-5]`: nothing memoized in front of `t()`, 0 here, 7 in core. Mutation: `lru_cache` on `t()` reddens it |
| BIND-6 | implemented | n/a (pure) | `test_BIND6_nothing_exported_shadows_a_core_name_with_something_else` and `test_BIND6_DI_hands_out_the_core_client_itself`: DI returns the core `LangsysClient` itself. The other exported names are framework idioms — the middleware, `t`/`at` over the shared client, DI providers, request-locale accessors — and `langsys_fastapi.messages` adds only the Pydantic side of the entry the core defines. Mutation: exporting a reimplemented core name reddens it |
| GRANT-1 | n/a (profile: browser) | - | A server binding holds a key, not a grant. No header is set here (`test_ABSENCE[WIRE-1]`) |
| GRANT-2 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-3 | n/a (profile: browser) | - | A server binding holds a key, not a grant |
| GRANT-4 | n/a (profile: browser) | - | A server binding holds a key, not a grant. The core asserts, live, that it never sends `X-Write-Grant` |
| CACHE-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[CACHE-1]`: no cache key built here, 0 here, 11 in core. `configure(cache=…)` passes the backend through unchanged |
| CACHE-2 | delegated | - | Core: no core row yet. Probe `test_ABSENCE[CACHE-2]`: no failure window here, 0 here, 0 in core. The shared client outlives every request, so the core's window does too |
| OBS-1 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[OBS-1]`: 0 here, 11 in core. The core re-arms its once-per-session notice on `reset_write_decision()`; called per request here, the request is the session |
| WIRE-1 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-1]`: no auth header here, 0 here, 8 in core |
| WIRE-2 | delegated | - | Core: implemented, n/a (pure). Probe `test_ABSENCE[WIRE-2]`: no response parsing here, 0 here, 17 in core |
| WIRE-3 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-3]`: 0 here, 20 in core. The locale this package hands the core is the core resolver's own answer; lowercasing for the wire happens in the core |
| WIRE-4 | delegated | - | Core: implemented, live. Probe `test_ABSENCE[WIRE-4]`: no API call of this package's own, 0 here, 12 in core. When the project's locales cannot be read, the core's resolver serves the configured base locale rather than raising |
| WIRE-5 | implemented | n/a (pure) | `test_WIRE5_configure_redirects_the_api_base_even_after_first_use`: requests arrive at one double, then at a second after `configure()` is called again once the client has been used. `test_WIRE5_the_seam_is_findable_where_an_integrator_looks`: the README's Configuration section names `api_url` and `LANGSYS_API_URL`, and so does the `configure()` docstring. The contract tests reach the shared double through this seam. Mutation: `configure()` not rebuilding the client reddens the first |
| CONF-1 | implemented | live | Every row whose property depends on what the API answers is proven against a server that can say no, asserting what it accepted: REG-3 and SRV-1 live; SRV-3, SRV-6 and MSG-8's evidence against the contract double, with drift for the absence. Every path: SRV-1 is proven on sync `t()`, async `at()` and DI. The mock-backed unit tests beside them are supporting evidence, not the grade |
| CONF-2 | implemented | n/a (pure) | Every row carries a tier, and `_dev_/conformance_counts.py` rejects a tier its status cannot carry, including anything but `-` on a delegated row. The shared contract fixture is vendored by tree id (`542f57f5`) and reached through WIRE-5's seam; the one absence proven here drifts the capability and carries its control (SRV-3). `live` evidence comes from a committed, idempotent seeder |
| CONF-3 | implemented | n/a (pure) | `_dev_/mutations.py`: 21 mutations across every implemented row that running something can break. Each must redden its named tests against a green baseline, and the tree is restored byte-for-byte afterwards; all 21 redden against core `8575631`. For delegated rows, each probe's firing control is the mutation |

---

## Gaps, ranked by cost

1. **Delegated rows are only as good as the core rows they cite.** At `8575631` the core's file
   grades spec 8.0.1: 21 delegated rules (REG-13, ICU-6, TOK-6, MARK-3, MARK-4, MSG-5, MSG-6, MSG-8, MSG-11, MIG-1, MIG-2, MIG-3, MIG-4, MIG-5, MIG-6, MIG-7, MIG-8, MIG-9, SNAP-1, SNAP-3, CACHE-2) have no core row yet, and it grades GATE-2, GATE-5, REG-8, REG-9 `provisional`; GATE-7, TOK-3, TOK-4 `partial`; TOK-2 `held (strip ruling)`. Those are the
   core's to close; these rows follow its grades as it re-rows.
2. **A `{category}` or `{phrase}` placeholder cannot be passed to `t()` or `at()` as a keyword,**
   and `category=` is silently taken as the category — the placeholder stays unfilled and the
   phrase is queued under that category. The core takes placeholders only through a `params`
   mapping; the matching shape here is a `params=` mapping on `t()` and `at()`, decided together
   with `langsys-python-django`, which shares the signature. Until then the README documents the
   DI client as the way to pass those names.
3. **The declared dependency does not express what the middleware needs.** `pyproject.toml` says
   `langsys>=0.1.0`; the middleware needs the core's request scope and request-locale resolver,
   which it carries from `8575631` on. The floor moves with the core's first release that
   includes them.
4. **Four sentences go beyond the reference wording table.** `less_than` ("must be less than
   {value}"), `extra_forbidden` (`not_allowed`, "is not allowed"), a model or mapping of the wrong
   type ("must be an object"), and the whole-request templates for a missing or malformed body
   are this binding's own wording. They follow the reference's form, and are named here so the
   fleet can adopt or replace them as one.
5. **A URL locale is read from the query string only.** SRV-6 also allows a path segment or
   subdomain the app routes by; an app that routes that way has no hook here yet to feed it in.
6. **A raised request's send timing rests on the core's debounce.** Its scope ends as the
   exception leaves the middleware, before Starlette's error middleware sends the 500, and the
   core's debounce sends its misses 400ms later — after the error response, as
   `test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response` asserts, but
   by timing rather than by an event.

## Reproducing

```bash
.venv/bin/pytest                          # 114 passed, the contract double included; live tests skip
php artisan db:seed                       # in langsys2: (re)creates the slot-15 fixture
.venv/bin/pytest -m integration           # 5 live; environment in tests/test_live.py
.venv/bin/python _dev_/mutations.py       # CONF-3: every mutation must redden its named tests
python3 _dev_/conformance_counts.py       # this file's tally, against the pinned spec blob
```

The contract tests need Node 18 or later. The editable link follows `langsys-python`'s working
tree; to run against the commit this file cites, prefix any command above with `PYTHONPATH`:

```bash
mkdir -p /tmp/langsys-core && git -C ../langsys-python archive 8575631 src | tar -x -C /tmp/langsys-core
PYTHONPATH=/tmp/langsys-core/src .venv/bin/pytest
```
