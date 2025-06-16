# reports/audit_report.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Table, TableStyle, PageBreak, Image
)

# reuse your connection, user-lookup, and canvas-numbering from process_report
from .process_report import get_db_connection, get_latest_user, NumberedCanvas

def get_audit_data(start_dt, end_dt, interval, config):
    """
    Fetch AuditReport entries between start_dt and end_dt,
    convert timestamp to IST, filter out system/service accounts,
    and apply row number-based interval filtering.
    """
    conn = get_db_connection(config, db_name="Audit")
    cursor = conn.cursor()

    # SQL Query with ROW_NUMBER() and interval filtering
    query = """
    SELECT 
        DATEADD(SECOND, 19800, TimeStmp) AS LocalTS,
        MessageText,
        UserID,
        UserFullName,
        Audience,
        MT.rownum
    FROM (
        SELECT 
            DATEADD(SECOND, 19800, TimeStmp) AS TimeStmp,
            MessageText,
            UserID,
            UserFullName,
            Audience,
            ROW_NUMBER() OVER (ORDER BY TimeStmp) AS rownum
        FROM AuditReport
        WHERE 
            TimeStmp BETWEEN ? AND ?
            AND UserID NOT IN (
                'NT AUTHORITY\\NETWORK SERVICE',
                'N/A',
                'WORKGROUP\\WIN-U1DFOUPBRPI$',
                'WIN-U1DFOUPBRPI\\ADMIN',
                'FactoryTalk Service',
                'NT AUTHORITY\\LOCAL SERVICE',
                'NT AUTHORITY\\SYSTEM'
            )
    ) MT
    WHERE 
        MT.rownum % ? = (CASE WHEN ? > 1 THEN 1 ELSE MT.rownum % ? END)
    ORDER BY TimeStmp
    """

    # Parameters: start_dt, end_dt, interval, interval, interval
    params = [start_dt, end_dt, interval, interval, interval]

    try:
        cursor.execute(query, params)
        cols = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        df = pd.DataFrame.from_records(rows, columns=cols)

        if not df.empty:
            # Convert LocalTS to datetime and split into Date/Time
            df['LocalTS'] = pd.to_datetime(df['LocalTS'])
            df['Date'] = df['LocalTS'].dt.strftime('%d-%m-%Y')
            df['Time'] = df['LocalTS'].dt.strftime('%H:%M')

            # Drop unnecessary columns
            df.drop(columns=['LocalTS', 'rownum'], inplace=True)

            return df[['Date', 'Time', 'MessageText', 'UserID']]
        else:
            return df

    finally:
        pass
    #     conn.close()

def generate_audit_pdf_report(df, params):
    """
    Build a PDF with:
      • Logo + company name
      • “Audit Report” title
      • FROM / TO date params
      • A four-column table
      • Footer with Printed By, Printed Date, Page X of Y, Verified By
    """
    buffer = BytesIO()

    # margins
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
            # — logo —
            try:
                logo = Image('alivus_logo.png', width=60, height=60)
                logo.drawOn(canvas, 15*mm, doc.pagesize[1] - 25*mm)
            except:
                pass

            # — company name —
            canvas.setFont('Helvetica-Bold', 16)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 20*mm,
                "ALIVUS LIFE SCIENCES LIMITED ANKLESHWAR"
            )

            # — report title —
            canvas.setFont('Helvetica-Bold', 14)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 32*mm,
                "Audit Report"
            )

            # — date params —
            if params:
                canvas.setFont('Helvetica', 9)
                y0 = doc.pagesize[1] -  40*mm
                canvas.drawString(
                    120*mm, y0,
                    f"FROM DATE: {params.get('FROM DATE','')}"
                )
                canvas.drawString(
                    120*mm, y0 - 5*mm,
                    f"TO DATE:   {params.get('TO DATE','')}"
                )

            canvas.restoreState()

        def _draw_footer(self, canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)

            # Printed By
            pb = params.get('Printed By', '[no user logged in]')
            canvas.drawString(20*mm, 10*mm, f"Printed By: {pb}")

            # Printed Date (center)
            pd_txt = datetime.now().strftime('%d/%m/%Y %H:%M')
            pd_w = canvas.stringWidth(f"Printed Date: {pd_txt}", 'Helvetica', 8)
            canvas.drawString(
                (doc.pagesize[0] - pd_w)/2,
                10*mm,
                f"Printed Date: {pd_txt}"
            )

            # Verified By
            canvas.drawString(170*mm, 10*mm, "Verified By:")

            canvas.restoreState()

    # assemble the story
    story = []
    if not df.empty:
        data = [df.columns.tolist()] + df.values.tolist()
        tbl = Table(data, repeatRows=1, colWidths=[30*mm, 20*mm, 100*mm, 30*mm])
        tbl.setStyle(TableStyle([
            ('ALIGN', (0,0),(1,-1), 'CENTER'),
            ('ALIGN', (2,0),(2,-1), 'LEFT'),
            ('ALIGN', (3,0),(3,-1), 'CENTER'),
            ('FONTSIZE', (0,0),(-1,0), 9),
            ('FONTSIZE', (0,1),(-1,-1), 7),
            ('BACKGROUND', (0,0),(-1,0), colors.whitesmoke),
            ('TEXTCOLOR', (0,0),(-1,-1), colors.black),
            ('GRID', (0,0),(-1,-1), 0.5, colors.grey),
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
    interval = st.number_input("Time Interval (minutes)", min_value=1, value=10)
    
    if st.button("Generate Report"):
        df = get_audit_data(start_dt, end_dt, interval, databases)
        if df.empty:
            st.warning("No audit records found for that period.")
            return

        # st.dataframe(df, use_container_width=True)
        st.table(df)
        params = {
            "FROM DATE": start_dt.strftime('%d/%m/%Y %H:%M'),
            "TO DATE":   end_dt.strftime('%d/%m/%Y %H:%M'),
            "Printed By": get_latest_user(databases)
        }
        pdf = generate_audit_pdf_report(df, params)

        st.download_button(
            label="📥 Print Report",
            data=pdf,
            file_name=f"audit_report_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf"
        )
