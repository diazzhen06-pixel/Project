import sys, os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))


# helpers/grade_helper.py
from pymongo.collection import Collection
from typing import List, Optional
import pandas as pd

from helpers.cache_helper import cache_meta


from pymongo import MongoClient

# MongoDB Connection
try:
    client = MongoClient("mongodb+srv://aldenroxy:N53wxkFIvbAJjZjc@cluster0.l7fdbmf.mongodb.net") # Or your connection string
    db = client['mit261']
    print("Successfully connected to MongoDB!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")
    sys.exit()


''' def assign_teacher_to_subject(db, student_id: int, semester_id: int, subject_code: str, teacher_name: str) -> bool:
    """
    Assign a teacher to a specific subject of a student in the grades collection.
    Returns True if the update was successful, False if subject not found.
    """
    grades_col: Collection = db["grades"]

    grade_doc = grades_col.find_one({"StudentID": student_id, "SemesterID": semester_id})
    if not grade_doc or subject_code not in grade_doc.get("SubjectCodes", []):
        return False

    index = grade_doc["SubjectCodes"].index(subject_code)
    grades_col.update_one(
        {"_id": grade_doc["_id"]},
        {"$set": {f"Teachers.{index}": teacher_name}}
    )
    return True '''

def assign_teacher_to_subject(subject_code: str, teacher_name: str) -> bool:
    
    subjects_col: Collection = db["subjects"]

    grades_col: Collection = db["grades"]

    result = subjects_col.update_one(

        {"_id": subject_code},   # subject_code is stored in _id

        {"$set": {"Teacher": teacher_name}}

    )

    grades_col.update_many(

        {

            "SubjectCodes": subject_code,

            "$or": [

                {f"Teachers": {"$exists": False}},

                {f"Teachers": None},

                {f"Teachers": ""},

            ]

        },

        {"$set": {"Teachers.$": teacher_name}}  # update matching subject entry

    )

    return result.modified_count > 0

def set_student_grade(db, student_id: int, semester_id: int, subject_code: str, grade: int) -> bool:
    """
    Set/update a grade for a student in a specific subject.
    Returns True if updated, False if not found.
    """
    grades_col: Collection = db["grades"]

    grade_doc = grades_col.find_one({"StudentID": student_id, "SemesterID": semester_id})
    if not grade_doc or subject_code not in grade_doc.get("SubjectCodes", []):
        return False

    index = grade_doc["SubjectCodes"].index(subject_code)
    grades_col.update_one(
        {"_id": grade_doc["_id"]},
        {"$set": {f"Grades.{index}": grade}}
    )
    return True


def set_subject_status(db, student_id: int, semester_id: int, subject_code: str, status: str) -> bool:
    """
    Set/update the status of a subject for a student (e.g., '', 'Dropped', 'INC').
    Returns True if updated, False if not found.
    """
    grades_col: Collection = db["grades"]

    grade_doc = grades_col.find_one({"StudentID": student_id, "SemesterID": semester_id})
    if not grade_doc or subject_code not in grade_doc.get("SubjectCodes", []):
        return False

    # Ensure Status array exists and has the same length as SubjectCodes
    if "Status" not in grade_doc or len(grade_doc["Status"]) != len(grade_doc["SubjectCodes"]):
        grade_doc["Status"] = [""] * len(grade_doc["SubjectCodes"])
        grades_col.update_one({"_id": grade_doc["_id"]}, {"$set": {"Status": grade_doc["Status"]}})

    index = grade_doc["SubjectCodes"].index(subject_code)
    grades_col.update_one(
        {"_id": grade_doc["_id"]},
        {"$set": {f"Status.{index}": status}}
    )
    return True


def get_student_grades(db, student_id: int, semester_id: int) -> Optional[dict]:
    """
    Retrieve the full grade document for a student in a semester.
    """
    return db["grades"].find_one({"StudentID": student_id, "SemesterID": semester_id})
