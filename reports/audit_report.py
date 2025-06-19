# reports/audit_report.py
import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Table, TableStyle, PageBreak, Image
)

from io import BytesIO
from reportlab.platypus import BaseDocTemplate, Frame, PageTemplate, Table, TableStyle, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
# reuse your connection, user-lookup, and canvas-numbering from process_report
from .process_report import get_db_connection, get_latest_user, NumberedCanvas


def get_audit_data(start_dt, end_dt, config):
    """
    Fetch AuditReport entries between start_dt and end_dt,
    convert timestamp to IST, filter out system/service accounts.
    """
    conn = get_db_connection(config, db_name="Audit")

    query = """
    WITH AuditCTE AS (
      SELECT
        TimeStmp AS UTC_Time,
        MessageText,
        UserID,
        UserFullName,
        Audience
      FROM AuditReport
      WHERE TimeStmp BETWEEN ? AND ?
        AND UserID NOT IN (
          'NT AUTHORITY\\NETWORK SERVICE',
          'N/A',
          'WORKGROUP\\WIN-U1DFOUPBRPI$',
          'WIN-U1DFOUPBRPI\\ADMIN',
          'FactoryTalk Service',
          'NT AUTHORITY\\LOCAL SERVICE',
          'NT AUTHORITY\\SYSTEM'
        )
    )
    SELECT
      UTC_Time,
      MessageText,
      UserID,
      UserFullName,
      Audience
    FROM AuditCTE
    ORDER BY UTC_Time;
    """

    # Query with UTC times
    df = pd.read_sql_query(query, conn, params=[start_dt, end_dt])

    if df.empty:
        return df

    # Convert to proper datetime types
    df['UTC_Time'] = pd.to_datetime(df['UTC_Time'])
    
    # Convert UTC to IST (+5:30)
    df['IST_Time'] = df['UTC_Time'] + timedelta(hours=5, minutes=30)
    
    # Format for display
    df['Date'] = df['IST_Time'].dt.strftime('%d-%m-%Y')
    df['Time'] = df['IST_Time'].dt.strftime('%H:%M:%S')

    return df[['Date', 'Time', 'MessageText', 'UserID', 'UTC_Time', 'IST_Time']]



# def get_audit_data(start_dt, end_dt, config):
#     """
#     Fetch AuditReport entries between start_dt and end_dt,
#     convert timestamp to IST, filter out system/service accounts.
#     """
#     conn = get_db_connection(config, db_name="Audit")

#     query = """
#     WITH AuditCTE AS (
#       SELECT
#         TimeStmp,
#         MessageText,
#         UserID,
#         UserFullName,
#         Audience
#       FROM AuditReport
#       WHERE TimeStmp BETWEEN ? AND ?
#         AND UserID NOT IN (
#           'NT AUTHORITY\\NETWORK SERVICE',
#           'N/A',
#           'WORKGROUP\\WIN-U1DFOUPBRPI$',
#           'WIN-U1DFOUPBRPI\\ADMIN',
#           'FactoryTalk Service',
#           'NT AUTHORITY\\LOCAL SERVICE',
#           'NT AUTHORITY\\SYSTEM'
#         )
#     )
#     SELECT
#       DATEADD(SECOND, 19800, TimeStmp) AS LocalTS,
#       MessageText,
#       UserID,
#       UserFullName,
#       Audience
#     FROM AuditCTE
#     ORDER BY TimeStmp;
#     """

#     # pandas will infer column names from the cursor.description
#     df = pd.read_sql_query(query, conn, params=[start_dt, end_dt])

#     # If no rows, return empty frame
#     if df.empty:
#         return df

#     # Split out Date/Time
#     df['LocalTS'] = pd.to_datetime(df['LocalTS'])
#     df['Date'] = df['LocalTS'].dt.strftime('%d-%m-%Y')
#     df['Time'] = df['LocalTS'].dt.strftime('%H:%M:%S')

#     return df[['Date', 'Time', 'MessageText', 'UserID']]



# Assume these are defined somewhere
# from your_project.utils import NumberedCanvas

