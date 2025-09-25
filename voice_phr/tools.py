from google.genai import types
import logging
import uuid
import json
import re
from typing import Dict, Any
from voice_phr.db_config import DBops
from voice_phr.api_calls import *
from voice_phr.utils.custom_exception import ApplicationException
info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')


def format_phone_number(phone):
    """Format phone number to (XXX) XXX-XXXX format"""
    if not phone:
        return phone
    
    # Remove all non-digit characters
    digits = re.sub(r'\D', '', str(phone))
    
    # If it's 11 digits and starts with 1, remove the 1
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    
    # If it's exactly 10 digits, format it
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    
    # Return original if not 10 digits
    return phone

def format_allergy_name(allergy_name):
    """Capitalize each word in allergy name using .title() method"""
    if not allergy_name:
        return allergy_name
    
    return str(allergy_name).title()

def concatenate_insurance_address(insurance_address, insurance_city, insurance_state):
    """Concatenate insurance address components into full address"""
    parts = []
    if insurance_address:
        parts.append(str(insurance_address))
    if insurance_city:
        parts.append(str(insurance_city))
    if insurance_state:
        parts.append(str(insurance_state))
    
    return ", ".join(parts) if parts else ""

update_demo_function = types.FunctionDeclaration(
    name="update_demo",
    description="Update patient demographics using patient_account as identifier.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "first_name": types.Schema(type="STRING"),
            "last_name": types.Schema(type="STRING"),
            "gender": types.Schema(type="STRING"),
            "address": types.Schema(type="STRING"),
            "city": types.Schema(type="STRING"),
            "state": types.Schema(type="STRING"),
            "zip": types.Schema(type="STRING"),
            "email_address": types.Schema(type="STRING"),
            "cell_phone": types.Schema(type="STRING"),
            "languages": types.Schema(type="STRING"),
            "patient_account": types.Schema(type="STRING"),
        },
        required=[
            "first_name", "last_name", "gender", "address", "city",
            "state", "zip", "email_address", "cell_phone", "languages", "patient_account"
        ]
    )
)

delete_allergy_tool = types.FunctionDeclaration(
    name="delete_patient_allergy",
    description="Delete a patient's allergy by name.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING"),
            "practice_code": types.Schema(type="STRING"),
            "allergy_id": types.Schema(type="STRING"),
        },
        required=["patient_account", "practice_code", "allergy_id"]
    )
)

search_allergy_tool = types.FunctionDeclaration(
    name="search_allergy",
    description="Search for allergies based on allergy name query",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "allergy_query": types.Schema(
                type=types.Type.STRING,
                description="The allergy name or keyword to search for"
            ),
            "practice_code": types.Schema(
                type=types.Type.STRING,
                description="The practice code for the patient"
            ),
            "patient_account": types.Schema(
                type=types.Type.STRING,
                description="The patient account number"
            )
        },
        required=["allergy_query", "practice_code", "patient_account"]
    )
)

add_allergy_function = types.FunctionDeclaration(
    name="add_allergy",
    description="Add a new allergy for the patient with allergy details",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "allergy_code": types.Schema(
                type=types.Type.STRING,
                description="The allergy code from search results"
            ),
            "allergy_name": types.Schema(
                type=types.Type.STRING,
                description="The full allergy name/description"
            ),
            "severity": types.Schema(
                type=types.Type.STRING,
                description="The severity level of the allergy"
            ),
            "reaction": types.Schema(
                type=types.Type.STRING,
                description="The reaction to the allergy"
            ),
            "allergy_type_id": types.Schema(
                type=types.Type.STRING,
                description="The allergy type ID from search results"
            ),
            "practice_code": types.Schema(
                type=types.Type.STRING,
                description="The practice code for the patient"
            ),
            "patient_account": types.Schema(
                type=types.Type.STRING,
                description="The patient account number"
            )
        },
        required=["allergy_code", "allergy_name", "severity", "reaction", "allergy_type_id", "practice_code", "patient_account"]
    )
)


# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

