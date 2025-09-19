import os
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from pymongo import MongoClient
import plotly.express as px

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import tempfile




# ----------------- MongoDB Connection -----------------
@st.cache_resource
def get_db():
    load_dotenv()
    user = os.getenv("MONGO_USER")
    password = os.getenv("MONGO_PASS")

    if not user or not password:
        st.error("❌ Environment variables MONGO_USER or MONGO_PASS are not set.")
        return None

    try:
        uri = f"mongodb+srv://{user}:{password}@cluster0.fav2kov.mongodb.net/mit261"
        client = MongoClient(uri)
        return client["mit261"]
    except Exception as e:
        st.error(f"❌ Database connection failed: {e}")
        return None


# ----------------- Student Panel -----------------
def student_panel():
    pd.options.display.float_format = '{:.2f}'.format
    st.subheader("📖 Student Panel")

    db = get_db()
    if db is None:
        return

    students_col = db["students"]
    grades_col = db["grades"]

    # ----------------- Search -----------------
    search_query = st.text_input("🔍 Search by Name or Course")
    query = {}
    if search_query:
        query = {
            "$or": [
                {"Name": {"$regex": search_query, "$options": "i"}},
                {"Course": {"$regex": search_query, "$options": "i"}},
            ]
        }

    student_ids_with_records = grades_col.distinct("StudentID")
    base_filter = {"_id": {"$in": student_ids_with_records}}
    if query:
        base_filter.update(query)

    count = students_col.count_documents(base_filter)
    st.info(f"🧾 Number of student records with academic data: *{count}*")

    if count == 0:
        st.warning("⚠️ No student records with academic data found.")
        return

    # ----------------- Pagination -----------------
    page_size = 20
    total_pages = (count // page_size) + (1 if count % page_size else 0)
    if "page" not in st.session_state:
        st.session_state.page = 1

    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if st.button("⬅️ Previous") and st.session_state.page > 1:
            st.session_state.page -= 1
    with col3:
        if st.button("Next ➡️") and st.session_state.page < total_pages:
            st.session_state.page += 1

    st.markdown(f"*📄 Page {st.session_state.page} of {total_pages}*")

    skip_count = (st.session_state.page - 1) * page_size
    student_cursor = students_col.find(
        base_filter, {"_id": 1, "Name": 1, "Course": 1, "YearLevel": 1}
    ).skip(skip_count).limit(page_size)

    student_list = list(student_cursor)
    df_students = pd.DataFrame(student_list)
    df_students.rename(columns={
        "_id": "Student ID",
        "Name": "Full Name",
        "Course": "Course",
        "YearLevel": "Year Level"
    }, inplace=True)

    if "Full Name" in df_students.columns:
        df_students.sort_values(by="Full Name", inplace=True)

    st.markdown("### 📋 Student List")
    if df_students.empty:
        st.warning("⚠️ No students found with this filter.")
        return

    selection = st.dataframe(
        df_students,
        selection_mode="single-row",
        on_select="rerun",
        hide_index=True,
        use_container_width=True
    )

    if selection and selection.selection.rows:
        selected_student_index = selection.selection.rows[0]
        selected_student_id = df_students.iloc[selected_student_index]["Student ID"]
        st.session_state.selected_student_id = selected_student_id

    st.markdown("---")

    # ----------------- Show Academic Records -----------------
    if "selected_student_id" in st.session_state:
        selected_id = st.session_state.selected_student_id

        pipeline = [
            {"$match": {"StudentID": selected_id}},
            {"$lookup": {
                "from": "students",
                "localField": "StudentID",
                "foreignField": "_id",
                "as": "student_info"
            }},
            {"$unwind": "$student_info"},
            {"$lookup": {
                "from": "subjects",
                "localField": "SubjectCodes",
                "foreignField": "_id",
                "as": "subject_info"
            }},
            {"$lookup": {
                "from": "semesters",
                "localField": "SemesterID",
                "foreignField": "_id",
                "as": "semester_info"
            }},
            {"$unwind": {"path": "$semester_info", "preserveNullAndEmptyArrays": True}},
            {"$project": {
                "_id": 0,
                "StudentID": 1,
                "Name": "$student_info.Name",
                "Course": "$student_info.Course",
                "YearLevel": "$student_info.YearLevel",
                "SubjectCodes": "$SubjectCodes",
                "Grades": "$Grades",
                "Teachers": "$Teachers",
                "Subjects": "$subject_info",
                "SemesterID": "$SemesterID",
                "Semester": {"$ifNull": ["$semester_info.Semester", "Not Assigned"]},
                "SchoolYear": {"$ifNull": ["$semester_info.SchoolYear", "Not Assigned"]}
            }}
        ]

        academic_records = list(grades_col.aggregate(pipeline))
        if not academic_records:
            st.error("⚠️ No academic records found for this student.")
            return

        # ----------------- Build Academic DataFrame -----------------
        df_academic = pd.DataFrame()
        for record in academic_records:
            subjects = record.get("Subjects", [])
            grades = record.get("Grades", [])
            teachers = record.get("Teachers", [])
            codes = record.get("SubjectCodes", [])

            for i in range(len(subjects)):
                grade_val = grades[i] if i < len(grades) else 0
                df_academic = pd.concat([df_academic, pd.DataFrame([{
                    "SubjectCode": codes[i] if i < len(codes) else "N/A",
                    "Description": subjects[i].get("Description", "N/A"),
                    "Units": subjects[i].get("Units", 0),
                    "FinalGrade": round(float(grade_val), 2),
                    "Instructor": teachers[i] if i < len(teachers) else "N/A",
                    "Semester": record.get("Semester") or "Not Assigned",
                    "SchoolYear": record.get("SchoolYear") or "Not Assigned",
                    "Name": record.get("Name"),
                    "Course": record.get("Course"),
                    "YearLevel": record.get("YearLevel")
                }])], ignore_index=True)

        student_info = df_academic[["Name", "Course", "YearLevel"]].iloc[0]
        st.markdown(f"### 👤 {student_info['Name']}")
        st.write(f"*Course:* {student_info['Course']} | *Year Level:* {student_info['YearLevel']}")

        df_academic.sort_values(by=["SchoolYear", "Semester"], inplace=True)
        st.markdown("### 📚 Academic Records")

        gpa_list = []
        for (sy, sem), group in df_academic.groupby(["SchoolYear", "Semester"], sort=False):
            numeric_grades = pd.to_numeric(group["FinalGrade"], errors="coerce")
            gpa = numeric_grades.mean() if numeric_grades.notna().any() else None
            gpa_list.append({"SchoolYear": sy, "Semester": sem, "GPA": round(gpa, 2) if gpa else None})

            st.markdown(f"#### 🏫 {sy} - {sem}")
            st.dataframe(group[["SubjectCode","Description","Units","FinalGrade","Instructor"]], hide_index=True)
            st.write(f"📊 Average Grade (GPA): {round(gpa,2) if gpa else 'N/A'}")

        df_gpa = pd.DataFrame(gpa_list)
        df_gpa["Term"] = df_gpa["SchoolYear"].astype(str) + " - " + df_gpa["Semester"].astype(str)
        fig = px.line(df_gpa, x="Term", y="GPA", title="📈 GPA per Semester", markers=True)
        st.plotly_chart(fig, use_container_width=True)

        # ----------------- PDF Download -----------------
        def generate_pdf():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmpfile:
                doc = SimpleDocTemplate(tmpfile.name, pagesize=letter)
                elements = []
                styles = getSampleStyleSheet()

                # --- Header ---
                elements.append(Paragraph("Academic Record", styles["Title"]))
                elements.append(Spacer(1, 12))
                elements.append(Paragraph(f"Name: {student_info['Name']}", styles["Normal"]))
                elements.append(Paragraph(f"Course: {student_info['Course']}", styles["Normal"]))
                elements.append(Paragraph(f"Year Level: {student_info['YearLevel']}", styles["Normal"]))
                elements.append(Spacer(1, 20))

                # --- Academic Records by Semester ---
                for (sy, sem), group in df_academic.groupby(["SchoolYear", "Semester"], sort=False):
                    elements.append(Paragraph(f"🏫 {sy} - {sem}", styles["Heading2"]))
                    elements.append(Spacer(1, 6))

                    # Table data
                    table_data = [["SubjectCode", "Description", "Units", "FinalGrade", "Instructor"]]
                    for _, row in group.iterrows():
                        table_data.append([
                            row["SubjectCode"],
                            row["Description"],
                            str(row["Units"]),
                            f"{row['FinalGrade']:.2f}",
                            row["Instructor"]
                        ])

                    # Add average row
                    numeric_grades = pd.to_numeric(group["FinalGrade"], errors="coerce")
                    avg_grade = numeric_grades.mean() if numeric_grades.notna().any() else 0
                    table_data.append(["", "AVERAGE", str(group["Units"].sum()), f"{avg_grade:.2f}", ""])

                    # Table styling
                    table = Table(table_data, repeatRows=1, hAlign="LEFT")
                    table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('GRID', (0, 0), (-1, -1), 0.25, colors.black),
                        ('BACKGROUND', (0, -1), (-1, -1), colors.whitesmoke),
                        ('FONTNAME', (1, -1), (1, -1), 'Helvetica-Bold'),
                        ('TEXTCOLOR', (3, -1), (3, -1), colors.blue),
                    ]))
                    elements.append(table)
                    elements.append(Spacer(1, 12))

                # --- GPA Line Graph ---
                chart_path = tmpfile.name.replace(".pdf", ".png")
                fig.write_image(chart_path)
                elements.append(Paragraph("📈 GPA per Semester", styles["Heading2"]))
                elements.append(Image(chart_path, width=400, height=250))

                doc.build(elements)
                return tmpfile.name

        pdf_file = generate_pdf()
        with open(pdf_file, "rb") as f:
            st.download_button(
                "⬇️ Download Academic Record (PDF)",
                f,
                file_name=f"academic_record_{selected_id}.pdf",
                mime="application/pdf"
            )


# ----------------- Run App -----------------
if __name__ == "__main__":
    student_panel()
