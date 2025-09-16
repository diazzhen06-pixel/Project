import streamlit as st
import pandas as pd
import numpy as np
import io
import matplotlib.pyplot as plt
from datetime import datetime
from bson import ObjectId

# ------------------
# Helper functions
# ------------------

def get_teacher_subjects(df_merged, teacher_name):
    subjects = []
    for _, row in df_merged.iterrows():
        if isinstance(row.get("Teachers"), list) and teacher_name in row["Teachers"]:
            codes = row.get("SubjectCodes", [])
            if isinstance(codes, list):
                subjects.extend(codes)
    return sorted(set(subjects))

def get_students_for_subject(df_merged, subject_code):
    filt = df_merged[df_merged["SubjectCodes"].apply(lambda codes: subject_code in codes if isinstance(codes, list) else False)].copy()
    return filt.reset_index(drop=True)

def get_student_grade_from_row(row, subject):
    # uses columns SubjectCodes & Grades arrays in df_merged
    if isinstance(row.get("SubjectCodes"), list) and isinstance(row.get("Grades"), list):
        for idx, code in enumerate(row["SubjectCodes"]):
            if code == subject and idx < len(row["Grades"]):
                return row["Grades"][idx]
    return None

def update_student_grade(db, student_id, subject_code, new_grade):
    # Update in grades collection (assumes array positional operator)
    # If document structure differs, adapt queries.
    db["grades"].update_one(
        {"StudentID": student_id, "SubjectCodes": subject_code},
        {"$set": {"Grades.$": new_grade}},
    )

def lock_final_grades(db, teacher_name, subject_code):
    # Mark subject grades locked by teacher (simple flag document)
    db["grades"].update_many(
        {"SubjectCodes": subject_code},
        {"$set": {"FinalLocked": True, "LockedBy": teacher_name, "LockedAt": datetime.utcnow()}}
    )

def fetch_grade_history(db, student_id):
    # Return list of grade documents for student
    docs = list(db["grades"].find({"StudentID": student_id}))
    return docs

def compute_grade_distribution(page_students, subject):
    # Return list of numeric grades from df rows
    grades = []
    for _, r in page_students.iterrows():
        g = get_student_grade_from_row(r, subject)
        if g is not None:
            try:
                grades.append(float(g))
            except:
                pass
    return grades

def plot_histogram_matplotlib(grades, title="Grade Distribution"):
    fig, ax = plt.subplots()
    if len(grades) == 0:
        ax.text(0.5, 0.5, "No grades available", ha="center", va="center")
    else:
        ax.hist(grades, bins=10)
        ax.set_xlabel("Grades")
        ax.set_ylabel("Frequency")
    ax.set_title(title)
    st.pyplot(fig)
    plt.close(fig)

def plot_pass_fail(grades, passing_threshold=75):
    fig, ax = plt.subplots()
    if len(grades) == 0:
        ax.text(0.5, 0.5, "No grades available", ha="center", va="center")
    else:
        passed = sum(1 for g in grades if g >= passing_threshold)
        failed = sum(1 for g in grades if g < passing_threshold)
        ax.bar(["Pass", "Fail"], [passed, failed])
        ax.set_ylabel("Number of Students")
        ax.set_title("Pass vs Fail")
    st.pyplot(fig)
    plt.close(fig)

def compute_subject_difficulty(db, teacher_subjects):
    # For each subject compute fail rate and dropout rate if available
    rows = []
    for subj in teacher_subjects:
        # Query grades collection for subject
        docs = list(db["grades"].find({"SubjectCodes": subj}))
        # Flatten numeric grades
        flattened = []
        for d in docs:
            # If Grades stored as array of numbers along with SubjectCodes
            if isinstance(d.get("Grades"), list) and isinstance(d.get("SubjectCodes"), list):
                for idx, code in enumerate(d["SubjectCodes"]):
                    if code == subj and idx < len(d["Grades"]):
                        try:
                            flattened.append(float(d["Grades"][idx]))
                        except:
                            pass
        total = len(flattened)
        fail_rate = (sum(1 for g in flattened if g < 75) / total * 100) if total > 0 else 0
        # dropout rate: try to get from students collection if 'Dropped' or attendance
        dropouts = db["students"].count_documents({"EnrolledSubjects": subj, "Status": {"$in": ["Dropped", "DroppedOut"]}})
        # difficulty heuristic
        if fail_rate >= 20:
            diff = "High"
        elif fail_rate >= 10:
            diff = "Medium"
        else:
            diff = "Low"
        rows.append({"CourseCode": subj, "FailRate": round(fail_rate,1), "DropoutRate": dropouts, "Difficulty": diff})
    return pd.DataFrame(rows)

