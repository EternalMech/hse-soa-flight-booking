import hmac

import grpc

from services.config import api_key


class ApiKeyInterceptor(grpc.ServerInterceptor):
    def __init__(self):
        self.key = api_key().encode()

    def intercept_service(self, continuation, details):
        handler = continuation(details)
        if handler is None:
            return None
        keys = [value for key, value in details.invocation_metadata if key == "x-api-key"]
        if len(keys) == 1 and hmac.compare_digest(keys[0].encode(), self.key):
            return handler

        def deny(request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Требуется корректный API Key сервиса")

        factory = {
            (False, False): grpc.unary_unary_rpc_method_handler,
            (False, True): grpc.unary_stream_rpc_method_handler,
            (True, False): grpc.stream_unary_rpc_method_handler,
            (True, True): grpc.stream_stream_rpc_method_handler,
        }[handler.request_streaming, handler.response_streaming]
        return factory(deny, request_deserializer=handler.request_deserializer, response_serializer=handler.response_serializer)