remove_delete_medication_tool = types.FunctionDeclaration(
    name="handle_remove_delete_medication",
    description=(
        "Remove a specific medication from a patient's records based on the provided medication name. "
        "The model will identify the correct medication by matching the name, retrieve its associated 'patient_prescription_id', "
        "and update the patient's record by setting that 'patient_prescription_id' to an empty string. "
        "This simulates the deletion of the pharmacy in the system."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "medication_name": types.Schema(
                type="STRING", 
                description="Name of the medication to delete (e.g., 'Pharbetol 325 mg tablet')"
            ),
            "patient_account": types.Schema(
                type="STRING",
                description="Unique identifier of the patient"
            ),
            "practice_code": types.Schema(
                type="STRING",
                description="Code of the practice to which the patient belongs"
            ),
            "medications": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    description="Each object contains information about a medication, including its unique patient_prescription_id and name."
                ),
                description=(
                    "List of medication records associated with the patient. "
                    "Each item is a dictionary containing medications details such as name and patient_prescription_id. "
                    "This data can be sourced either from the patient medications listed in the prompt or from prior conversation history. "
                    "The model will use this to locate and remove the correct medication."
                )
            )
        },
        required=["medication_name", "patient_account", "practice_code", "medications"]
    )
)

remove_delete_pharmacy_tool = types.FunctionDeclaration(
    name="handle_remove_delete_pharmacy",
    description=(
        "Remove a specific pharmacy from a patient's records based on the provided pharmacy name. "
        "The model will identify the correct pharmacy by matching the name, retrieve its associated 'pharmacy_id', "
        "and update the patient's record by setting that 'pharmacy_id' to an empty string. "
        "This simulates the deletion of the pharmacy in the system."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "pharmacy_name": types.Schema(
                type="STRING", 
                description="Name of the pharmacy to delete (e.g., 'CVS Pharmacy')"
            ),
            "patient_account": types.Schema(
                type="STRING",
                description="Unique identifier of the patient"
            ),
            "practice_code": types.Schema(
                type="STRING",
                description="Code of the practice to which the patient belongs"
            ),
            "pharmacies": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    description="Each object contains information about a pharmacy, including its unique pharmacy_id and name."
                ),
                description=(
                    "List of pharmacy records associated with the patient. "
                    "Each item is a dictionary containing pharmacy details such as name and pharmacy_id. "
                    "This data can be sourced either from the patient pharmacies listed in the prompt or from prior conversation history. "
                    "The model will use this to locate and remove the correct pharmacy."
                )
            )
        },
        required=["pharmacy_name", "patient_account", "practice_code", "pharmacies"]
    )
)

search_pharmacy_tool = types.FunctionDeclaration(
    name="handle_search_pharmacy",
    description="Search for pharmacies based on a keyword or partial name. This will return a list of possible pharmacy matches.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "search_term": types.Schema(type="STRING", description="Keyword or partial name of the pharmacy to search for (e.g., 'Walgreens', 'CVS')"),
            "patient_account": types.Schema(type="STRING")
        },
        required=["search_term", "patient_account"]
    )
)

search_medication_tool = types.FunctionDeclaration(
    name="handle_search_medication",
    description="Search for medications by name or partial name. This will return a list of possible medication matches.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "medication_name": types.Schema(type="STRING", description="Keyword or partial name of the medication to search for (e.g., 'pana', 'aspirin')"),
            "practice_code": types.Schema(type="STRING", description="The practice code to use for searching medications")
        },
        required=["medication_name", "practice_code"]
    )
)

get_medication_sig_tool = types.FunctionDeclaration(
    name="handle_get_medication_sig",
    description="Get medication instructions (SIG) from the user. This collects how the medication should be taken.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "medication_name": types.Schema(type="STRING", description="The name of the medication for which instructions are being provided"),
            "sig": types.Schema(type="STRING", description="Instructions on how the medication should be taken (e.g., 'Take 1 tablet by mouth twice daily', '2 pills every morning')")
        },
        required=["medication_name", "sig"]
    )
)

search_diagnosis_tool = types.FunctionDeclaration(
    name="handle_search_diagnosis",
    description="Search for diagnosis codes by keyword. This will return a list of possible diagnosis matches with ICD-10 codes.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "query": types.Schema(type="STRING", description="Keyword to search for diagnoses (e.g., 'heart', 'diabetes')"),
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code to use for searching diagnoses")
        },
        required=["query", "patient_account", "practice_code"]
    )
)

save_medication_tool = types.FunctionDeclaration(
    name="handle_save_medication",
    description="Save a new medication to the patient's record. After a user selects a medication from search results (by position or name), use the corresponding medication_id. For diagnosis, use the ICD-10 code from diagnosis search results.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "medicine_code": types.Schema(type="STRING", description="The medication code from search results"),
            "medicine_name": types.Schema(type="STRING", description="The name of the medication to save"),
            "sig": types.Schema(type="STRING", description="Instructions on how to take the medication"),
            "diag_code": types.Schema(type="STRING", description="The ICD-10 diagnosis code (optional)"),
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["medicine_code", "medicine_name", "patient_account", "practice_code"]
    )
)

