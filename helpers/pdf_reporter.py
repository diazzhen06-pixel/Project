from fpdf import FPDF
import pandas as pd

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Faculty Report', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    def chapter_title(self, title):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, title, 0, 1, 'L')
        self.ln(10)

    def chapter_body(self, body):
        self.set_font('Arial', '', 12)
        self.multi_cell(0, 10, body)
        self.ln()

    def add_table(self, df):
        self.set_font('Arial', 'B', 10)

        # Calculate column widths
        page_width = self.w - 2 * self.l_margin
        num_columns = len(df.columns)
        if num_columns == 0:
            return
        col_width = page_width / num_columns
        col_widths = [col_width] * num_columns

        # Header
        for i, col in enumerate(df.columns):
            self.cell(col_widths[i], 10, col, 1, 0, 'C')
        self.ln()

        # Data
        self.set_font('Arial', '', 10)
        for index, row in df.iterrows():
            for i, col in enumerate(df.columns):
                self.cell(col_widths[i], 10, str(row[col]), 1, 0, 'L')
            self.ln()


def generate_faculty_report_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title(f"Class Report for {data['subject_code']}")

    # Metadata
    pdf.chapter_body(f"Teacher: {data['teachers_str']}")
    pdf.chapter_body(f"Subject: {data['subject_description']}")
    pdf.chapter_body(f"Semester: {data['semester_info']}")
    pdf.chapter_body(f"Average GPA: {data['avg_gpa']:.2f}")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')


def generate_grade_submission_status_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title("Grade Submission Status")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')


def generate_intervention_candidates_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title("Intervention Candidates List")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')


def generate_subject_difficulty_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title("Subject Difficulty Heatmap")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')


def generate_student_progress_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title("Student Progress Tracker")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')


def generate_grade_distribution_pdf(data):
    pdf = PDF()
    pdf.add_page()

    # Title
    pdf.chapter_title("Class Grade Distribution Report")

    # Metadata
    pdf.chapter_body(f"Teacher: {data['teacher_name']}")
    pdf.chapter_body(f"Semester ID: {data['semester_id']}")

    # Table
    pdf.add_table(data['dataframe'])

    return pdf.output(dest='S')
