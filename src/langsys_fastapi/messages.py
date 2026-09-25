"""Server messages for FastAPI (spec MSG family): validation failures as entries.

The core's ``langsys.messages`` owns the entry shape, the fill, the template checks and the
listing command. This module supplies what only the framework knows:

* which Pydantic rules failed, and with what parameters (MSG-9) — entries are built from the
  failure's type and context, never from Pydantic's rendered text;
* the label a field declares with ``Field(title=…)`` or ``Query(title=…)`` (MSG-10);
* the default langsys envelope a FastAPI app answers a failed request with;
* a provider that lists every template an app's routes can emit, for
  ``python -m langsys.messages --provider …`` (MSG-7).

The wording follows the reference table: the label is written into the sentence, and only a
value that is not translatable — a number, a date — stays a ``{name}`` marker (MSG-3). A size
rule takes its code from the field's type through the core's ``size_code`` (MSG-2).

Setup::

    from langsys_fastapi.messages import install
    install(app)   # a failed request answers 422 with the langsys envelope
"""

from __future__ import annotations

import contextlib
import enum
from collections.abc import Iterable, Iterator, Mapping, Sequence
from datetime import date, time
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
from uuid import UUID

import annotated_types as at
from fastapi import FastAPI, Request
from fastapi.dependencies.utils import get_flat_dependant
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from langsys.messages import TemplateProblem, server_message, size_code
from pydantic import AnyUrl, BaseModel, EmailStr
from pydantic_core import PydanticCustomError
from starlette.concurrency import run_in_threadpool

from .client import get_client

if TYPE_CHECKING:
    from langsys import LangsysClient

__all__ = [
    "declared_templates",
    "declares",
    "entries_from_errors",
    "install",
    "message_error",
    "validation_entries",
    "validation_exception_handler",
]

Entry = dict[str, Any]
Declared = Union[str, Mapping[str, Any], TemplateProblem]
F = TypeVar("F", bound=Callable[..., Any])

#: The envelope's own entry, and the ones for a request that failed as a whole.
FAILED = ("validation_failed", "The request failed validation.")
BODY_REQUIRED = ("required", "The request body is required.")
BODY_NOT_JSON = ("invalid_format", "The request body must be valid JSON.")
GENERIC = ("invalid", "The :attribute is invalid.")
EMAIL = ("invalid_format", "The :attribute must be a valid email address.")

#: Pydantic error type -> (code, wording). `:attribute` is where the label is written in.
_PLAIN: dict[str, tuple[str, str]] = {
    "missing": ("required", "The :attribute is required."),
    "string_type": ("invalid_type", "The :attribute must be text."),
    "string_pattern_mismatch": ("invalid_format", "The :attribute format is invalid."),
    "enum": ("invalid_option", "The selected :attribute is invalid."),
    "literal_error": ("invalid_option", "The selected :attribute is invalid."),
    "extra_forbidden": ("not_allowed", "The :attribute is not allowed."),
}
for _kind in ("int_type", "int_parsing", "int_from_float"):
    _PLAIN[_kind] = ("invalid_type", "The :attribute must be a whole number.")
for _kind in ("float_type", "float_parsing", "decimal_type", "decimal_parsing"):
    _PLAIN[_kind] = ("invalid_type", "The :attribute must be a number.")
for _kind in ("bool_type", "bool_parsing"):
    _PLAIN[_kind] = ("invalid_type", "The :attribute must be true or false.")
for _kind in ("list_type", "tuple_type", "set_type", "frozen_set_type"):
    _PLAIN[_kind] = ("invalid_type", "The :attribute must be a list.")
for _kind in ("model_type", "model_attributes_type", "dict_type"):
    _PLAIN[_kind] = ("invalid_type", "The :attribute must be an object.")
for _kind in ("url_type", "url_parsing", "url_scheme", "url_syntax_violation", "url_too_long"):
    _PLAIN[_kind] = ("invalid_format", "The :attribute must be a valid URL.")
for _kind in ("uuid_type", "uuid_parsing", "uuid_version"):
    _PLAIN[_kind] = ("invalid_format", "The :attribute must be a valid UUID.")
for _kind in (
    "date_type",
    "date_parsing",
    "date_from_datetime_parsing",
    "date_from_datetime_inexact",
    "datetime_type",
    "datetime_parsing",
    "datetime_from_date_parsing",
    "time_type",
    "time_parsing",
):
    _PLAIN[_kind] = ("invalid_format", "The :attribute must be a valid date.")

