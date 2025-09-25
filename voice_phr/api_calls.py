import logging
import requests
import json
import uuid
from voice_phr.utils.custom_exception import ApplicationException
from typing import TypedDict, List, Dict, Any, Tuple

info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')

CHECKIN_API_TOKEN = ('Bxxbh!W-cNm_T&N-RJ7$6h6u64Hx@Uc#2%$YQwq6VLfjmj=Rg-!4M9hHDpQKdby+')

class DemographicsService:
    
    @staticmethod
    def process_demographics_data(request_data: dict, uid: str) -> dict:
        CHECKIN_API_URL = ('https://checkinapiqa.gobreeze.com/api/checkinform/GetPatientAgainst_Name_DOB_APT')
        required = [
            'PATIENT_ACCOUNT',
            'APPOINTMENT_ID',
            'DOB',
            'FIRST_NAME',
            'LAST_NAME',
            'PRACTICE_CODE'
        ]
        missing = [f for f in required if not request_data.get(f)]
        if missing:
            error_logger.error(f'{uid} | Missing inputs: {missing}')
            raise ApplicationException(
                detail=f"Missing required fields: {', '.join(missing)}",
                code=400
            )

        api_payload = {
            "PATIENT_ACCOUNT": request_data["PATIENT_ACCOUNT"],
            "APPOINTMENT_ID": request_data["APPOINTMENT_ID"],
            "DOB": request_data["DOB"], 
            "FIRST_NAME": request_data["FIRST_NAME"],
            "LAST_NAME": request_data["LAST_NAME"],
            "PRACTICE_CODE": request_data["PRACTICE_CODE"]
        }

        pretty = json.dumps(api_payload, indent=4)
        info_logger.info(f'{uid} | Outbound payload:\n{pretty}')

        headers = {
                    'token': f"{CHECKIN_API_TOKEN}",
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                    }

        try:
            resp = requests.post(
                CHECKIN_API_URL,
                headers=headers,
                json=api_payload,
                timeout=30,
                verify=False,
                allow_redirects=False 
            )
            info_logger.info(f"{uid} | Final URL after redirect: {resp.url}")
            info_logger.info(f"{uid} | Response status code: {resp.status_code}")
            info_logger.info(f"{uid} | Response headers: {resp.headers}")
            info_logger.info(f"{uid} | Response content: {resp.text}")

            try:
                data = resp.json()
            except ValueError as e:
                raise ApplicationException(
                    detail="Invalid payload format from check-in API",
                    code=502
                )
        except Exception as e:
            error_logger.error(f'{uid} | Check-in API call failed: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient data",
                code=500
            )

        payload = data.get('RESPONSE')
        if not isinstance(payload, list) or not payload:
            error_logger.error(f'{uid} | Invalid or empty RESPONSE: {data}')
            raise ApplicationException(
                detail="Invalid payload format from check-in API",
                code=500
            )
        patient = payload[0]

        clean_demographics = {
                "PATIENT_ACCOUNT": request_data.get("PATIENT_ACCOUNT"),
                "PRACTICE_CODE": request_data.get("PRACTICE_CODE"), 
                "APPOINTMENT_ID": patient.get("APPOINTMENT_ID"),
                "FIRSTNAME": patient.get('FIRSTNAME'),
                "LASTNAME": patient.get('LASTNAME'),
                "GENDER": patient.get('GENDER'),
                "ADDRESS": patient.get('ADDRESS'),
                "ZIP": patient.get('ZIP'),
                "CITY": patient.get('CITY'),
                "STATE": patient.get('STATE').strip(),
                "LANGUAGES": patient.get('LANGUAGES'),
                "EMAIL_ADDRESS": patient.get('EMAIL_ADDRESS'),
                "CELL_PHONE": patient.get('CELL_PHONE')
            }
        
        info_logger.info(f'{uid} | Clean demographics ready')
        info_logger.info(f'{uid} | Clean demographics: {json.dumps(clean_demographics, indent=4)}')
        info_logger.debug(f'{uid} | Clean demographics: {json.dumps(clean_demographics, indent=4)}')
        return clean_demographics

