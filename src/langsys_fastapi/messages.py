"""Server messages for FastAPI (spec MSG family): Pydantic's validation errors, translatable.

FastAPI answers a failed request with its own 422 body, ``{"detail": [error, …]}``, and this
module leaves that body exactly as FastAPI writes it. It attaches one entry per error under a
configurable key, so each failure can be translated (MSG-1):

* ``code`` — Pydantic's own error ``type``, passed through unchanged (MSG-2);
* ``field`` — Pydantic's own ``loc``;
* ``template`` — Pydantic's own sentence for that type, before its values are filled (MSG-3,
  MSG-9), with ``params`` filling its markers, and ``message``, the template filled.

A number in Pydantic's sentence stays a ``{name}`` marker. Text Pydantic writes into its sentence
— the plural ``s``, the allowed values of a ``Literal``, a pattern, a validator's own message — is
written in, so the translator sees the whole sentence. Pydantic's messages never name the field,
so no label is written in. Filled, a template is exactly the ``msg`` Pydantic rendered; where it
could not be, the entry registers Pydantic's words as they stand, with no params.

Setup::

    from langsys_fastapi.messages import install
    install(app)   # FastAPI's own 422 body, plus "langsys_errors": [entry, …]
"""

from __future__ import annotations

import contextlib
import enum
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import date, datetime, time
from decimal import Decimal
from inspect import isclass
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Callable,
    Literal,
    Optional,
    TypeVar,
    Union,
    get_args,
    get_origin,
)

import annotated_types as at
from fastapi import FastAPI, Request
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from langsys.messages import (
    DEFAULT_ATTACH_KEY,
    TemplateProblem,
    attach_server_messages,
    fill_template,
    server_message,
    template_markers,
)
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic_core._pydantic_core import list_all_errors
from starlette.concurrency import run_in_threadpool

from .client import get_client

if TYPE_CHECKING:
    from langsys import LangsysClient

__all__ = [
    "declared_templates",
    "declares",
    "entries_from_errors",
    "install",
    "validation_entries",
]

Entry = dict[str, Any]
Declared = Union[str, Mapping[str, Any], TemplateProblem]
F = TypeVar("F", bound=Callable[..., Any])

#: Pydantic's own unfilled sentence for each of its error types.
_PYDANTIC: dict[str, str] = {e["type"]: e["message_template_python"] for e in list_all_errors()}

#: For the sentences whose `{expected_plural}` Pydantic derives itself, the count it follows.
_SUFFIX_COUNT = {
    "string_too_short": "min_length",
    "string_too_long": "max_length",
    "too_short": "min_length",
    "too_long": "max_length",
}

#: Templates apps declared for their own validators' errors (see `declares`).
_DECLARED: set[str] = set()


def declares(*templates: str) -> Callable[[F], F]:
    """Name the templates a custom validator can fail with — its ``PydanticCustomError``
    message templates — so the listing command lists them rather than reporting the validator,
    and an error it raises is matched back to its template. Put it under ``@field_validator``."""
    _DECLARED.update(templates)

    def mark(func: F) -> F:
        for target in (func, getattr(func, "__func__", None)):
            if target is not None:
                with contextlib.suppress(AttributeError, TypeError):
                    setattr(target, "__langsys_templates__", templates)  # noqa: B010
        return func

    return mark


# -- errors -> entries -----------------------------------------------------------------------


def entries_from_errors(
    errors: Iterable[Mapping[str, Any]], *, client: Optional[LangsysClient] = None
) -> list[Entry]:
    """An entry for each of Pydantic's ``errors()``. With ``client`` each goes through
    ``client.server_message``, which registers a template the catalog lacks after the response
    (MSG-8) and warns on a catalogued phrase in a marker (MSG-11)."""
    build = client.server_message if client is not None else server_message
    entries: list[Entry] = []
    for error in errors:
        code = str(error.get("type", ""))
        template, params = _template(code, dict(error.get("ctx") or {}), str(error.get("msg", "")))
        entries.append(
            build(template, params or None, field=list(error.get("loc") or ()), code=code)
        )
    return entries


def validation_entries(
    exc: RequestValidationError, client: Optional[LangsysClient] = None
) -> list[Entry]:
    """Entries for a failed FastAPI request."""
    return entries_from_errors(exc.errors(), client=client)


def install(app: FastAPI, *, key: str = DEFAULT_ATTACH_KEY) -> None:
    """Attach entries to FastAPI's own 422 body under ``key`` — the core's ``langsys_errors`` by
    default; the body is otherwise FastAPI's."""

    async def handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        native = await request_validation_exception_handler(request, exc)
        entries = await run_in_threadpool(validation_entries, exc, get_client())
        body = json.loads(bytes(native.body))
        attach_server_messages(body, entries, key)
        kept = {
            k: v
            for k, v in native.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }
        return JSONResponse(body, native.status_code, headers=kept)

    app.add_exception_handler(RequestValidationError, handler)  # type: ignore[arg-type]


