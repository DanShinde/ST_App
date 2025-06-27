# reports/alarm_report.py
import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate,
    Table, TableStyle, Image, PageBreak
)
import base64

# reuse your connection and canvas-numbering from process_report
from .process_report import get_db_connection, get_latest_user, NumberedCanvas

# @st.cache_data(ttl=3600)
def get_alarm_data(start_dt_utc, end_dt_utc, config):
    """
    Fetch alarms between UTC start_dt and end_dt.
    Returns a DataFrame with columns [Date, Time, Alarm, UTC_Time, IST_Time].
    """
    conn = get_db_connection(config, db_name="Alarms")
    
    query = """
    SELECT
      EventTimeStamp AS UTC_Time,
      MessageText AS Alarm
    FROM View_1
    WHERE EventTimeStamp BETWEEN ? AND ?
      AND MessageText <> 'Alarm fault: Alarm input quality is bad'
      AND MessageText <> 'Alarm fault cleared: Alarm input quality is good'
    ORDER BY EventTimeStamp
    """
    
    df = pd.read_sql_query(query, conn, params=[start_dt_utc, end_dt_utc])

    if df.empty:
        return df

    # Convert to proper datetime types
    df['UTC_Time'] = pd.to_datetime(df['UTC_Time'])
    
    # Convert UTC to IST (+5:30)
    df['IST_Time'] = df['UTC_Time'] + timedelta(hours=5, minutes=30)
    
    # Format for display
    df['Date'] = df['IST_Time'].dt.strftime('%d-%m-%Y')
    df['Time'] = df['IST_Time'].dt.strftime('%H:%M:%S')
    # Remove duplicates where Date, Time, and Alarm are identical
    df = df.drop_duplicates(subset=['Date', 'Time', 'Alarm'])
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
        sd = st.date_input("Start Date", value=datetime.now(), format="DD/MM/YYYY")
        start_time_str = st.text_input("Start Time", value="00:00")
        try:
            stime = time(*map(int, start_time_str.split(':')))
        except ValueError:
            st.error("Please enter time in HH:MM format")
            stime = time(0, 0)

    with c2:
        ed = st.date_input("End Date", value=datetime.now(), format="DD/MM/YYYY")
        end_time_str = st.text_input("End Time", value="23:59")
        try:
            etime = time(*map(int, end_time_str.split(':')))
        except ValueError:
            st.error("Please enter time in HH:MM format")
            etime = time(23, 59)

    start_dt = datetime.combine(sd, stime)
    end_dt = datetime.combine(ed, etime)
    start_dt_utc = start_dt - timedelta(hours=5, minutes=30)
    end_dt_utc = end_dt - timedelta(hours=5, minutes=30)
    if st.button("Generate Report"):
        # df = get_alarm_data(start_dt, end_dt, databases)
        with st.spinner("Fetching data from database..."):
            df = get_alarm_data(start_dt_utc, end_dt_utc, databases)
        if df.empty:
            st.warning("No alarms found for that period.")
        else:
            

            # Generate PDF and show download button
            params = {
                "FROM DATE": start_dt.strftime('%d/%m/%Y %H:%M'),
                "TO DATE": end_dt.strftime('%d/%m/%Y %H:%M'),
                "Printed By": get_latest_user(databases)
            }

            pdf = generate_alarm_pdf_report(df, params)

            # st.download_button(
            #     label="📥 Print Report",
            #     data=pdf,
            #     file_name=f"Alarm_Report_{datetime.now():%Y%m%d_%H%M}.pdf",
            #     mime="application/pdf"
            # )
            
            # Encode the PDF to base64 so it can be rendered in HTML
            pdf_b64 = base64.b64encode(pdf).decode()

            # Inject HTML + JS to display and auto-print the PDF
            st.markdown(f"""
                <style>
                    .pdf-container {{
                        width: 100%;
                        height: 80vh;
                        border: none;
                    }}
                </style>
                <h4>📄 Previewing Report </h4>
                <iframe class="pdf-container" 
                        src="data:application/pdf;base64,{pdf_b64}" 
                        type="application/pdf"
                        onload="this.contentWindow.print();">
                </iframe>
            """, unsafe_allow_html=True)

            # --- Style the DataFrame as HTML table ---
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

            /* Fixed width and no wrap for Date & Time */
            .styled-table td:nth-child(1), 
            .styled-table td:nth-child(2) {
                white-space: nowrap;
                width: 120px;
            }

            /* Allow wrapping for Description and other long-text columns */
            .styled-table td:nth-child(4) {
                white-space: normal;
                word-wrap: break-word;
                max-width: 400px;
            }
            </style>
            """, unsafe_allow_html=True)

            # Display the styled HTML table
            # st.markdown(styled_html, unsafe_allow_html=True)