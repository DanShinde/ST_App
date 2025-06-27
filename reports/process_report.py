# reports/process_report.py
import base64
import pytz
import streamlit as st
import os
import pandas as pd
import pyodbc
from datetime import datetime, time
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter, A4, portrait
from reportlab.lib import colors
from io import BytesIO
from reportlab.lib.units import mm
    # --- Logo + Header in One Line ---
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, Image, TableStyle, Frame, PageTemplate, BaseDocTemplate, PageBreak
from reportlab.platypus.flowables import HRFlowable
from itertools import islice
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.enums import TA_CENTER
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# @st.cache_resource
# def get_db_connection():
#     from config import get_connection_string
#     conn_str = get_connection_string()
#     return pyodbc.connect(conn_str)

# @st.cache_data(ttl=3600)
def get_latest_user(config):
    try:
        conn = get_db_connection(config,'Audit')
        cursor = conn.cursor()
        query = """
        SELECT TOP (1)
            DATEADD(SECOND, 9900, TimeStmp) AS TimeStmp,
            UserID
        FROM AuditReport
        WHERE (UserID <> 'NT AUTHORITY\\NETWORK SERVICE') 
          AND (UserID <> 'N/A') 
          AND (UserID <> 'WORKGROUP\\WIN-U1DFOUPBRPI$') 
          AND (UserID <> 'WIN-U1DFOUPBRPI\\ADMIN') 
          AND (UserID <> 'FactoryTalk Service') 
          AND (UserID <> 'NT AUTHORITY\\LOCAL SERVICE') 
          AND (UserID <> 'NT AUTHORITY\\SYSTEM')
        ORDER BY TimeStmp DESC;
        """
        cursor.execute(query)
        result = cursor.fetchone()
        return result[1] if result else "[no user logged in]"
    except Exception as e:
        st.warning(f"Could not fetch user from AuditReport: {str(e)}")
        return "[no user logged in]"
    finally:
        conn.close()
        


# @st.cache_resource
def get_db_connection(config, db_name='Process'):
    db_config = config.get(db_name, {})
    
    if not db_config:
        raise ValueError(f"Database configuration for {db_name} not found")
    
    if db_config['authentication'].lower() == 'windows':
        conn_str = (
            f"Driver={{{db_config['driver']}}};"
            f"Server={db_config['server']};"
            f"Database={db_config['database']};"
            "Trusted_Connection=yes;"
        )
    else:
        conn_str = (
            f"Driver={{{db_config['driver']}}};"
            f"Server={db_config['server']};"
            f"Database={db_config['database']};"
            f"UID={db_config['username']};"
            f"PWD={db_config['password']};"
        )
    
    return pyodbc.connect(conn_str)



def get_tag_options(config):
    """
    Get available tag names (TagIndex 2–47) in the exact order
    used by get_report_data().
    """
    conn = get_db_connection(config=config, db_name='Process')
    query = """
    WITH TagList AS (
        SELECT  2 AS TagIndex,  'TT-102'   AS DisplayName UNION ALL
        SELECT  3,            'TT-103'   UNION ALL
        SELECT  4,            'TT-104'   UNION ALL
        SELECT  5,            'TT-105'   UNION ALL
        SELECT  6,            'TT-106'   UNION ALL
        SELECT  7,            'TT-107'   UNION ALL
        SELECT  8,            'TT-108'   UNION ALL
        SELECT  9,            'TT-109'   UNION ALL
        SELECT 10,            'TT-110'   UNION ALL
        SELECT 11,            'TT-111'   UNION ALL
        SELECT 12,            'TT-112'   UNION ALL
        SELECT 13,            'TT-113'   UNION ALL
        SELECT 14,            'TT-114'   UNION ALL
        SELECT 15,            'TT-130'   UNION ALL
        SELECT 16,            'TT-506'   UNION ALL
        SELECT 17,            'PT-118'   UNION ALL
        SELECT 18,            'PT-119'   UNION ALL
        SELECT 19,            'PT-120'   UNION ALL
        SELECT 20,            'PT-121'   UNION ALL
        SELECT 21,            'PT-122'   UNION ALL
        SELECT 22,            'PT-123'   UNION ALL
        SELECT 23,            'PT-124'   UNION ALL
        SELECT 24,            'PT-125'   UNION ALL
        SELECT 25,            'PT-128'   UNION ALL
        SELECT 26,            'TMF-101'  UNION ALL
        SELECT 27,            'TMF-102'  UNION ALL
        SELECT 28,            'TMF-103'  UNION ALL
        SELECT 29,            'TMF-104'  UNION ALL
        SELECT 30,            'TMF-105'  UNION ALL
        SELECT 31,            'TMF-106'  UNION ALL
        SELECT 32,            'TMF-107'  UNION ALL
        SELECT 33,            'TMF-108'  UNION ALL
        SELECT 34,            'MTR-101'  UNION ALL
        SELECT 35,            'MTR-102'  UNION ALL
        SELECT 36,            'MTR-103'  UNION ALL
        SELECT 37,            'MTR-104'  UNION ALL
        SELECT 38,            'MTR-105'  UNION ALL
        SELECT 39,            'MTR-106'  UNION ALL
        SELECT 40,            'MTR-107'  UNION ALL
        SELECT 41,            'MTR-108'  UNION ALL
        SELECT 42,            'MTR-109'  UNION ALL
        SELECT 43,            'RLT-101'  UNION ALL
        SELECT 44,            'MFM-101'  UNION ALL
        SELECT 45,            'pH-101'   UNION ALL
        SELECT 46,            'pH-102'   UNION ALL
        SELECT 47,            'OZ-101'
    )
    SELECT DisplayName
    FROM TagList
    ORDER BY TagIndex;
    """
    df = pd.read_sql(query, conn)
    return df