def generate_audit_pdf_report(df, params):
    buffer = BytesIO()

    # Margins and page setup
    PAGE_SIZE = A4
    LEFT, RIGHT = 10*mm, 10*mm
    TOP, BOTTOM = 50*mm, 20*mm

    class MyDoc(BaseDocTemplate):
        def __init__(self, fn, **kw):
            super().__init__(fn, pagesize=PAGE_SIZE, **kw)
            frame_h = self.pagesize[1] - TOP - BOTTOM
            frame = Frame(LEFT, BOTTOM,
                          self.pagesize[0] - LEFT - RIGHT,
                          frame_h, id='normal')
            tpl = PageTemplate(id='all',
                               frames=[frame],
                               onPage=self.header_footer)
            self.addPageTemplates([tpl])

        def header_footer(self, canvas, doc):
            self._draw_header(canvas, doc)
            self._draw_footer(canvas, doc)

        def _draw_header(self, canvas, doc):
            canvas.saveState()
            try:
                logo = Image('alivus_logo.png', width=60, height=60)
                logo.drawOn(canvas, 15*mm, doc.pagesize[1] - 25*mm)
            except:
                pass

            canvas.setFont('Helvetica-Bold', 16)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 20*mm,
                "ALIVUS LIFE SCIENCES LIMITED ANKLESHWAR"
            )

            canvas.setFont('Helvetica-Bold', 14)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 32*mm,
                "Audit Report"
            )

            if params:
                canvas.setFont('Helvetica', 9)
                y0 = doc.pagesize[1] - 40*mm
                canvas.drawString(120*mm, y0, f"FROM DATE: {params.get('FROM DATE','')}")
                canvas.drawString(120*mm, y0 - 5*mm, f"TO DATE:   {params.get('TO DATE','')}")

            canvas.restoreState()

        def _draw_footer(self, canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.black)
            
            # Printed By
            printedBy = params.get('Printed By', '[no user logged in]') 
            canvas.drawString(10 * mm, 10 * mm, f"Printed By: {printedBy}")

            # Printed Date (centered)
            printed_date = datetime.now().strftime('%d/%m/%Y %H:%M')
            date_text_width = canvas.stringWidth(printed_date, 'Helvetica', 8)
            center_x = (doc.pagesize[0] / 2) - (date_text_width / 2) - 10 * mm
            canvas.drawString(center_x, 10 * mm, f"Printed Date: {printed_date}")
            
            # Page Number (right side)
            page_num = canvas.getPageNumber()
            # canvas.drawRightString(150 * mm, 10 * mm, f"Page {page_num}")
            
            # Verified By line
            canvas.drawString(170 * mm, 10 * mm, "Verified By: ")
            canvas.restoreState()

    # Prepare story
    story = []

    if not df.empty:
        styles = getSampleStyleSheet()
        style_normal = styles['Normal']
        style_normal.fontSize = 7
        style_normal.leading = 8

        # Convert DataFrame to list of lists with Paragraphs for wrapping
        data = [df.columns.tolist()]
        col_count = len(df.columns)

        # Define which column should expand (e.g., index 2 = third column)
        EXPAND_COL_INDEX = 2  # Change this as needed (e.g., Description/UserID)

        # Estimate max width per column
        col_widths = []
        max_col_widths = [120*mm] * col_count  # Max possible width for each column

        for idx, col in enumerate(df.columns):
            max_text_width = max(
                canvas.Canvas('').stringWidth(str(val), 'Helvetica', 7)
                for val in df[col].astype(str).tolist()
            )
            col_widths.append(max(max_text_width + 10, 20*mm))

        # Adjust expanding column to take up remaining space
        fixed_width_sum = sum(col_widths[:EXPAND_COL_INDEX] + col_widths[EXPAND_COL_INDEX+1:])
        expand_col_width = max(30*mm, PAGE_SIZE[0] - LEFT - RIGHT - fixed_width_sum)
        col_widths[EXPAND_COL_INDEX] = expand_col_width

        # Wrap text in each cell using Paragraph
        for _, row in df.iterrows():
            wrapped_row = []
            for i, val in enumerate(row):
                if i == EXPAND_COL_INDEX:
                    wrapped_row.append(Paragraph(str(val), style_normal))
                else:
                    wrapped_row.append(str(val))
            data.append(wrapped_row)

        tbl = Table(data, repeatRows=1, colWidths=col_widths)
        tbl.setStyle(TableStyle([
            ('ALIGN', (0,0),(1,-1), 'CENTER'),
            ('ALIGN', (2,0),(2,-1), 'LEFT'),
            ('ALIGN', (3,0),(3,-1), 'CENTER'),
            ('FONTSIZE', (0,0),(-1,0), 9),
            ('FONTSIZE', (0,1),(-1,-1), 7),
            ('BACKGROUND', (0,0),(-1,0), colors.whitesmoke),
            ('TEXTCOLOR', (0,0),(-1,-1), colors.black),
            ('GRID', (0,0),(-1,-1), 0.5, colors.grey),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ]))
        story.append(tbl)

    doc = MyDoc(buffer,
                leftMargin=LEFT, rightMargin=RIGHT,
                topMargin=TOP, bottomMargin=BOTTOM)
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def show(databases):
    st.subheader("📘 Audit Report")

    # — date/time pickers —
    c1, c2 = st.columns(2)
    with c1:
        sd = st.date_input("Start Date", value=datetime.now(),  format="DD/MM/YYYY")
        # stime = st.time_input("Start Time", value=time(0,0))
        start_time_str = st.text_input("Start Time", value="00:00")
        try:
            stime = time(*map(int, start_time_str.split(':')))
        except:
            st.error("Please enter time in HH:MM format")
            stime = time(0, 0)
    with c2:
        ed = st.date_input("End Date", value=datetime.now(),  format="DD/MM/YYYY")
        # etime = st.time_input("End Time", value=time(23,59))
        end_time_str = st.text_input("End Time", value="23:59")
        try:
            etime = time(*map(int, end_time_str.split(':')))
        except:
            st.error("Please enter time in HH:MM format")
            etime = time(23, 59)

    start_dt = datetime.combine(sd, stime)
    end_dt   = datetime.combine(ed, etime)
    start_dt_utc = start_dt - timedelta(hours=5, minutes=30)
    end_dt_utc = end_dt - timedelta(hours=5, minutes=30)
    # interval = st.number_input("Time Interval (minutes)", min_value=1, value=10)
    
    if st.button("Generate Report"):
        with st.spinner("Fetching data from database..."):
            df = get_audit_data(start_dt_utc, end_dt_utc, databases)
        if df.empty:
            st.warning("No audit records found for that period.")
            return

        # st.dataframe(df, use_container_width=True)
        params = {
            "FROM DATE": start_dt.strftime('%d/%m/%Y %H:%M'),
            "TO DATE":   end_dt.strftime('%d/%m/%Y %H:%M'),
            "Printed By": get_latest_user(databases)
        }
        pdf = generate_audit_pdf_report(df, params)

        st.download_button(
            label="📥 Print Report",
            data=pdf,
            file_name=f"Audit_Report_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf"
        )
        if df.empty:
            st.warning("No audit records found for that period.")
            return

        # --- Style the DataFrame as HTML table with fixed column widths ---
        styled_html = df.to_html(index=False, classes='styled-table', escape=False)

        # Custom CSS to style the table
        st.markdown("""
        <style>
        .styled-table {
            width: 100%;
            border-collapse: collapse;
            font-family: Arial, sans-serif;
            background-color: white;
            margin-bottom: 20px;
        }

        .styled-table th, .styled-table td {
            border: 1px solid #ddd;
            padding: 8px;
            vertical-align: top;
        }

        .styled-table th {
            background-color: #f2f2f2;
            text-align: center;
            font-weight: bold;
        }

        .styled-table td:nth-child(1), 
        .styled-table td:nth-child(2) {
            white-space: nowrap;
            width: 120px; /* Date */
        }

        .styled-table td:nth-child(3), 
        .styled-table td:nth-child(4) {
            white-space: normal;
            word-wrap: break-word;
            max-width: 400px;
        }
        </style>
        """, unsafe_allow_html=True)

        # Display the styled HTML table
        st.markdown(styled_html, unsafe_allow_html=True)

