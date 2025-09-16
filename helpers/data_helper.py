import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from typing import Optional
import pandas as pd
from dotenv import load_dotenv
import pymongo
from pymongo import MongoClient
import time

# from config.settings import MONGODB_URI, CACHE_MAX_AGE
from helpers.cache_helper import cache_meta, load_or_query


pd.set_option('display.max_columns', None)

# client = MongoClient(MONGODB_URI)


def student_find(db, query, collection, course=None, limit=10):
    """Search students by keywords in any order (case-insensitive). Optionally filter by course."""
    words = query.strip().split()
    regex_pattern = "".join(f"(?=.*{word})" for word in words) + ".*"
    regex_query = {"Name": {"$regex": regex_pattern, "$options": "i"}}

    # Filter by course if provided
    if course:
        regex_query["Course"] = course

    return list(collection.find(regex_query, {"Name": 1, "Course": 1, "YearLevel": 1}).limit(limit))

def get_students_collection(db, StudentID=None, limit=100000000):
    def query():


        query_filter = {"Course": "BSBA"}

        if StudentID:
            # Use direct match if single ID, or $in if list of IDs
            if isinstance(StudentID, list):
                query_filter["_id"] = {"$in": StudentID}
            else:
                query_filter["_id"] = StudentID

        cursor = db.students.find(
            query_filter,
            {"_id": 1, "Name": 1, "Course": 1, "YearLevel": 1}
        )

        if limit:
            cursor = cursor.limit(limit)

        return pd.DataFrame(list(cursor))

    return load_or_query("students_cache_x.pkl", query)

@cache_meta(ttl=660000000) #60 minutes
def get_students(db, StudentID=None, limit=1000):


    # Start pipeline from grades, since only students with grades matter
    pipeline = [
        {
            "$match": {  # filter by StudentID if provided
                **({"StudentID": StudentID} if StudentID else {})
            }
        },
        {"$group": {"_id": "$StudentID"}},  # unique students with grades
        {
            "$lookup": {  # join with students collection
                "from": "students",
                "localField": "_id",
                "foreignField": "_id",
                "as": "student"
            }
        },
        {"$unwind": "$student"},  # flatten student array
        {
            "$project": {
                "_id": "$student._id",
                "Name": "$student.Name",
                "Course": "$student.Course",
                "YearLevel": "$student.YearLevel"
            }
        },
        {"$sort": {"Name": 1}}
    ]

    if limit:
        pipeline.append({"$limit": limit})

    cursor = db.grades.aggregate(pipeline)  # NOTE: run on grades_col
    return pd.DataFrame(list(cursor))

def get_subjects(db, batch_size=1000):


    cursor = db.subjects.find({}, {"_id": 1, "Description": 1, "Units": 1, "Teacher": 1})

    docs, chunks = [], []
    for i, doc in enumerate(cursor, 1):
        docs.append(doc)
        if i % batch_size == 0:
            chunks.append(pd.DataFrame(docs))
            docs = []

    if docs:
        chunks.append(pd.DataFrame(docs))

    df = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

    if not df.empty:
        df.rename(columns={"_id": "Subject Code"}, inplace=True)
        df["Subject Code"] = df["Subject Code"].astype(str)

    return df



@cache_meta(ttl=600000) #60 minutes
def get_semester_names(db):
    print('fetching semester from semesters collection as list')
    return db.semesters.distinct("Semester")

@cache_meta(ttl=600000) #60 minutes
def get_semesters(db, batch_size=1000):
    print('fetching semesters collection as DataFrame')


    cursor = db.semesters.find({}, {"_id": 1, "Semester": 1, "SchoolYear": 1})

    docs, chunks = [], []
    for i, doc in enumerate(cursor, 1):
        docs.append(doc)
        if i % batch_size == 0:
            chunks.append(pd.DataFrame(docs))
            docs = []

    if docs:
        chunks.append(pd.DataFrame(docs))

    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

@cache_meta(ttl=600000) #60 minutes
def get_school_years(db):
    years = db.semesters.distinct("SchoolYear")
    return sorted(years, reverse=True)

@cache_meta(ttl=600000) #60 minutes
def get_current_school_year(db):
    years = db.semesters.distinct("SchoolYear")
    latest_year = sorted(years, key=lambda y: int(str(y).split("-")[0]), reverse=True)[0]

    return latest_year