def _template(
    kind: str, ctx: dict[str, Any], rendered: Optional[str]
) -> tuple[str, dict[str, Any]]:
    """Pydantic's sentence for ``kind`` with its values settled: a number or a date stays a
    marker and becomes a param; text is written in. ``rendered`` is Pydantic's own ``msg``: the
    filled template must equal it, or Pydantic's words stand as the template, with no params."""
    source = _PYDANTIC.get(kind)
    if source is None:
        source = next((t for t in sorted(_DECLARED) if _fills(t, ctx) == rendered), None)
        if source is None:
            return (rendered or kind), {}
        return source, {m: _param(ctx[m]) for m in template_markers(source) if m in ctx}
    text, params = source, {}
    for name in template_markers(source):
        if name == "expected_plural" and name not in ctx:
            count = ctx.get(_SUFFIX_COUNT.get(kind, ""))
            text = text.replace("{expected_plural}", "" if count == 1 else "s")
        elif name in ctx and _is_value(ctx[name]):
            params[name] = _param(ctx[name])
        elif name in ctx:
            text = text.replace("{" + name + "}", str(ctx[name]))
    if rendered is not None and fill_template(text, params) != rendered:
        return rendered, {}
    return text, params


def _fills(template: str, ctx: dict[str, Any]) -> str:
    return fill_template(template, {k: _param(v) for k, v in ctx.items()})