def get_report_data(start_datetime, end_datetime, selected_tags, batch_id=None, config=None):
    """Get report data by pivoting StringTable (Batch/User) and FloatTable (sensors) in SQL."""
    if not selected_tags:
        return pd.DataFrame()

    conn = get_db_connection(config=config, db_name='Process')

    # build the pivot-CTE SQL
    query = """
    WITH
      StringPivot AS (
        SELECT
          DateAndTime,
          MAX(CASE WHEN TagIndex = 1 THEN Val END) AS [Batch ID],
          MAX(CASE WHEN TagIndex = 0 THEN Val END) AS [User ID]
        FROM dbo.StringTable
        WHERE TagIndex IN (0,1)
        GROUP BY DateAndTime
      ),
      FloatPivot AS (
        SELECT
          DateAndTime,
          MAX(CASE WHEN TagIndex =  2 THEN Val END)  AS [TT-102],
          MAX(CASE WHEN TagIndex =  3 THEN Val END)  AS [TT-103],
          MAX(CASE WHEN TagIndex =  4 THEN Val END)  AS [TT-104],
          MAX(CASE WHEN TagIndex =  5 THEN Val END)  AS [TT-105],
          MAX(CASE WHEN TagIndex =  6 THEN Val END)  AS [TT-106],
          MAX(CASE WHEN TagIndex =  7 THEN Val END)  AS [TT-107],
          MAX(CASE WHEN TagIndex =  8 THEN Val END)  AS [TT-108],
          MAX(CASE WHEN TagIndex =  9 THEN Val END)  AS [TT-109],
          MAX(CASE WHEN TagIndex = 10 THEN Val END)  AS [TT-110],
          MAX(CASE WHEN TagIndex = 11 THEN Val END)  AS [TT-111],
          MAX(CASE WHEN TagIndex = 12 THEN Val END)  AS [TT-112],
          MAX(CASE WHEN TagIndex = 13 THEN Val END)  AS [TT-113],
          MAX(CASE WHEN TagIndex = 14 THEN Val END)  AS [TT-114],
          MAX(CASE WHEN TagIndex = 15 THEN Val END)  AS [TT-130],
          MAX(CASE WHEN TagIndex = 16 THEN Val END)  AS [TT-506],
          MAX(CASE WHEN TagIndex = 17 THEN Val END)  AS [PT-118],
          MAX(CASE WHEN TagIndex = 18 THEN Val END)  AS [PT-119],
          MAX(CASE WHEN TagIndex = 19 THEN Val END)  AS [PT-120],
          MAX(CASE WHEN TagIndex = 20 THEN Val END)  AS [PT-121],
          MAX(CASE WHEN TagIndex = 21 THEN Val END)  AS [PT-122],
          MAX(CASE WHEN TagIndex = 22 THEN Val END)  AS [PT-123],
          MAX(CASE WHEN TagIndex = 23 THEN Val END)  AS [PT-124],
          MAX(CASE WHEN TagIndex = 24 THEN Val END)  AS [PT-125],
          MAX(CASE WHEN TagIndex = 25 THEN Val END)  AS [PT-128],
          MAX(CASE WHEN TagIndex = 26 THEN Val END)  AS [TMF-101],
          MAX(CASE WHEN TagIndex = 27 THEN Val END)  AS [TMF-102],
          MAX(CASE WHEN TagIndex = 28 THEN Val END)  AS [TMF-103],
          MAX(CASE WHEN TagIndex = 29 THEN Val END)  AS [TMF-104],
          MAX(CASE WHEN TagIndex = 30 THEN Val END)  AS [TMF-105],
          MAX(CASE WHEN TagIndex = 31 THEN Val END)  AS [TMF-106],
          MAX(CASE WHEN TagIndex = 32 THEN Val END)  AS [TMF-107],
          MAX(CASE WHEN TagIndex = 33 THEN Val END)  AS [TMF-108],
          MAX(CASE WHEN TagIndex = 34 THEN Val END)  AS [MTR-101],
          MAX(CASE WHEN TagIndex = 35 THEN Val END)  AS [MTR-102],
          MAX(CASE WHEN TagIndex = 36 THEN Val END)  AS [MTR-103],
          MAX(CASE WHEN TagIndex = 37 THEN Val END)  AS [MTR-104],
          MAX(CASE WHEN TagIndex = 38 THEN Val END)  AS [MTR-105],
          MAX(CASE WHEN TagIndex = 39 THEN Val END)  AS [MTR-106],
          MAX(CASE WHEN TagIndex = 40 THEN Val END)  AS [MTR-107],
          MAX(CASE WHEN TagIndex = 41 THEN Val END)  AS [MTR-108],
          MAX(CASE WHEN TagIndex = 42 THEN Val END)  AS [MTR-109],
          MAX(CASE WHEN TagIndex = 43 THEN Val END)  AS [RLT-101],
          MAX(CASE WHEN TagIndex = 44 THEN Val END)  AS [MFM-101],
          MAX(CASE WHEN TagIndex = 45 THEN Val END)  AS [pH-101],
          MAX(CASE WHEN TagIndex = 46 THEN Val END)  AS [pH-102],
          MAX(CASE WHEN TagIndex = 47 THEN Val END)  AS [OZ-101]
        FROM dbo.FloatTable
        WHERE TagIndex BETWEEN 2 AND 47
        GROUP BY DateAndTime
      )
    SELECT
      s.DateAndTime,
      s.[Batch ID],
      s.[User ID],
      f.[TT-102], f.[TT-103], f.[TT-104], f.[TT-105],
      f.[TT-106], f.[TT-107], f.[TT-108], f.[TT-109],
      f.[TT-110], f.[TT-111], f.[TT-112], f.[TT-113],
      f.[TT-114], f.[TT-130], f.[TT-506],
      f.[PT-118], f.[PT-119], f.[PT-120], f.[PT-121],
      f.[PT-122], f.[PT-123], f.[PT-124], f.[PT-125],
      f.[PT-128],
      f.[TMF-101], f.[TMF-102], f.[TMF-103], f.[TMF-104],
      f.[TMF-105], f.[TMF-106], f.[TMF-107], f.[TMF-108],
      f.[MTR-101], f.[MTR-102], f.[MTR-103], f.[MTR-104],
      f.[MTR-105], f.[MTR-106], f.[MTR-107], f.[MTR-108],
      f.[MTR-109],
      f.[RLT-101], f.[MFM-101], f.[pH-101], f.[pH-102],
      f.[OZ-101]
    FROM StringPivot AS s
    INNER JOIN FloatPivot AS f
      ON s.DateAndTime = f.DateAndTime
    WHERE s.DateAndTime BETWEEN ? AND ?
    ORDER BY s.DateAndTime;
    """

    params = [ start_datetime, end_datetime ]
    # if batch_id:
    #     params.append(batch_id)

    df = pd.read_sql(query, conn, params=params)

    # now drop any columns the user didn’t select
    keep = ['DateAndTime', 'Batch ID', 'User ID'] + selected_tags
    df = df.loc[:, [c for c in keep if c in df.columns]]

    if not df.empty:
        df['DateAndTime'] = pd.to_datetime(df['DateAndTime'])
        df[['Date','Time']] = df['DateAndTime'].dt.strftime('%d-%m-%Y %H:%M').str.split(' ', expand=True)
        numeric = df.select_dtypes('number').columns
        # df[numeric] = df[numeric].round(2)
        # first round, then format each cell as a string with 2 decimals
        df[numeric] = (
            df[numeric]
            .round(2)
            .applymap(lambda x: f"{x:.2f}")
        )
    
    df = df.drop_duplicates(subset=['Date','Time'])
    return df