@cache_meta(ttl=1440)  # 1 day
def get_teachers(db,course: str = None):
    """
    Fetches all teachers who taught subjects to students of a specific course.
    If no course is specified, it fetches all teachers.
    Returns a DataFrame with columns: ['Teacher', 'Subject Code', 'Subject Description', 'Student Count']
    """

    # Build the filter based on whether a course is provided
    query_filter = {}
    if course:
        query_filter["Course"] = course

    # 1. Get student IDs based on the filter
    students_cursor = db.students.find(query_filter, {"_id": 1})
    student_ids = [s["_id"] for s in students_cursor]

    # If no students are found (either for the specific course or in general)
    if not student_ids:
        return pd.DataFrame()

    # 2. Get all grades for these students
    grades_cursor = db.grades.find(
        {"StudentID": {"$in": student_ids}},
        {"StudentID": 1, "SubjectCodes": 1, "Teachers": 1}
    )

    rows = []
    for doc in grades_cursor:
        # The zip function handles cases where the arrays are of unequal length or empty.
        for code, teacher in zip(doc.get("SubjectCodes", []), doc.get("Teachers", [])):
            if code and teacher:  # Ensure both code and teacher exist
                rows.append({"Subject Code": code, "Teacher": teacher, "StudentID": doc["StudentID"]})

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)

    # 3. Join with subjects collection to get subject description
    subjects = db.subjects.find({}, {"_id": 1, "Description": 1})
    subj_map = {s["_id"]: s.get("Description", "") for s in subjects}
    df["Subject Description"] = df["Subject Code"].map(subj_map)
    

    # 4. Aggregate by teacher + subject
    summary = df.groupby(["Teacher", "Subject Code", "Subject Description"]).agg(
        Student_Count=("StudentID", "nunique")
    ).reset_index()

    return summary

def get_all_subjects(db):
    """
    Fetches all subjects from the subjects collection.
    """
    return pd.DataFrame(list(db.subjects.find({}, {"Description": 1, "Units": 1, "Teacher": 1})))

def get_all_teachers(db):
    """
    Fetches all unique teacher names from the subjects collection.
    """
    return db.subjects.distinct("Teacher")

def update_subject_teacher(db, subject_code: str, teacher_name: str) -> bool:
    """
    Updates the teacher for a given subject in the subjects collection.
    Returns True if the update was successful, False otherwise.
    """
    result = db.subjects.update_one(
        {"_id": subject_code},
        {"$set": {"Teacher": teacher_name}}
    )
    return result.modified_count > 0

def get_students_in_subject(db, subject_code: str) -> list:
    """
    Fetches all students enrolled in a specific subject.
    """
    pipeline = [
        {"$match": {"SubjectCodes": subject_code}},
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
        {"$project": {
            "_id": 0,
            "StudentID": "$StudentID",
            "Name": "$student_info.Name",
            "Course": "$student_info.Course",
            "YearLevel": "$student_info.YearLevel"
        }}
    ]
    return list(db.grades.aggregate(pipeline))