class Allergies:
    LOGIN_URL = "https://qa-webservices.mtbc.com/SmartTALKPHR/api/Auth/Login"
    ALLERGIES_URL = "https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Allergies/GetPatientAllergies"
    DELETE_ALLERGY_URL = "https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Allergies/DeleteAllergy"
    SAVE_ALLERGY_URL = "https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Allergies/SavePatientAllergies"
    
    
    @staticmethod
    def get_patient_allergies(patient_account: str, practice_code: str, uid: str) -> dict:
        """
        Fetch and clean patient allergies data
        Args:
            patient_account: Patient's account number
            practice_code: Practice code for the patient
            uid: Unique identifier for logging
        Returns:
            dict: Cleaned allergies data
        """
        try:
            # Validate inputs
            if not practice_code:
                error_logger.error(f"{uid} | Missing practice code")
                raise ApplicationException(detail="Practice code is required", code=400)
            
            if not patient_account:
                error_logger.error(f"{uid} | Missing patient account")
                raise ApplicationException(detail="Patient account is required", code=400)

            # Login payload
            login_payload = {
                "CELLPHONE": "",
                "DOB": "",
                "LASTNAME": "",
                "loginType": "user credentials",
                "password": "2211ba1417311ee6a901f819a3116ab511386a5ca4d9c44d18cd2134634736cf3e23c9338171fa64aa9adc556be989cee970c35a5f95d35f08d856ff746b1aee",
                "timezone": "",
                "userName": "carecloud.mobile.team@gmail.com"
            }
            
            info_logger.debug(f"{uid} | Attempting login with payload: {json.dumps(login_payload)}")
            
            # Get access token
            try:
                login_response = requests.post(
                    Allergies.LOGIN_URL,
                    json=login_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10,
                    verify=False
                )
                login_response.raise_for_status()
                token_data = login_response.json()
                
                if token_data.get('statusCode') != 200:
                    error_logger.error(f"{uid} | Auth failed with status: {token_data.get('statusCode')}")
                    raise ApplicationException(
                        detail=f"Authentication failed: {token_data.get('message', 'Unknown error')}",
                        code=401
                    )
                
                access_token = token_data['data']['accessTokenResponse']['accessToken']
                info_logger.debug(f"{uid} | Successfully obtained access token")
                
            except requests.RequestException as e:
                error_logger.error(f"{uid} | Login failed: {str(e)}")
                raise ApplicationException(
                    detail="Failed to authenticate with server",
                    code=401
                )

            # Get allergies with token
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            # Ensure proper format for query parameters
            params = {
                'PracticeCode': str(practice_code).strip(),  # Ensure string and remove whitespace
                'PatientAccount': str(patient_account).strip()  # Ensure string and remove whitespace
            }
            
            info_logger.debug(f"{uid} | Requesting allergies with params: {params}")
            
            try:
                allergies_response = requests.get(
                    Allergies.ALLERGIES_URL,
                    headers=headers,
                    params=params,
                    timeout=10,
                    verify=False
                )
                
                # Log the actual URL being called
                info_logger.debug(f"{uid} | Request URL: {allergies_response.url}")
                
                if allergies_response.status_code != 200:
                    error_logger.error(
                        f"{uid} | Allergies API failed with status {allergies_response.status_code}. "
                        f"Response: {allergies_response.text}"
                    )
                    raise ApplicationException(
                        detail=f"Failed to fetch allergies data: {allergies_response.text}",
                        code=allergies_response.status_code
                    )
                
                allergies_data = allergies_response.json()
                
                if allergies_data.get('statusCode') != 200:
                    error_logger.error(f"{uid} | API returned error: {allergies_data}")
                    raise ApplicationException(
                        detail=f"Failed to fetch allergies: {allergies_data.get('message', 'Unknown error')}",
                        code=502
                    )
                
                info_logger.debug(f"{uid} | Successfully fetched allergies data")
                
            except requests.RequestException as e:
                error_logger.error(
                    f"{uid} | Failed to fetch allergies: {str(e)}\n"
                    f"URL: {Allergies.ALLERGIES_URL}\n"
                    f"Params: {params}"
                )
                raise ApplicationException(
                    detail="Failed to fetch allergies data",
                    code=502
                )

            # Clean and return allergies data
            clean_allergies = {
                "patientAllergies": [
                    {
                        "allergyDescription": allergy.get("allergyDescription", ""),
                        "allergySeverity": allergy.get("allergySeverity", ""),
                        "allergyReactionDescription": allergy.get("allergyReactionDescription", ""),
                        "patientAllergyId": allergy.get("patientAllergyId", "")
                    }
                    for allergy in allergies_data.get("data", {}).get("patientAllergies", [])
                    
                ]
            }
            
            info_logger.info(f"{uid} | Clean allergies data prepared")
            info_logger.info(f"{uid} | Clean allergies: {json.dumps(clean_allergies, indent=4)}")
            
            return clean_allergies

        except Exception as e:
            error_logger.error(f"{uid} | Error in get_patient_allergies: {str(e)}")
            raise
    
    @staticmethod
    def delete_patient_allergy(patient_account: str, practice_code: str, allergy_id: str, uid: str) -> dict:
        try:
            # Get auth token
            login_payload = {
                "CELLPHONE": "",
                "DOB": "",
                "LASTNAME": "",
                "loginType": "user credentials",
                "password": "2211ba1417311ee6a901f819a3116ab511386a5ca4d9c44d18cd2134634736cf3e23c9338171fa64aa9adc556be989cee970c35a5f95d35f08d856ff746b1aee",
                "timezone": "",
                "userName": "carecloud.mobile.team@gmail.com"
            }
            login_response = requests.post(
                Allergies.LOGIN_URL,
                json=login_payload,
                headers={'Content-Type': 'application/json'},
                timeout=10,
                verify=False
            )
            login_response.raise_for_status()
            token_data = login_response.json()
            access_token = token_data['data']['accessTokenResponse']['accessToken']

            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "practiceCode": practice_code,
                "patientAccount": patient_account,
                "allergyId": allergy_id,
                "deleted": True,
                "modifiedBy": patient_account  
            }
            info_logger.info(f"{uid} | ALLERGY API: Delete payload: {json.dumps(payload)}")

            response = requests.post(
                Allergies.DELETE_ALLERGY_URL,
                headers=headers,
                json=payload,
                timeout=10,
                verify=False
            )
            response.raise_for_status()
            result = response.json()
            if result.get("statusCode") == 200:
                info_logger.info(f"{uid} | ALLERGY API: Successfully deleted allergy {allergy_id}")
                return {"success": True, "message": "Allergy deleted"}
            else:
                error_logger.error(f"{uid} | ALLERGY API: Delete failed: {result.get('message', 'Unknown error')}")
                return {"success": False, "message": result.get("message", "Failed to delete allergy")}
        except Exception as e:
            error_logger.error(f"{uid} | ALLERGY API: Exception during delete: {str(e)}")
            return {"success": False, "message": str(e)}
    
    @staticmethod
    def search_allergy(practice_code: str, allergy_query: str, uid: str) -> dict:
        try:
            url = "https://smartsearch.mtbc.com/api/Allergies/GetAllergiesIncludingFreeText"
            params = {
                "PracticeCode": practice_code,
                "allergyCategory": "MEDICINE",  
                "query": allergy_query
            }
            info_logger.info(f"{uid} | SMARTSEARCH ALLERGY API: Request params: {json.dumps(params)}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            result = response.json()
            docs = result.get("response", {}).get("docs", [])
            clean_allergies = [
                {
                    "ALLERGY_CODE": doc.get("ALLERGY_CODE", ""),
                    "DESCRIPTION": doc.get("DESCRIPTION", ""),
                    "Allergy_type_id": doc.get("Allergy_type_id", "")
                }
                for doc in docs
            ]
            info_logger.info(f"{uid} | SMARTSEARCH ALLERGY API: Found {len(clean_allergies)} allergies for query '{allergy_query}'")
            return {
                "success": True,
                "allergies": clean_allergies
            }
        except Exception as e:
            error_logger.error(f"{uid} | SMARTSEARCH ALLERGY API: Exception during search: {str(e)}")
            return {
                "success": False,
                "allergies": [],
                "message": str(e)
            }

    
    @staticmethod
    def save_patient_allergy(patient_account: str, practice_code: str, allergy_code: str, 
                           allergy_name: str, severity: str, reaction: str, allergy_type_id: str = "2", uid: str = None) -> dict:

        if not uid:
            uid = str(uuid.uuid4())
            
        try:
            # Validate inputs
            if not practice_code:
                error_logger.error(f"{uid} | Missing practice code")
                return {"success": False, "message": "Practice code is required"}
            
            if not patient_account:
                error_logger.error(f"{uid} | Missing patient account")
                return {"success": False, "message": "Patient account is required"}
                
            if not allergy_code:
                error_logger.error(f"{uid} | Missing allergy code")
                return {"success": False, "message": "Allergy code is required"}
                
            if not allergy_name:
                error_logger.error(f"{uid} | Missing allergy name")
                return {"success": False, "message": "Allergy name is required"}

            # Login payload
            login_payload = {
                "CELLPHONE": "",
                "DOB": "",
                "LASTNAME": "",
                "loginType": "user credentials",
                "password": "2211ba1417311ee6a901f819a3116ab511386a5ca4d9c44d18cd2134634736cf3e23c9338171fa64aa9adc556be989cee970c35a5f95d35f08d856ff746b1aee",
                "timezone": "",
                "userName": "carecloud.mobile.team@gmail.com"
            }
            
            info_logger.debug(f"{uid} | Attempting login for save allergy")
            
            # Get access token
            try:
                login_response = requests.post(
                    Allergies.LOGIN_URL,
                    json=login_payload,
                    headers={'Content-Type': 'application/json'},
                    timeout=10,
                    verify=False
                )
                login_response.raise_for_status()
                token_data = login_response.json()
                
                if token_data.get('statusCode') != 200:
                    error_logger.error(f"{uid} | Login failed: {token_data}")
                    return {"success": False, "message": "Failed to authenticate"}
                
                access_token = token_data['data']['accessTokenResponse']['accessToken']
                info_logger.debug(f"{uid} | Successfully obtained access token for save allergy")
                
            except requests.RequestException as e:
                error_logger.error(f"{uid} | Login failed: {str(e)}")
                return {"success": False, "message": "Failed to authenticate with server"}

            # Prepare save allergy payload
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            # Map severity to severity ID
            severity_mapping = {
                "Unknown": "1",
                "Mild": "2", 
                "Mild to Moderate": "3",
                "Moderate": "4",
                "Moderate to severe": "5",
                "Severe": "6",
                "Fatal": "7"
            }
            
            severity_id = severity_mapping.get(severity, "1")  # Default to Unknown if not found
            
            save_payload = {
                "allergyCode": allergy_code,
                "allergyDescription": allergy_name,
                "allergyId": "",
                "allergyReactions": [],
                "allergySeverityId": severity_id,
                "allergyTyepIdUnSnomed": "",  # Note: API has typo "Tyep"
                "allergyTypeId": allergy_type_id,
                "comments": "",
                "endDate": "",
                "ipAddress": "",
                "language": "en",
                "patientAccount": patient_account,
                "practiceCode": practice_code,
                "reactionDescription": reaction,
                "reactionId": "",
                "startDate": "",
                "validUserID": ""
            }
            
            info_logger.info(f"{uid} | SAVE ALLERGY API: Save payload: {json.dumps(save_payload, indent=2)}")
            
            try:
                save_response = requests.post(
                    Allergies.SAVE_ALLERGY_URL,
                    headers=headers,
                    json=save_payload,
                    timeout=10,
                    verify=False
                )
                
                info_logger.info(f"{uid} | SAVE ALLERGY API: Response status: {save_response.status_code}")
                info_logger.info(f"{uid} | SAVE ALLERGY API: Response content: {save_response.text}")
                
                save_response.raise_for_status()
                result = save_response.json()
                
                if result.get("statusCode") == 200:
                    info_logger.info(f"{uid} | SAVE ALLERGY API: Successfully saved allergy {allergy_name}")
                    return {
                        "success": True,
                        "message": f"Successfully added {allergy_name} allergy",
                        "allergy_name": allergy_name,
                        "severity": severity,
                        "reaction": reaction
                    }
                else:
                    error_message = result.get("message", "Unknown error")
                    error_logger.error(f"{uid} | SAVE ALLERGY API: Save failed: {error_message}")
                    return {"success": False, "message": f"Failed to save allergy: {error_message}"}
                
            except requests.RequestException as e:
                error_logger.error(f"{uid} | SAVE ALLERGY API: Request failed: {str(e)}")
                return {"success": False, "message": "Failed to save allergy"}

        except Exception as e:
            error_logger.error(f"{uid} | SAVE ALLERGY API: Exception during save: {str(e)}")
            return {"success": False, "message": str(e)}
        
class MedicationService:

    AUTH_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Auth/Login'
    MEDICATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Medication/GetPatientMedications'
    DELETE_MEDICATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Medication/DeleteMedicine'
    SEARCH_MEDICATION_API_URL = 'https://live-webservices.mtbc.com/Talklive/api/Medication/GetMedicineByName'
    SEARCH_AUTH_API_URL = 'https://live-webservices.mtbc.com/Talklive/api/Authentication/GetToken'
    SEARCH_DIAGNOSIS_API_URL = 'https://smartsearch.mtbc.com/api/talkEHRICDsTenNineSnomedForDoctors/PickICDsTenNineSnomedForDoctors'
    SAVE_MEDICATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Medication/SaveMedicine'

    @staticmethod
    def get_auth_token(uid: str) -> str:
        payload = {
            "CELLPHONE": "",
            "DOB": "",
            "LASTNAME": "",
            "loginType": "user credentials",
            "password": "2211ba1417311ee6a901f819a3116ab511386a5ca4d9c44d18cd2134634736cf3e23c9338171fa64aa9adc556be989cee970c35a5f95d35f08d856ff746b1aee",
            "timezone": "",
            "userName": "carecloud.mobile.team@gmail.com"
        }
        
        info_logger.debug(f'{uid} | AUTH API: Request payload: {json.dumps(payload, indent=4)}')
                
        headers = {
            'Content-Type': 'application/json-patch+json',
            'accept': '*/*'
        }
        
        try:           
            response = requests.post(
                MedicationService.AUTH_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            info_logger.info(f'{uid} | MEDICATION API: Auth response status code: {response.status_code}')
            response.raise_for_status()
            auth_data = response.json()
        
            token = None
            
            if (auth_data.get('statusCode') == 200 and 
                'data' in auth_data and 
                'accessTokenResponse' in auth_data['data'] and 
                'accessToken' in auth_data['data']['accessTokenResponse']):
                
                token = auth_data['data']['accessTokenResponse']['accessToken']
                
            else:
                
                error_logger.error(f'{uid} | MEDICATION API: Could not find accessToken in expected location')
            
            if not token:
                error_logger.error(f'{uid} | MEDICATION API: Auth token not found in response')
                raise ApplicationException(
                    detail="Failed to retrieve auth token",
                    code=502
                )
                
            info_logger.info(f'{uid} | MEDICATION API: Successfully retrieved auth token')
            return token
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | MEDICATION API: Auth API call failed with status {getattr(e.response, "status_code", "No status")}')
            error_logger.exception(f'{uid} | MEDICATION API: Auth failure details: {str(e)}')
            raise ApplicationException(
                detail="Failed to authenticate with medication API",
                code=502
            )
    
    @staticmethod
    def get_patient_medications(patient_account,practice_code,uid) -> list:
        
        if not patient_account:
            error_logger.error(f'{uid} | MEDICATION API: Missing PATIENT_ACCOUNT')
            raise ApplicationException(
                detail="Missing PATIENT_ACCOUNT",
                code=400
            )
        if not practice_code:   
            error_logger.error(f'{uid} | MEDICATION API: Missing PRACTICE_CODE')
            raise ApplicationException(
                detail="Missing PRACTICE_CODE",
                code=400
            )
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}          
            params = {'PracticeCode': practice_code, 'PatientAccount': patient_account}
            # Print get_patient_medications params
            info_logger.debug(f'{uid} | MEDICATION API: Request parameters: {json.dumps(params, indent=4)}')
            # print(f"Get Medications API Parameters: {json.dumps(params, indent=4)}")
            
            response = requests.get(
                MedicationService.MEDICATION_API_URL,
                headers=headers,
                params=params,
                timeout=10)           
            response.raise_for_status()
            med_data = response.json()
            
            if not med_data:
                error_logger.error(f'{uid} | MEDICATION API: Empty response received')
                raise ApplicationException(
                    detail="Empty response from medication API",
                    code=502
                )    
            if med_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | MEDICATION API: Non-200 status in response body: {med_data.get("statusCode")}')
                error_logger.error(f'{uid} | MEDICATION API: Error message: {med_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {med_data.get('message', 'Unknown error')}",
                    code=502
                )
            medications = med_data.get('data', {}).get('getPatientMedicationsList', [])
            
            filtered_meds = []
            for med in medications:
                filtered_meds.append({
                    'medication_name': med.get('medicineName', ''),
                    'intake': med.get('sig', ''),
                    'diagnosis': med.get('diagnosis', ''),
                    'added_by': med.get('addedBy', ''),
                    'patient_prescription_id': med.get('patientPrescriptionId', ''),
                    'unitCode': med.get('unitCode', ''),
                    'diagCode': med.get('diagCode', '')
                })
            
            info_logger.info(f'{uid} | MEDICATION API: Successfully retrieved {len(filtered_meds)} medications for patient')
            if not filtered_meds:
                info_logger.info(f'{uid} | MEDICATION API: Patient has no medications on record')
            else:
                info_logger.debug(f'{uid} | MEDICATION API: First medication: {filtered_meds[0].get("medication_name", "N/A")}')
            # print(f"Filtered_data_fro_get_medication_api: {filtered_meds}")
            return filtered_meds
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | MEDICATION API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | MEDICATION API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | MEDICATION API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | MEDICATION API: Failed to fetch patient medications: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient medications",
                code=502
            )

    @staticmethod
    def get_search_auth_token(uid: str) -> str:
        payload = {
            "ApplicationName": "string",
            "Password": "b3oVyTw7Dhkfas3GxFI6npfWXs0DL8oN2C5WWgcEz/M=",
            "UserName": "RxEpServices"
        }
        
        info_logger.debug(f'{uid} | SEARCH AUTH API: Request payload: {json.dumps(payload, indent=4)}')
                
        headers = {
            'Content-Type': 'application/json',
            'accept': '*/*'
        }
        
        try:           
            response = requests.post(
                MedicationService.SEARCH_AUTH_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            info_logger.info(f'{uid} | MEDICATION SEARCH API: Auth response status code: {response.status_code}')
            response.raise_for_status()
            auth_data = response.json()
            
            # Log the complete response for debugging
            info_logger.debug(f'{uid} | MEDICATION SEARCH API: Auth response: {json.dumps(auth_data)}')
            
            # The token is in 'access_token', not 'token'
            token = auth_data.get('access_token')
            
            if not token:
                error_logger.error(f'{uid} | MEDICATION SEARCH API: Auth token not found in response')
                raise ApplicationException(
                    detail="Failed to retrieve search auth token",
                    code=502
                )
                
            info_logger.info(f'{uid} | MEDICATION SEARCH API: Successfully retrieved auth token')
            return token
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | MEDICATION SEARCH API: Auth API call failed with status {getattr(e.response, "status_code", "No status")}')
            error_logger.exception(f'{uid} | MEDICATION SEARCH API: Auth failure details: {str(e)}')
            raise ApplicationException(
                detail="Failed to authenticate with medication search API",
                code=502
            )
    
    @staticmethod
    def search_medication(medication_name: str, practice_code: str, provider_code: str = "53481719", uid: str = None) -> dict:

        if not uid:
            uid = str(uuid.uuid4())
            
        if not medication_name or len(medication_name.strip()) < 2:
            error_logger.error(f'{uid} | MEDICATION SEARCH API: Medication search query too short: "{medication_name}"')
            return {'success': False, 'message': 'Search query must be at least 2 characters', 'medications': []}
            
        if not practice_code:
            error_logger.error(f'{uid} | MEDICATION SEARCH API: Missing PRACTICE_CODE')
            return {'success': False, 'message': 'Missing PRACTICE_CODE', 'medications': []}
            
        try:
            token = MedicationService.get_search_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            payload = {
                "Medicine_Name": medication_name,
                "Practice_code": practice_code,
                "Provider_code": provider_code
            }
            
            info_logger.info(f'{uid} | MEDICATION SEARCH API: Search payload: {json.dumps(payload, indent=4)}')
            response = requests.post(
                MedicationService.SEARCH_MEDICATION_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if not result:
                error_logger.error(f'{uid} | MEDICATION SEARCH API: Empty response received')
                return {'success': False, 'message': 'No response from medication search API', 'medications': []}
            info_logger.info(f'{uid} | MEDICATION SEARCH API: Result type: {type(result).__name__}')
            medications = result if isinstance(result, list) else []
            
            if not medications:
                info_logger.info(f'{uid} | MEDICATION SEARCH API: No medications found for query "{medication_name}"')
                return {
                    'success': True,
                    'message': f'No medications found matching "{medication_name}"',
                    'medications': []
                }
                
            formatted_medications = []
            for idx, med in enumerate(medications):
                formatted_med = {
                    'medication_id': med.get('medicine_code', '').strip(),
                    'medication_name': med.get('medicine_trade', '').strip(),
                    'generic_description': med.get('generic_description', '').strip(),
                    'controlled': med.get('Controlled', False),
                    'generic': med.get('GENERIC', 'N') == 'Y',
                    'status': med.get('STATUS', '').strip(),
                    'dea': med.get('DEA', '').strip(),
                    'index': idx + 1  
                }
                
                info_logger.info(f'{uid} | MEDICATION SEARCH RESULT #{idx+1}: Name: {formatted_med["medication_name"]}, ID: {formatted_med["medication_id"]}')
                
                formatted_medications.append(formatted_med)
                
            info_logger.info(f'{uid} | MEDICATION SEARCH API: Found {len(formatted_medications)} medications matching "{medication_name}"')
            
            return {
                'success': True,
                'message': f'Found {len(formatted_medications)} medications matching "{medication_name}"',
                'medications': formatted_medications
            }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | MEDICATION SEARCH API: Request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | MEDICATION SEARCH API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | MEDICATION SEARCH API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {
                'success': False,
                'message': 'Failed to search for medications',
                'medications': []
            }
    
    @staticmethod
    def delete_medication(patient_account: str, practice_code: str, medication_query: str, 
                        medications_data: list, uid: str) -> dict:
        if not medications_data:
            error_logger.error(f'{uid} | MEDICATION API: No medications data available')
            return {'success': False, 'message': 'No medication data available'}
            
    
        if not isinstance(medications_data, list):
            error_logger.error(f'{uid} | MEDICATION API: medications_data is not a list: {type(medications_data)}')
            return {'success': False, 'message': 'Invalid medications data format'}
        
        info_logger.info(f'{uid} | MEDICATION API: Searching for medication matching "{medication_query}"')

        matched_med = None
        for med in medications_data:
            if not isinstance(med, dict):
                continue
                
            med_name = med.get('medication_name', '')
            if med_name and (medication_query.lower() in med_name.lower() or med_name.lower() in medication_query.lower()):
                matched_med = med
                info_logger.info(f'{uid} | MEDICATION API: Found match: {med_name}')
                break
        
        # If no match found
        if not matched_med:
            error_logger.info(f'{uid} | MEDICATION API: No medication match found for "{medication_query}"')
            return {'success': False, 'message': f'No medication matching "{medication_query}" found'}
            
        # Extract patient_prescription_id safely
        patient_prescription_id = matched_med.get('patient_prescription_id')
        if not patient_prescription_id:
            error_logger.error(f'{uid} | MEDICATION API: Missing patient_prescription_id for matched medication')
            return {'success': False, 'message': 'Missing required ID for medication deletion'}
        
        # Get auth token and prepare for deletion
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}
            payload = {
                'PatientAccount': patient_account,
                'PatientPrescriptionId': patient_prescription_id,
                'PracticeCode': practice_code
            }
            
            # Log payload at INFO level for better visibility
            info_logger.info(f'{uid} | MEDICATION API: Delete payload: {json.dumps(payload, indent=4)}')
            
            # Make the delete request
            response = requests.post(
                MedicationService.DELETE_MEDICATION_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | MEDICATION API: Successfully deleted medication: {matched_med.get("medication_name")}')
                return {
                    'success': True, 
                    'message': f'Successfully removed {matched_med.get("medication_name")}'
                }
            else:
                error_logger.error(f'{uid} | MEDICATION API: Delete failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to delete medication')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | MEDICATION API: Delete request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to complete deletion request'}
        
    @staticmethod
    def search_diagnosis(query: str, patient_account: str, practice_code: str, uid: str) -> dict:
        """
        Search for diagnosis codes matching the given query
        
        Args:
            query: Search term for diagnosis
            patient_account: Patient's account number
            practice_code: Practice code
            uid: Unique identifier for logging
            
        Returns:
            dict: Dictionary containing diagnosis search results with success flag
        """
        if not uid:
            uid = str(uuid.uuid4())
            
        if not query or len(query.strip()) < 2:
            error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Diagnosis search query too short: "{query}"')
            return {
                'success': False, 
                'message': 'Search query must be at least 2 characters', 
                'diagnoses': []
            }
            
        if not practice_code:
            error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Missing PRACTICE_CODE')
            return {'success': False, 'message': 'Missing PRACTICE_CODE', 'diagnoses': []}
            
        if not patient_account:
            error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Missing PATIENT_ACCOUNT')
            return {'success': False, 'message': 'Missing PATIENT_ACCOUNT', 'diagnoses': []}
            
        try:
            headers = {
                'Content-Type': 'application/json'
            }
            
            payload = {
                "EndTo": "19",
                "PaginationSize": "20",
                "PatientAccount": patient_account,
                "PracticeCode": practice_code,
                "Query": query
            }
            
            info_logger.info(f'{uid} | DIAGNOSIS SEARCH API: Search payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                MedicationService.SEARCH_DIAGNOSIS_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if not result:
                error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Empty response received')
                return {'success': False, 'message': 'No response from diagnosis search API', 'diagnoses': []}
            
            # Extract diagnoses data from response
            diagnoses_data = result.get('docs', [])
            
            if not diagnoses_data:
                info_logger.info(f'{uid} | DIAGNOSIS SEARCH API: No diagnoses found for query "{query}"')
                return {
                    'success': True,
                    'message': f'No diagnoses found matching "{query}"',
                    'diagnoses': []
                }
                
            formatted_diagnoses = []
            for idx, diag in enumerate(diagnoses_data):
                formatted_diag = {
                    'diagnosis_code': diag.get('ICD10_CODE', '').strip(),
                    'diagnosis_description': diag.get('ICD10_DESCRIPTION', '').strip(),
                    'index': idx + 1
                }
                
                info_logger.info(f'{uid} | DIAGNOSIS SEARCH RESULT #{idx+1}: Code: {formatted_diag["diagnosis_code"]}, Description: {formatted_diag["diagnosis_description"]}')
                formatted_diagnoses.append(formatted_diag)
                
            num_found = result.get('numFound', '0')
            info_logger.info(f'{uid} | DIAGNOSIS SEARCH API: Found {num_found} diagnoses matching "{query}"')
            
            return {
                'success': True,
                'message': f'Found {num_found} diagnoses matching "{query}"',
                'diagnoses': formatted_diagnoses
            }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | DIAGNOSIS SEARCH API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {
                'success': False,
                'message': 'Failed to search for diagnoses',
                'diagnoses': []
            }
    
    @staticmethod
    def save_medication(patient_account: str, practice_code: str, medicine_code: str, 
                      medicine_name: str, sig: str, diag_code: str, uid: str) -> dict:
        """
        Save a new medication to the patient's record
        
        Args:
            patient_account: Patient's account number
            practice_code: Practice code
            medicine_code: Medication code from search results
            medicine_name: Medication name
            sig: Medication instructions/dosage
            diag_code: Diagnosis code (ICD10)
            uid: Unique identifier for logging
            
        Returns:
            dict: Dictionary containing success flag and message
        """
        if not patient_account:
            error_logger.error(f'{uid} | SAVE MEDICATION API: Missing PATIENT_ACCOUNT')
            return {'success': False, 'message': 'Missing PATIENT_ACCOUNT'}
            
        if not practice_code:
            error_logger.error(f'{uid} | SAVE MEDICATION API: Missing PRACTICE_CODE')
            return {'success': False, 'message': 'Missing PRACTICE_CODE'}
            
        if not medicine_code:
            error_logger.error(f'{uid} | SAVE MEDICATION API: Missing medicine_code')
            return {'success': False, 'message': 'Missing medication code'}
            
        if not medicine_name:
            error_logger.error(f'{uid} | SAVE MEDICATION API: Missing medicine_name')
            return {'success': False, 'message': 'Missing medication name'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            payload = {
                "diagCode": diag_code or "",
                "ipAddress": "",
                "language": "en",
                "medicineCode": medicine_code,
                "medicineName": medicine_name,
                "patientAccount": patient_account,
                "practiceCode": practice_code,
                "prescriptionId": "",
                "sig": sig or "",
                "unitCode": ""
            }
            
            info_logger.info(f'{uid} | SAVE MEDICATION API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                MedicationService.SAVE_MEDICATION_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE MEDICATION API: Successfully saved medication: {medicine_name}')
                return {
                    'success': True, 
                    'message': f'Successfully added {medicine_name}'
                }
            else:
                error_logger.error(f'{uid} | SAVE MEDICATION API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to save medication')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE MEDICATION API: Save request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SAVE MEDICATION API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SAVE MEDICATION API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete save request'}


class PharmaciesService:

    PHARMACIES_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Demographics/GetPatientPharmaciesInfo'
    UPDATE_PHARMACY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/AddUpdatePharmacy'
    SEARCH_PHARMACY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Demographics/SearchPatientPharmacy'
    

    @staticmethod
    def get_patient_pharmacies(patient_account,practice_code,uid) -> list:
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'} 
            params = {'PracticeCode': practice_code, 'PatientAccount': patient_account}
            
            # Print get_patient_pharmacies params
            info_logger.debug(f'{uid} | PHARMACIES API: Request parameters: {json.dumps(params, indent=4)}')

            response = requests.get(
                PharmaciesService.PHARMACIES_API_URL,
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()
            pharm_data = response.json()
            if not pharm_data:
                error_logger.error(f'{uid} | PHARMACIES API: Empty response received')
                raise ApplicationException(
                    detail="Empty response from pharmacies API",
                    code=502
                )
            
            if pharm_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | PHARMACIES API: Non-200 status in response body: {pharm_data.get("statusCode")}')
                error_logger.error(f'{uid} | PHARMACIES API: Error message: {pharm_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {pharm_data.get('message', 'Unknown error')}",
                    code=502
                )

            # Safely extract pharmacies data, handling possible nested structure
            data = pharm_data.get('data', {})
            pharmacies = data.get('pharmacies', []) if isinstance(data, dict) else data
            
            if not isinstance(pharmacies, list):
                error_logger.error(f'{uid} | PHARMACIES API: Expected list of pharmacies but got {type(pharmacies)}')
                pharmacies = []
            
            # Process and filter pharmacies data to include only relevant fields
            filtered_pharmacies = []
            for pharm in pharmacies:
                if not isinstance(pharm, dict):
                    error_logger.warning(f'{uid} | PHARMACIES API: Invalid pharmacy data format: {pharm}')
                    continue
                
                # Log available keys in the pharmacy data to help with debugging
                if len(filtered_pharmacies) == 0:
                    info_logger.debug(f'{uid} | PHARMACIES API: First pharmacy keys: {list(pharm.keys())}')
                    info_logger.debug(f'{uid} | PHARMACIES API: First pharmacy data: {json.dumps(pharm, indent=2)}')
                    
                filtered_pharmacies.append({
                    'pharmacy_name'   : pharm.get('pharmacY_NAME', '').strip(),
                    'pharmacy_phone'  : pharm.get('pharmacY_PHONE', '').strip(),
                    'pharmacy_fax'    : pharm.get('pharmacY_FAX',   '').strip(),
                    'pharmacy_address': pharm.get('pharmacY_ADDRESS','').strip(),
                    'pharmacy_id': (
                        pharm.get('pharmacY_CODE')    
                        or pharm.get('PHARMACY_CODE')
                        or ''             
                    ).strip()
                })
            
            info_logger.info(f'{uid} | PHARMACIES API: Successfully retrieved {len(filtered_pharmacies)} pharmacies for patient')
            if not filtered_pharmacies:
                info_logger.info(f'{uid} | PHARMACIES API: Patient has no pharmacies on record')
            else:
                info_logger.debug(f'{uid} | PHARMACIES API: First pharmacy: {filtered_pharmacies[0].get("pharmacy_name", "N/A")}')
            
            return filtered_pharmacies
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PHARMACIES API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | PHARMACIES API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | PHARMACIES API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | PHARMACIES API: Failed to fetch patient pharmacies: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient pharmacies",
                code=502
            )        

    @staticmethod
    def delete_pharmacy(patient_account: str, practice_code: str, pharmacy_query: str, 
                        pharmacy_data: list, uid: str) -> dict:
        if not pharmacy_data:
            error_logger.error(f'{uid} | PHARMACY API: No pharmacy data available')
            return {'success': False, 'message': 'No pharmacy data available'}
            
        if not isinstance(pharmacy_data, list):
            error_logger.error(f'{uid} | PHARMACY API: pharmacy_data is not a list: {type(pharmacy_data)}')
            return {'success': False, 'message': 'Invalid pharmacy data format'}
        
        info_logger.info(f'{uid} | PHARMACY API: Searching for pharmacy matching "{pharmacy_query}"')

        matched_pharmacy = None
        for pharmacy in pharmacy_data:
            if not isinstance(pharmacy, dict):
                continue
                
            pharmacy_name = pharmacy.get('pharmacy_name', '')
            if pharmacy_name and (pharmacy_query.lower() in pharmacy_name.lower() or pharmacy_name.lower() in pharmacy_query.lower()):
                matched_pharmacy = pharmacy
                info_logger.info(f'{uid} | PHARMACY API: Found match: {pharmacy_name}')
                break
        
        # If no match found
        if not matched_pharmacy:
            # Log available pharmacies for debugging
            pharmacy_names = [p.get('pharmacy_name', 'Unknown') for p in pharmacy_data if isinstance(p, dict)]
            error_logger.info(f'{uid} | PHARMACY API: No pharmacy match found for "{pharmacy_query}". Available pharmacies: {pharmacy_names}')
            return {'success': False, 'message': f'No pharmacy matching "{pharmacy_query}" found. Available pharmacies: {", ".join(pharmacy_names) if pharmacy_names else "None"}'}
            
        pharmacy_id = (
            matched_pharmacy.get('pharmacy_id'))
    
        
        if not pharmacy_id:
            error_logger.error(f'{uid} | PHARMACY API: Missing pharmacy_id for matched pharmacy')
            return {'success': False, 'message': 'Missing required ID for pharmacy deletion'}
        
        # Get auth token and prepare for deletion
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}
            
            payload = {
                'app_source': 'TBI',
                'patient_account': patient_account,
                'practice_code': practice_code,
                'pharmacy_id': '', 
                'pharmacy2_id': '',       
                'pharmacy3_id': ''        
            }
            
            all_pharmacy_ids = []
            
            # First, collect all pharmacy IDs
            for pharm in pharmacy_data:
                if not isinstance(pharm, dict):
                    continue
            
                pharm_id = (
                    pharm.get('pharmacy_id'))
                
                if pharm_id:
                    all_pharmacy_ids.append(pharm_id)
            
            # The pharmacy to delete will have empty string as its ID
            for i, pharm_id in enumerate(all_pharmacy_ids):
                if i > 2:  # We only have fields for up to 3 pharmacies
                    info_logger.warning(f'{uid} | PHARMACY API: More than 3 pharmacies found. Only first 3 will be processed.')
                    break
                    
                field_name = f'pharmacy_id' if i == 0 else f'pharmacy{i+1}_id'
                
                if pharm_id == pharmacy_id:
                    payload[field_name] = ''  # This is the pharmacy to delete
                else:
                    payload[field_name] = pharm_id
            
            info_logger.info(f'{uid} | PHARMACY API: Pharmacy to delete name: {matched_pharmacy.get("pharmacy_name", "Unknown")}')
            info_logger.info(f'{uid} | PHARMACY API: Delete payload: {json.dumps(payload, indent=4)}')
            
            # Make the delete request
            response = requests.post(
                PharmaciesService.UPDATE_PHARMACY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            # Log the raw response for debugging
            info_logger.info(f'{uid} | PHARMACY API: Response status code: {response.status_code}')
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | PHARMACY API: Successfully deleted pharmacy: {matched_pharmacy.get("pharmacy_name")}')
                return {
                    'success': True, 
                    'message': f'Successfully removed {matched_pharmacy.get("pharmacy_name")}',
                    'deleted_pharmacy': matched_pharmacy
                }
            else:
                error_logger.error(f'{uid} | PHARMACY API: Delete failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to delete pharmacy')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PHARMACY API: Delete request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to complete deletion request'}
            
    @staticmethod
    def search_pharmacy(patient_account: str, pharmacy_query: str, uid: str) -> dict:

        if not patient_account:
            error_logger.error(f'{uid} | PHARMACY SEARCH API: Missing PATIENT_ACCOUNT')
            return {'success': False, 'message': 'Missing PATIENT_ACCOUNT', 'pharmacies': []}
        
        if not pharmacy_query or len(pharmacy_query.strip()) < 2:
            error_logger.error(f'{uid} | PHARMACY SEARCH API: Pharmacy search query too short: "{pharmacy_query}"')
            return {'success': False, 'message': 'Search query must be at least 2 characters', 'pharmacies': []}
            
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json'
            }
            
            # Build the search payload
            payload = {
                "patientAccount": patient_account,
                "pharmacyAddress": "",
                "pharmacyCity": "",
                "pharmacyFax": "",
                "pharmacyName": pharmacy_query,
                "pharmacyPhone": "",
                "pharmacyState": "",
                "pharmacyTopRecord": "5",
                "pharmacyZip": ""
            }
            
            info_logger.info(f'{uid} | PHARMACY SEARCH API: Search payload: {json.dumps(payload, indent=4)}')
            
            # Make the search request
            response = requests.post(
                PharmaciesService.SEARCH_PHARMACY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if not result:
                error_logger.error(f'{uid} | PHARMACY SEARCH API: Empty response received')
                return {'success': False, 'message': 'No response from pharmacy search API', 'pharmacies': []}
                
            if result.get('statusCode') != 200:
                error_logger.error(f'{uid} | PHARMACY SEARCH API: Non-200 status in response body: {result.get("statusCode")}')
                error_logger.error(f'{uid} | PHARMACY SEARCH API: Error message: {result.get("message", "No message")}')
                return {
                    'success': False, 
                    'message': f"API error: {result.get('message', 'Unknown error')}",
                    'pharmacies': []
                }
                
            # Extract pharmacy data
            pharmacies = result.get('data', [])
            
            if not pharmacies:
                info_logger.info(f'{uid} | PHARMACY SEARCH API: No pharmacies found for query "{pharmacy_query}"')
                return {
                    'success': True,
                    'message': f'No pharmacies found matching "{pharmacy_query}"',
                    'pharmacies': []
                }
                
                # Process the pharmacy data into a consistent format
            formatted_pharmacies = []
            for idx, pharm in enumerate(pharmacies):
                pharmacy_id = pharm.get('pharmacyCode', '').strip()
                pharmacy_name = pharm.get('pharmacyName', '').strip()
                
                formatted_pharmacy = {
                    'pharmacy_id': pharmacy_id,
                    'pharmacy_name': pharmacy_name,
                    'pharmacy_address': pharm.get('pharmacyAddress', '').strip(),
                    'pharmacy_city': pharm.get('pharmacyCity', '').strip(),
                    'pharmacy_state': pharm.get('pharmacyState', '').strip(),
                    'pharmacy_zip': pharm.get('pharmacyZip', '').strip(),
                    'pharmacy_phone': pharm.get('pharmacyPhone', '').strip(),
                    'pharmacy_fax': pharm.get('pharmacyFax', '').strip(),
                    'index': idx + 1,  # Add a 1-based index for easy reference
                    'pharmacyCode': pharmacy_id  # Also keep the original key for reference
                }
                
                # Log each pharmacy for debugging
                info_logger.info(f'{uid} | PHARMACY SEARCH RESULT #{idx+1}: Name: {pharmacy_name}, ID: {pharmacy_id}')
                
                formatted_pharmacies.append(formatted_pharmacy)
                
            info_logger.info(f'{uid} | PHARMACY SEARCH API: Found {len(formatted_pharmacies)} pharmacies matching "{pharmacy_query}"')
            
            return {
                'success': True,
                'message': f'Found {len(formatted_pharmacies)} pharmacies matching "{pharmacy_query}"',
                'pharmacies': formatted_pharmacies
            }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PHARMACY SEARCH API: Request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | PHARMACY SEARCH API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | PHARMACY SEARCH API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {
                'success': False,
                'message': 'Failed to search for pharmacies',
                'pharmacies': []
            }
    
    @staticmethod
    def add_pharmacy(patient_account: str, practice_code: str, pharmacy_id: str, current_pharmacies: list, uid: str) -> dict:

        if not patient_account:
            error_logger.error(f'{uid} | PHARMACY ADD API: Missing PATIENT_ACCOUNT')
            return {'success': False, 'message': 'Missing PATIENT_ACCOUNT'}
            
        if not practice_code:
            error_logger.error(f'{uid} | PHARMACY ADD API: Missing PRACTICE_CODE')
            return {'success': False, 'message': 'Missing PRACTICE_CODE'}
            
        # Validate pharmacy ID
        if not pharmacy_id or pharmacy_id.strip() == '':
            error_logger.error(f'{uid} | PHARMACY ADD API: Missing or empty PHARMACY_ID')
            return {'success': False, 'message': 'Missing or invalid pharmacy ID'}
        
        # Sanitize pharmacy_id by trimming any whitespace
        pharmacy_id = pharmacy_id.strip()
        
        # Log the pharmacy ID we're about to add
        info_logger.info(f'{uid} | PHARMACY ADD API: Adding pharmacy with ID: {pharmacy_id}')
            
        if not isinstance(current_pharmacies, list):
            error_logger.warning(f'{uid} | PHARMACY ADD API: Invalid current_pharmacies format. Using empty list.')
            current_pharmacies = []
            
        # Check if we already have 3 pharmacies (system maximum)
        if len(current_pharmacies) >= 3:
            error_logger.warning(f'{uid} | PHARMACY ADD API: Patient already has maximum number of pharmacies (3)')
            return {
                'success': False,
                'message': 'You already have the maximum number of pharmacies (3). Please delete one before adding a new one.'
            }
            
        # Collect existing pharmacy IDs
        pharmacy_ids = []
        for pharm in current_pharmacies:
            if isinstance(pharm, dict):
                pharm_id = pharm.get('pharmacy_id')
                if pharm_id:
                    pharmacy_ids.append(pharm_id)
                    
                    # Check if this pharmacy is already added - compare as strings to avoid type mismatches
                    if str(pharm_id).strip() == str(pharmacy_id).strip():
                        error_logger.info(f'{uid} | PHARMACY ADD API: Pharmacy {pharmacy_id} already exists for patient')
                        return {
                            'success': False,
                            'message': f'This pharmacy is already in your profile.'
                        }
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}
            
            # Prepare the payload for adding the pharmacy
            payload = {
                'app_source': 'TBI',
                'patient_account': patient_account,
                'practice_code': practice_code,
                'pharmacy_id': '', 
                'pharmacy2_id': '',       
                'pharmacy3_id': ''        
            }
            
            # Add existing pharmacy IDs to payload
            for i, existing_id in enumerate(pharmacy_ids):
                field_name = f'pharmacy_id' if i == 0 else f'pharmacy{i+1}_id'
                payload[field_name] = existing_id
                
            # Add the new pharmacy ID to the next available slot
            if len(pharmacy_ids) == 0:
                payload['pharmacy_id'] = pharmacy_id
                info_logger.info(f'{uid} | PHARMACY ADD API: Adding as primary pharmacy_id')
            elif len(pharmacy_ids) == 1:
                payload['pharmacy2_id'] = pharmacy_id
                info_logger.info(f'{uid} | PHARMACY ADD API: Adding as pharmacy2_id')
            elif len(pharmacy_ids) == 2:
                payload['pharmacy3_id'] = pharmacy_id
                info_logger.info(f'{uid} | PHARMACY ADD API: Adding as pharmacy3_id')
                
            info_logger.info(f'{uid} | PHARMACY ADD API: Complete pharmacy payload: {json.dumps(payload, indent=4)}')
            response = requests.post(
                PharmaciesService.UPDATE_PHARMACY_API_URL,  
                headers=headers,
                json=payload,
                timeout=10
            )
            
            info_logger.info(f'{uid} | PHARMACY ADD API: Response status code: {response.status_code}')
            info_logger.info(f'{uid} | PHARMACY ADD API: Response content: {response.text[:200]}') 
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | PHARMACY ADD API: Successfully added pharmacy with ID: {pharmacy_id}')
                return {
                    'success': True,
                    'message': 'Pharmacy successfully added to your profile.'
                }
            else:
                error_logger.error(f'{uid} | PHARMACY ADD API: Add failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to add pharmacy')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PHARMACY ADD API: Request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | PHARMACY ADD API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | PHARMACY ADD API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {
                'success': False,
                'message': 'Failed to add pharmacy to your profile'
            }


class FamilyHistoryService:

    FAMILY_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Familyhistory/GetFamilyHistory'
    SAVE_FAMILY_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Familyhistory/SaveFamilyHX'
    DELETE_FAMILY_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Familyhistory/DeleteFamilyHX'
    
    @staticmethod
    def get_patient_family_history(patient_account: str, practice_code: str, uid: str) -> list:
        if not patient_account:
            error_logger.error(f'{uid} | FAMILY HISTORY API: Missing PATIENT_ACCOUNT')
            raise ApplicationException(
                detail="Missing PATIENT_ACCOUNT",
                code=400
            )
        if not practice_code:   
            error_logger.error(f'{uid} | FAMILY HISTORY API: Missing PRACTICE_CODE')
            raise ApplicationException(
                detail="Missing PRACTICE_CODE",
                code=400
            )
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}          
            params = {'PracticeCode': practice_code, 'PatientAccount': patient_account}
            
            info_logger.debug(f'{uid} | FAMILY HISTORY API: Request parameters: {json.dumps(params, indent=4)}')
            
            response = requests.get(
                FamilyHistoryService.FAMILY_HISTORY_API_URL,
                headers=headers,
                params=params,
                timeout=10
            )           
            response.raise_for_status()
            family_data = response.json()
            
            if not family_data:
                error_logger.error(f'{uid} | FAMILY HISTORY API: Empty response received')
                raise ApplicationException(
                    detail="Empty response from family history API",
                    code=502
                )    
            if family_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | FAMILY HISTORY API: Non-200 status in response body: {family_data.get("statusCode")}')
                error_logger.error(f'{uid} | FAMILY HISTORY API: Error message: {family_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {family_data.get('message', 'Unknown error')}",
                    code=502
                )

            family_history_list = family_data.get('data', {}).get('familyHistories', [])
            
            filtered_family_history = []
            for fh in family_history_list:
                diagnosis_desc = fh.get('familyHistoryDiagnosisDescription', '')
                disease_name = ''
                if 'ICD9:' in diagnosis_desc:
                    start_idx = diagnosis_desc.find('ICD9:') + 5
                    end_idx = diagnosis_desc.find('Snomed:')
                    if end_idx > start_idx:
                        disease_name = diagnosis_desc[start_idx:end_idx].strip()
                    else:
                        disease_name = diagnosis_desc[start_idx:].strip()
                
                relationship_mapping = {'F': 'Father','M': 'Mother','B': 'Brother','S': 'Sister','C': 'Child','G': 'Grandfather','GM': 'Grandmother','U': 'Uncle','A': 'Aunt'}                
                relationship_code = fh.get('relationship', '')
                relationship_name = relationship_mapping.get(relationship_code, relationship_code)
                
                filtered_family_history.append({
                    'family_history_id': fh.get('familyHistoryId', ''),
                    'disease_name': disease_name,
                    'diagnosis_description': diagnosis_desc,
                    'relationship': relationship_name,
                    'relationship_code': relationship_code,
                    'deceased': fh.get('isDeceased', ''),
                    'age': fh.get('age', ''),
                    'age_at_onset': fh.get('ageAtOnset', ''),
                    'description': fh.get('description', ''),
                    'name': fh.get('name', ''),
                    'modified_date': fh.get('modifiedDate', '')
                })
            
            info_logger.info(f'{uid} | FAMILY HISTORY API: Successfully retrieved {len(filtered_family_history)} family history entries for patient')
            if not filtered_family_history:
                info_logger.info(f'{uid} | FAMILY HISTORY API: Patient has no family history on record')
            else:
                info_logger.debug(f'{uid} | FAMILY HISTORY API: First family history entry: {filtered_family_history[0].get("disease_name", "N/A")} for {filtered_family_history[0].get("relationship", "N/A")}')
            
            return filtered_family_history
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | FAMILY HISTORY API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | FAMILY HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | FAMILY HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | FAMILY HISTORY API: Failed to fetch patient family history: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient family history",
                code=502
            )

    @staticmethod
    def get_common_diseases(uid: str = None) -> list:
        if not uid:
            uid = str(uuid.uuid4())
            
        common_diseases = [
            {"diseaseCode": "E11", "diseaseName": "Diabetes"},
            {"diseaseCode": "I25", "diseaseName": "Heart Disease"},
            {"diseaseCode": "I10", "diseaseName": "High Blood Pressure"},
            {"diseaseCode": "C78", "diseaseName": "Cancer"},
            {"diseaseCode": "J45", "diseaseName": "Asthma"},
            {"diseaseCode": "F32", "diseaseName": "Depression"},
            {"diseaseCode": "M79", "diseaseName": "Arthritis"},
            {"diseaseCode": "I64", "diseaseName": "Stroke"},
            {"diseaseCode": "K58", "diseaseName": "Irritable Bowel Syndrome"},
            {"diseaseCode": "E78", "diseaseName": "High Cholesterol"},
            {"diseaseCode": "N18", "diseaseName": "Kidney Disease"},
            {"diseaseCode": "K21", "diseaseName": "GERD"},
            {"diseaseCode": "G40", "diseaseName": "Epilepsy"},
            {"diseaseCode": "F84", "diseaseName": "Autism"},
            {"diseaseCode": "Q90", "diseaseName": "Down Syndrome"}
        ]
        
        info_logger.info(f'{uid} | FAMILY HISTORY: Retrieved {len(common_diseases)} common diseases')
        return common_diseases

    @staticmethod
    def save_family_history(patient_account: str, practice_code: str, disease_code: str, 
                          disease_name: str, relationship_code: str, deceased: str, uid: str) -> dict:
        if not patient_account or not practice_code or not disease_code or not disease_name or not relationship_code:
            error_logger.error(f'{uid} | SAVE FAMILY HISTORY API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            # Build the correct payload structure based on API requirements
            payload = {
                "age": "",    
                "ageAtOnSet": "",
                "diagnosisList": [  
                    {
                        "icdNineCode": "",
                        "icdNineDescription": disease_name,
                        "icdTenCODE": disease_code,
                        "icdTenDescription": "",
                        "snomedDescription": ""
                    }
                ],
                "familyHistorystructureReconcileId": "-1",
                "isDeceased": deceased or "0", 
                "name": "",
                "patientAccount": patient_account,
                "practiceCode": practice_code, 
                "realtionShip": relationship_code,
                "validUserId": patient_account             
            }
            
            info_logger.info(f'{uid} | SAVE FAMILY HISTORY API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                FamilyHistoryService.SAVE_FAMILY_HISTORY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE FAMILY HISTORY API: Successfully saved family history: {disease_name}')
                return {
                    'success': True, 
                    'message': f'Successfully added {disease_name} to family history'
                }
            else:
                error_logger.error(f'{uid} | SAVE FAMILY HISTORY API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to save family history')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE FAMILY HISTORY API: Save request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SAVE FAMILY HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SAVE FAMILY HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete save request'}

    @staticmethod
    def delete_family_history(patient_account: str, practice_code: str, family_hx_id: str, uid: str) -> dict:
        if not patient_account or not practice_code or not family_hx_id:
            error_logger.error(f'{uid} | DELETE FAMILY HISTORY API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            payload = {
                "familyHXId": family_hx_id,
                "patientAccount": patient_account,
                "practiceCode": practice_code
            }
            
            info_logger.info(f'{uid} | DELETE FAMILY HISTORY API: Delete payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                FamilyHistoryService.DELETE_FAMILY_HISTORY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | DELETE FAMILY HISTORY API: Successfully deleted family history: {family_hx_id}')
                return {
                    'success': True, 
                    'message': 'Successfully deleted family history entry'
                }
            else:
                error_logger.error(f'{uid} | DELETE FAMILY HISTORY API: Delete failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to delete family history')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | DELETE FAMILY HISTORY API: Delete request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | DELETE FAMILY HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | DELETE FAMILY HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete delete request'}



class SocialHistoryService:

    SOCIAL_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/SocialHistory/GetSocialHistory'
    SAVE_SOCIAL_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/SocialHistory/SavePatientSocialHistory'
    
    @staticmethod
    def get_patient_social_history(patient_account: str, practice_code: str, uid: str) -> dict:
        if not patient_account:
            error_logger.error(f'{uid} | SOCIAL HISTORY API: Missing PATIENT_ACCOUNT')
            raise ApplicationException(
                detail="Missing PATIENT_ACCOUNT",
                code=400
            )
        if not practice_code:   
            error_logger.error(f'{uid} | SOCIAL HISTORY API: Missing PRACTICE_CODE')
            raise ApplicationException(
                detail="Missing PRACTICE_CODE",
                code=400
            )
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}          
            params = {'PracticeCode': practice_code, 'PatientAccount': patient_account}
            
            info_logger.debug(f'{uid} | SOCIAL HISTORY API: Request parameters: {json.dumps(params, indent=4)}')
            
            response = requests.get(
                SocialHistoryService.SOCIAL_HISTORY_API_URL,
                headers=headers,
                params=params,
                timeout=10
            )           
            
            response.raise_for_status()
            social_data = response.json()
            
            if not social_data:
                error_logger.error(f'{uid} | SOCIAL HISTORY API: Empty response received')
                raise ApplicationException(
                    detail="Empty response from social history API",
                    code=502
                )    
            if social_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | SOCIAL HISTORY API: Non-200 status in response body: {social_data.get("statusCode")}')
                error_logger.error(f'{uid} | SOCIAL HISTORY API: Error message: {social_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {social_data.get('message', 'Unknown error')}",
                    code=502
                )

            social_history_data = social_data.get('data', {}).get('socialHistory', {})
            
            # Extract and format the social history data
            formatted_social_history = {
                'socialhxId': social_history_data.get('socialhxId', ''),
                'education': social_history_data.get('education', ''),
                'industryCode': social_history_data.get('industryCode', ''),
                'tobaccoStatusIdPk': social_history_data.get('tobaccoStatusIdPk', ''),
                'industryStartDate': social_history_data.get('industryStartDate', ''),
                'industryEndDate': social_history_data.get('industryEndDate', ''),
                'tobaccoStatus': social_history_data.get('tobaccoStatus', ''),
                'alcoholDay': social_history_data.get('alcoholDay', ''),
                'tobaccoStartDate': social_history_data.get('tobaccoStartDate', ''),
                'tobaccoEndDate': social_history_data.get('tobaccoEndDate', ''),
                'riskAssessmentStructId': social_history_data.get('riskAssessmentStructId', ''),
                'exercise': social_history_data.get('exercise', ''),
                'seatbelts': social_history_data.get('seatbelts', ''),
                'exposure': social_history_data.get('exposure', ''),
                'suicideRisk': social_history_data.get('suicideRisk', ''),
                'feelsSafe': social_history_data.get('feelsSafe', ''),
                'drugUse': social_history_data.get('drugUse', ''),
                'notes': social_history_data.get('notes', ''),
                'caffineUsage': social_history_data.get('caffineUsage', ''),
                'caffineUsageFrequency': social_history_data.get('caffineUsageFrequency', ''),
                'drugUseDetails': social_history_data.get('drugUseDetails', ''),
                'isReconcile': social_history_data.get('isReconcile', '')
            }
            
            info_logger.info(f'{uid} | SOCIAL HISTORY API: Successfully retrieved social history for patient')
            if not any(formatted_social_history.values()):
                info_logger.info(f'{uid} | SOCIAL HISTORY API: Patient has no social history on record')
            else:
                info_logger.debug(f'{uid} | SOCIAL HISTORY API: Social history includes tobacco status: {formatted_social_history.get("tobaccoStatus", "N/A")}')
            
            return formatted_social_history
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SOCIAL HISTORY API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SOCIAL HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SOCIAL HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
                    
            error_logger.exception(f'{uid} | SOCIAL HISTORY API: Failed to fetch patient social history: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient social history",
                code=502
            )
        except Exception as e:
            error_logger.exception(f'{uid} | SOCIAL HISTORY API: Failed to fetch patient social history: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient social history",
                code=502
            )

    @staticmethod
    def     save_patient_social_history(patient_account: str, practice_code: str, 
                                  alcohol_per_day: str = "", tobacco_status_id: str = "", 
                                  drug_use: str = "", feels_safe: str = "", 
                                  risk_assessment_id: str = "", social_history_id: str = "",
                                  uid: str = None) -> dict:
        if not patient_account or not practice_code:
            error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            # Determine drug use details based on drug use value
            drug_use_details = "0" if drug_use == "Never" else ""
            
            payload = {
                "alcohalPerDay": alcohol_per_day,
                "alcohalUsage": alcohol_per_day,
                "caffineUsage": "False",
                "drugUse": drug_use,
                "drugUseDetails": drug_use_details,
                "educationId": "",
                "exercise": "",
                "exposure": "",
                "feels_Safe": feels_safe,
                "howLongUsingTobaco": "",
                "industryCode": "",
                "industryEndDate": "",
                "industryStartDate": "",
                "ipAddress": "127.0.0.1",
                "patientAccount": patient_account,
                "pmh": [
                    {
                        "afTblPatientMedicalHistoryItemsSettingCustomizedId": "0",
                        "afTblPatientMedicalHistoryItemsSettingId": "5651689",
                        "deleted": "False",
                        "diagnoseId": "0",
                        "diagnosisDescription": "Tinea unguium",
                        "isActive": "True"
                    }
                ],
                "practiceCode": practice_code,
                "request": [
                    {
                        "columnType": "DROPDOWN",
                        "intakeFormQuestionId": "544125",
                        "options": "",
                        "patientIntakeFormsId": "565101",
                        "patientIntakeFormsName": "Template",
                        "sectionName": "Allergy"
                    }
                ],
                "riskAssessmentId": risk_assessment_id,
                "seatBelts": "",
                "socialHistoryId": social_history_id,
                "tobacoEndDate": "",
                "tobacoStartDate": "",
                "tobacoStatus": "",
                "tobacoStatusId": tobacco_status_id,
                "tobacoStatusIdPk": tobacco_status_id
            }
            
            info_logger.info(f'{uid} | SAVE SOCIAL HISTORY API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                SocialHistoryService.SAVE_SOCIAL_HISTORY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE SOCIAL HISTORY API: Successfully saved social history')
                return {
                    'success': True, 
                    'message': 'Successfully saved social history'
                }
            else:
                error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to save social history')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Save request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete save request'}
        except Exception as e:
            error_logger.error(f'{uid} | SAVE SOCIAL HISTORY API: Unexpected error: {str(e)}')
            return {'success': False, 'message': 'Failed to save social history'}