def generate_pdf_report(df, title="Process Data Report", params=None):
    buffer = BytesIO()

    # Define page size and margins
    PAGE_SIZE = A4
    LEFT_MARGIN = 10*mm
    RIGHT_MARGIN = 10*mm
    TOP_MARGIN = 50*mm  # Extra space for header
    BOTTOM_MARGIN = 20*mm

    class MyDocTemplate(BaseDocTemplate):
        def __init__(self, filename, **kwargs):
            BaseDocTemplate.__init__(self, filename, **kwargs)
            # Calculate available height for content
            content_height = self.pagesize[1] - TOP_MARGIN - BOTTOM_MARGIN

            # Create a frame that leaves space for header and footer
            frame = Frame(
                LEFT_MARGIN, BOTTOM_MARGIN,
                self.pagesize[0] - LEFT_MARGIN - RIGHT_MARGIN, content_height,
                leftPadding=0, rightPadding=0,
                bottomPadding=0, topPadding=0,
                id='normal'
            )

            # Create page template with header and footer functions
            template = PageTemplate(
                id='AllPages',
                frames=frame,
                onPage=self.header_footer
            )
            self.addPageTemplates([template])

        def header_footer(self, canvas, doc):
            self.header(canvas, doc)
            self.footer(canvas, doc)

        def header(self, canvas, doc):
            canvas.saveState()

            # First Row: Logo + Company Name
            # Logo on left
            try:
                logo = Image('alivus_logo.png', width=60, height=60)
                logo.drawOn(canvas, 15*mm, doc.pagesize[1] - 25*mm)
            except:
                pass

            # Company name centered
            canvas.setFont('Helvetica-Bold', 16)
            company_name = "ALIVUS LIFE SCIENCES LIMITED ANKLESHWAR"
            canvas.drawCentredString(doc.pagesize[0]/2, doc.pagesize[1] - 20*mm, company_name)
            #Report title centered
            canvas.drawCentredString(
                doc.pagesize[0]/2,
                doc.pagesize[1] - 32*mm,
                "Process Parameter Report"
            )
            # Second Row: Parameters
            if params:
                canvas.setFont('Helvetica', 9)
                y_pos = doc.pagesize[1] - 40*mm

                # Draw parameters
                param_items = [
                    ("FROM DATE:", params.get('FROM DATE', '')),
                    ("TO DATE:", params.get('TO DATE', '')),
                    ("BATCH ID:", params.get('BATCH ID', 'Not specified'))
                ]

                col_width = 50*mm
                right_col_x = doc.pagesize[0] - 20*mm - col_width

                for i, (label, value) in enumerate(param_items):
                    # if i < 2:  # First two items on left
                    #     x = 20*mm
                    #     y = y_pos - i*5*mm
                    # else:  # Last item on right
                    x = right_col_x + 10*mm
                    y = y_pos - (i-2)*5*mm 

                    canvas.drawString(x, y, f"{label} {value}")

            canvas.restoreState()

        def footer(self, canvas, doc):
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

    # Create the document
    doc = MyDocTemplate(
        buffer,
        pagesize=PAGE_SIZE,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN
    )

    # Prepare the story (content)
    story = []

    if not df.empty:
        # Remove BatchID and UserID from DataFrame
        fixed_columns = ['Date', 'Time']
        df = df[[col for col in df.columns if col in fixed_columns or col not in ['BatchID', 'UserID']]]

        # Round numeric values
        numeric_cols = df.select_dtypes(include=['number']).columns
        df[numeric_cols] = df[numeric_cols].round(2)

        # Build Table in chunks
        def chunk_list(lst, size):
            """Helper: Yield successive chunks of list"""
            it = iter(lst)
            return iter(lambda: list(islice(it, size)), [])

        data_cols = [col for col in df.columns if col not in fixed_columns]
        max_data_cols_per_page = 8  # Reduced to fit with header
        col_chunks = list(chunk_list(data_cols, max_data_cols_per_page))

        for i, cols in enumerate(col_chunks):
            cols_with_fixed = fixed_columns + cols
            sub_df = df[cols_with_fixed]

            # Prepare table data with units below column names
            styles = getSampleStyleSheet()
            styles["Normal"].alignment = TA_CENTER
            # Create a custom style for centered headers
            centered_header_style = ParagraphStyle(
                name='CenteredHeader',
                parent=styles['Normal'],
                alignment=TA_CENTER,  # Horizontal centering
                spaceBefore=0,        # Remove extra space before the paragraph
                spaceAfter=0          # Remove extra space after the paragraph
            )
            header = []
            for col in sub_df.columns:
                if 'TT' in col:  # Example logic to identify temperature columns
                # Combine column name and unit in a single cell °C
                    header.append(Paragraph(f"{col}<br/>{'(Deg.C)'}", style=styles["Normal"]))
                elif 'PT' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(Bar)", style=styles["Normal"]))
                elif 'TMF' in col:  # Example logic to identify flow columns
                    header.append(Paragraph(f"{col}<br/>(Kg/Hr)", style=styles["Normal"]))
                elif 'MTR' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(LPH)", style=styles["Normal"]))
                elif 'OZ' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(PPMV)", style=styles["Normal"]))
                elif 'RLT' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(%)", style=styles["Normal"]))
                elif 'MFM' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(LPH)", style=styles["Normal"]))
                elif 'PH' in col:  # Example logic to identify pressure columns
                    header.append(Paragraph(f"{col}<br/>(pH)", style=styles["Normal"]))
                else:
                    header.append(Paragraph(col, style=centered_header_style))

            # Add data rows
            data = [header] + sub_df.astype(str).values.tolist()

            # Build table
            table = Table(data, repeatRows=1)  # Repeat the header row
            style = TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),  # Center all content
                ('FONTSIZE', (0, 0), (-1, 0), 9),       # Larger font size for column names
                ('FONTSIZE', (0, 1), (-1, -1), 8),      # Normal font size for data rows
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),  # Center header row vertically
                ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),  # Background for header row
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),  # Text color
                ('GRID', (0, 0), (-1, -1), 1, colors.black),     # Grid lines
                ('BOX', (0, 0), (-1, -1), 1, colors.black),      # Outer border
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),  # Separator line after header
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),   # Background for data rows
            ])

            table.setStyle(style)
            story.append(table)


            if i < len(col_chunks) - 1:
                story.append(PageBreak())

    # Build the document
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes

class NumberedCanvas(Canvas):
    # your little template: you could even make this configurable
    page_template = "Page {page} of {nb}"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        # stash away everything about the page we’ve just finished
        self._saved_page_states.append(dict(self.__dict__))
        # start a fresh one
        self._startPage()

    def save(self):
        # now we know how many pages we actually made
        total_pages = len(self._saved_page_states)

        for state in self._saved_page_states:
            # restore that page’s state
            self.__dict__.update(state)
            # fill in the {page} and {nb}
            footer = self.page_template.format(
                page=self._pageNumber, 
                nb=total_pages
            )
            # draw it wherever you like
            self.setFont('Helvetica', 8)
            self.drawRightString(
                150 * mm,   # X-pos
                10 * mm,    # Y-pos
                footer
            )
            # and finally emit the page
            super().showPage()

        # all pages done, write out the file
        super().save()

def show_styled_table(df):
    print(df.head())
        # Remove 'DisplayName' column
    df_no_index = df.drop(columns=['DisplayName'], errors='ignore')
    df_no_index = df
    # Reset index to avoid showing internal IDs
    df_no_index = df_no_index.reset_index(drop=True)
    
    # Reorder columns if necessary
    cols = ['Date', 'Time'] + [col for col in df_no_index.columns if col not in ['Date', 'Time']]
    df_no_index = df_no_index[cols]
    
    # Convert DataFrame to HTML
    styled_html = df_no_index.to_html(index=False, classes='styled-table', escape=False)
    
    # Define CSS styling
    st.markdown("""
    <style>
    .styled-table {
        width: 100%;
        border-collapse: collapse;
        font-family: Arial, sans-serif;
        margin-bottom: 20px;
    }

    .styled-table th, .styled-table td {
        border: 1px solid #ddd;
        padding: 8px;
        vertical-align: top;
        text-align: center;
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
                
    /* Hide the first column (DisplayName) 
    .styled-table td:nth-child(1), 
    .styled-table th:nth-child(1) {
        display: none;
    } */
                
    /* Allow wrapping for long-text columns (e.g., MessageText or Value) */
    .styled-table td:nth-child(n+3) {
        white-space: normal;
        word-wrap: break-word;
        max-width: 400px;
    }
    </style>
    """, unsafe_allow_html=True)

    # Display the styled table
    st.markdown(styled_html, unsafe_allow_html=True)

