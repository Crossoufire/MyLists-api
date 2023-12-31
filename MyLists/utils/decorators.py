import time
from functools import wraps
from typing import Callable
from flask import abort, request
from MyLists.utils.enums import MediaType
from MyLists.utils.utils import get_models_group


def validate_media_type(func: Callable):
    """ Validate the <media_type> before giving access to the route """

    @wraps(func)
    def wrapper(media_type: str, *args, **kwargs):
        try:
            media_type = MediaType(media_type)
        except:
            return abort(400)

        return func(media_type=media_type, *args, **kwargs)

    return wrapper


def media_endpoint_decorator(type_ = None):
    """ Decorator for checking JSON data before accessing the route. Add an endpoint type before creating the
    decorator """

    def decorator(func: Callable):
        """" Actual decorator implementation """

        @wraps(func)
        def wrapper():
            try:
                # Parse JSON data
                json_data = request.get_json()
                media_id = int(json_data["media_id"])
                media_type = json_data["media_type"]

                # Handle payload with optional type conversion
                payload = type_(json_data["payload"]) if type_ else json_data.get("payload", None) or None
            except:
                return abort(400)

            # Check if <media_type> valid
            try:
                media_type = MediaType(media_type)
                models = get_models_group(media_type)
            except ValueError:
                return abort(400)

            # Call original function with extracted parameters
            return func(media_id, media_type, payload, models)

        return wrapper

    return decorator


def get_timing_exec(func):
    """ Return the approximate time a function takes """

    @wraps(func)
    def wrapper(*args, **kwargs):

        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()

        print(f"Elapsed time: {int((end_time - start_time) * 1000)} ms")

        return result

    return wrapper

