    raise exc
During handling of the above exception, another exception occurred:
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/errors.py", line 162, in __call__
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/uvicorn/protocols/http/httptools_impl.py", line 426, in run_asgi
    await self.app(scope, receive, _send)
    result = await app(  # type: ignore[func-returns-value]
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/cors.py", line 91, in __call__
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 84, in __call__
    await self.simple_response(scope, receive, send, request_headers=headers)
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/applications.py", line 1106, in __call__
    await super().__call__(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/applications.py", line 122, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/errors.py", line 184, in __call__
    jsonable_encoder(
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/cors.py", line 146, in simple_response
    await self.app(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/fastapi/encoders.py", line 287, in jsonable_encoder
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 88, in __call__
    encoded_value = jsonable_encoder(
    response = await handler(request, exc)
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^
                    ^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/exception_handlers.py", line 25, in request_validation_exception_handler
  File "/usr/local/lib/python3.11/site-packages/fastapi/encoders.py", line 316, in jsonable_encoder
    content={"detail": jsonable_encoder(exc.errors())},
    return ENCODERS_BY_TYPE[type(obj)](obj)
                       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/encoders.py", line 301, in jsonable_encoder
  File "/usr/local/lib/python3.11/site-packages/fastapi/encoders.py", line 59, in <lambda>
    bytes: lambda o: o.decode(),
                     ^^^^^^^^^^
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff in position 157: invalid start byte