def get_intervention_candidates(df_page, subject, db, threshold=75):
    candidates = []
    for _, r in df_page.iterrows():
        sid = r["StudentID"]
        g = get_student_grade_from_row(r, subject)
        if g is None:
            flag = "Missing Grade"
            candidates.append({"StudentID": sid, "Name": r["Name"], "CourseCode": subject, "CourseName": r.get("Course", ""), "CurrentGrade": "INC", "RiskFlag": flag})
        else:
            try:
                gv = float(g)
                if gv < threshold:
                    candidates.append({"StudentID": sid, "Name": r["Name"], "CourseCode": subject, "CourseName": r.get("Course", ""), "CurrentGrade": gv, "RiskFlag": "At Risk (<{})".format(threshold)})
            except:
                pass
    return pd.DataFrame(candidates)

def grade_submission_status(db, teacher_name, teacher_subjects):
    rows = []
    for subj in teacher_subjects:
        # Count total students expected for subject (students collection or grades collection)
        total = db["grades"].count_documents({"SubjectCodes": subj})
        submitted = db["grades"].count_documents({"SubjectCodes": subj, "Grades": {"$exists": True, "$ne": []}})
        rate = int((submitted / total * 100) if total > 0 else 0)
        rows.append({"CourseCode": subj, "Submitted": submitted, "Total": total, "SubmissionRate": f"{rate}%"})
    return pd.DataFrame(rows)

def export_df_to_csv_bytes(df):
    buf = io.BytesIO()
    df.to_csv(buf, index=False)
    buf.seek(0)
    return buf

# ------------------
# Main dashboard
# ------------------

