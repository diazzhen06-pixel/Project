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
