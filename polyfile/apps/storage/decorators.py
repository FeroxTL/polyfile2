from collections.abc import Callable
from functools import wraps

from django.http import Http404, HttpRequest, JsonResponse

from polyfile.core.exceptions import HttpException, NotFound
from polyfile.core.http import render_error_page, vary_on_accept, wants_html


def _get_request(args: tuple, kwargs: dict) -> HttpRequest | None:
    if args and isinstance(args[0], HttpRequest):
        return args[0]
    request = kwargs.get("request")
    return request if isinstance(request, HttpRequest) else None


def catch_storage_exceptions(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        request = _get_request(args, kwargs)
        try:
            return func(*args, **kwargs)
        except HttpException as e:
            if request is not None and wants_html(request):
                return render_error_page(
                    request,
                    status=e.status_code,
                    message=e.detail,
                )
            # TODO: BaseHttpErrorSchema
            return vary_on_accept(JsonResponse(status=e.status_code, data={
                'error_id': e.error_code,
                'description': e.description,
                'message': e.detail,
            }))
        except Http404 as e:
            if request is not None and wants_html(request):
                return render_error_page(
                    request,
                    status=NotFound.status_code,
                    message=str(e),
                )
            return vary_on_accept(JsonResponse(status=NotFound.status_code, data={
                'error_id': NotFound.error_code,
                'description': NotFound.description,
                'message': str(e),
            }))
    return wrapper