add_pharmacy_tool = types.FunctionDeclaration(
    name="handle_add_pharmacy",
    description="Add a pharmacy to the patient's profile using the EXACT pharmacyCode value from previous search results. NEVER GUESS THE PHARMACY ID! After a user selects a pharmacy by position (e.g., \"add first one\", \"select 3rd\", \"number 2\") or name (e.g., \"add CVS\"), you MUST look up the corresponding 'pharmacyCode' field from the search results and use that value. CRITICAL ERROR TO AVOID: When user selects \"third\" or \"3rd\", DO NOT use '3' as the pharmacy_id - you must use the actual pharmacyCode value (e.g., '1001183') from that pharmacy in search results. POSITION MAPPING: '1'/'first' → get ID from index 0, '2'/'second' → get ID from index 1, '3'/'third' → get ID from index 2, etc. The 'pharmacyCode' is always a multi-digit identifier (e.g., '1001087'). DO NOT extract numbers from the pharmacy name (e.g., do NOT use '02593' from 'WALGREENS DRUG STORE #02593'). ONLY use the specific 'pharmacyCode' value obtained from the prior search results.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "pharmacy_id": types.Schema(type="STRING", description="The exact pharmacyCode from the search results data. This is the 'pharmacyCode' field from the previous search_pharmacy results for the selected pharmacy. It's a unique internal identifier (e.g., '1001087'). NEVER use any number that appears in the pharmacy name. DO NOT use store numbers that may appear in pharmacy names (e.g., NOT '02593' from 'WALGREENS DRUG STORE #02593'). Use ONLY the specific pharmacyCode value from the search results data."),
            "patient_account": types.Schema(type="STRING"),
            "practice_code": types.Schema(type="STRING")
        },
        required=["pharmacy_id", "patient_account", "practice_code"]
    )
)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# FAMILY HISTORY TOOLS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

get_family_history_tool = types.FunctionDeclaration(
    name="handle_get_family_history",
    description="Get the patient's existing family history data from the system.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["patient_account", "practice_code"]
    )
)

get_common_diseases_tool = types.FunctionDeclaration(
    name="handle_get_common_diseases",
    description="Get a list of common diseases that can be selected for family history.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number")
        },
        required=["patient_account"]
    )
)

save_family_history_tool = types.FunctionDeclaration(
    name="handle_save_family_history",
    description="Save family history entries for a patient. Each entry includes disease information, relationship, and deceased status.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "family_history_entries": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "disease_name": types.Schema(type="STRING", description="Name of the disease/condition"),
                        "disease_code": types.Schema(type="STRING", description="ICD-10 code for the disease"),
                        "relationship": types.Schema(type="STRING", description="Relationship code (B=Brother, C=Child, F=Father, M=Mother, S=Sister, etc.)"),
                        "deceased": types.Schema(type="STRING", description="Deceased status: '1' for deceased, '0' for alive")
                    },
                    required=["disease_name", "disease_code", "relationship", "deceased"]
                ),
                description="Array of family history entries to save"
            )
        },
        required=["patient_account", "practice_code", "family_history_entries"]
    )
)

delete_family_history_tool = types.FunctionDeclaration(
    name="handle_delete_family_history",
    description="Delete a specific family history entry using the family history ID extracted from the patient's family history data.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "family_hx_id": types.Schema(type="STRING", description="The family history ID (familyHistoryId) to delete")
        },
        required=["patient_account", "practice_code", "family_hx_id"]
    )
)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# SOCIAL HISTORY TOOLS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

get_social_history_tool = types.FunctionDeclaration(
    name="handle_get_social_history",
    description="Get current social history information for a patient including tobacco status, alcohol usage, drug use, and safety information.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING"),
            "practice_code": types.Schema(type="STRING")
        },
        required=["patient_account", "practice_code"]
    )
)

save_social_history_tool = types.FunctionDeclaration(
    name="handle_save_social_history",
    description="Save patient social history information including tobacco status, alcohol usage, drug use, and safety at home responses.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING"),
            "practice_code": types.Schema(type="STRING"),
            "tobacco_status_id": types.Schema(type="STRING", description="The tobacco status ID from user selection (e.g., '449868002' for Current every day smoker)"),
            "alcohol_per_day": types.Schema(type="STRING", description="Alcohol consumption per day from user selection"),
            "drug_use": types.Schema(type="STRING", description="Drug use status from user selection"),
            "feels_safe": types.Schema(type="STRING", description="Whether patient feels safe at home - 'yes' or 'no'"),
            "risk_assessment_id": types.Schema(type="STRING", description="Risk assessment ID from existing patient data"),
            "social_history_id": types.Schema(type="STRING", description="Social history ID from existing patient data")
        },
        required=["patient_account", "practice_code", "tobacco_status_id", "alcohol_per_day", "drug_use", "feels_safe"]
    )
)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# PAST SURGICAL HISTORY TOOLS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