def new_faculty_panel(df_merged, semesters_map, db):
    st.title("🎓 Faculty Dashboard (Database-driven)")

    # Login / select teacher
    teachers = sorted(
        set(
            teacher
            for teachers_list in df_merged["Teachers"].dropna()
            if isinstance(teachers_list, list)
            for teacher in teachers_list
        )
    )
    if not teachers:
        st.error("No teachers found in df_merged")
        return

    teacher_name = st.sidebar.selectbox("Select Teacher", [""] + teachers)
    if not teacher_name:
        st.info("Please select your name from the sidebar to continue")
        return

    st.sidebar.markdown(f"**Logged in as:** {teacher_name}")

    # Semester selection (if semesters_map provided)
    semester = st.sidebar.selectbox("Semester", [""] + list(semesters_map.keys())) if semesters_map else st.sidebar.text_input("Semester")
    if semester == "":
        semester = None

    # Module navigation (sidebar)
    module = st.sidebar.radio("Module", [
        "Class & Subject Management",
        "Grading & Evaluation",
        "Attendance & Class Records",
        "Advising & Academic Support",
        "Reports"
    ])

    # Precompute teacher subjects
    teacher_subjects = get_teacher_subjects(df_merged, teacher_name)

    # -----------------------
    # Class & Subject Management
    # -----------------------
    if module == "Class & Subject Management":
        st.header("📚 Class & Subject Management")

        st.subheader("📚 View Assigned Subjects")
        if len(teacher_subjects) == 0:
            st.warning("No assigned subjects for this teacher")
        else:
            st.table(pd.DataFrame({"AssignedSubjects": teacher_subjects}))

        st.subheader("🗓 Class Schedule")
        # If you have schedules collection, show schedule for teacher
        schedules = list(db.get("schedules", {}).find({"Teacher": teacher_name})) if "schedules" in db.list_collection_names() else []
        if schedules:
            sched_df = pd.DataFrame(schedules)
            st.dataframe(sched_df, use_container_width=True)
        else:
            st.info("No schedule collection found or no schedule items for this teacher.")

        st.subheader("👨‍🎓 Class Roster / Student List")
        selected_subject = st.selectbox("Select subject to view roster", [""] + teacher_subjects)
        if selected_subject:
            students = get_students_for_subject(df_merged, selected_subject)
            if students.empty:
                st.info("No students enrolled.")
            else:
                # Pagination
                page_size = st.sidebar.number_input("Roster page size", min_value=5, max_value=50, value=10)
                total = len(students)
                pages = (total + page_size - 1) // page_size
                page = st.sidebar.number_input("Roster page", min_value=1, max_value=max(1,pages), value=1, step=1)
                s_idx = (page-1)*page_size
                e_idx = s_idx + page_size
                page_students = students.iloc[s_idx:e_idx].copy()
                page_students["Grade"] = page_students.apply(lambda r: get_student_grade_from_row(r, selected_subject), axis=1)
                st.dataframe(page_students[["StudentID","Name","Course","YearLevel","Grade"]], use_container_width=True)

                # Quick export roster
                csv_bytes = export_df_to_csv_bytes(page_students[["StudentID","Name","Course","YearLevel","Grade"]])
                st.download_button("📥 Download roster CSV (page)", csv_bytes, file_name=f"roster_{selected_subject}_page{page}.csv")

                # Student profile quick view
                selected_student = st.selectbox("Select student for profile", [""] + page_students["StudentID"].tolist(), key=f"profile_{selected_subject}_{page}")
                if selected_student:
                    r = page_students[page_students["StudentID"] == selected_student].iloc[0]
                    st.markdown(f"**Name:** {r['Name']}")
                    st.markdown(f"**ID:** {r['StudentID']}")
                    st.markdown(f"**Course:** {r.get('Course','')}")
                    st.markdown(f"**Year Level:** {r.get('YearLevel','')}")
                    st.markdown(f"**Status:** {r.get('Status','Active')}")
                    # Show grade history
                    gh = fetch_grade_history(db, selected_student)
                    if gh:
                        st.write("Grade history (raw):")
                        st.json(gh[0:5])  # show up to 5 docs
                    else:
                        st.info("No grade history found in DB for this student.")

    # -----------------------
    # Grading & Evaluation
    # -----------------------
    elif module == "Grading & Evaluation":
        st.header("📝 Grading & Evaluation")

        if len(teacher_subjects) == 0:
            st.warning("No assigned subjects")
            return

        selected_subject = st.selectbox("Select subject to grade", [""] + teacher_subjects)
        if not selected_subject:
            st.info("Choose a subject")
            return

        students = get_students_for_subject(df_merged, selected_subject)
        if students.empty:
            st.info("No students")
            return

        # Attach grade column
        students["Grade"] = students.apply(lambda r: get_student_grade_from_row(r, selected_subject), axis=1)

        # Pagination
        page_size = st.sidebar.number_input("Grades page size", min_value=5, max_value=50, value=10, key=f"gradesize_{selected_subject}")
        total_students = len(students)
        total_pages = (total_students + page_size - 1) // page_size
        page = st.sidebar.number_input("Grades page", min_value=1, max_value=max(1,total_pages), value=1, key=f"gradepage_{selected_subject}")
        start = (page-1)*page_size
        end = start + page_size
        page_students = students.iloc[start:end].copy()

        st.subheader(f"Students - Page {page}/{max(1,total_pages)}")
        display_df = page_students[["StudentID","Name","Course","YearLevel","Grade"]].copy()
        st.dataframe(display_df, use_container_width=True)

        # Editing
        selected_student = st.selectbox("Select student to edit", [""] + page_students["StudentID"].tolist(), key=f"selgrade_{selected_subject}_{page}")
        if selected_student:
            row = page_students[page_students["StudentID"] == selected_student].iloc[0]
            current_grade = get_student_grade_from_row(row, selected_subject) or 0
            with st.expander(f"Update {row['Name']} ({selected_student})"):
                new_grade = st.number_input("Grade", min_value=0, max_value=100, value=int(current_grade), key=f"inp_grade_{selected_student}_{selected_subject}_{page}")
                if st.button("💾 Save Grade", key=f"savegrade_{selected_student}_{selected_subject}_{page}"):
                    update_student_grade(db, selected_student, selected_subject, new_grade)
                    st.success("Grade updated in database")

        # Submit final grades (lock)
        st.markdown("---")
        if st.button("🔒 Submit Final Grades (Lock for this subject)", key=f"lock_{selected_subject}"):
            lock_final_grades(db, teacher_name, selected_subject)
            st.success("Grades locked for this subject")

        # Reports: distribution + pass/fail + analytics
        st.subheader("Grade Distribution & Analytics")
        grades = compute_grade_distribution(students, selected_subject)
        plot_histogram_matplotlib(grades, title=f"Grade Distribution - {selected_subject}")
        plot_pass_fail(grades)

        # Grade summary
        if len(grades) > 0:
            arr = np.array(grades)
            summary = {"Mean": np.mean(arr), "Median": np.median(arr), "Highest": np.max(arr), "Lowest": np.min(arr)}
            st.table(pd.DataFrame([summary]).T.rename(columns={0:"Value"}))
        else:
            st.info("No numeric grades available to summarize")

        # Grade submission status for teacher
        st.subheader("Grade Submission Status (Your subjects)")
        status_df = grade_submission_status(db, teacher_name, teacher_subjects)
        st.dataframe(status_df, use_container_width=True)

    # -----------------------
    # Attendance & Class Records
    # -----------------------
    elif module == "Attendance & Class Records":
        st.header("📋 Attendance & Class Records")

        st.subheader("Record Attendance")
        sel_sub = st.selectbox("Select Subject", [""] + teacher_subjects, key="att_sub")
        if sel_sub:
            date = st.date_input("Date", value=datetime.today())
            students = get_students_for_subject(df_merged, sel_sub)
            students = students.reset_index(drop=True)
            if students.empty:
                st.info("No students")
            else:
                st.write("Mark attendance (Present/Absent)")
                # Use unique keys per student and date
                for idx, r in students.iterrows():
                    sid = r["StudentID"]
                    default = r.get("Attendance", {}).get(str(date), "Present") if isinstance(r.get("Attendance"), dict) else "Present"
                    choice = st.selectbox(f"{r['Name']} ({sid})", ["Present","Absent","Late"], index=0 if default=="Present" else (1 if default=="Absent" else 2), key=f"att_{sel_sub}_{sid}_{date}")
                    # Save to DB on selection (or later via Save button)
                    # We'll offer a Save All button
                if st.button("💾 Save Attendance", key=f"save_att_{sel_sub}_{date}"):
                    # iterate and write attendance records
                    for idx, r in students.iterrows():
                        sid = r["StudentID"]
                        selected = st.session_state.get(f"att_{sel_sub}_{sid}_{date}", "Present")
                        db["attendance"].update_one(
                            {"StudentID": sid, "Subject": sel_sub, "Date": str(date)},
                            {"$set": {"Status": selected, "MarkedBy": teacher_name, "Timestamp": datetime.utcnow()}},
                            upsert=True
                        )
                    st.success("Attendance saved")

        st.subheader("View Attendance Summary")
        sel_sub2 = st.selectbox("Select subject for summary", [""] + teacher_subjects, key="att_summary_sub")
        if sel_sub2:
            # aggregate attendance from attendance collection
            pipeline = [
                {"$match": {"Subject": sel_sub2}},
                {"$group": {"_id": {"StudentID": "$StudentID", "Status": "$Status"}, "count": {"$sum":1}}}
            ]
            # If attendance collection missing, fallback to info
            if "attendance" in db.list_collection_names():
                agg = list(db["attendance"].aggregate(pipeline))
                if not agg:
                    st.info("No attendance records found for this subject")
                else:
                    # pivot
                    rows = {}
                    for doc in agg:
                        sid = doc["_id"]["StudentID"]
                        status = doc["_id"]["Status"]
                        cnt = doc["count"]
                        rows.setdefault(sid, {})[status] = cnt
                    df_rows = []
                    for sid, stats in rows.items():
                        student = df_merged[df_merged["StudentID"]==sid]
                        name = student.iloc[0]["Name"] if not student.empty else sid
                        df_rows.append({"StudentID": sid, "Name": name, **stats})
                    st.dataframe(pd.DataFrame(df_rows).fillna(0))
            else:
                st.info("No attendance collection in DB to summarize")

        st.subheader("📥 Export Class Records")
        sel_sub3 = st.selectbox("Select subject to export (grades + attendance)", [""] + teacher_subjects, key="export_sub")
        if sel_sub3:
            students = get_students_for_subject(df_merged, sel_sub3)
            if not students.empty:
                students["Grade"] = students.apply(lambda r: get_student_grade_from_row(r, sel_sub3), axis=1)
                csvb = export_df_to_csv_bytes(students[["StudentID","Name","Course","YearLevel","Grade"]])
                st.download_button("📥 Download full class CSV", csvb, file_name=f"{sel_sub3}_class_records.csv")

    # -----------------------
    # Advising & Academic Support
    # -----------------------
    elif module == "Advising & Academic Support":
        st.header("🎯 Advising & Academic Support")

        st.subheader("Advising Tools")
        advise_student = st.text_input("Enter StudentID to view advising summary")
        if advise_student:
            student = df_merged[df_merged["StudentID"]==advise_student]
            if student.empty:
                st.info("Student not found")
            else:
                r = student.iloc[0]
                st.markdown(f"**Name:** {r['Name']}")
                st.markdown(f"**Course:** {r.get('Course','')}")
                st.markdown(f"**YearLevel:** {r.get('YearLevel','')}")
                # Check curriculum vs taken courses if you have curriculum DB
                if "curriculum" in db.list_collection_names():
                    # placeholder for curriculum comparison
                    st.info("Prerequisite and curriculum checks available if curriculum data is present.")
                # Endorsement
                if st.button("🧾 Add Endorsement / Recommendation", key=f"endorse_{advise_student}"):
                    db["endorsements"].insert_one({"StudentID": advise_student, "By": teacher_name, "CreatedAt": datetime.utcnow(), "Note": "Endorsement added via faculty panel"})
                    st.success("Endorsement recorded")

        st.subheader("Prerequisite Validation")
        st.info("You can validate pre-reqs if curriculum & grades are present in DB. This will be implemented using your curriculum schema.")

    # -----------------------
    # Reports consolidated
    # -----------------------
    elif module == "Reports":
        st.header("📊 Reports")

        # 1. Class Grade Distribution (per subject)
        st.subheader("1) Class Grade Distribution")
        sel_sub = st.selectbox("Select subject", [""] + teacher_subjects, key="rep_dist_sub")
        if sel_sub:
            students = get_students_for_subject(df_merged, sel_sub)
            grades = compute_grade_distribution(students, sel_sub)
            plot_histogram_matplotlib(grades, title=f"Grade Distribution - {sel_sub}")

        # 2. Student Progress Tracker
        st.subheader("2) Student Progress Tracker")
        sid = st.text_input("Student ID", key="rep_progress_sid")
        if sid:
            # collect GPA per semester from db["grades"] if stored
            # Assume db["student_gpa"] stores docs with fields {"StudentID","Semester","GPA"}
            if "student_gpa" in db.list_collection_names():
                gpas = list(db["student_gpa"].find({"StudentID": sid}).sort("Semester", 1))
                if gpas:
                    df_gpa = pd.DataFrame(gpas)
                    fig, ax = plt.subplots()
                    ax.plot(df_gpa["Semester"], df_gpa["GPA"], marker="o")
                    ax.set_title(f"GPA Trend - {sid}")
                    ax.set_xlabel("Semester")
                    ax.set_ylabel("GPA")
                    st.pyplot(fig)
                    plt.close(fig)
                else:
                    st.info("No GPA history for this student.")
            else:
                st.info("No student_gpa collection in DB.")

        # 3. Subject Difficulty Heatmap
        st.subheader("3) Subject Difficulty Heatmap")
        subj_df = compute_subject_difficulty(db, teacher_subjects)
        if not subj_df.empty:
            st.dataframe(subj_df, use_container_width=True)
            # Simple heatmap using pivot (matplotlib)
            fig, ax = plt.subplots(figsize=(6, max(2, len(subj_df)*0.5)))
            ax.table(cellText=subj_df[["CourseCode","FailRate","DropoutRate","Difficulty"]].values, colLabels=["Course","Fail%","Dropouts","Difficulty"], loc="center")
            ax.axis("off")
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("No subject difficulty data")

        # 4. Intervention Candidates
        st.subheader("4) Intervention Candidates List")
        sel_sub_i = st.selectbox("Select subject to scan for interventions", [""] + teacher_subjects, key="rep_interv_sub")
        if sel_sub_i:
            students = get_students_for_subject(df_merged, sel_sub_i)
            page_size = 50
            candidates = get_intervention_candidates(students, sel_sub_i, db, threshold=75)
            if candidates.empty:
                st.info("No intervention candidates found.")
            else:
                st.table(candidates)

        # 5. Grade Submission Status
        st.subheader("5) Grade Submission Status")
        status_df = grade_submission_status(db, teacher_name, teacher_subjects)
        st.dataframe(status_df, use_container_width=True)

        # 6. Custom Query Builder
        st.subheader("6) Custom Query Builder")
        st.markdown("Example queries: `Show all students with < 75 in CS101`")
        q_subject = st.text_input("Subject code (e.g., CS101)", key="cq_sub")
        q_op = st.selectbox("Operator", ["<", "<=", ">", ">=", "=="], key="cq_op")
        q_val = st.number_input("Value", value=75, key="cq_val")
        if st.button("Run Query", key="cq_run"):
            if q_subject:
                students = get_students_for_subject(df_merged, q_subject)
                matched = []
                for _, r in students.iterrows():
                    g = get_student_grade_from_row(r, q_subject)
                    try:
                        if g is not None:
                            expr = f"{float(g)} {q_op} {float(q_val)}"
                            if eval(expr):
                                matched.append({"StudentID": r["StudentID"], "Name": r["Name"], "CourseCode": q_subject, "Grade": g})
                    except Exception:
                        pass
                if matched:
                    st.table(pd.DataFrame(matched))
                else:
                    st.info("No matching students found.")
            else:
                st.warning("Please enter a subject code for the query")

        # 7. Students Grade Analytics (Per Teacher)
        st.subheader("7) Students Grade Analytics (Per Teacher)")
        sel_teacher_analytics = st.selectbox("Select Teacher", [""] + teachers, key="analytics_teacher")
        if sel_teacher_analytics:
            subs = get_teacher_subjects(df_merged, sel_teacher_analytics)
            sel_sub_a = st.selectbox("Select Subject", [""] + subs, key="analytics_sub")
            if sel_sub_a:
                students = get_students_for_subject(df_merged, sel_sub_a)
                students["Grade"] = students.apply(lambda r: get_student_grade_from_row(r, sel_sub_a), axis=1)
                numeric = students["Grade"].apply(lambda x: pd.to_numeric(x, errors="coerce")).dropna()
                if not numeric.empty:
                    summary = {"Mean": numeric.mean(), "Median": numeric.median(), "Highest": numeric.max(), "Lowest": numeric.min()}
                    st.table(pd.DataFrame([summary]).T.rename(columns={0:"Value"}))
                st.dataframe(students[["StudentID","Name","Course","YearLevel","Grade"]], use_container_width=True)

    # end dashboard
    st.write("---")
    st.caption("Faculty dashboard — integrated with database. Adapt collection names if your DB schema differs.")