class PastSurgicalHistoryService:

    PAST_SURGICAL_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/SurgicalHistory/GetPastSurgicalHistory'
    SAVE_PAST_SURGICAL_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/SurgicalHistory/SaveUpdatePastSurgicalHistory'
    DELETE_PAST_SURGICAL_HISTORY_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/SurgicalHistory/DeletePastSurgicalHistory'
    
    @staticmethod
    def get_patient_past_surgical_history(patient_account: str, practice_code: str, uid: str) -> list:
        if not patient_account:
            error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Missing PATIENT_ACCOUNT')
            raise ApplicationException(
                detail="Missing PATIENT_ACCOUNT",
                code=400
            )
        if not practice_code:   
            error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Missing PRACTICE_CODE')
            raise ApplicationException(
                detail="Missing PRACTICE_CODE",
                code=400
            )
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}          
            params = {'PracticeCode': practice_code, 'PatientAccount': patient_account}
            
            info_logger.debug(f'{uid} | PAST SURGICAL HISTORY API: Request parameters: {json.dumps(params, indent=4)}')
            
            response = requests.get(
                PastSurgicalHistoryService.PAST_SURGICAL_HISTORY_API_URL,
                headers=headers,
                params=params,
                timeout=10
            )           
            response.raise_for_status()
            surgical_data = response.json()
            
            if not surgical_data:
                error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Empty response received')
                raise ApplicationException(
                    detail="Empty response from past surgical history API",
                    code=502
                )    
            if surgical_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Non-200 status in response body: {surgical_data.get("statusCode")}')
                error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Error message: {surgical_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {surgical_data.get('message', 'Unknown error')}",
                    code=502
                )

            surgical_history_list = surgical_data.get('data', [])
            
            filtered_surgical_history = []
            for sh in surgical_history_list:
                surgery_date = sh.get('surgerY_DATE', '')
                surgery_name = sh.get('surgerY_NAME', '')
                surgery_place = sh.get('surgerY_PLACE', '')
                post_surgery_complications = sh.get('posT_SURGERY_COMPLICATIONS', '')
                
                filtered_surgical_history.append({
                    'past_surgical_history_structure_id': sh.get('pasT_SURGICAL_HISTORY_STRUCTURE_ID', ''),
                    'surgery_date': surgery_date,
                    'surgery_name': surgery_name,
                    'surgery_place': surgery_place,
                    'post_surgery_complications': post_surgery_complications,
                    'created_by': sh.get('createD_BY', ''),
                    'created_date': sh.get('createD_DATE', ''),
                    'modified_by': sh.get('modifieD_BY', ''),
                    'modified_date': sh.get('modifieD_DATE', '')
                })
            
            info_logger.info(f'{uid} | PAST SURGICAL HISTORY API: Successfully retrieved {len(filtered_surgical_history)} past surgical history entries for patient')
            if not filtered_surgical_history:
                info_logger.info(f'{uid} | PAST SURGICAL HISTORY API: Patient has no past surgical history on record')
            else:
                info_logger.debug(f'{uid} | PAST SURGICAL HISTORY API: First surgical history entry: {filtered_surgical_history[0].get("surgery_name", "N/A")} on {filtered_surgical_history[0].get("surgery_date", "N/A")}')
            
            return filtered_surgical_history
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | PAST SURGICAL HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | PAST SURGICAL HISTORY API: Failed to fetch patient past surgical history: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient past surgical history",
                code=502
            )

    @staticmethod
    def save_past_surgical_history(patient_account: str, practice_code: str, surgery_name: str, 
                                 surgery_place: str, surgery_date: str, uid: str) -> dict:
        if not patient_account or not practice_code or not surgery_name or not surgery_date:
            error_logger.error(f'{uid} | SAVE PAST SURGICAL HISTORY API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            payload = {
                "createdBy": patient_account,
                "language": "en",
                "pastSurgicalHistoryStructureReconcileId": "",
                "patientAccount": patient_account,
                "postSurgeryComplications": "",
                "practiceCode": practice_code,
                "surgeryDate": surgery_date,
                "surgeryName": surgery_name,
                "surgeryPlace": surgery_place or ""
            }
            
            info_logger.info(f'{uid} | SAVE PAST SURGICAL HISTORY API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                PastSurgicalHistoryService.SAVE_PAST_SURGICAL_HISTORY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE PAST SURGICAL HISTORY API: Successfully saved past surgical history: {surgery_name}')
                return {
                    'success': True, 
                    'message': f'Successfully added {surgery_name} to past surgical history'
                }
            else:
                error_logger.error(f'{uid} | SAVE PAST SURGICAL HISTORY API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to save past surgical history')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE PAST SURGICAL HISTORY API: Save request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SAVE PAST SURGICAL HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SAVE PAST SURGICAL HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete save request'}

    @staticmethod
    def delete_past_surgical_history(patient_account: str, practice_code: str, past_surgical_history_structure_id: str, 
                                   patient_name: str, uid: str) -> dict:
        if not patient_account or not practice_code or not past_surgical_history_structure_id:
            error_logger.error(f'{uid} | DELETE PAST SURGICAL HISTORY API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            payload = {
                "deleted": True,
                "modifiedBy": patient_name or "Patient",
                "pastSurgicalHistoryStructureId": past_surgical_history_structure_id,
                "patientAccount": patient_account,
                "practiceCode": practice_code
            }
            
            info_logger.info(f'{uid} | DELETE PAST SURGICAL HISTORY API: Delete payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                PastSurgicalHistoryService.DELETE_PAST_SURGICAL_HISTORY_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | DELETE PAST SURGICAL HISTORY API: Successfully deleted past surgical history: {past_surgical_history_structure_id}')
                return {
                    'success': True, 
                    'message': 'Successfully deleted past surgical history entry'
                }
            else:
                error_logger.error(f'{uid} | DELETE PAST SURGICAL HISTORY API: Delete failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to delete past surgical history')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | DELETE PAST SURGICAL HISTORY API: Delete request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | DELETE PAST SURGICAL HISTORY API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | DELETE PAST SURGICAL HISTORY API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete delete request'}