def show(databases):
    st.subheader("📅 Process Report")

    date_col1, date_col2 = st.columns(2)
    with date_col1:
        start_date = st.date_input("Start Date", value=datetime.now(),  format="DD/MM/YYYY")

        # start_time = st.time_input("Start Time", value=time(0, 0))
        # start_time = st.time_input("Start Time", value=time(0, 0), key="start_time")
        start_time_str = st.text_input("Start Time", value="00:00")
        try:
            start_time = time(*map(int, start_time_str.split(':')))
        except:
            st.error("Please enter time in HH:MM format")
            start_time = time(0, 0)
    with date_col2:
        end_date = st.date_input("End Date", value=datetime.now(),  format="DD/MM/YYYY")
        
        # end_time = st.time_input("End Time", value=time(23, 59))
        end_time_str = st.text_input("End Time", value="23:59")
        try:
            end_time = time(*map(int, end_time_str.split(':')))
        except:
            st.error("Please enter time in HH:MM format")
            end_time = time(23, 59)

    start_datetime = datetime.combine(start_date, start_time)
    end_datetime = datetime.combine(end_date, end_time)

    tag_options = get_tag_options(config=databases)
    selected_tags = st.multiselect(
        "Select Tags",
        options=tag_options['DisplayName'].unique(),
        default=tag_options['DisplayName'].iloc[:3].tolist() if not tag_options.empty else []
    )

    batch_id = st.text_input("Batch ID ", value="")

    interval = st.number_input("Time Interval (minutes)", min_value=1, value=10)

    generate_btn = st.button("Generate Report", type="primary")


    if generate_btn and selected_tags and batch_id:
        with st.spinner("Fetching data from database..."):
            df = get_report_data(start_datetime, end_datetime, selected_tags, batch_id, config=databases)

        if not df.empty:
            # Apply sampling interval
            if interval >= 1:
                # Convert DateAndTime to datetime
                df['DateAndTime'] = pd.to_datetime(df['DateAndTime'], format='%d-%m-%Y %H:%M')

                # Split into Date and Time columns
                df['Date'] = df['DateAndTime'].dt.strftime('%d-%m-%Y')
                df['Time'] = df['DateAndTime'].dt.strftime('%H:%M')

                # Sampling based on time interval
                df = df[df['DateAndTime'].dt.minute % interval == 0]

                # Drop original DateAndTime and unnecessary columns
                df.drop(columns=['DateAndTime', 'Batch ID', 'User ID'], inplace=True, errors='ignore')
                # Reorder columns: Date first, Time second, then the rest
                cols = ['Date', 'Time'] + [col for col in df.columns if col not in ['Date', 'Time']]
                df = df[cols]


            st.success("Report data loaded successfully")
            # st.dataframe(df, use_container_width=True)
            report_params = {
                "FROM DATE": start_datetime.strftime('%d/%m/%Y %H:%M'),
                "TO DATE": end_datetime.strftime('%d/%m/%Y %H:%M'),
                "BATCH ID": batch_id or "Not specified",
                "TAGS SELECTED": ", ".join(selected_tags),
                "RECORD COUNT": len(df),
                "Printed By": get_latest_user(databases)
            }

            pdf = generate_pdf_report(df, params=report_params)
            # st.download_button(
            #     label="📥 Print Report",
            #     data=pdf,
            #     file_name=f"Process_Report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
            #     mime='application/pdf'
            # )
            df_no_index = df.reset_index(drop=True, inplace=False)
            
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
            # show_styled_table(df)
        else:
            st.warning("No data found for the selected parameters")
    elif batch_id == "":
        st.warning("Please enter a Batch ID")
    elif generate_btn:
        st.warning("Please select at least one tag")
