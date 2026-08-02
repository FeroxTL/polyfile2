from collections.abc import Callable
from functools import wraps

from django.http import Http404, JsonResponse

from polyfile.application.exceptions import HttpException, NotFound


def catch_storage_exceptions(func: Callable):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HttpException as e:
            # TODO: BaseHttpErrorSchema
            return JsonResponse(status=e.status_code, data={
                # TODO: add 'error': self.__class__.__name__; rename classes
                'description': e.description,
                'message': e.detail,
            })
        except Http404 as e:
            return JsonResponse(status=NotFound.status_code, data={
                'description': NotFound.description,
                'message': str(e),
            })
    return wrapper