def get_grade_distribution_by_faculty(db, teacher_name: str, semester_id: int, subject_code: str = None):
    """
    Calculates the grade distribution for a given faculty member and semester, grouped by program.

    Args:
        db: The pymongo database instance.
        teacher_name: The name of the teacher to filter by.
        semester_id: The ID of the semester to filter by.
        subject_code: The subject code to filter by.

    Returns:
        A pandas DataFrame with the grade distribution.
    """
    if not teacher_name or not semester_id:
        return pd.DataFrame()

    pipeline = [
        # Match documents for the given semester
        {"$match": {"SemesterID": semester_id}},
        # Unwind arrays to deconstruct them
        {"$unwind": {"path": "$Teachers", "includeArrayIndex": "teacher_idx"}},
        {"$unwind": {"path": "$Grades", "includeArrayIndex": "grade_idx"}},
        {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "subject_idx"}},
        # Filter to match the teacher and ensure indices are aligned
        {"$match": {"$expr": {"$and": [
            {"$eq": ["$Teachers", teacher_name]},
            {"$eq": ["$teacher_idx", "$grade_idx"]},
            {"$eq": ["$teacher_idx", "$subject_idx"]}
        ]}}},
    ]

    if subject_code:
        pipeline.append({"$match": {"SubjectCodes": subject_code}})

    pipeline.extend([
        # Join with students to get Course
        {"$lookup": {
            "from": "students",
            "localField": "StudentID",
            "foreignField": "_id",
            "as": "student_info"
        }},
        {"$unwind": "$student_info"},
        # Join with curriculum to get programName
        {"$lookup": {
            "from": "curriculum",
            "localField": "student_info.Course",
            "foreignField": "programCode",
            "as": "curriculum_info"
        }},
        {"$unwind": {"path": "$curriculum_info", "preserveNullAndEmptyArrays": True}},
        # Group by program and collect all grades
        {"$group": {
            "_id": {
                "programCode": "$student_info.Course",
                "programName": {"$ifNull": ["$curriculum_info.programName", "$student_info.Course"]}
            },
            "grades": {"$push": "$Grades"}
        }}
    ]

    try:
        data = list(db.grades.aggregate(pipeline))
    except Exception as e:
        print(f"An error occurred during aggregation: {e}")
        return pd.DataFrame()

    if not data:
        return pd.DataFrame()

    # Process the data with pandas
    records = []
    for item in data:
        program_code = item["_id"]["programCode"]
        program_name = item["_id"]["programName"]

        # Convert grades to numeric (force non-numeric to NaN)
        grades = pd.to_numeric(pd.Series(item["grades"]), errors="coerce")
        grades = grades.dropna().astype(int)  # drop NaNs, cast to int
        total_grades = len(grades)

        if total_grades == 0:
            continue

        # Debug
        print("grades:", grades.head(), "dtype:", grades.dtype)

        # Define grade bins
        bins = {
            "95-100(%)": ((grades >= 95) & (grades <= 100)).sum(),
            "90-94(%)": ((grades >= 90) & (grades <= 94)).sum(),
            "85-89(%)": ((grades >= 85) & (grades <= 89)).sum(),
            "80-84(%)": ((grades >= 80) & (grades <= 84)).sum(),
            "75-79(%)": ((grades >= 75) & (grades <= 79)).sum(),
            "Below 75(%)": (grades < 75).sum()
        }

        # Calculate percentages and create record
        record = {
            "programCode": program_code,
            "programName": program_name,
            "Total": total_grades
        }

        for key, value in bins.items():
            percentage = (value / total_grades) * 100 if total_grades > 0 else 0
            record[key] = f"{percentage:.2f}%"

        records.append(record)


    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # Reorder columns to match request
    column_order = [
        "programCode", "programName", "95-100(%)", "90-94(%)", "85-89(%)",
        "80-84(%)", "75-79(%)", "Below 75(%)", "Total"
    ]

    # Ensure all columns exist
    for col in column_order:
        if col not in df:
            df[col] = 0 if col != 'Total' else '0.00%'

    df = df[column_order]

    return df



if __name__ == "__main__":

    # Assign teacher
    # assign_teacher_to_subject(db, student_id=1, semester_id=6, subject_code="IT405", teacher_name="Prof. Alden Quiñones")

    # # Update grade
    # set_student_grade(db, student_id=1, semester_id=6, subject_code="IT405", grade=95)

    # # Set status
    # set_subject_status(db, student_id=1, semester_id=6, subject_code="IT405", status="Dropped")

    # # Fetch full record
    # doc = get_student_grades(db, student_id=1, semester_id=6)
    # print(doc["SubjectCodes"], doc["Grades"], doc["Teachers"], doc["Status"])

    data = get_teachers('Computer Science')
    print(data)
