import matplotlib.pyplot as plt
from pymongo import MongoClient
from collections import defaultdict
import numpy as np
import os
import pandas as pd
import hashlib
import pickle
import time
from functools import wraps
import statistics
from helpers.cache_helper import cache_meta

class report_helper(object):
    print("Initializing load_all_data!")
    def __init__(self, arg):
        super(report_helper, self).__init__()
        self.arg = arg
        self.db = arg["db"]
        

    @cache_meta()
    def get_top_performers(self,school_year=None, semester=None):
        # --- Step 1: Fetch everything in bulk ---
        grades = list(self.db.grades.find({}))
        semesters = {s["_id"]: s for s in self.db.semesters.find({})}
        students = {st["_id"]: st for st in self.db.students.find({})}

        total = len(grades)
        data = []

        for idx, g in enumerate(grades, start=1):
            if not g.get("Grades"):  # Skip empty grades
                continue

            # --- Step 2: Join with semester ---
            sem = semesters.get(g.get("SemesterID"))
            if not sem:
                continue

            # Apply filters
            if school_year and int(sem.get("SchoolYear")) != int(school_year):
                continue
            if semester and sem.get("Semester") != semester:
                continue

            # --- Step 3: Join with student ---
            student = students.get(g.get("StudentID"))
            if not student:
                continue

            # --- Step 4: Compute average ---
            avg_grade = sum(g["Grades"]) / len(g["Grades"])

            data.append({
                "Student": student.get("Name"),
                "Course": student.get("Course"),
                "YearLevel": student.get("YearLevel"),
                "Semester": sem.get("Semester"),
                "SchoolYear": sem.get("SchoolYear"),
                "Average": avg_grade
            })

            # --- Step 5: Print progress ---
            if idx % max(1, total // 5) == 0:  # every 20%
                percent = (idx / total) * 100
                print(f"Processing... ({percent:.0f}% done)")

        # --- Step 6: Sort and limit ---
        top10 = sorted(data, key=lambda x: x["Average"], reverse=True)[:10]

        return pd.DataFrame(top10)

    @cache_meta()
    def get_failing_students(self,school_year=None, semester=None):
        # Convert numpy types to plain Python types
        if school_year is not None:
            school_year = int(school_year)  # ensure BSON-safe
        if semester is not None:
            semester = str(semester)        # ensure BSON-safe

        pipeline = [
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},
            {
                "$match": {
                    **({"sem.SchoolYear": school_year} if school_year else {}),
                    **({"sem.Semester": semester} if semester else {}),
                    "Grades.0": {"$exists": True}
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "Student": "$student.Name",
                    "Course": "$student.Course",
                    "Semester": "$sem.Semester",
                    "SchoolYear": "$sem.SchoolYear",
                    "Subjects Taken": {"$size": "$Grades"},
                    "Failures": {
                        "$size": {
                            "$filter": {
                                "input": "$Grades",
                                "as": "g",
                                "cond": {"$lt": ["$$g", 75]}
                            }
                        }
                    }
                }
            },
            {
                "$addFields": {
                    "FailureRate": {
                        "$cond": [
                            {"$gt": ["$Subjects Taken", 0]},
                            {"$divide": ["$Failures", "$Subjects Taken"]},
                            0
                        ]
                    }
                }
            },
            {"$match": {"FailureRate": {"$gt": 0.3}}},
            {"$sort": {"Failures": -1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if not df.empty:
            df["Failure Rate"] = (df["FailureRate"] * 100).round(0).astype(int).astype(str) + "%"
            df = df.drop(columns=["FailureRate"])

        return df


    @cache_meta()
    def get_students_with_improvement(self,selected_semester="All", selected_sy="All"):
        match_stage = {"Grades.0": {"$exists": True}}  # skip students with no grades

        if selected_sy != "All":
            match_stage["sem.SchoolYear"] = int(selected_sy)  # ensure BSON-safe int
        if selected_semester != "All":
            match_stage["sem.Semester"] = str(selected_semester)

        pipeline = [
            # Join with semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            # Join with students
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},
            # Apply filters
            {"$match": match_stage},
            # Compute average grade per (student, semester)
            {
                "$project": {
                    "_id": 0,
                    "StudentID": "$StudentID",
                    "Student": "$student.Name",
                    "SchoolYear": "$sem.SchoolYear",
                    "Semester": "$sem.Semester",
                    "AvgGrade": {"$avg": "$Grades"}
                }
            },
            # Group all semesters for each student
            {
                "$group": {
                    "_id": "$StudentID",
                    "Student": {"$first": "$Student"},
                    "history": {
                        "$push": {
                            "SchoolYear": "$SchoolYear",
                            "Semester": "$Semester",
                            "AvgGrade": "$AvgGrade"
                        }
                    }
                }
            }
        ]

        results = list(self.db.grades.aggregate(pipeline))

        # Now handle improvement logic in Python (small dataset)
        improved = []
        for r in results:
            history = sorted(
                r["history"],
                key=lambda x: (x["SchoolYear"], x["Semester"])  # sort by SY + Semester
            )
            if len(history) > 1 and history[-1]["AvgGrade"] > history[0]["AvgGrade"]:
                improved.append({
                    "Student": r["Student"],
                    "Initial Avg": history[0]["AvgGrade"],
                    "Latest Avg": history[-1]["AvgGrade"],
                    "Improvement": history[-1]["AvgGrade"] - history[0]["AvgGrade"],
                    "SchoolYear": history[-1]["SchoolYear"],
                    "Semester": history[-1]["Semester"],
                })

        return pd.DataFrame(improved).sort_values("Improvement", ascending=False)


    @cache_meta()
    def get_distribution_of_grades(self,selected_semester="All", selected_sy="All"):
        match_stage = {}
        if selected_sy != "All":
            match_stage["sem.SchoolYear"] = int(selected_sy)  # ensure safe int
        if selected_semester != "All":
            match_stage["sem.Semester"] = str(selected_semester)

        pipeline = [
            # Expand grades array -> one row per grade
            {"$unwind": "$Grades"},
            # Join with semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            # Apply filters (if any)
            {"$match": match_stage} if match_stage else {"$match": {}},
            # Project only needed fields
            {
                "$project": {
                    "_id": 0,
                    "Grade": "$Grades",
                    "Semester": "$sem.Semester",
                    "SchoolYear": "$sem.SchoolYear"
                }
            }
        ]

        result = list(self.db.grades.aggregate(pipeline))
        return pd.DataFrame(result)


    # B. Subject and Teacher Analytics
    @cache_meta()
    def get_hardest_subject(self,course=None, school_year=None):
        match_stage = {}
        if course:
            match_stage["student.Course"] = course
        if school_year:
            match_stage["sem.SchoolYear"] = int(school_year)

        pipeline = [
            # Join with semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            # Join with students
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},
            # Apply filters only if present
            *( [{"$match": match_stage}] if match_stage else [] ),
            # Unwind grades + subjects
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx"}},
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx", "$idx2"]}}},
            # Count fails + totals per subject
            {
                "$group": {
                    "_id": "$SubjectCodes",
                    "Fails": {"$sum": {"$cond": [{"$lt": ["$Grades", 75]}, 1, 0]}},
                    "Total": {"$sum": 1}
                }
            },
            # Join with subjects
            {
                "$lookup": {
                    "from": "subjects",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "subj"
                }
            },
            {"$unwind": {"path": "$subj", "preserveNullAndEmptyArrays": True}},
            # Compute failure rate
            {
                "$project": {
                    "Subject": "$_id",
                    "Description": "$subj.Description",
                    "Fails": 1,
                    "Total": 1,
                    "Failure Rate": {
                        "$cond": [
                            {"$gt": ["$Total", 0]},
                            {"$multiply": [{"$divide": ["$Fails", "$Total"]}, 100]},
                            0
                        ]
                    }
                }
            },
            {"$sort": {"Failure Rate": -1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame()

        df["Failure Rate %"] = df["Failure Rate"].round(0).astype(int).astype(str) + "%"
        return df.reset_index(drop=True)


    @cache_meta()
    def get_easiest_subjects(self,course=None, school_year=None):
        """
        Returns DataFrame with:
          - Subject
          - Description
          - High Performers (>=90)
          - High Rate (% numeric 0–100)
          - Students (total)
        Filters: course, school_year
        """

        # Only add filters if provided
        match_stage = {}
        if course:
            match_stage["student.Course"] = course
        if school_year:
            match_stage["sem.SchoolYear"] = int(school_year)

        pipeline = [
            # Join semesters first
            {"$lookup": {
                "from": "semesters",
                "localField": "SemesterID",
                "foreignField": "_id",
                "as": "sem"
            }},
            {"$unwind": "$sem"},

            # Join students
            {"$lookup": {
                "from": "students",
                "localField": "StudentID",
                "foreignField": "_id",
                "as": "student"
            }},
            {"$unwind": "$student"},

            # Apply filters only if present
            *( [{"$match": match_stage}] if match_stage else [] ),

            # Unwind grades + subjects together
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx"}},
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx", "$idx2"]}}},

            # Group by subject
            {
                "$group": {
                    "_id": "$SubjectCodes",
                    "HighCount": {"$sum": {"$cond": [{"$gte": ["$Grades", 90]}, 1, 0]}},
                    "Total": {"$sum": 1}
                }
            },

            # Lookup subject info
            {"$lookup": {
                "from": "subjects",
                "localField": "_id",
                "foreignField": "_id",
                "as": "subj"
            }},
            {"$unwind": {"path": "$subj", "preserveNullAndEmptyArrays": True}},

            # Compute high rate
            {"$project": {
                "Subject": "$_id",
                "Description": "$subj.Description",
                "High Performers": "$HighCount",
                "Students": "$Total",
                "High Rate": {
                    "$cond": [
                        {"$gt": ["$Total", 0]},
                        {"$multiply": [{"$divide": ["$HighCount", "$Total"]}, 100]},
                        0
                    ]
                }
            }},

            {"$sort": {"High Rate": -1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame()

        df["High Grades"] = df["High Rate"].round(0).astype(int).astype(str) + "%"
        return df.reset_index(drop=True)

    @cache_meta()
    def get_avg_grades_per_teacher(self,school_year=None, semester=None):
        match_stage = {}
        if school_year:
            match_stage["sem.SchoolYear"] = int(school_year)
        if semester:
            match_stage["sem.Semester"] = semester

        pipeline = [
            # Join semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},

            # Apply filters only if provided
            *( [{"$match": match_stage}] if match_stage else [] ),

            # Unwind teachers and grades
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx"}},
            {"$unwind": {"path": "$Teachers", "includeArrayIndex": "idx2"}},

            # Make sure teacher and grade indices align
            {"$match": {"$expr": {"$eq": ["$idx", "$idx2"]}}},

            # Group by teacher
            {
                "$group": {
                    "_id": "$Teachers",
                    "Average Grade": {"$avg": "$Grades"},
                    "Count": {"$sum": 1}
                }
            },
            {"$sort": {"Average Grade": -1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={"_id": "Teacher"})
        df["Semester"] = semester if semester else "All"
        df["SchoolYear"] = school_year if school_year else "All"

        return df.reset_index(drop=True)

    @cache_meta()
    def get_teachers_with_high_failures(self,school_year=None, semester=None):
        match_stage = {}
        if school_year:
            match_stage["sem.SchoolYear"] = int(school_year)
        if semester:
            match_stage["sem.Semester"] = semester

        pipeline = [
            # Join semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},

            # Apply filters (only if provided)
            *( [{"$match": match_stage}] if match_stage else [] ),

            # Unwind Grades and Teachers with indices
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx"}},
            {"$unwind": {"path": "$Teachers", "includeArrayIndex": "idx2"}},

            # Match teacher-grade pairs (same index)
            {"$match": {"$expr": {"$eq": ["$idx", "$idx2"]}}},

            # Group by teacher
            {
                "$group": {
                    "_id": "$Teachers",
                    "Total": {"$sum": 1},
                    "Failures": {"$sum": {"$cond": [{"$lt": ["$Grades", 75]}, 1, 0]}}
                }
            },

            # Compute Failure Rate
            {
                "$project": {
                    "Teacher": "$_id",
                    "Total": 1,
                    "Failures": 1,
                    "Failure Rate": {
                        "$cond": [
                            {"$gt": ["$Total", 0]},
                            {"$round": [{"$multiply": [{"$divide": ["$Failures", "$Total"]}, 100]}, 2]},
                            0
                        ]
                    }
                }
            },

            {"$sort": {"Failure Rate": -1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame()

        df["Semester"] = semester if semester else "All"
        df["SchoolYear"] = school_year if school_year else "All"

        return df.reset_index(drop=True)

    # C. Course and Curriculum Insights
    @cache_meta()
    def get_grade_trend_per_course(self):
        pipeline = [
            # Join with semesters
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},

            # Join with students
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},

            # Exclude records without grades
            {"$match": {"Grades.0": {"$exists": True}}},

            # Compute per-record average
            {
                "$project": {
                    "Course": "$student.Course",
                    "SchoolYear": "$sem.SchoolYear",
                    "Average": {"$avg": "$Grades"}
                }
            },

            # Group by Course + SchoolYear
            {
                "$group": {
                    "_id": {"Course": "$Course", "SchoolYear": "$SchoolYear"},
                    "Average": {"$avg": "$Average"}
                }
            },

            # Reshape
            {
                "$project": {
                    "Course": "$_id.Course",
                    "SchoolYear": "$_id.SchoolYear",
                    "Average": 1,
                    "_id": 0
                }
            },

            # Sort for trends
            {"$sort": {"Course": 1, "SchoolYear": 1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        return pd.DataFrame(result)


    # @cache_meta()
    def get_subject_load_intensity(self):
        pipeline = [
            # Join students
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},

            # Project course + subject load (array length of SubjectCodes)
            {
                "$project": {
                    "Course": "$student.Course",
                    "Load": {"$size": {"$ifNull": ["$SubjectCodes", []]}}
                }
            },

            # Group by course and compute average load
            {
                "$group": {
                    "_id": "$Course",
                    "Load": {"$avg": "$Load"}
                }
            },

            # Reshape result
            {
                "$project": {
                    "Course": "$_id",
                    "Load": 1,
                    "_id": 0
                }
            },
            {"$sort": {"Course": 1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        return pd.DataFrame(result)


    @cache_meta()
    def get_ge_vs_major(self,school_year=None):
        pipeline = [
            # Join semesters collection to get SchoolYear
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "semester"
                }
            },
            {"$unwind": "$semester"},
        ]

        # Optional filter
        if school_year:
            pipeline.append({"$match": {"semester.SchoolYear": school_year}})

        pipeline += [
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx1"}},
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx1", "$idx2"]}}},
            {
                "$project": {
                    "SchoolYear": "$semester.SchoolYear",  # carry over
                    "Type": {
                        "$cond": [
                            {"$regexMatch": {"input": "$SubjectCodes", "regex": "^GE"}},
                            "GE",
                            "Major"
                        ]
                    },
                    "Grade": {"$toDouble": "$Grades"}
                }
            },
            {
                "$group": {
                    "_id": {
                        "SchoolYear": "$SchoolYear",
                        "Type": "$Type"
                    },
                    "Average": {"$avg": "$Grade"},
                    "Count": {"$sum": 1}
                }
            },
            {
                "$project": {
                    "SchoolYear": "$_id.SchoolYear",
                    "Type": "$_id.Type",
                    "Average": 1,
                    "Count": 1,
                    "_id": 0
                }
            },
            {"$sort": {"SchoolYear": 1, "Type": 1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        return pd.DataFrame(result)



    # D. Semester and Academic Year Analysis

    @cache_meta()
    def get_lowest_gpa_semester(self):
        # Step 1: Pull raw grades with semester info
        pipeline = [
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx1"}},
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx1", "$idx2"]}}},
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            {
                "$project": {
                    "SemesterID": "$SemesterID",
                    "Semester": "$sem.Semester",
                    "SchoolYear": "$sem.SchoolYear",
                    "SubjectCode": "$SubjectCodes",
                    "Grade": "$Grades"
                }
            }
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Step 2: Compute GPA per semester (Python side)
        sem_stats = (
            df.groupby(["SemesterID", "Semester", "SchoolYear"])["Grade"]
            .mean()
            .reset_index(name="SemesterGPA")
        )

        # ✅ Exclude semesters with GPA < 50
        sem_stats = sem_stats[sem_stats["SemesterGPA"] >= 50]

        if sem_stats.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Pick the lowest GPA semester
        best_row = sem_stats.loc[sem_stats["SemesterGPA"].idxmin()]

        sem_id = best_row["SemesterID"]
        semester = best_row["Semester"]
        school_year = best_row["SchoolYear"]
        sem_avg = best_row["SemesterGPA"]

        # Step 3: Compute GPA per subject in that semester
        subjects_df = (
            df[df["SemesterID"] == sem_id]
            .groupby("SubjectCode")["Grade"]
            .agg(GPA="mean", Count="count")
            .reset_index()
        )

        # ✅ Exclude subjects with GPA < 50
        subjects_df = subjects_df[subjects_df["GPA"] >= 50]

        # Sort subjects ascending (worst → best)
        subjects_df = subjects_df.sort_values("GPA", ascending=True)

        # Step 4: Build header DataFrame
        header = pd.DataFrame([{
            "Semester": semester,
            "SchoolYear": school_year,
            "SemesterGPA": sem_avg
        }])

        return header, subjects_df




    @cache_meta()
    def get_best_gpa_semester(self):
        # Step 1: Pull raw grades with semester info
        pipeline = [
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx1"}},
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx1", "$idx2"]}}},
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},
            {
                "$project": {
                    "SemesterID": "$SemesterID",
                    "Semester": "$sem.Semester",
                    "SchoolYear": "$sem.SchoolYear",
                    "SubjectCode": "$SubjectCodes",
                    "Grade": "$Grades"
                }
            }
        ]

        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame(), pd.DataFrame()

        # Step 2: Compute GPA per semester in Python
        sem_stats = (
            df.groupby(["SemesterID", "Semester", "SchoolYear"])["Grade"]
            .mean()
            .reset_index(name="SemesterGPA")
        )

        # Pick the best semester (highest GPA)
        best_row = sem_stats.loc[sem_stats["SemesterGPA"].idxmax()]

        sem_id = best_row["SemesterID"]
        semester = best_row["Semester"]
        school_year = best_row["SchoolYear"]
        sem_avg = best_row["SemesterGPA"]

        # Step 3: Compute GPA per subject in that semester
        subjects_df = (
            df[df["SemesterID"] == sem_id]
            .groupby("SubjectCode")["Grade"]
            .agg(GPA="mean", Count="count")
            .reset_index()
            .sort_values("GPA", ascending=False)
        )

        # Step 4: Build header DataFrame
        header = pd.DataFrame([{
            "Semester": semester,
            "SchoolYear": school_year,
            "SemesterGPA": sem_avg
        }])

        return header, subjects_df


    @cache_meta()
    def get_grade_deviation_across_semesters(self):
        pipeline = [
            # Unwind subjects + grades together
            {"$unwind": {"path": "$SubjectCodes", "includeArrayIndex": "idx1"}},
            {"$unwind": {"path": "$Grades", "includeArrayIndex": "idx2"}},
            {"$match": {"$expr": {"$eq": ["$idx1", "$idx2"]}}},

            # Attach semester info
            {
                "$lookup": {
                    "from": "semesters",
                    "localField": "SemesterID",
                    "foreignField": "_id",
                    "as": "sem"
                }
            },
            {"$unwind": "$sem"},

            # Project flat records (no $group)
            {
                "$project": {
                    "Subject": "$SubjectCodes",
                    "Semester": "$sem._id",
                    "Grade": "$Grades"
                }
            }
        ]

        # Get flat records
        result = list(self.db.grades.aggregate(pipeline))
        df = pd.DataFrame(result)

        if df.empty:
            return pd.DataFrame()

        # Compute stats in Python
        stats = (
            df.groupby("Subject")["Grade"]
            .agg(Mean="mean", StdDev="std", Count="count")
            .reset_index()
        )

        # Exclude subjects with mean < 50
        stats = stats[stats["Mean"] >= 50]

        # Sort by StdDev descending
        stats = stats.sort_values("StdDev", ascending=False).reset_index(drop=True)

        return stats



    # E. Student Demographics
    @cache_meta()
    def get_year_level_distribution(self):
        # Pull YearLevel only
        cursor = self.db.students.find({}, {"YearLevel": 1, "_id": 0})
        df = pd.DataFrame(list(cursor))

        # If YearLevel is missing, replace with "Unknown"
        if "YearLevel" not in df.columns:
            df["YearLevel"] = "Unknown"
        else:
            df["YearLevel"] = df["YearLevel"].fillna("Unknown")

        # Count occurrences like Mongo $group
        df = (
            df.groupby("YearLevel")
              .size()
              .reset_index(name="Count")
              .sort_values("YearLevel")
              .reset_index(drop=True)
        )

        return df


    @cache_meta()
    def get_student_count_per_course(self):
        pipeline = [
            {
                "$group": {
                    "_id": "$Course",       # Group by Course
                    "Count": {"$sum": 1}    # Count number of students per course
                }
            },
            {
                "$project": {
                    "Course": "$_id",       # Rename _id to Course
                    "Count": 1,
                    "_id": 0
                }
            },
            {
                "$sort": {"Count": -1}      # Optional: sort by student count descending
            }
        ]

        result = list(self.db.students.aggregate(pipeline))
        df = pd.DataFrame(result)
        return df
        
    @cache_meta()
    def get_performance_by_year_level(self):
        pipeline = [
            # Join with students collection
            {
                "$lookup": {
                    "from": "students",
                    "localField": "StudentID",
                    "foreignField": "_id",
                    "as": "student"
                }
            },
            {"$unwind": "$student"},

            # Compute average grade per student
            {
                "$project": {
                    "YearLevel": "$student.YearLevel",
                    "Average": {"$avg": "$Grades"}
                }
            },

            # Group by year level and average across students
            {
                "$group": {
                    "_id": "$YearLevel",
                    "Average": {"$avg": "$Average"}
                }
            },

            # Sort nicely
            {"$sort": {"_id": 1}}
        ]

        result = list(self.db.grades.aggregate(pipeline))
        return pd.DataFrame(result).rename(columns={"_id": "YearLevel"})

    @cache_meta()
    def get_Schoolyear_options(self):
        return self.db.semesters.distinct("SchoolYear")

    @cache_meta()
    def get_course_options(self):
        return self.db.students.distinct("Course")

    @cache_meta()
    def get_semester_options(self):
        return self.db.semesters.distinct("Semester")


if __name__ == "__main__":
    # from app import st
    pass
