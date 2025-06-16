# reports/process_report.py
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



# @st.cache_resource
# def get_db_connection():
#     from config import get_connection_string
#     conn_str = get_connection_string()
#     return pyodbc.connect(conn_str)

@st.cache_data(ttl=3600)
def get_latest_user(config):
    try:
        conn = get_db_connection(config,'Audit')
        cursor = conn.cursor()
        query = """
        SELECT TOP (1)
            DATEADD(SECOND, 19800, TimeStmp) AS TimeStmp,
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
        


@st.cache_resource
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


@st.cache_data(ttl=3600)
def get_tag_options(config):
    conn = get_db_connection(config=config, db_name='Process')
    cursor = conn.cursor()
    query = """
    SELECT 
        TagIndex, 
        SUBSTRING(TagName, CHARINDEX(']', TagName) + 1, 
            CHARINDEX('.', TagName + '.') - CHARINDEX(']', TagName) - 1
        ) AS DisplayName
    FROM TagTable
    WHERE TagIndex NOT IN (0, 1)
    ORDER BY TagIndex
    """
    cursor.execute(query)
    columns = [column[0] for column in cursor.description]
    data = cursor.fetchall()
    return pd.DataFrame.from_records(data, columns=columns)


@st.cache_data
def get_report_data(start_datetime, end_datetime, selected_tags, batch_id=None, config=None):
    conn = get_db_connection(config=config)
    cursor = conn.cursor()

    tag_options = get_tag_options(config=config)
    tag_indices = tag_options[tag_options['DisplayName'].isin(selected_tags)]['TagIndex'].tolist()
    if not tag_indices:
        return pd.DataFrame()

    query = """
    SELECT 
        f.DateAndTime,
        t.TagIndex,
        SUBSTRING(t.TagName, CHARINDEX(']', t.TagName) + 1, 
            CHARINDEX('.', t.TagName + '.') - CHARINDEX(']', t.TagName) - 1) AS DisplayName,
        f.Val,
        s.BatchID,
        s.UserID
    FROM FloatTable f
    JOIN TagTable t ON f.TagIndex = t.TagIndex
    LEFT JOIN (
        SELECT DateAndTime,
               MAX(CASE WHEN TagIndex = 1 THEN Val END) AS BatchID,
               MAX(CASE WHEN TagIndex = 0 THEN Val END) AS UserID
        FROM StringTable
        WHERE TagIndex IN (0, 1)
        GROUP BY DateAndTime
    ) s ON f.DateAndTime = s.DateAndTime
    WHERE f.DateAndTime BETWEEN ? AND ?
    AND f.TagIndex IN ({})
    """.format(','.join(['?'] * len(tag_indices)))

    params = [start_datetime, end_datetime] + tag_indices

    # if batch_id:
    #     query += " AND s.BatchID = ?"
    #     params.append(batch_id)

    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]
    data = cursor.fetchall()
    df = pd.DataFrame.from_records(data, columns=columns)

    if not df.empty:
        df = df.pivot_table(
            index=['DateAndTime', 'BatchID', 'UserID'],
            columns='DisplayName',
            values='Val'
        ).reset_index()
        df['DateAndTime'] = df['DateAndTime'].dt.strftime('%d-%m-%Y %H:%M')

        # Round numeric values to 2 decimals
        numeric_cols = df.select_dtypes(include=['number']).columns
        for col in numeric_cols:
            df[col] = df[col].map(lambda x: f"{x:.2f}")
        # df[numeric_cols] = df[numeric_cols].round(2)

    return df


def generate_pdf_report(df, title="Process Data Report", params=None):
    buffer = BytesIO()
    
    # Define page size and margins
    PAGE_SIZE = A4
    LEFT_MARGIN = 10*mm
    RIGHT_MARGIN = 10*mm
    TOP_MARGIN = 50*mm  # Extra space for header
    BOTTOM_MARGIN = 20*mm
    
    # Create a custom document template
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
                    x = right_col_x
                    y = y_pos - (i-2)*5*mm
                    
                    canvas.drawString(x, y, f"{label} {value}")
            
            canvas.restoreState()
        
        def footer(self, canvas, doc):
            canvas.saveState()
            canvas.setFont('Helvetica', 8)
            canvas.setFillColor(colors.black)
            
            # Printed By
            printedBy = params.get('Printed By', '[no user logged in]') 
            canvas.drawString(20 * mm, 10 * mm, f"Printed By: {printedBy}")

            # Printed Date (centered)
            printed_date = datetime.now().strftime('%d/%m/%Y %H:%M')
            date_text_width = canvas.stringWidth(printed_date, 'Helvetica', 8)
            center_x = (doc.pagesize[0] / 2) - (date_text_width / 2) - 20 * mm
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
        fixed_columns = ['Date','Time']
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
        max_data_cols_per_page = 10  # Reduced to fit with header
        col_chunks = list(chunk_list(data_cols, max_data_cols_per_page))
        
        for i, cols in enumerate(col_chunks):
            cols_with_fixed = fixed_columns + cols
            sub_df = df[cols_with_fixed]
            
            # Prepare table data
            data = [sub_df.columns.tolist()] + sub_df.astype(str).values.tolist()
            
            # Build table
            table = Table(data, repeatRows=1)
            style = TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 7),
                ('BACKGROUND', (0, 0), (-1, 0), colors.whitesmoke),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BOX', (0, 0), (-1, -1), 1, colors.black),
                ('LINEBELOW', (0, 0), (-1, 0), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ])
            
            table.setStyle(style)
            story.append(table)
            
            if i < len(col_chunks) - 1:
                story.append(PageBreak())
    
    # Build the document
    # doc.build(story)
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

        # if not df.empty:
        #     # Apply sampling interval
        #     if interval > 1:
        #         df['datetime_obj'] = pd.to_datetime(df['DateAndTime'], format='%d-%m-%Y %H:%M')
        #         df['date'] = pd.to_datetime(df['datetime_obj'].dt.date)
        #         df = df[df['datetime_obj'].dt.minute % interval == 0].drop(columns=['datetime_obj'])
        #         df.drop(columns=['BatchID', 'UserID'], inplace=True)
        if not df.empty:
            # Apply sampling interval
            if interval > 1:
                # Convert DateAndTime to datetime
                df['DateAndTime'] = pd.to_datetime(df['DateAndTime'], format='%d-%m-%Y %H:%M')

                # Split into Date and Time columns
                df['Date'] = df['DateAndTime'].dt.strftime('%d-%m-%Y')
                df['Time'] = df['DateAndTime'].dt.strftime('%H:%M')

                # Sampling based on time interval
                df = df[df['DateAndTime'].dt.minute % interval == 0]

                # Drop original DateAndTime and unnecessary columns
                df.drop(columns=['DateAndTime', 'BatchID', 'UserID'], inplace=True, errors='ignore')
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

            pdf_bytes = generate_pdf_report(df, params=report_params)
            st.download_button(
                label="📥 Print Report",
                data=pdf_bytes,
                file_name=f"process_report_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                mime='application/pdf'
            )
            st.table(df)

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
        else:
            st.warning("No data found for the selected parameters")
    elif batch_id == "":
        st.warning("Please enter a Batch ID")
    elif generate_btn:
        st.warning("Please select at least one tag")

    