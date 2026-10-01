"""Request / response middleware hooks."""

from __future__ import annotations

from typing import Any, Callable, Protocol

from zframe.client.response import Response

RequestPrep = dict[str, Any]


class RequestHook(Protocol):
    def __call__(self, request: RequestPrep) -> RequestPrep: ...


class ResponseHook(Protocol):
    def __call__(self, response: Response) -> Response: ...


class Hook:
    """Simple callable hooks container."""

    def __init__(
        self,
        *,
        on_request: list[RequestHook] | None = None,
        on_response: list[ResponseHook] | None = None,
    ) -> None:
        self.on_request: list[RequestHook] = list(on_request or [])
        self.on_response: list[ResponseHook] = list(on_response or [])

    def add_request(self, hook: RequestHook) -> None:
        self.on_request.append(hook)

    def add_response(self, hook: ResponseHook) -> None:
        self.on_response.append(hook)

    def apply_request(self, request: RequestPrep) -> RequestPrep:
        for hook in self.on_request:
            request = hook(request)
        return request

    def apply_response(self, response: Response) -> Response:
        for hook in self.on_response:
            response = hook(response)
        return response


def logging_request_hook(request: RequestPrep) -> RequestPrep:
    from zframe.report.logging import get_logger

    logger = get_logger("zframe.client")
    logger.info(
        ">>> %s %s headers=%s",
        request.get("method"),
        request.get("url"),
        {k: v for k, v in (request.get("headers") or {}).items() if k.lower() != "authorization"},
    )
    return request


def logging_response_hook(response: Response) -> Response:
    from zframe.report.logging import get_logger

    logger = get_logger("zframe.client")
    logger.info(
        "<<< %s %s status=%s elapsed=%.1fms",
        response.request.method,
        response.url,
        response.status_code,
        response.elapsed_ms,
    )
    return response


AuthApplyFn = Callable[[RequestPrep], RequestPrep]
