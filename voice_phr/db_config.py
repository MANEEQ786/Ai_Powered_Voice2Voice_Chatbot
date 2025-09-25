import pymssql
import logging
from dotenv import load_dotenv
import os
import json
import pandas as pd

load_dotenv()

info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')




class DBConnection:    
    @staticmethod
    def live_db():
        try:
            conn = pymssql.connect(
                user = DB_USER,
                password = DB_PASSWORD,
                host = DB_HOST,
                database = DB_NAME,
                autocommit = True,
            )
            cursor = conn.cursor()
            return conn, cursor
        except Exception as e:
            error_logger.error(f"DB Connection Error: {str(e)}")
            raise e
    
    @staticmethod 
    def db_disconnect(conn, cursor):        
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except Exception as e:
            error_logger.error(f"DB Disconnect Error: {str(e)}")
            raise e
        
class DBops:
    @staticmethod
    def update_demo(first_name, last_name, gender, address, city, state, zip, email_address, cell_phone, languages, patient_account):
        """
        Update patient demographics in the database
        """
        try:
            conn = None
            cursor = None
            try:
                conn, cursor = DBConnection.live_db()
                query = """
                    UPDATE Patient
                    SET
                        First_Name = %s,
                        Last_Name = %s,
                        Gender = %s,
                        Address = %s,
                        City = %s,
                        State = %s,
                        ZIP = %s,
                        Email_Address = %s,
                        cell_phone = %s,
                        languages = %s
                    WHERE
                        Patient_Account = %s
                """
                cursor.execute(query, (
                    first_name, last_name, gender, address, city, 
                    state, zip, email_address, cell_phone, languages, patient_account
                ))
                conn.commit()
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
            return True
        except Exception as e:
            error_logger.error(f"Error updating demographics: {str(e)}")
            return False
    
    @staticmethod
    def insert_chatbot_log(session_id, patient_account=None, chat_hist=None, agent=None, status=None,practice_code=None, appointment_id=None):
        conn = None
        cursor = None
        try:
            conn, cursor = DBConnection.live_db()
            
            if isinstance(chat_hist, dict):
                chat_hist = json.dumps(chat_hist)
                
            insert_query = """
            INSERT INTO AI_CHECKIN_LOGS (
                SESSION_ID,
                PATIENT_ACCOUNT,
                CHAT_HIST,
                AGENT,
                STATUS,
                PRACTICE_CODE,
                APPOINTMENT_ID
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, (session_id, patient_account, chat_hist, agent, status, practice_code, appointment_id))
            conn.commit()
            return True
        except pymssql.Error as e:
            error_logger.error(f"Error inserting chatbot log: {str(e)}")
            return False
        finally:
            DBConnection.db_disconnect(conn, cursor)

    @staticmethod
    def check_session_exists(session_id):
        conn = None
        cursor = None
        try:
            conn, cursor = DBConnection.live_db()
            query = """
            SELect 1 FROM AI_CHECKIN_LOGS WITH (NOLOCK, NOWAIT)
            WHERE SESSION_ID = %s
            """
            cursor.execute(query, (session_id,))
            count = cursor.fetchone()[0]
            return count > 0
        except pymssql.Error as e:
            error_logger.error(f"Error checking session: {str(e)}")
            return False
        finally:
            DBConnection.db_disconnect(conn, cursor)

    @staticmethod
    def execute_conversation_query(session_id):
        conn = None
        cursor = None
        try:
            conn, cursor = DBConnection.live_db()
            query = """
            SELECT CHAT_HIST 
            FROM AI_CHECKIN_LOGS WITH (NOLOCK, NOWAIT)
            WHERE SESSION_ID = %s
            ORDER BY CREATED_DATE
            """
            cursor.execute(query, (session_id,))
            rows = cursor.fetchall()
            
            conversation_history = []
            for row in rows:
                if row[0]:
                    try:
                        # Parse JSON from the chat history
                        chat_message = json.loads(row[0])
                        conversation_history.append(chat_message)
                    except json.JSONDecodeError:
                        # If not valid JSON, add as plain text
                        conversation_history.append({"role": "unknown", "content": row[0]})
            
            return conversation_history
        except Exception as e:
            error_logger.error(f"Error retrieving conversation: {str(e)}")
            return []
        finally:
            DBConnection.db_disconnect(conn, cursor)
            
    @staticmethod      
    def get_patient_account_for_session(session_id):
        """
        Get patient account for a given session ID from the database
        """
        try:
            conn = None
            cursor = None
            try:
                conn, cursor = DBConnection.live_db()
                query = """
                    SELECT TOP 1 PATIENT_ACCOUNT 
                    FROM AI_CHECKIN_LOGS 
                    WHERE SESSION_ID = %s AND PATIENT_ACCOUNT IS NOT NULL
                    ORDER BY CREATED_DATE ASC
                """
                cursor.execute(query, (session_id,))
                result = cursor.fetchone()
                return result[0] if result else None
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        except Exception as e:
            error_logger.error(f"Error getting patient account for session: {str(e)}")
            return None
        
    @staticmethod
    def get_patient_demographics(patient_account):
        try:
            conn = None
            cursor = None
            try:
                conn, cursor = DBConnection.live_db()
                query = """
                    SELECT 
                        First_Name,
                        Last_Name,
                        Gender,
                        Address,
                        City,
                        State,
                        ZIP,
                        Email_Address,
                        cell_phone,
                        languages,
                        practice_code
                    FROM Patient 
                    WHERE Patient_Account = %s
                """
                cursor.execute(query, (patient_account,))
                row = cursor.fetchone()
                if row:
                    # Map DB field names to expected field names
                    return {
                        "FIRSTNAME": row[0] or "",
                        "LASTNAME": row[1] or "",
                        "GENDER": row[2] or "",
                        "ADDRESS": row[3] or "",
                        "CITY": row[4] or "",
                        "STATE": row[5] or "",
                        "ZIP": row[6] or "",
                        "EMAIL_ADDRESS": row[7] or "",
                        "CELL_PHONE": row[8] or "",
                        "LANGUAGES": row[9] or "",
                        "PRACTICE_CODE": row[10] or ""
                    }
                return None
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        except Exception as e:
            error_logger.error(f"Error getting patient demographics: {str(e)}")
            return None
    
    @staticmethod
    def get_session_data(session_id):
        try:
            df=pd.DataFrame()
            query = """
            WITH LastFive AS (
                SELECT TOP 20 
                    CHAT_HIST,
                    CREATED_DATE,
                    PATIENT_ACCOUNT,
                    SESSION_ID,
                    AGENT,
                    PRACTICE_CODE,
                    APPOINTMENT_ID
                FROM AI_CHECKIN_LOGS WITH (NOLOCK, NOWAIT)
                WHERE session_id = %s
                ORDER BY CREATED_DATE DESC
            )
            SELECT 
                TOP 1 PATIENT_ACCOUNT, AGENT,PRACTICE_CODE, APPOINTMENT_ID,
                STUFF((
                    SELECT ', ' + CHAT_HIST
                    FROM LastFive
                    ORDER BY CREATED_DATE
                    FOR XML PATH(''), TYPE
                ).value('.', 'NVARCHAR(MAX)'), 1, 2, '') AS CHAT_HIST
            FROM LastFive;
            """
            conn,cursor = DBConnection.live_db()
            df = pd.read_sql(query, conn, params=[session_id])
            info_logger.info(f"dataframe for session_id {session_id}:\n{df}")
            return df
        except Exception as e:
            error_logger.error(f"Error getting session data: {str(e)}")
            return df
        finally:    
            DBConnection.db_disconnect(conn, cursor)
            
            
    @staticmethod
    def get_specility(appointment_id):
        """
        Get the specialty description for a given appointment ID from the database
        """
        try:
            conn = None
            cursor = None
            try:
                conn, cursor = DBConnection.live_db()
                query = """
                    SELECT tc.Description AS Provider_Specialty
                    FROM Appointments a
                    INNER JOIN providers p ON a.Provider_Code = p.Provider_Code
                    INNER JOIN Taxonomy_Codes tc ON p.Taxonomy_Code = tc.Taxonomy_Codes
                    WHERE a.Appointment_Id = %s
                """
                cursor.execute(query, (appointment_id,))
                result = cursor.fetchone()
                return result[0] if result else None
            finally:
                if cursor:
                    cursor.close()
                if conn:
                    conn.close()
        except Exception as e:
            error_logger.error(f"Error getting specialty for appointment: {str(e)}")
            return None
        
        
        