#: Pydantic size error -> (a value of the field's type, for `size_code`; which bound; marker;
#: the context key holding the bound; wording).
_SIZED: dict[str, tuple[Any, str, str, str, str]] = {
    "string_too_short": (
        "",
        "small",
        "min",
        "min_length",
        "The :attribute must be at least {min} characters.",
    ),
    "string_too_long": (
        "",
        "large",
        "max",
        "max_length",
        "The :attribute must not be longer than {max} characters.",
    ),
    "too_short": (
        [],
        "small",
        "min",
        "min_length",
        "The :attribute must have at least {min} items.",
    ),
    "too_long": (
        [],
        "large",
        "max",
        "max_length",
        "The :attribute must not have more than {max} items.",
    ),
    "greater_than_equal": (0, "small", "min", "ge", "The :attribute must be at least {min}."),
    "less_than_equal": (0, "large", "max", "le", "The :attribute must not be greater than {max}."),
    "greater_than": (0, "small", "value", "gt", "The :attribute must be greater than {value}."),
    "less_than": (0, "large", "value", "lt", "The :attribute must be less than {value}."),
}

#: A bound that is a date is a date comparison, worded as the reference's after/before rules.
_DATED: dict[str, str] = {
    "greater_than_equal": "The :attribute must be on or after {date}.",
    "greater_than": "The :attribute must be after {date}.",
    "less_than_equal": "The :attribute must be on or before {date}.",
    "less_than": "The :attribute must be before {date}.",
}

#: The context key `message_error()` carries its declared template under.
_TEMPLATE_KEY = "langsys_template"
_SOURCES = ("body", "query", "path", "header", "cookie")


def message_error(code: str, template: str, **params: Any) -> PydanticCustomError:
    """A validator failure with a declared template (MSG-9). Raise it from a Pydantic validator:

    ``raise message_error("already_taken", "The email has already been taken.")``

    ``template`` is a whole sentence with the label written in; ``params`` fill its ``{name}``
    markers and hold only values that are not translatable. List the template in your provider
    (see :func:`declares`) so it is registered ahead of time.
    """
    return PydanticCustomError(code, template, {**params, _TEMPLATE_KEY: template})


def declares(*templates: str) -> Callable[[F], F]:
    """Name the templates a custom validator can fail with, so :func:`declared_templates` lists
    them rather than reporting the validator as unlistable. Put it under ``@field_validator``."""

    def mark(func: F) -> F:
        # Under @field_validator the object may be a classmethod; tag the function it wraps too.
        for target in (func, getattr(func, "__func__", None)):
            if target is not None:
                with contextlib.suppress(AttributeError, TypeError):
                    setattr(target, "__langsys_templates__", templates)  # noqa: B010
        return func

    return mark


# -- errors -> entries (MSG-9, MSG-10) ---------------------------------------------------------


def entries_from_errors(
    errors: Iterable[Mapping[str, Any]],
    root: Any,
    *,
    client: Optional[LangsysClient] = None,
) -> list[Entry]:
    """Entries for Pydantic ``errors()``, whose ``loc`` is relative to ``root`` — a model class,
    or FastAPI's parameters by source. With ``client``, each entry goes through
    ``client.server_message`` (MSG-8 registration, MSG-11 check); without, the core's pure
    constructor."""
    build = client.server_message if client is not None else server_message
    entries: list[Entry] = []
    for error in errors:
        kind = str(error.get("type", ""))
        loc = tuple(error.get("loc") or ())
        path = loc[1:] if loc and loc[0] in _SOURCES and isinstance(root, Mapping) else loc
        field = ".".join(str(part) for part in path)
        params: dict[str, Any] = {}
        if kind == "json_invalid":
            code, template = BODY_NOT_JSON
            field = ""
        elif not path:
            code, template = BODY_REQUIRED if kind == "missing" else FAILED
        else:
            label, annotation = _describe(root, loc if isinstance(root, Mapping) else path)
            code, template, params = _rule(kind, dict(error.get("ctx") or {}), label, annotation)
        entries.append(build(code, template, params or None, field or None))
    return entries


