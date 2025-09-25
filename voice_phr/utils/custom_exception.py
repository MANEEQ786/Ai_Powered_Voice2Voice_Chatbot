from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler
import logging

error_logger = logging.getLogger('api_error')


class ApplicationException(APIException):
    def __init__(self, detail=None, code=None):
        super().__init__(detail, code)
        if detail is None:
            self.detail = 'Something went wrong!!'
        else:
            self.detail=detail
        if code is None:
            self.status_code =500
        else:
            self.status_code =code


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        response.data['message'] = response.data['detail']
        del response.data['detail']
    error_logger.error(response)
    return response