@cache_meta(ttl=600000) #60 minutes
def get_courses(db):
    return db.students.distinct("Course")

@cache_meta(ttl=600000) #60 minutes
def get_grades(db, student_id: int | None = None, batch_size: int = 1000):
    print("Fetching data", end="")
    # 🔹 Build query filter
    query = {}
    if student_id is not None:
        query["StudentID"] = int(student_id)

    cursor = db.grades.find(
        query,
        {
            "_id": 1,
            "StudentID": 1,
            "SubjectCodes": 1,
            "Grades": 1,
            "Teachers": 1,
            "SemesterID": 1,
        },
    )

    docs, chunks = [], []
    for i, doc in enumerate(cursor, 1):
        docs.append(doc)
        if i % batch_size == 0:
            print(".", end="")
            chunks.append(pd.DataFrame(docs))
            docs = []

    if docs:  # add remaining docs
        chunks.append(pd.DataFrame(docs))

    return pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()

def get_student_subjects_grades(db, StudentID=None, limit=1000):
    """
    Returns all subjects and grades for a specific student with:
    ["Subject Code", "Description", "Grade", "Semester", "SchoolYear"]
    """
    cache_key = f"student_subjects_grades_{StudentID}x"

    def query():
        if StudentID is not None:
            student_id = int(StudentID)
            grade_doc = db.grades.find_one({"StudentID": student_id})
            print(grade_doc)
        else:
            return pd.DataFrame()

        if not grade_doc:
            return pd.DataFrame()

        # Build rows manually
        rows = []
        subject_codes = grade_doc.get("SubjectCodes", [])
        grades = grade_doc.get("Grades", [])
        semester_id = grade_doc.get("SemesterID")


        # Lookup semester info once
        sem = db.semesters.find_one({"_id": semester_id})
        semester = sem["Semester"] if sem else None
        school_year = sem["SchoolYear"] if sem else None

        for code, grade in zip(subject_codes, grades):
            subj = db.subjects.find_one({"_id": code})
            desc = subj["Description"] if subj else None

            rows.append({
                "Subject Code": code,
                "Description": desc,
                "Grade": grade,
                "Semester": semester,
                "SchoolYear": school_year
            })

        # Apply limit
        if limit:
            rows = rows[:limit]

        return pd.DataFrame(rows)

    return load_or_query(cache_key, query)

def get_instructor_subjects(db, instructor_name=None, limit=1000):
    """
    Returns a DataFrame with columns:
    ["Teacher", "Subject Code", "Description", "Units"]

    If instructor_name is provided, it filters subjects where Teacher contains the string (case-insensitive).
    """
    cache_key = f"instructor_subjects_cache_{instructor_name if instructor_name else 'all'}.pkl"

    def query():



        filter_query = {}
        if instructor_name:
            # Case-insensitive wildcard search
            filter_query["Teacher"] = {"$regex": instructor_name, "$options": "i"}

        cursor = db.subjects.find(
            filter_query,
            {"_id": 1, "Description": 1, "Units": 1, "Teacher": 1}
        ).sort("Teacher", 1)

        df = pd.DataFrame(list(cursor))
        if df.empty:
            return df

        df.rename(columns={"_id": "Subject Code"}, inplace=True)
        df["Subject Code"] = df["Subject Code"].astype(str)

        if limit:
            df = df.head(limit)

        return df

    return load_or_query(cache_key, query)


def get_curriculum(db, program_code):
    """
    Returns the curriculum for a given program code.
    """
    def query():

        program_doc = db.curriculum.find_one({"programCode": program_code})

        if program_doc and "subjects" in program_doc:
            df = pd.DataFrame(program_doc["subjects"])
            # Rename columns to be consistent
            df.rename(columns={"code": "Subject Code", "name": "Description"}, inplace=True)
            return df
        else:
            return pd.DataFrame()

    # Define a cache key based on the program code
    cache_key = f"curriculum_{program_code}.pkl"
    return load_or_query(cache_key, query)


# ===============================
# TEST RUN
# ===============================
if __name__ == "__main__":

    
    # print( get_students_collection().head(1)) #   b'$2b$12$7gc.TcApIFGSEC3anIVHoufkm5L/vx.t0O5Vj8syaCAn7UOvW6Nyu'

    # print(get_student_subjects_grades(StudentID=500001))
    # print(get_subjects())

    pass