class InsuranceService:

    INSURANCE_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Insurance/GetPatientInsuranceInfo'
    DELETE_INSURANCE_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Insurance/DeletePatientInsurance'
    SEARCH_INSURANCE_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Insurance/SearchPatientInsurance'
    SAVE_SUBSCRIBER_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Insurance/AddUpdateSubscriber'
    SAVE_INSURANCE_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Insurance/AddPatientInsurance'
    ZIP_CODE_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/Demographics/ZipCityState'
    
    @staticmethod
    def get_patient_insurance(patient_account: str, practice_code: str, appointment_id: str, uid: str) -> dict:

        if not patient_account:
            error_logger.error(f'{uid} | INSURANCE API: Missing PATIENT_ACCOUNT')
            raise ApplicationException(detail="Missing PATIENT_ACCOUNT", code=400)
        if not practice_code:   
            error_logger.error(f'{uid} | INSURANCE API: Missing PRACTICE_CODE')
            raise ApplicationException(detail="Missing PRACTICE_CODE", code=400)
        if not appointment_id:   
            error_logger.error(f'{uid} | INSURANCE API: Missing APPOINTMENT_ID')
            raise ApplicationException(detail="Missing APPOINTMENT_ID", code=400)
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}
            
            params = {'PracticeCode': practice_code,'PatientAccount': patient_account,'AppointmentId': appointment_id}
            info_logger.debug(f'{uid} | INSURANCE API: Request parameters: {json.dumps(params, indent=4)}')
            
            response = requests.get(InsuranceService.INSURANCE_API_URL,headers=headers,params=params,timeout=10)
            response.raise_for_status()
            insurance_data = response.json()
            
            if not insurance_data:
                error_logger.error(f'{uid} | INSURANCE API: Empty response received')
                raise ApplicationException(detail="Empty response from insurance API", code=502)
            
            if insurance_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | INSURANCE API: Non-200 status in response body: {insurance_data.get("statusCode")}')
                error_logger.error(f'{uid} | INSURANCE API: Error message: {insurance_data.get("message", "No message")}')
                raise ApplicationException(detail=f"API error: {insurance_data.get('message', 'Unknown error')}", code=502)
            
            insurances = insurance_data.get('data', [])
            
            if not isinstance(insurances, list):
                error_logger.error(f'{uid} | INSURANCE API: Expected list of insurances but got {type(insurances)}')
                insurances = []
            
            # Process and categorize insurance data
            categorized_insurances = {'primary': None,'secondary': None,'other': None}
            
            for insurance in insurances:
                insurance_type = insurance.get('prI_SEC_OTH_TYPE', '')
                
                formatted_insurance = {
                    'patient_insurance_id': insurance.get('patienT_INSURANCE_ID', ''),
                    'insurance_type': 'Primary' if insurance_type == 'P' else 'Secondary' if insurance_type == 'S' else 'Other' if insurance_type == 'O' else 'Unknown',
                    'insurance_type_code': insurance_type,
                    'policy_number': insurance.get('policY_NUMBER', ''),
                    'insurance_id': insurance.get('insurancE_ID', ''),
                    'insurance_name': insurance.get('inspayeR_DESCRIPTION', ''),
                    'insurance_address': insurance.get('insurancE_ADDRESS', ''),
                    'insurance_city': insurance.get('insurancE_CITY', ''),
                    'insurance_state': insurance.get('insurancE_STATE', ''),
                    'insurance_zip': insurance.get('insurancE_ZIP', ''),
                    'relationship': insurance.get('relationshiP_DESCRIPTION', ''),
                    'relationship_code': insurance.get('relationship', ''),
                    'subscriber': insurance.get('subscriber', ''),
                    'group_number': insurance.get('group_Number', ''),
                    'group_name': insurance.get('group_Name', ''),
                    'co_payment': insurance.get('co_Payment', ''),
                    'deductions': insurance.get('deductions', ''),
                    'effective_date': insurance.get('effective_Date', ''),
                    'termination_date': insurance.get('termination_Date', ''),
                    'guarantor_code': insurance.get('guarantoR_CODE', '')
                }
                
                if insurance_type == 'P':
                    categorized_insurances['primary'] = formatted_insurance
                elif insurance_type == 'S':
                    categorized_insurances['secondary'] = formatted_insurance
                elif insurance_type == 'O':
                    categorized_insurances['other'] = formatted_insurance
            
            info_logger.info(f'{uid} | INSURANCE API: Successfully retrieved insurance data for patient')
            info_logger.debug(f'{uid} | INSURANCE API: Categorized insurance data: {json.dumps(categorized_insurances, indent=4)}')
            return categorized_insurances
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | INSURANCE API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | INSURANCE API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | INSURANCE API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | INSURANCE API: Failed to fetch patient insurance: {str(e)}')
            raise ApplicationException(detail="Failed to retrieve patient insurance", code=502)
    
    @staticmethod
    def delete_patient_insurance(patient_account: str, practice_code: str, insurance_id: str, uid: str) -> dict:
        if not patient_account or not practice_code or not insurance_id:
            error_logger.error(f'{uid} | DELETE INSURANCE API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}','Content-Type': 'application/json','Accept': '*/*'}
            
            payload = {"insuranceId": insurance_id,"modifiedBy": patient_account,"patientAccount": patient_account,"practiceCode": practice_code}
            info_logger.info(f'{uid} | DELETE INSURANCE API: Delete payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(InsuranceService.DELETE_INSURANCE_API_URL,headers=headers,json=payload,timeout=10)
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | DELETE INSURANCE API: Successfully deleted insurance: {insurance_id}')
                return {'success': True, 'message': 'Insurance successfully deleted'}
            else:
                error_logger.error(f'{uid} | DELETE INSURANCE API: Delete failed: {result.get("message", "Unknown error")}')
                return {'success': False, 'message': result.get('message', 'Failed to delete insurance')}
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | DELETE INSURANCE API: Delete request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to complete deletion request'}
    
    @staticmethod
    def search_insurance(patient_account: str, practice_code: str, insurance_name: str, patient_state: str, uid: str) -> dict:
        """Search for insurance by name"""
        if not patient_account or not practice_code or not insurance_name:
            error_logger.error(f'{uid} | SEARCH INSURANCE API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters', 'insurances': []}
        
        if len(insurance_name.strip()) < 2:
            error_logger.error(f'{uid} | SEARCH INSURANCE API: Insurance search query too short: "{insurance_name}"')
            return {'success': False, 'message': 'Search query must be at least 2 characters', 'insurances': []}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}','Content-Type': 'application/json','Accept': '*/*'}
            
            payload = {
                "callFrom": "STATE",
                "flag": "0",
                "groupName": "",
                "insuranceName": insurance_name,
                "pageIndex": "1",
                "pageSize": "20",
                "patientAccount": patient_account,
                "patientState": patient_state or "",
                "practiceCode": practice_code,
                "providerCode": "",
                "zip": ""
            }
            
            info_logger.info(f'{uid} | SEARCH INSURANCE API: Search payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(InsuranceService.SEARCH_INSURANCE_API_URL,headers=headers,json=payload,timeout=10)
            
            response.raise_for_status()
            result = response.json()
            
            if not result:
                error_logger.error(f'{uid} | SEARCH INSURANCE API: Empty response received')
                return {'success': False, 'message': 'No response from insurance search API', 'insurances': []}
            
            if result.get('statusCode') != 200:
                error_logger.error(f'{uid} | SEARCH INSURANCE API: Non-200 status: {result.get("statusCode")}')
                return {'success': False, 'message': result.get('message', 'Search failed'), 'insurances': []}
            
            insurances = result.get('data', [])
            
            if not isinstance(insurances, list):
                error_logger.error(f'{uid} | SEARCH INSURANCE API: Expected list but got {type(insurances)}')
                insurances = []
            
            formatted_insurances = []
            for idx, insurance in enumerate(insurances):
                formatted_insurance = {
                    'insurance_name': insurance.get('inspayeR_DESCRIPTION', ''),
                    'insurance_id': insurance.get('insurancE_ID', ''),
                    'insname_id': insurance.get('insName_Id', ''),
                    'insurance_address': insurance.get('insurancE_ADDRESS', ''),
                    'insurance_city': insurance.get('insurancE_CITY', ''),
                    'insurance_state': insurance.get('insurancE_STATE', ''),
                    'insurance_zip': insurance.get('insurancE_ZIP', ''),
                    'group_name': insurance.get('grouP_NAME', ''),
                    'group_id': insurance.get('grouP_ID', ''),
                    'inspayer_id': insurance.get('inspayeR_ID', ''),
                    'setup_name': insurance.get('setuP_NAME', ''),
                    'index': idx + 1
                }
                formatted_insurances.append(formatted_insurance)
            
            info_logger.info(f'{uid} | SEARCH INSURANCE API: Found {len(formatted_insurances)} insurances matching "{insurance_name}"')
            
            return {
                'success': True,
                'message': f'Found {len(formatted_insurances)} insurances matching "{insurance_name}"',
                'insurances': formatted_insurances
            }
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SEARCH INSURANCE API: Request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to search for insurances', 'insurances': []}
    
    @staticmethod
    def get_zip_city_state(practice_code: str, patient_account: str, zip_code: str, uid: str) -> dict:
        if not practice_code or not patient_account or not zip_code:
            error_logger.error(f'{uid} | ZIP CODE API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}'}
            
            params = {'PracticeCode': practice_code,'PatientAccount': patient_account,'ZipCode': zip_code}
            
            info_logger.debug(f'{uid} | ZIP CODE API: Request parameters: {json.dumps(params, indent=4)}')
            
            response = requests.get(InsuranceService.ZIP_CODE_API_URL,headers=headers,params=params,timeout=10)
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200 and result.get('data'):
                data = result['data'][0] if isinstance(result['data'], list) and len(result['data']) > 0 else result['data']
                
                return {'success': True,'zip_code': data.get('zipCode', zip_code),'city': data.get('cityName', ''),'state': data.get('stateCode', '')}
            else:
                error_logger.error(f'{uid} | ZIP CODE API: Invalid response: {result}')
                return {'success': False, 'message': 'Invalid zip code or no data found'}
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | ZIP CODE API: Request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to lookup zip code'}
    
    @staticmethod
    def save_subscriber(practice_code: str, patient_account: str, subscriber_data: dict, uid: str) -> dict:
        """Save subscriber information"""
        required_fields = ['first_name', 'last_name', 'address', 'city', 'state', 'zip_code', 'dob']
        missing_fields = [field for field in required_fields if not subscriber_data.get(field)]
        
        if missing_fields:
            error_logger.error(f'{uid} | SAVE SUBSCRIBER API: Missing required fields: {missing_fields}')
            return {'success': False, 'message': f'Missing required fields: {", ".join(missing_fields)}'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}','Content-Type': 'application/json','Accept': '*/*'}
            
            payload = {
                "GUARANT_PRACTICE_CODE": practice_code,
                "GUARANT_TYPE": "S",
                "guaranT_ADDRESS": subscriber_data['address'],
                "guaranT_CITY": subscriber_data['city'],
                "guaranT_FNAME": subscriber_data['first_name'],
                "guaranT_GENDER": subscriber_data.get('gender', ''),
                "guaranT_HOME_PHONE": subscriber_data.get('home_phone', ''),
                "guaranT_LNAME": subscriber_data['last_name'],
                "guaranT_MI": subscriber_data.get('middle_initial', ''),
                "guaranT_SSN": subscriber_data.get('ssn', ''),
                "guaranT_STATE": subscriber_data['state'],
                "guaranT_WORK_PHONE": subscriber_data.get('work_phone', ''),
                "guaranT_WORK_PHONE_EXT": subscriber_data.get('work_phone_ext', ''),
                "guarant_dob": subscriber_data['dob'],
                "guarant_zip": subscriber_data['zip_code'],
                "guarantoR_CODE": "",
                "modified_By": patient_account,
                "patientAccount": patient_account,
                "practiceCode": practice_code
            }
            
            info_logger.info(f'{uid} | SAVE SUBSCRIBER API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                InsuranceService.SAVE_SUBSCRIBER_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                guarantor_code = result.get('data', {}).get('guarantorCode', '')
                info_logger.info(f'{uid} | SAVE SUBSCRIBER API: Successfully saved subscriber with guarantor code: {guarantor_code}')
                return {
                    'success': True,
                    'guarantor_code': guarantor_code,
                    'message': 'Subscriber successfully saved'
                }
            else:
                error_logger.error(f'{uid} | SAVE SUBSCRIBER API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False,
                    'message': result.get('message', 'Failed to save subscriber')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE SUBSCRIBER API: Request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to save subscriber information'}
    
    @staticmethod
    def save_insurance(patient_account: str, practice_code: str, insurance_data: dict, uid: str) -> dict:
        """Save patient insurance information"""
        required_fields = ['insurance_id', 'policy_number', 'relationship', 'type']
        missing_fields = [field for field in required_fields if not insurance_data.get(field)]
        
        if missing_fields:
            error_logger.error(f'{uid} | SAVE INSURANCE API: Missing required fields: {missing_fields}')
            return {'success': False, 'message': f'Missing required fields: {", ".join(missing_fields)}'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {'Authorization': f'Bearer {token}','Content-Type': 'application/json','Accept': '*/*'}
            
            payload = {
                "allowedVisit": insurance_data.get('allowed_visit', ''),
                "copay": insurance_data.get('copay', ''),
                "copayPercent": insurance_data.get('copay_percent', ''),
                "createdBy": practice_code,
                "deductable": insurance_data.get('deductible', ''),
                "effectiveFrom": insurance_data.get('effective_from', ''),
                "effectiveTo": insurance_data.get('effective_to', ''),
                "groupId": insurance_data.get('group_id', ''),
                "groupName": insurance_data.get('group_name', ''),
                "guarantoR_CODE": insurance_data.get('guarantor_code', ''),
                "insuranceId": insurance_data['insuranceid'],
                "patientAccount": patient_account,
                "policyNumber": insurance_data['policy_number'],
                "practiceCode": practice_code,
                "relationship": insurance_data['relationship'],
                "subscriber": insurance_data.get('subscriber', ''),
                "type": insurance_data['type'],
                "wcInfo": insurance_data.get('wc_info', '')
            }
            
            info_logger.info(f'{uid} | SAVE INSURANCE API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                InsuranceService.SAVE_INSURANCE_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE INSURANCE API: Successfully saved insurance')
                return {'success': True, 'message': 'Insurance successfully saved'}
            else:
                error_logger.error(f'{uid} | SAVE INSURANCE API: Save failed: {result.get("message", "Unknown error")}')
                return {'success': False, 'message': result.get('message', 'Failed to save insurance')}
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE INSURANCE API: Request failed: {str(e)}')
            return {'success': False, 'message': 'Failed to save insurance information'}


class PastHospitalizationService:

    PAST_HOSPITALIZATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/PastHospitalization/GetPastHospitalization'
    SAVE_PAST_HOSPITALIZATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/PastHospitalization/SaveUpdatePastHospitalization'
    DELETE_PAST_HOSPITALIZATION_API_URL = 'https://qa-webservices.mtbc.com/SmartTALKPHR/api/Checkin/PastHospitalization/DeletePastHospitalization'
    
    @staticmethod
    def get_patient_past_hospitalization(patient_account: str, practice_code: str, uid: str) -> list:
        if not patient_account:
            error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Missing patient_account parameter')
            raise ApplicationException(
                detail="Patient account is required",
                code=400
            )
            
        if not practice_code:   
            error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Missing practice_code parameter')
            raise ApplicationException(
                detail="Practice code is required",
                code=400
            )
            
        try:
            token = MedicationService.get_auth_token(uid)
            
            headers = {'Authorization': f'Bearer {token}','Accept': 'application/json'}
            params = {'PracticeCode': practice_code,'PatientAccount': patient_account}
            
            info_logger.info(f'{uid} | PAST HOSPITALIZATION API: Requesting data for patient: {patient_account}')
            
            response = requests.get(
                PastHospitalizationService.PAST_HOSPITALIZATION_API_URL,
                headers=headers,
                params=params,
                timeout=10
            )
            
            response.raise_for_status()
            
            hospitalization_data = response.json()
            info_logger.debug(f'{uid} | PAST HOSPITALIZATION API: Raw response: {json.dumps(hospitalization_data, indent=2)}')
            
            if not hospitalization_data:
                error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Empty response')
                raise ApplicationException(
                    detail="Empty response from past hospitalization API",
                    code=502
                )    
                
            if hospitalization_data.get('statusCode') != 200:
                error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Non-200 status in response body: {hospitalization_data.get("statusCode")}')
                error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Error message: {hospitalization_data.get("message", "No message")}')
                raise ApplicationException(
                    detail=f"API error: {hospitalization_data.get('message', 'Unknown error')}",
                    code=502
                )

            hospitalization_list = hospitalization_data.get('data', [])
            
            filtered_hospitalization = []
            for hosp in hospitalization_list:
                hosp_date = hosp.get('hosP_DATE', '')
                reason = hosp.get('reason', '')
                duration = hosp.get('duration', '')
                comments = hosp.get('comments', '')
                
                filtered_hospitalization.append({
                    'past_hosp_structure_id': hosp.get('pasT_HOSP_STRUCTURE_ID', ''),
                    'hosp_date': hosp_date,
                    'reason': reason,
                    'duration': duration,
                    'comments': comments,
                    'created_by': hosp.get('createD_BY', ''),
                    'created_date': hosp.get('createD_DATE', ''),
                    'modified_by': hosp.get('modifieD_BY', ''),
                    'modified_date': hosp.get('modifieD_DATE', '')
                })
            
            info_logger.info(f'{uid} | PAST HOSPITALIZATION API: Successfully retrieved {len(filtered_hospitalization)} past hospitalization entries for patient')
            if not filtered_hospitalization:
                info_logger.info(f'{uid} | PAST HOSPITALIZATION API: Patient has no past hospitalization on record')
            else:
                info_logger.debug(f'{uid} | PAST HOSPITALIZATION API: First hospitalization entry: {filtered_hospitalization[0].get("reason", "N/A")} on {filtered_hospitalization[0].get("hosp_date", "N/A")}')
            
            return filtered_hospitalization
            
        except requests.RequestException as e:
            error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Request failed with status {getattr(e.response, "status_code", "No status")}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | PAST HOSPITALIZATION API: Raw error response: {e.response.text if e.response.content else "No content"}')
            error_logger.exception(f'{uid} | PAST HOSPITALIZATION API: Failed to fetch patient past hospitalization: {str(e)}')
            raise ApplicationException(
                detail="Failed to retrieve patient past hospitalization",
                code=502
            )

    @staticmethod
    def save_past_hospitalization(patient_account: str, practice_code: str, reason: str, 
                                duration: str, hosp_date: str, comment: str = "", uid: str = None) -> dict:
        if not patient_account or not practice_code or not reason or not hosp_date or not duration:
            error_logger.error(f'{uid} | SAVE PAST HOSPITALIZATION API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            payload = {
                "comment": comment or "",
                "createdBy": patient_account,
                "duration": duration,
                "hospDate": hosp_date,
                "language": "en",
                "pastHospitalizationId": "",
                "patientAccount": patient_account,
                "practiceCode": practice_code,
                "reason": reason
            }
            
            info_logger.info(f'{uid} | SAVE PAST HOSPITALIZATION API: Save payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                PastHospitalizationService.SAVE_PAST_HOSPITALIZATION_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | SAVE PAST HOSPITALIZATION API: Successfully saved past hospitalization: {reason}')
                return {
                    'success': True, 
                    'message': f'Successfully added {reason} to past hospitalization history',
                    'reason': reason,
                    'hosp_date': hosp_date,
                    'duration': duration,
                    'comment': comment
                }
            else:
                error_logger.error(f'{uid} | SAVE PAST HOSPITALIZATION API: Save failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to save past hospitalization')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | SAVE PAST HOSPITALIZATION API: Save request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | SAVE PAST HOSPITALIZATION API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | SAVE PAST HOSPITALIZATION API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete save request'}

    @staticmethod
    def delete_past_hospitalization(patient_account: str, practice_code: str, past_hospitalization_id: str, 
                                  patient_name: str, uid: str) -> dict:
        if not patient_account or not practice_code or not past_hospitalization_id:
            error_logger.error(f'{uid} | DELETE PAST HOSPITALIZATION API: Missing required parameters')
            return {'success': False, 'message': 'Missing required parameters'}
        
        try:
            token = MedicationService.get_auth_token(uid)
            headers = {
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': '*/*'
            }
            
            payload = {
                "deleted": True,
                "modifiedBy": patient_name or "Patient",
                "pastHospitalizationId": past_hospitalization_id,
                "patientAccount": patient_account,
                "practiceCode": practice_code
            }
            
            info_logger.info(f'{uid} | DELETE PAST HOSPITALIZATION API: Delete payload: {json.dumps(payload, indent=4)}')
            
            response = requests.post(
                PastHospitalizationService.DELETE_PAST_HOSPITALIZATION_API_URL,
                headers=headers,
                json=payload,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('statusCode') == 200:
                info_logger.info(f'{uid} | DELETE PAST HOSPITALIZATION API: Successfully deleted past hospitalization: {past_hospitalization_id}')
                return {
                    'success': True, 
                    'message': 'Successfully deleted past hospitalization entry'
                }
            else:
                error_logger.error(f'{uid} | DELETE PAST HOSPITALIZATION API: Delete failed: {result.get("message", "Unknown error")}')
                return {
                    'success': False, 
                    'message': result.get('message', 'Failed to delete past hospitalization')
                }
                
        except requests.RequestException as e:
            error_logger.error(f'{uid} | DELETE PAST HOSPITALIZATION API: Delete request failed: {str(e)}')
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_content = e.response.json() if e.response.content else "No content"
                    error_logger.error(f'{uid} | DELETE PAST HOSPITALIZATION API: Error response: {error_content}')
                except:
                    error_logger.error(f'{uid} | DELETE PAST HOSPITALIZATION API: Raw error response: {e.response.text if e.response.content else "No content"}')
            return {'success': False, 'message': 'Failed to complete delete request'}