def validation_entries(
    exc: RequestValidationError, request: Request, client: Optional[LangsysClient] = None
) -> list[Entry]:
    """Entries for a failed FastAPI request, labelled from the route's own parameters."""
    return entries_from_errors(exc.errors(), _route_roots(request), client=client)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Answer a failed request with the default langsys envelope:
    ``{"status": false, "error": {code, message, template, "errors": [entry, …]}}``."""
    client = get_client()
    entries = await run_in_threadpool(validation_entries, exc, request, client)
    failed = await run_in_threadpool(client.server_message, *FAILED)
    return JSONResponse({"status": False, "error": {**failed, "errors": entries}}, 422)


def install(app: FastAPI) -> None:
    """Answer every failed request validation with :func:`validation_exception_handler`."""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]


def _rule(
    kind: str, ctx: dict[str, Any], label: str, annotation: Any
) -> tuple[str, str, dict[str, Any]]:
    if _TEMPLATE_KEY in ctx:  # message_error(): the app declared the sentence
        template = str(ctx.pop(_TEMPLATE_KEY))
        return kind, template, ctx
    if kind in _SIZED:
        probe, too, marker, key, wording = _SIZED[kind]
        bound = ctx.get(key)
        if kind in _DATED and (_is_temporal(annotation) or isinstance(bound, (date, time))):
            shown = bound.isoformat() if isinstance(bound, (date, time)) else str(bound)
            return "invalid_date", _labelled(_DATED[kind], label), {"date": shown}
        return size_code(probe, too), _labelled(wording, label), {marker: _number(bound)}
    if kind == "value_error" and _unwrap(annotation) is EmailStr:
        return EMAIL[0], _labelled(EMAIL[1], label), {}
    if kind in _PLAIN:
        code, wording = _PLAIN[kind]
        return code, _labelled(wording, label), {}
    if kind in ("value_error", "assertion_error") and ctx.get("error") is not None:
        # Text only: the validator's author wrote this sentence, so it is the template.
        return "invalid", str(ctx["error"]), {}
    return GENERIC[0], _labelled(GENERIC[1], label), {}


def _labelled(wording: str, label: str) -> str:
    return wording.replace(":attribute", label)


def _number(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    return value


# -- labels (MSG-10) ---------------------------------------------------------------------------


def _route_roots(request: Request) -> Any:
    """FastAPI's parameters by source, for the route that served ``request``."""
    route = request.scope.get("route")
    roots: dict[str, Any] = {source: {} for source in _SOURCES}
    if not isinstance(route, APIRoute):
        return roots
    flat = get_flat_dependant(route.dependant)
    for source, params in (
        ("query", flat.query_params),
        ("path", flat.path_params),
        ("header", flat.header_params),
        ("cookie", flat.cookie_params),
    ):
        roots[source] = {param.alias: param for param in params}
    if route.body_field is not None:
        roots["body"] = _annotation(route.body_field)
    return roots


def _describe(root: Any, path: Sequence[Any]) -> tuple[str, Any]:
    """The label declared for the field at ``path``, and that field's annotation. A field with no
    declared label is named by its key — never a name guessed from it — and the listing reports
    it (MSG-10)."""
    node, info = root, None
    for key in path:
        node, found = _step(node, key)
        if found is not None:
            info = found
        if node is None:
            break
    title = getattr(info, "title", None)
    key = next((str(k) for k in reversed(path) if isinstance(k, str) and k not in _SOURCES), "")
    return (title or key), node


def _step(node: Any, key: Any) -> tuple[Any, Any]:
    if isinstance(node, Mapping):
        if key in node and not isinstance(node[key], Mapping) and not _is_model(node[key]):
            param = node[key]
            return _annotation(param), getattr(param, "field_info", None)
        return node.get(key), None
    node = _unwrap(node)
    if isinstance(key, int):
        args = [a for a in get_args(node) if a is not Ellipsis]
        return (args[-1] if args else None), None
    if _is_model(node):
        for name, info in node.model_fields.items():
            if key in (name, info.alias, info.validation_alias):
                return info.annotation, info
        return None, None
    if get_origin(node) in (dict, Mapping):
        pair = get_args(node)
        return (pair[1] if len(pair) == 2 else None), None
    return None, None


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


def _is_temporal(annotation: Any) -> bool:
    kind = _unwrap(annotation)
    return isclass(kind) and issubclass(kind, (date, time))


def _is_model(annotation: Any) -> bool:
    return isclass(annotation) and issubclass(annotation, BaseModel)


