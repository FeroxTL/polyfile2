from django.utils.translation import gettext as _

from polyfile.application.exceptions import HttpException


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
