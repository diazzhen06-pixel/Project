import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import pandas as pd
import pickle
from functools import wraps
import hashlib
import time
from config.settings import CACHE_MAX_AGE
CACHE_DIR = "./cache"

def cache_result(ttl=600000000):  # default no expiration
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            print(f'Func: {func.__name__}', end='')

            ttl_minutes = kwargs.pop('ttl', ttl)
            
            # Exclude db objects from args and kwargs
            filtered_args = tuple(a for a in args if not hasattr(a, "client") and not hasattr(a, "command"))
            filtered_kwargs = {k: v for k, v in kwargs.items() if not hasattr(v, "client") and not hasattr(v, "command")}

            cache_key = hashlib.md5(pickle.dumps((filtered_args, tuple(sorted(filtered_kwargs.items()))))).hexdigest()
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
                        print(result.head(5) if isinstance(result, pd.DataFrame) else result)
                        return result
            else:
                result = func(*args, **kwargs)

            with open(cache_name, "wb") as f:
                pickle.dump(result, f)

            print(' - fresh')
            if not result.empty:
                print(result.iloc[0] if isinstance(result, pd.DataFrame) else result)
            else:
                print('Empty data!')
            return result
        return wrapper
    return decorator

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

def load_or_query(cache_file, query_func):
    cache_file = f"./cache/{cache_file}"
    """Load DataFrame from cache or run query function."""
    if os.path.exists(cache_file):
        file_age = time.time() - os.path.getmtime(cache_file)
        if file_age < CACHE_MAX_AGE:
            print('Load from cache!')
            return pd.read_pickle(cache_file)


    df = query_func()
    if not df.empty:
        df.to_pickle(cache_file)
        pass
    return df

def save_checkpoint(last_index, results, CHECKPOINT_FILE):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(CHECKPOINT_FILE, "wb") as f:
        pickle.dump({"last_index": last_index, "results": results}, f)

def load_checkpoint(CHECKPOINT_FILE):
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "rb") as f:
            return pickle.load(f)
    return {"last_index": 0, "results": []}