# -- listing (MSG-7) ---------------------------------------------------------------------------


def declared_templates(app: FastAPI) -> Iterator[Declared]:
    """Every template ``app``'s routes can emit, for the core's listing command (MSG-7).

    A field with no declared label, and a custom validator whose templates are not declared with
    :func:`declares`, are reported as problems, so the command fails in CI rather than a raw key
    or an unlisted sentence reaching a user. Wire it up with a provider in your app::

        def templates():
            return declared_templates(app)

        # python -m langsys.messages --provider myapp.langsys:templates [--register]
    """
    for _, template in (FAILED, BODY_REQUIRED, BODY_NOT_JSON):
        yield {"template": template, "source": "langsys_fastapi"}
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


def _model_templates(model: Any, prefix: str, where: str, seen: set[Any]) -> Iterator[Declared]:
    """Templates for every field of ``model``; ``where`` names the route."""
    model = _unwrap(model)
    if not _is_model(model) or (model, prefix) in seen:
        return
    seen.add((model, prefix))
    source = f"{where} {model.__name__}"
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
        fields = getattr(validator.info, "fields", ())
        if declared is not None:
            for template in declared:
                yield {"template": template, "source": source, "field": ",".join(fields)}
            continue
        yield TemplateProblem(
            f"validator {validator.cls_var_name!r} can fail with text that cannot be listed "
            "ahead of time",
            source=source,
            field=",".join(fields),
            fix="fail with langsys_fastapi.messages.message_error(code, template) and name its "
            "templates with @declares(...)",
        )


def _field_templates(
    info: Any, annotation: Any, path: str, source: str, where: str, seen: set[Any]
) -> Iterator[Declared]:
    label = getattr(info, "title", None)
    if not label:
        yield TemplateProblem(
            "the field has no label, so its key would be written into the sentence",
            source=source,
            field=path,
            fix="declare Field(title=...) (MSG-10)",
        )
        return
    kind = _unwrap(annotation)
    templates: list[str] = []
    if info.is_required():
        templates.append(_PLAIN["missing"][1])
    templates.extend(_type_templates(kind))
    for rule in info.metadata:
        templates.extend(_constraint_templates(rule, kind))
    for template in templates:
        yield {"template": _labelled(template, label), "source": source, "field": path}
    origin = get_origin(kind)
    item = get_args(kind)[0] if origin in (list, tuple, set, frozenset) and get_args(kind) else None
    for nested in (kind, item):
        if _is_model(_unwrap(nested)):
            yield from _model_templates(nested, path, where, seen)


def _type_templates(kind: Any) -> list[str]:
    origin = get_origin(kind)
    if kind is EmailStr:
        return [EMAIL[1]]
    if origin is Literal or (isclass(kind) and issubclass(kind, enum.Enum)):
        return [_PLAIN["enum"][1]]
    if origin in (list, tuple, set, frozenset) or kind in (list, tuple, set, frozenset):
        return [_PLAIN["list_type"][1]]
    if not isclass(kind):
        return []
    for base, kinds in (
        (bool, "bool_type"),
        (int, "int_type"),
        (str, "string_type"),
        (float, "float_type"),
        (Decimal, "decimal_type"),
        (date, "date_type"),
        (time, "time_type"),
        (UUID, "uuid_type"),
        (AnyUrl, "url_type"),
    ):
        if issubclass(kind, base):
            return [_PLAIN[kinds][1]]
    if _is_model(kind):
        return [_PLAIN["model_type"][1]]
    return []


def _constraint_templates(rule: Any, kind: Any) -> list[str]:
    sized = get_origin(kind) in (list, tuple, set, frozenset)
    if isinstance(rule, at.MinLen):
        return [_SIZED["too_short" if sized else "string_too_short"][4]]
    if isinstance(rule, at.MaxLen):
        return [_SIZED["too_long" if sized else "string_too_long"][4]]
    for bound, kinds in (
        (at.Ge, "greater_than_equal"),
        (at.Gt, "greater_than"),
        (at.Le, "less_than_equal"),
        (at.Lt, "less_than"),
    ):
        if isinstance(rule, bound):
            return [_DATED[kinds] if _is_temporal(kind) else _SIZED[kinds][4]]
    if getattr(rule, "pattern", None):
        return [_PLAIN["string_pattern_mismatch"][1]]
    return []
