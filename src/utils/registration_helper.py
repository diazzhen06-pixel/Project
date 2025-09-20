import pandas as pd
from rapidfuzz import process, fuzz
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))



def find_best_match(query=None, course=None, collection=None, limit=200):

    if collection is None:
        raise ValueError("⚠️ You must pass a MongoDB collection (e.g., db.students).")

    filters = []

    # --- Name filter ---
    if query and isinstance(query, str):
        words = query.strip().split()
        regex_pattern = "".join(f"(?=.*{word})" for word in words) + ".*"
        filters.append({"Name": {"$regex": regex_pattern, "$options": "i"}})

    # --- Course filter ---
    if course and isinstance(course, str):
        filters.append({"Course": {"$regex": course, "$options": "i"}})

    # --- Build query ---
    if not filters:
        query_filter = {}
    elif len(filters) == 1:
        query_filter = filters[0]
    else:
        query_filter = {"$and": filters}

    # --- Execute query ---
    projection = {"Name": 1, "Course": 1}
    return list(collection.find(query_filter, projection).limit(limit))


if __name__  == "__main__":

    pass