# reports/alarm_report.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Table, TableStyle, Image, PageBreak
)

# reuse your connection and canvas-numbering from process_report
from .process_report import get_db_connection, get_latest_user, NumberedCanvas

@st.cache_data(ttl=3600)
def get_alarm_data(start_dt, end_dt, config):
    """
    Fetch alarms between start_dt and end_dt.
    Returns a DataFrame with columns [Date, Time, Alarm].
    """
    conn = get_db_connection(config, db_name="Alarms")
    cursor = conn.cursor()
    query = """
    SELECT
      DATEADD(SS, 19800, EventTimeStamp) AS LocalTS,
      MessageText AS Alarm
    FROM View_1
    WHERE EventTimeStamp BETWEEN ? AND ?
      AND MessageText <> 'Alarm fault: Alarm input quality is bad'
      AND MessageText <> 'Alarm fault cleared: Alarm input quality is good'
    ORDER BY DATEADD(SS, 19800, EventTimeStamp)
    """
    cursor.execute(query, [start_dt, end_dt])
    rows = cursor.fetchall()
    cols = [col[0] for col in cursor.description]
    cursor.close()
    conn.close()

    df = pd.DataFrame.from_records(rows, columns=cols)
    if df.empty:
        return df

    # split into Date / Time
    df['LocalTS'] = pd.to_datetime(df['LocalTS'])
    df['Date'] = df['LocalTS'].dt.strftime('%d-%m-%Y')
    df['Time'] = df['LocalTS'].dt.strftime('%H:%M')
    return df[['Date', 'Time', 'Alarm']]

def generate_alarm_pdf_report(df, params):
    """
    Build a PDF:
      • Logo + company header
      • “Alarm Report” title + FROM/TO
      • Table with Date | Time | Alarm
      • Footer with Printed By, Printed Date, “Page X of Y”, Verified By
    """
    buffer = BytesIO()
    PAGE_SIZE = A4
    LEFT, RIGHT = 10*mm, 10*mm
    TOP, BOTTOM = 50*mm, 20*mm

    class MyDoc(BaseDocTemplate):
        def __init__(self, filename, **kw):
            super().__init__(filename, pagesize=PAGE_SIZE, **kw)
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
            # logo
            try:
                logo = Image('alivus_logo.png', width=60, height=60)
                logo.drawOn(canvas, 15*mm, doc.pagesize[1] - 25*mm)
            except:
                pass
            # company name
            canvas.setFont('Helvetica-Bold', 16)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 20*mm,
                "ALIVUS LIFE SCIENCES LIMITED ANKLESHWAR"
            )
            # report title
            canvas.setFont('Helvetica-Bold', 14)
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 32*mm,
                "Alarm Report"
            )
            # date parameters
            if params:
                canvas.setFont('Helvetica', 9)
                y0 = doc.pagesize[1] - 40*mm
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
            # Printed Date
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

    story = []
    if not df.empty:
        data = [df.columns.tolist()] + df.values.tolist()
        # three columns: Date(30mm), Time(20mm), Alarm(flex)
        tbl = Table(data, repeatRows=1, colWidths=[30*mm, 20*mm, None])
        tbl.setStyle(TableStyle([
            ('ALIGN', (0,0),(1,-1), 'CENTER'),
            ('ALIGN', (2,0),(2,-1), 'LEFT'),
            ('FONTSIZE', (0,0),(-1,0), 9),
            ('FONTSIZE', (0,1),(-1,-1), 7),
            ('BACKGROUND', (0,0),(-1,0), colors.whitesmoke),
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
    st.subheader("📢 Alarm Report")

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
        ed = st.date_input("End Date", value=datetime.now(), format="DD/MM/YYYY")
        # etime = st.time_input("End Time", value=time(23,59))
        end_time_str = st.text_input("End Time", value="23:59")
        try:
            etime = time(*map(int, end_time_str.split(':')))
        except:
            st.error("Please enter time in HH:MM format")
            etime = time(23, 59)

    start_dt = datetime.combine(sd, stime)
    end_dt   = datetime.combine(ed, etime)

    if st.button("Generate Report"):
        df = get_alarm_data(start_dt, end_dt, databases)
        if df.empty:
            st.warning("No alarms found for that period.")
            st.session_state.df = None
        else:
            st.session_state.df = df

    if 'df' in st.session_state and st.session_state.df is not None and not st.session_state.df.empty:
        params = {
            "FROM DATE": start_dt.strftime('%d/%m/%Y %H:%M'),
            "TO DATE": end_dt.strftime('%d/%m/%Y %H:%M'),
            "Printed By": get_latest_user(databases)
        }
        pdf = generate_alarm_pdf_report(st.session_state.df, params)
        
        st.download_button(
            label="📥 Print Report",
            data=pdf,
            file_name=f"alarm_report_{datetime.now():%Y%m%d_%H%M}.pdf",
            mime="application/pdf"
        )

    # Make only the table scrollable with fixed height
    if 'df' in st.session_state and st.session_state.df is not None:
        st.markdown(
            f"""
            <div style="height: 400px; overflow: auto; margin-top: 20px;">
                {st.session_state.df.to_html(index=False)}
            </div>
            """,
            unsafe_allow_html=True
        )