def _is_value(value: Any) -> bool:
    """A number or a date: not translatable, so a marker (MSG-3)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float, Decimal, date, time)):
        return True
    if isinstance(value, str):
        for parse in (date.fromisoformat, datetime.fromisoformat, time.fromisoformat):
            try:
                parse(value)
                return True
            except ValueError:
                continue
    return False


def _param(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (date, time)):
        return value.isoformat()
    return value


# -- listing (MSG-7) ---------------------------------------------------------------------------


def declared_templates(app: FastAPI) -> Iterator[Declared]:
    """Every template ``app``'s routes can emit, for the core's listing command (MSG-7).

    What cannot be listed ahead of time — a sentence Pydantic fills with its parser's own text,
    a custom validator whose templates are not declared with :func:`declares` — is reported, and
    registers the first time it is emitted. Wire it up with a provider in your app::

        def templates():
            return declared_templates(app)

        # python -m langsys.messages --provider myapp.langsys:templates [--register]
    """
    for kind in ("missing", "model_attributes_type"):
        yield {"template": _PYDANTIC[kind], "source": "FastAPI request body"}
    yield _runtime("json_invalid", "FastAPI request body", "")
    seen: set[Any] = set()
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        where = f"{','.join(sorted(route.methods))} {route.path}"
        flat = get_flat_dependant(route.dependant)
        for param in (
            *flat.query_params,
            *flat.path_params,
            *flat.header_params,
            *flat.cookie_params,
        ):
            yield from _field_templates(
                param.field_info, _annotation(param), param.alias, where, where, seen
            )
        if route.body_field is not None:
            yield from _model_templates(_annotation(route.body_field), "", where, seen)


def _runtime(kind: str, source: str, field: str) -> TemplateProblem:
    return TemplateProblem(
        f"Pydantic fills {_PYDANTIC[kind]!r} with its parser's own text at runtime",
        source=source,
        field=field,
        fix="nothing is needed: it registers the first time it is emitted",
    )


def _model_templates(model: Any, prefix: str, where: str, seen: set[Any]) -> Iterator[Declared]:
    """Templates for every field of ``model``; ``where`` names the route."""
    model = _unwrap(model)
    if not _is_model(model) or (model, prefix) in seen:
        return
    seen.add((model, prefix))
    source = f"{where} {model.__name__}"
    if model.model_config.get("extra") == "forbid":
        yield {"template": _PYDANTIC["extra_forbidden"], "source": source}
    for name, info in model.model_fields.items():
        path = f"{prefix}.{info.alias or name}" if prefix else (info.alias or name)
        yield from _field_templates(info, info.annotation, path, source, where, seen)
    decorators = model.__pydantic_decorators__
    for validator in (*decorators.field_validators.values(), *decorators.model_validators.values()):
        declared = next(
            (
                getattr(f, "__langsys_templates__", None)
                for f in (validator.func, getattr(validator.func, "__func__", None))
                if getattr(f, "__langsys_templates__", None) is not None
            ),
            None,
        )
        fields = ",".join(getattr(validator.info, "fields", ()))
        if declared is not None:
            for template in declared:
                yield {"template": template, "source": source, "field": fields}
            continue
        yield TemplateProblem(
            f"validator {validator.cls_var_name!r} can fail with a message built at runtime",
            source=source,
            field=fields,
            fix="raise PydanticCustomError(type, template, ctx) and name its templates with "
            "@declares(...); until then it registers the first time it is emitted",
        )


def _field_templates(
    info: Any, annotation: Any, path: str, source: str, where: str, seen: set[Any]
) -> Iterator[Declared]:
    kind = _unwrap(annotation)
    if info.is_required():
        yield {"template": _PYDANTIC["missing"], "source": source, "field": path}
    for error_type in _type_errors(kind):
        if "{error}" in _PYDANTIC[error_type]:
            yield _runtime(error_type, source, path)
        else:
            yield {"template": _PYDANTIC[error_type], "source": source, "field": path}
    if get_origin(kind) is Literal or (isclass(kind) and issubclass(kind, enum.Enum)):
        template = _exact(kind)
        if template:
            yield {"template": template, "source": source, "field": path}
    for rule in info.metadata:
        for error_type, ctx in _constraint_errors(rule, kind):
            template, _ = _template(error_type, ctx, None)
            yield {"template": template, "source": source, "field": path}
    origin = get_origin(kind)
    item = get_args(kind)[0] if origin in (list, tuple, set, frozenset) and get_args(kind) else None
    for nested in (kind, item):
        if _is_model(_unwrap(nested)):
            yield from _model_templates(nested, path, where, seen)


def _exact(annotation: Any) -> Optional[str]:
    """Pydantic's own sentence for a value outside ``annotation``'s choices, from Pydantic."""
    try:
        TypeAdapter(annotation).validate_python(object())
    except ValidationError as failure:
        error = failure.errors()[0]
        template, _ = _template(error["type"], dict(error.get("ctx") or {}), error["msg"])
        return template
    return None


def _type_errors(kind: Any) -> list[str]:
    origin = get_origin(kind)
    if origin in (list, tuple, set, frozenset) or kind in (list, tuple, set, frozenset):
        return ["list_type"]
    if not isclass(kind):
        return []
    for base, kinds in (
        (bool, ["bool_type", "bool_parsing"]),
        (int, ["int_type", "int_parsing", "int_from_float"]),
        (str, ["string_type"]),
        (float, ["float_type", "float_parsing"]),
        (Decimal, ["decimal_type", "decimal_parsing"]),
        (datetime, ["datetime_type", "datetime_parsing"]),
        (date, ["date_type", "date_parsing"]),
        (time, ["time_type", "time_parsing"]),
    ):
        if issubclass(kind, base):
            return [k for k in kinds if k in _PYDANTIC]
    if _is_model(kind):
        return ["model_attributes_type"]
    return []


def _constraint_errors(rule: Any, kind: Any) -> list[tuple[str, dict[str, Any]]]:
    origin = get_origin(kind)
    collection = {list: "List", set: "Set", frozenset: "Frozenset", tuple: "Tuple"}.get(origin)
    if isinstance(rule, at.MinLen):
        if collection:
            return [
                (
                    "too_short",
                    {"field_type": collection, "min_length": rule.min_length, "actual_length": 0},
                )
            ]
        return [("string_too_short", {"min_length": rule.min_length})]
    if isinstance(rule, at.MaxLen):
        if collection:
            return [
                (
                    "too_long",
                    {"field_type": collection, "max_length": rule.max_length, "actual_length": 0},
                )
            ]
        return [("string_too_long", {"max_length": rule.max_length})]
    for bound, name, key in (
        (at.Ge, "greater_than_equal", "ge"),
        (at.Gt, "greater_than", "gt"),
        (at.Le, "less_than_equal", "le"),
        (at.Lt, "less_than", "lt"),
    ):
        if isinstance(rule, bound):
            return [(name, {key: getattr(rule, key)})]
    if isinstance(rule, at.MultipleOf):
        return [("multiple_of", {"multiple_of": rule.multiple_of})]
    if getattr(rule, "pattern", None):
        return [("string_pattern_mismatch", {"pattern": rule.pattern})]
    return []


def _annotation(field: Any) -> Any:
    info = getattr(field, "field_info", None)
    return getattr(info, "annotation", None) or getattr(field, "type_", None)


def _unwrap(annotation: Any) -> Any:
    while True:
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is Union:
            present = [a for a in args if a is not type(None)]
            if len(present) != 1:
                return annotation
            annotation = present[0]
        elif origin is Annotated:
            annotation = args[0]
        else:
            return annotation


def _is_model(annotation: Any) -> bool:
    return isclass(annotation) and issubclass(annotation, BaseModel)
