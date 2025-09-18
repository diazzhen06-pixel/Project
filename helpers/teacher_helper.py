from pymongo import MongoClient

def get_all_teachers(db):
    """
    Fetches all unique teacher names from the subjects collection.
    """
    return db.subjects.distinct("Teacher")
