# Copyright 2020 The gRPC authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Test of propagation of contextvars between threads."""

import contextlib
import logging
import sys
import unittest

import grpc

from tests.unit import test_common

_UNARY_UNARY = "/test/UnaryUnary"
_REQUEST = b"0000"


def _unary_unary_handler(request, context):
    return request


# TODO: Test for <3.7 and 3.7+.


def contextvars_supported():
    try:
        import contextvars
        return True
    except ImportError:
        return False


class _GenericHandler(grpc.GenericRpcHandler):

    def service(self, handler_call_details):
        if handler_call_details.method == _UNARY_UNARY:
            return grpc.unary_unary_rpc_method_handler(_unary_unary_handler)
        else:
            raise NotImplementedError()


@contextlib.contextmanager
def _server():
    try:
        server = test_common.test_server()
        target = '[::]:0'
        port = server.add_insecure_port(target)
        server.add_generic_rpc_handlers((_GenericHandler(),))
        server.start()
        yield port
    finally:
        server.stop(None)


if contextvars_supported():
    import contextvars

    _EXPECTED_VALUE = 24601
    test_var = contextvars.ContextVar("test_var", default=None)
    test_var.set(_EXPECTED_VALUE)

    class TestCallCredentials(grpc.AuthMetadataPlugin):

        def __init__(self):
            self._recorded_value = None

        def __call__(self, context, callback):
            self._recorded_value = test_var.get()
            callback((), None)

        def assert_called(self, test):
            test.assertEqual(_EXPECTED_VALUE, self._recorded_value)

else:

    class TestCallCredentials(grpc.AuthMetadataPlugin):

        def __call__(self, context, callback):
            callback((), None)

        def assert_called(self, test):
            pass


class ContextVarsPropagationTest(unittest.TestCase):

    def test_propagation_to_auth_plugin(self):
        with _server() as port:
            target = "localhost:{}".format(port)
            local_credentials = grpc.local_channel_credentials()
            test_call_credentials = TestCallCredentials()
            call_credentials = grpc.metadata_call_credentials(
                test_call_credentials, "test call credentials")
            composite_credentials = grpc.composite_channel_credentials(
                local_credentials, call_credentials)
            with grpc.secure_channel(target, composite_credentials) as channel:
                stub = channel.unary_unary(_UNARY_UNARY)
                response = stub(_REQUEST)
                self.assertEqual(_REQUEST, response)
                test_call_credentials.assert_called(self)

    # TODO: Test simple unary-unary.


if __name__ == '__main__':
    logging.basicConfig()
    unittest.main(verbosity=2)
