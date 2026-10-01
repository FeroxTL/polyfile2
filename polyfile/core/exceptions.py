import typing

from django.utils.translation import gettext as _


class HttpException(Exception):
    """Base HTTP exception."""
    status_code: int = 500
    error_code: str = 'unknown'
    description: str = _('A server error occurred.')

    def __init__(self, detail: typing.Any = None):
        self.detail: typing.Any = detail or self.description


class NotFound(HttpException):
    """Resource not found."""
    status_code = 404
    error_code = 'NotFound'
    description = _('Not found.')


class Unauthorized(HttpException):
    """Unauthorized request."""
    status_code = 401
    error_code = 'Unauthorized'
    description = _('Authentication credentials were not provided.')


class PermissionDenied(HttpException):
    """No permissions to perform action."""
    status_code = 403
    error_code = 'PermissionDenied'
    description = _('You do not have permission to perform this action.')


class FieldValidationError(HttpException):
    status_code = 400
    error_code = 'FieldValidationError'
    description = _('Error validating fields.')


class InvalidUserStorageError(HttpException):
    status_code = 400
    error_code = 'InvalidUserStorageError'
    description = _('User does not have storage.')


class InvalidFsNodeName(HttpException):
    status_code = 400
    error_code = 'InvalidFsNodeName'
    description = _('Invalid file or directory name')


class FsNodeNotFoundError(HttpException):
    status_code = 404
    error_code = 'FsNodeNotFoundError'
    description = _('No such file or directory.')


class FsNodeIsNotADirectoryError(HttpException):
    status_code = 409
    error_code = 'NotADirectoryError'
    description = _('Target path is not not a directory.')


class FsNodeExistsError(HttpException):
    status_code = 409
    error_code = 'FsNodeExistsError'
    description = _('Target object already exists.')
