import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
import pickle
from functools import wraps
import hashlib
import time

CACHE_DIR = "./cache"

def cache_meta(ttl=600000000):  # default no expiration
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print(f'-----------------------------------------------')
            print(f'Func: {func.__name__}', end = '')

            ttl_minutes = kwargs.pop('ttl', ttl)
            # args_tuple = tuple(arg for arg in args)
            args_tuple = tuple(arg for arg in args if not hasattr(arg, "__class__"))
            kwargs_tuple = tuple(sorted(kwargs.items()))
            cache_key = hashlib.md5(pickle.dumps((args_tuple, kwargs_tuple))).hexdigest()
            cache_name = f"./cache/{func.__name__}_{cache_key}.pkl"
            os.makedirs("./cache/", exist_ok=True)
            if os.path.exists(cache_name):
                file_mod_time = os.path.getmtime(cache_name)
                if (time.time() - file_mod_time) / 60 > ttl_minutes:
                    os.remove(cache_name)
                    result = func(*args, **kwargs)
                else:
                    with open(cache_name, "rb") as f:
                        result = pickle.load(f)
                        print(' - from cache')
                        return result 
            else:
                result = func(*args, **kwargs)


            with open(cache_name, "wb") as f:
                pickle.dump(result, f)

            print(' - fresh')

            return result
        return wrapper
    return decorator


def load_or_query(cache_key, query_func, ttl_minutes=60):
    """
    Loads data from a cache file if it exists and is not expired.
    Otherwise, it runs the query_func, caches the result, and returns it.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, cache_key)

    if os.path.exists(cache_path):
        # Check if the cache file is expired
        file_mod_time = os.path.getmtime(cache_path)
        if (time.time() - file_mod_time) / 60 < ttl_minutes:
            try:
                with open(cache_path, "rb") as f:
                    print(f"Loading from cache: {cache_key}")
                    return pickle.load(f)
            except (pickle.UnpicklingError, EOFError):
                print(f"Cache file {cache_path} is corrupted. Re-running query.")
                os.remove(cache_path)
        else:
            print(f"Cache file {cache_path} has expired. Re-running query.")
            os.remove(cache_path)


    print(f"Running query and caching: {cache_key}")
    result = query_func()

    # Cache the result
    with open(cache_path, "wb") as f:
        pickle.dump(result, f)

    return result