get_past_surgical_history_tool = types.FunctionDeclaration(
    name="handle_get_past_surgical_history",
    description="Get the patient's existing past surgical history data from the system.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["patient_account", "practice_code"]
    )
)

save_past_surgical_history_tool = types.FunctionDeclaration(
    name="handle_save_past_surgical_history",
    description="Save new past surgical history entries for a patient. Each entry includes surgery name, surgery place, and surgery date in yy-mm-dd format.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "surgery_name": types.Schema(type="STRING", description="Name of the surgery/procedure"),
            "surgery_place": types.Schema(type="STRING", description="Location where the surgery was performed"),
            "surgery_date": types.Schema(type="STRING", description="Date of surgery in yy-mm-dd format (e.g., '23-05-15')")
        },
        required=["patient_account", "practice_code", "surgery_name", "surgery_date"]
    )
)

delete_past_surgical_history_tool = types.FunctionDeclaration(
    name="handle_delete_past_surgical_history",
    description="Delete a specific past surgical history entry using the past surgical history structure ID extracted from the patient's surgical history data.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "past_surgical_history_structure_id": types.Schema(type="STRING", description="The past surgical history structure ID to delete"),
            "patient_name": types.Schema(type="STRING", description="The patient's name for audit trail")
        },
        required=["patient_account", "practice_code", "past_surgical_history_structure_id"]
    )
)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# PAST HOSPITALIZATION TOOLS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

get_past_hospitalization_tool = types.FunctionDeclaration(
    name="handle_get_past_hospitalization",
    description="Retrieve the patient's existing past hospitalization records from the system. Call this function when the user first enters or asks about their current hospitalization history.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["patient_account", "practice_code"]
    )
)

save_past_hospitalization_tool = types.FunctionDeclaration(
    name="handle_save_past_hospitalization",
    description="Save a new past hospitalization entry when the user provides complete information (reason + date + duration). Call immediately when you have all three required pieces of information.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "reason": types.Schema(type="STRING", description="The reason for hospitalization (e.g., 'Heart Surgery', 'Pneumonia Treatment')"),
            "duration": types.Schema(type="STRING", description="Duration of hospital stay (e.g., '5 days', '1 week', '3 days')"),
            "hosp_date": types.Schema(type="STRING", description="Date of hospitalization in yyyy-mm-dd format"),
            "comment": types.Schema(type="STRING", description="Optional comments about the hospitalization")
        },
        required=["patient_account", "practice_code", "reason", "duration", "hosp_date"]
    )
)

delete_past_hospitalization_tool = types.FunctionDeclaration(
    name="handle_delete_past_hospitalization",
    description="Delete a specific past hospitalization entry when the user asks to remove it. Extract the past_hosp_structure_id from the patient's hospitalization data.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "past_hospitalization_id": types.Schema(type="STRING", description="The past_hosp_structure_id extracted from patient hospitalization data"),
            "patient_name": types.Schema(type="STRING", description="The patient's name for audit trail")
        },
        required=["patient_account", "practice_code", "past_hospitalization_id"]
    )
)

# Insurance tool declarations
get_patient_insurance_tool = types.FunctionDeclaration(
    name="handle_get_patient_insurance",
    description="Retrieve the patient's existing insurance information from the system. This will return all insurance records categorized as Primary, Secondary, and Other.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["patient_account", "practice_code"]
    )
)

delete_patient_insurance_tool = types.FunctionDeclaration(
    name="handle_delete_patient_insurance",
    description="Delete a specific insurance record when the user asks to remove it. Use the insurance_id from the patient's insurance data (this maps to insuranceId in the API).",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number (maps to patientAccount in API)"),
            "practice_code": types.Schema(type="STRING", description="The practice code (maps to practiceCode in API)"),
            "insurance_id": types.Schema(type="STRING", description="The insurance_id to delete (maps to insuranceId in API)")
        },
        required=["patient_account", "practice_code", "insurance_id"]
    )
)

