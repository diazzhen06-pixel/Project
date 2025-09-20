from fpdf import FPDF
from io import BytesIO
import pandas as pd


class PDF(FPDF):
    def header(self):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, "Faculty Report", 0, 1, "C")

    def footer(self):
        self.set_y(-15)
        self.set_font("Arial", "I", 8)
        self.cell(0, 10, f"Page {self.page_no()}", 0, 0, "C")

    def add_table(self, dataframe: pd.DataFrame, title="Data Table"):
        self.set_font("Arial", "B", 12)
        self.cell(0, 10, title, 0, 1, "L")

        # Column headers
        self.set_font("Arial", "B", 8)
        col_width = self.epw / len(dataframe.columns)
        for col in dataframe.columns:
            self.cell(col_width, 10, str(col), border=1)
        self.ln()

        # Rows
        self.set_font("Arial", "", 8)
        for _, row in dataframe.iterrows():
            for item in row:
                self.cell(col_width, 10, str(item), border=1)
            self.ln()

    def add_image_from_bytes(self, image_bytes, w=180):
        """Add an image from raw bytes (PNG)"""
        bio = BytesIO(image_bytes)
        self.image(bio, w=w)


def generate_faculty_report_pdf(data: dict) -> bytes:
    """
    Generate a PDF for a faculty class report.
    """
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Faculty Class Report", 0, 1, "C")

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Subject: {data.get('subject_code')} - {data.get('subject_description')}", 0, 1)
    pdf.cell(0, 10, f"Teacher(s): {data.get('teachers_str')}", 0, 1)
    pdf.cell(0, 10, f"Semester: {data.get('semester_info')}", 0, 1)
    pdf.cell(0, 10, f"Class GPA: {data.get('avg_gpa'):.2f}", 0, 1)
    pdf.ln(5)

    # Data table
    if isinstance(data.get("dataframe"), pd.DataFrame) and not data["dataframe"].empty:
        pdf.add_table(data["dataframe"], title="Class Grades")

    # Charts
    charts = data.get("charts", [])
    if charts:
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "Visualizations", 0, 1, "C")
        for chart_bytes in charts:
            pdf.add_image_from_bytes(chart_bytes, w=180)
            pdf.ln(10)

    # ✅ Return raw PDF bytes (not bytearray)
    return pdf.output(dest="S").encode("latin1")


def generate_grade_distribution_pdf(data: dict) -> bytes:
    """
    Generate a PDF for grade distribution across programs.
    """
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Grade Distribution Report", 0, 1, "C")

    pdf.set_font("Arial", "", 12)
    pdf.cell(0, 10, f"Teacher: {data.get('teacher_name')}", 0, 1)
    pdf.cell(0, 10, f"Semester ID: {data.get('semester_id')}", 0, 1)
    pdf.ln(5)

    # Data table
    if isinstance(data.get("dataframe"), pd.DataFrame) and not data["dataframe"].empty:
        pdf.add_table(data["dataframe"], title="Grade Distribution by Program")

    # Charts
    charts = data.get("charts", [])
    if charts:
        pdf.add_page()
        pdf.set_font("Arial", "B", 14)
        pdf.cell(0, 10, "Distribution Charts", 0, 1, "C")
        for chart_bytes in charts:
            pdf.add_image_from_bytes(chart_bytes, w=180)
            pdf.ln(10)

    # ✅ Return raw PDF bytes (not bytearray)
    return pdf.output(dest="S").encode("latin1")
