import pandas as pd
from io import BytesIO

def generate_excel(df, filename):
    """Export dataframe to Excel (returns bytes)."""
    buffer = BytesIO()
    try:
        # Try xlsxwriter first
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="Report")
    except ImportError:
        # fallback to openpyxl if xlsxwriter not installed
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Report")
    buffer.seek(0)
    return buffer.read()