search_insurance_tool = types.FunctionDeclaration(
    name="handle_search_insurance",
    description="Search for insurance plans by name or partial name. This will return a list of possible insurance matches with pagination support.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "insurance_name": types.Schema(type="STRING", description="Keyword or partial name of the insurance to search for (e.g., 'Blue Cross', 'Aetna')"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "page": types.Schema(type="INTEGER", description="Page number for pagination (default: 1)")
        },
        required=["insurance_name", "practice_code","patient_account"]
    )
)

get_zip_city_state_tool = types.FunctionDeclaration(
    name="handle_get_zip_city_state",
    description="Get city and state information for a given ZIP code. This is used to auto-fill address information.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "zip_code": types.Schema(type="STRING", description="The ZIP code to lookup"),
            "practice_code": types.Schema(type="STRING", description="The practice code")
        },
        required=["patient_account","zip_code", "practice_code"]
    )
)

save_subscriber_tool = types.FunctionDeclaration(
    name="handle_save_subscriber",
    description="Save subscriber information when the relationship is not 'self'. This collects details about the insurance policy holder.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "subscriber_first_name": types.Schema(type="STRING", description="Subscriber's first name"),
            "subscriber_last_name": types.Schema(type="STRING", description="Subscriber's last name"),
            "subscriber_dob": types.Schema(type="STRING", description="Subscriber's date of birth in MM/DD/YYYY format"),
            "subscriber_gender": types.Schema(type="STRING", description="Subscriber's gender (M/F)"),
            "subscriber_address": types.Schema(type="STRING", description="Subscriber's address"),
            "subscriber_city": types.Schema(type="STRING", description="Subscriber's city"),
            "subscriber_state": types.Schema(type="STRING", description="Subscriber's state"),
            "subscriber_zip": types.Schema(type="STRING", description="Subscriber's ZIP code"),
            "subscriber_phone": types.Schema(type="STRING", description="Subscriber's phone number")
        },
        required=["patient_account", "practice_code", "subscriber_first_name", "subscriber_last_name", "subscriber_dob"]
    )
)

save_insurance_tool = types.FunctionDeclaration(
    name="handle_save_insurance",
    description="Save new insurance information for a patient. This includes insurance plan details, policy information, and subscriber details.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "patient_account": types.Schema(type="STRING", description="The patient account number"),
            "practice_code": types.Schema(type="STRING", description="The practice code"),
            "insurance_name": types.Schema(type="STRING", description="Name of the insurance company"),
            "insurance_id": types.Schema(type="STRING", description="Insurance company ID from search results"),
            "policy_number": types.Schema(type="STRING", description="Insurance policy number"),
            "group_number": types.Schema(type="STRING", description="Insurance group number"),
            "insurance_type": types.Schema(type="STRING", description="Type of insurance (Primary, Secondary, Other)"),
            "relationship": types.Schema(type="STRING", description="Relationship to subscriber (self, spouse, child, etc.)"),
            "effective_date": types.Schema(type="STRING", description="Insurance effective date in MM/DD/YYYY format"),
            "termination_date": types.Schema(type="STRING", description="Insurance termination date in MM/DD/YYYY format (optional)"),
            "subscriber_id": types.Schema(type="STRING", description="Subscriber ID if relationship is not 'self'")
        },
        required=["patient_account", "practice_code", "insurance_name", "insurance_id", "policy_number", "insurance_type", "relationship"]
    )
)



# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# Handler Functions for LLM Tool Calls
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_search_allergy(allergy_query, practice_code, patient_account, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        from voice_phr.api_calls import Allergies
        # Call the API function with correct parameter order
        result = Allergies.search_allergy(
            practice_code=practice_code,
            allergy_query=allergy_query,
            uid=uid
        )
        return result
    except Exception as e:
        error_logger.error(f"{uid} | Error searching for allergies: {str(e)}")
        return {"success": False, "allergies": [], "message": str(e)}

def handle_add_allergy(allergy_code, allergy_name, severity, reaction, allergy_type_id, practice_code, patient_account, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        from voice_phr.api_calls import Allergies
        
        # Use provided allergy_type_id (now required parameter)
        if not allergy_type_id:
            allergy_type_id = "2"  # fallback default
        
        info_logger.info(f"{uid} | Adding allergy with parameters:")
        info_logger.info(f"{uid} | - allergy_code: {allergy_code}")
        info_logger.info(f"{uid} | - allergy_name: {allergy_name}")
        info_logger.info(f"{uid} | - severity: {severity}")
        info_logger.info(f"{uid} | - reaction: {reaction}")
        info_logger.info(f"{uid} | - allergy_type_id: {allergy_type_id}")
        info_logger.info(f"{uid} | - practice_code: {practice_code}")
        info_logger.info(f"{uid} | - patient_account: {patient_account}")
        
        # Call the API function
        result = Allergies.save_patient_allergy(
            patient_account=patient_account,
            practice_code=practice_code,
            allergy_code=allergy_code,
            allergy_name=allergy_name,
            severity=severity,
            reaction=reaction,
            allergy_type_id=allergy_type_id,
            uid=uid
        )
        return result
    except Exception as e:
        error_logger.error(f"{uid} | Error adding allergy: {str(e)}")
        return {"success": False, "message": str(e)}
    
def handle_remove_delete_medication(medication_name,patient_account,practice_code,medications, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        # If medications is None, we need to fetch them
        if medications is None:
            medications = MedicationService.get_patient_medications(patient_account=patient_account, practice_code=correct_practice_code, uid=uid)
        else:
            info_logger.info(f"{uid} | Using provided medication data, skipping API call")  
        result = MedicationService.delete_medication(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            medication_query=medication_name,
            medications_data=medications,
            uid=uid
        ) 
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting medication: {str(e)}")
        return str(e)

def handle_remove_delete_pharmacy(pharmacy_name,patient_account,practice_code,pharmacies,uid=None):
    if not uid:
        uid = str(uuid.uuid4())
        
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
        if pharmacies is None:
            info_logger.info(f"{uid} | No pharmacies data provided, fetching from API")
            # Get the pharmacies data first
            pharmacies = PharmaciesService.get_patient_pharmacies(patient_account=patient_account, practice_code=correct_practice_code, uid=uid)
        else:
            info_logger.info(f"{uid} | Using provided pharmacies data, skipping API call")
            
        result = PharmaciesService.delete_pharmacy(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            pharmacy_query=pharmacy_name,
            pharmacy_data=pharmacies,
            uid=uid
        )
               
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting pharmacy: {str(e)}")
        return str(e)

def handle_search_pharmacy(patient_account,search_term,uid=None):  
    if not uid:
        uid = str(uuid.uuid4())
    try:
        result = PharmaciesService.search_pharmacy(
            patient_account=patient_account,
            pharmacy_query=search_term,
            uid=uid
        ) 
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error searching for pharmacies: {str(e)}")
        return str(e)

def handle_search_medication(practice_code, medication_name, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        result = MedicationService.search_medication(
            medication_name=medication_name,
            practice_code=practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error searching for medications: {str(e)}")
        return str(e)

def handle_get_medication_sig(medication_name, sig, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    info_logger.info(f"{uid} | Received medication instructions (SIG) for {medication_name}: '{sig}'")
    return {
        "success": True,
        "medication_name": medication_name,
        "sig": sig,
        "message": f"Successfully captured instructions for {medication_name}"
    }

def handle_search_diagnosis(query, patient_account, practice_code, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        result = MedicationService.search_diagnosis(
            query=query,
            patient_account=patient_account,
            practice_code=practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error searching for diagnoses: {str(e)}")
        return {"success": False, "message": str(e), "diagnoses": []}
    except Exception as e:
        error_logger.error(f"{uid} | Unexpected error searching for diagnoses: {str(e)}")
        return {"success": False, "message": "An unexpected error occurred", "diagnoses": []}

def handle_save_medication(medicine_code, medicine_name, patient_account, practice_code, sig="", diag_code="", uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        result = MedicationService.save_medication(
            patient_account=patient_account,
            practice_code=practice_code,
            medicine_code=medicine_code,
            medicine_name=medicine_name,
            sig=sig,
            diag_code=diag_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving medication: {str(e)}")
        return {"success": False, "message": str(e)}
    except Exception as e:
        error_logger.error(f"{uid} | Unexpected error saving medication: {str(e)}")
        return {"success": False, "message": "An unexpected error occurred"}

def handle_add_pharmacy(pharmacy_id,patient_account,practice_code,pharmacies=None,uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    
    # Log the provided pharmacy_id for debugging
    info_logger.info(f"{uid} | PHARMACY ADD ATTEMPT: Received pharmacy_id: '{pharmacy_id}'")

    # Validate pharmacy_id - it must be a non-empty numeric string from search results.
    if not pharmacy_id or not pharmacy_id.isdigit():
        error_message = (
            f"Invalid pharmacy_id: '{pharmacy_id}'. "
            "Pharmacy ID must be the exact numeric ID obtained from pharmacy search results. "
            "It should not contain text, special characters, or be derived from the pharmacy name."
        )
        error_logger.error(f"{uid} | {error_message}")
        return {"success": False, "message": error_message}

    correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
    
    if practice_code != correct_practice_code:
        error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
        
    if pharmacies is None:
        info_logger.info(f"{uid} | No pharmacies data provided, fetching from API")
        pharmacies = PharmaciesService.get_patient_pharmacies(patient_account=patient_account, practice_code=correct_practice_code, uid=uid)
    else:
        info_logger.info(f"{uid} | Using provided pharmacies data, skipping API call")


    try:
        result = PharmaciesService.add_pharmacy(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            pharmacy_id=pharmacy_id,
            current_pharmacies=pharmacies,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error adding pharmacy: {str(e)}")
        return str(e)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# FAMILY HISTORY HANDLER FUNCTIONS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_get_family_history(patient_account, practice_code, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = FamilyHistoryService.get_patient_family_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting family history: {str(e)}")
        return str(e)

def handle_get_common_diseases(patient_account, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        result = FamilyHistoryService.get_common_diseases(uid=uid)
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting common diseases: {str(e)}")
        return str(e)

def handle_save_family_history(patient_account, practice_code, family_history_entries, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
        results = []
        for entry in family_history_entries:
            result = FamilyHistoryService.save_family_history(
                patient_account=patient_account,
                practice_code=correct_practice_code,
                disease_code=entry.get('disease_code', ''),
                disease_name=entry.get('disease_name', ''),
                relationship_code=entry.get('relationship', ''),
                deceased=entry.get('deceased', '0'),
                uid=uid
            )
            results.append(result)
        if len(results) == 1:
            return results[0]
        else:
            return {'success': True, 'message': f'Successfully saved {len(results)} family history entries'}
            
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving family history: {str(e)}")
        return str(e)

def handle_delete_family_history(patient_account, practice_code, family_hx_id, uid=None):
    """Handle deleting a specific family history entry"""
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = FamilyHistoryService.delete_family_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            family_hx_id=family_hx_id,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting family history: {str(e)}")
        return str(e)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# PAST SURGICAL HISTORY HANDLER FUNCTIONS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_get_past_surgical_history(patient_account, practice_code, uid=None):
    """Handle getting patient's existing past surgical history data"""
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastSurgicalHistoryService.get_patient_past_surgical_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting past surgical history: {str(e)}")
        return str(e)

def handle_save_past_surgical_history(patient_account, practice_code, surgery_name, surgery_place, surgery_date, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastSurgicalHistoryService.save_past_surgical_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            surgery_name=surgery_name,
            surgery_place=surgery_place,
            surgery_date=surgery_date,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving past surgical history: {str(e)}")
        return str(e)

def handle_delete_past_surgical_history(patient_account, practice_code, past_surgical_history_structure_id, patient_name=None, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastSurgicalHistoryService.delete_past_surgical_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            past_surgical_history_structure_id=past_surgical_history_structure_id,
            patient_name=patient_name or "Patient",
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting past surgical history: {str(e)}")
        return str(e)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# PAST HOSPITALIZATION HANDLER FUNCTIONS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_get_past_hospitalization(patient_account, practice_code, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastHospitalizationService.get_patient_past_hospitalization(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting past hospitalization: {str(e)}")
        return str(e)

def handle_save_past_hospitalization(patient_account, practice_code, reason, duration, hosp_date, comment="", uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastHospitalizationService.save_past_hospitalization(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            reason=reason,
            duration=duration,
            hosp_date=hosp_date,
            comment=comment,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving past hospitalization: {str(e)}")
        return str(e)

def handle_delete_past_hospitalization(patient_account, practice_code, past_hospitalization_id, patient_name=None, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = PastHospitalizationService.delete_past_hospitalization(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            past_hospitalization_id=past_hospitalization_id,
            patient_name=patient_name or "Patient",
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting past hospitalization: {str(e)}")
        return str(e)



# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# SOCIAL HISTORY HANDLER FUNCTIONS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_get_social_history(patient_account, practice_code, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = SocialHistoryService.get_patient_social_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting social history: {str(e)}")
        return str(e)

def handle_save_social_history(patient_account, practice_code, tobacco_status_id, alcohol_per_day, 
                             drug_use, feels_safe, risk_assessment_id="", social_history_id="", uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = SocialHistoryService.save_patient_social_history(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            tobacco_status_id=tobacco_status_id,
            alcohol_per_day=alcohol_per_day,
            drug_use=drug_use,
            feels_safe=feels_safe,
            risk_assessment_id=risk_assessment_id,
            social_history_id=social_history_id,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving social history: {str(e)}")
        return str(e)

# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@
# INSURANCE HANDLER FUNCTIONS
# @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@

def handle_get_patient_insurance(patient_account, practice_code, uid=None):
    """Handle getting patient's existing insurance information"""
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = InsuranceService.get_patient_insurance(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting patient insurance: {str(e)}")
        return str(e)

def handle_delete_patient_insurance(patient_account, practice_code, insurance_id, patient_name=None, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")
            
        result = InsuranceService.delete_patient_insurance(
            patient_account=patient_account,
            practice_code=correct_practice_code,
            insurance_id=insurance_id,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error deleting patient insurance: {str(e)}")
        return str(e)

def handle_search_insurance(insurance_name, practice_code, patient_account, page=1, uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code 
            
        result = InsuranceService.search_insurance(
            patient_account=correct_practice_code,
            practice_code=practice_code,
            insurance_name=insurance_name,
            patient_state="",  # Default empty, can be enhanced later
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error searching insurance: {str(e)}")
        return str(e)

def handle_get_zip_city_state(patient_account,zip_code, practice_code, uid=None):
    """Handle getting city and state information for a ZIP code"""
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        result = InsuranceService.get_zip_city_state(
            zip_code=zip_code,
            practice_code=practice_code,
             patient_account=correct_practice_code,
            uid=uid
        )
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error getting ZIP city state: {str(e)}")
        return str(e)

def handle_save_subscriber(**args: Any) -> Dict[str, Any]:

    info_logger.info(f"Function call detected: handle_save_subscriber with args: {args}")
    try:
        practice_code = args.get("practice_code")
        patient_account = args.get("patient_account")
        
        uid = args.get("uid")

        if not practice_code or not patient_account:
            error_logger.error("Missing practice_code or patient_account in handle_save_subscriber")
            raise ApplicationException("Practice code and patient account are required.")

        subscriber_data = {
            "first_name": args.get("subscriber_first_name"),
            "last_name": args.get("subscriber_last_name"),
            "dob": args.get("subscriber_dob"),
            "address": args.get("subscriber_address"),
            "city": args.get("subscriber_city"),
            "state": args.get("subscriber_state"),
            "zip_code": args.get("subscriber_zip")
        }
        info_logger.info(f"Calling InsuranceService.save_subscriber with practice_code='{practice_code}', patient_account='{patient_account}', subscriber_data='{subscriber_data}', uid='{uid}'")

        result = InsuranceService.save_subscriber(
            practice_code=practice_code,
            patient_account=patient_account,
            subscriber_data=subscriber_data,
            uid=uid  # Pass the extracted uid
        )
        info_logger.info(f"Subscriber saved successfully: {result}")
        return result
    except Exception as e:
        error_logger.error(f"Error in handle_save_subscriber: {e}", exc_info=True)
        raise ApplicationException(f"Failed to save subscriber: {str(e)}")

def handle_save_insurance(patient_account, practice_code, insurance_name, insurance_id, policy_number, 
                         insurance_type, relationship, group_number="", effective_date="", 
                         termination_date="", subscriber_id="", uid=None):
    if not uid:
        uid = str(uuid.uuid4())
    try:
        correct_practice_code = patient_account[:7] if patient_account and len(patient_account) >= 7 else practice_code
        if practice_code != correct_practice_code:
            error_logger.warning(f"{uid} | Practice code mismatch: Received {practice_code}, corrected to {correct_practice_code}")

        type_mapping = {"Primary": "P","Secondary": "S","Other": "O","P": "P","S": "S","O": "O"}
    
        insurance_type_code = type_mapping.get(insurance_type.capitalize() if insurance_type else insurance_type, insurance_type)
        
        relationship_mapping = {"Self": "S","Spouse": "P","Child": "C","Other": "O","S": "S","P": "P","C": "C","O": "O"}
        
        relationship_code = relationship_mapping.get(relationship.capitalize() if relationship else relationship, relationship)

        insurance_data = {
            'insurance_id': insurance_id, 
            'insuranceid': insurance_id,   
            'policy_number': policy_number,
            'group_number': group_number or "",
            'type': insurance_type_code,
            'relationship': relationship_code,
            'effective_from': effective_date or "",
            'effective_to': termination_date or "",
            'guarantor_code': "",
            'subscriber': subscriber_id or ""
        } 
        result = InsuranceService.save_insurance(patient_account=patient_account,practice_code=correct_practice_code,insurance_data=insurance_data,uid=uid)
        return result
    except ApplicationException as e:
        error_logger.error(f"{uid} | Error saving insurance: {str(e)}")
        return str(e)
