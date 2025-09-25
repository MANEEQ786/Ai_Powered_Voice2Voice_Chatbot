import time
import traceback
from config.config import *
from voice_phr.api_calls import Allergies
from voice_phr.utils.custom_exception import ApplicationException
from rest_framework.exceptions import APIException
from voice_phr.db_config import DBops
import asyncio
import json
import re
import os
import uuid
import logging
from typing import Optional
from voice_phr.tools import *
from google import genai
from google.genai import types
import vertexai
from vertexai.generative_models import GenerativeModel, Content, Part, GenerationConfig


import asyncio
import json
import traceback
import os
from typing import AsyncGenerator

info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')

class GenerateResponse:
    def __init__(self):
        pass
    
    @staticmethod
    def clean_response(text):
        if text is None:
            return ""
        print("text......................\n",text)
        # Remove markdown code block markers and common prefixes
        cleaned = text.replace("```json", "").replace("```", "").strip()
        
        # Remove common AI response prefixes
        prefixes_to_remove = [
            "Here's the information you requested.",
            "Here is the information you requested.",
            "I'll help you with that.",
            "Let me help you with that.",
            "Sure, I can help with that."
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        # Try to extract JSON object if it's wrapped in other text
        import re
        # Look for JSON objects that start with { and end with }
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, cleaned, re.DOTALL)
        
        if matches:
            # Return the largest JSON object found (most complete)
            largest_match = max(matches, key=len)
            info_logger.info(f"🔍 EXTRACTED JSON OBJECT: {largest_match[:200]}...")
            return largest_match
        
        # If no JSON found, try to look for speech/display patterns in the text
        speech_match = re.search(r'"speech"\s*:\s*"([^"]*)"', cleaned)
        display_match = re.search(r'"display"\s*:\s*"([^"]*)"', cleaned)
        
        if speech_match and display_match:
            # Reconstruct JSON from found patterns
            reconstructed = {
                "speech": speech_match.group(1),
                "display": display_match.group(1)
            }
            return json.dumps(reconstructed)
        
        return cleaned
    
    @staticmethod
    def format_update_demo_response(args, result):
        """Format the response for demographic updates into speech and display fields"""
        if result:
            speech = "Here are the updated demographic details. Would you like to make any changes?"

            # Format phone number properly: (XXX) XXX-XXXX
            phone = args.get('cell_phone', '')
            formatted_phone = f"({phone[:3]}) {phone[3:6]}-{phone[6:]}" if len(phone) == 10 else phone

            display = (
                f"**📋 Updated Demographics**\n\n"
                f"- **First Name:** {args.get('first_name', '').title()}\n"
                f"- **Last Name:** {args.get('last_name', '').title()}\n"
                f"- **Gender:** {args.get('gender', '').title()}\n"
                f"- **Address:** {args.get('address', '').title()}\n"
                f"- **City:** {args.get('city', '').title()}\n"
                f"- **State:** {args.get('state', '').upper()}\n"
                f"- **ZIP:** `{args.get('zip', '')}`\n"
                f"- **Email:** {args.get('email_address', '').lower()}\n"
                f"- **Phone:** `{formatted_phone}`\n"
                f"- **Languages:** {args.get('languages', '').title()}"
            )

            return {
                "speech": speech,
                "display": display
            }
        else:
            return {
                "speech": "Failed to update patient demographic details.",
                "display": "**❌ Update Failed**\n\nPlease try again."
            }
  
    @staticmethod
    def format_delete_allergy_response(args, result, updated_allergies=None):
        """Format the response for allergy deletion into speech and display fields"""
        allergy_name = args.get('allergy_name', 'The allergy')
        
        if result.get("success"):
            info_logger.info(f"📝 Formatting successful delete response for: {allergy_name}")
            info_logger.info(f"🔍 Updated allergies data: {updated_allergies}")
            
            # ✅ FIXED: Check if we have valid updated allergies data
            if updated_allergies and "patientAllergies" in updated_allergies:
                allergies = updated_allergies.get("patientAllergies", [])
                info_logger.info(f"✅ Found {len(allergies)} remaining allergies")
                
                # Handle empty reaction descriptions properly and format as table
                if allergies:
                    allergies_display = "**🏥 Current Allergies**\n\n"
                    allergies_display += "| No. | Allergy | Severity | Reactions |\n"
                    allergies_display += "|----|---------|----------|----------|\n"
                    for i, a in enumerate(allergies, 1):
                        reactions = a['allergyReactionDescription'] if a['allergyReactionDescription'] else "None specified"
                        allergies_display += f"| {i} | {a['allergyDescription'].title()} | {a['allergySeverity'].title()} | {reactions.title()} |\n"
                else:
                    allergies_display = "**🏥 Current Allergies**\n\nNo known allergies."
            else:
                info_logger.warning("⚠️ No valid updated allergies data - using fallback message")
                allergies_display = "Unable to retrieve updated allergy list. The allergy has been deleted successfully."
            
            return {
                "speech": f"{allergy_name.title()} has been deleted from your allergy list. Here are your current allergies. Would you like to delete any other allergies or proceed to the next section?",
                "display": allergies_display
            }
        else:
            # Handle failed deletion
            error_message = result.get('message', 'Unknown error occurred')
            info_logger.error(f"❌ Delete failed for {allergy_name}: {error_message}")
            
            return {
                "speech": f"I'm sorry, I couldn't delete {allergy_name.title()}. {error_message}. Please try again.",
                "display": f"**❌ Failed to Delete Allergy**\n\n**{allergy_name.title()}:** {error_message}"
            }
      
    @staticmethod
    def format_search_allergy_response(result):
        """Format the response for allergy search into speech and display fields"""
        if result and result.get('success') and result.get('allergies'):
            allergies = result.get('allergies', [])
            
            # Create display text with formatted allergy table
            display_text = "**🔍 Search Results**\n\n"
            display_text += "| No. | Allergy Name |\n"
            display_text += "|----|----------|\n"
            for idx, allergy in enumerate(allergies, 1):
                display_text += f"| {idx} | {allergy.get('DESCRIPTION', 'N/A')} |\n"
            
            speech_text = f"I found {len(allergies)} allergies matching your search. Please tell me the full name of the allergy you want to add from the list below."
            
            return {
                "speech": speech_text,
                "display": display_text.strip(),
                "_search_results": result  # Store raw results for later use
            }
        else:
            error_msg = result.get('message', 'No allergies found') if result else 'Search failed'
            return {
                "speech": f"I couldn't find any allergies matching your search. {error_msg}. Please try a different search term.",
                "display": "**❌ No Search Results**\n\nNo matching allergies found."
            }
    
    @staticmethod
    def format_add_allergy_response(result):
        """Format the response for adding allergy into speech and display fields"""
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't add the allergy. {result}",
                "display": f"**❌ Failed to Add Allergy**\n\n{result}"
            }
            
        if result and result.get('success'):
            allergy_name = result.get('allergy_name', 'the allergy')
            severity = result.get('severity', '')
            reaction = result.get('reaction', '')
            
            return {
                "speech": f"Great! I've successfully added {allergy_name} with {severity} severity and {reaction} reaction to your allergy list. Would you like to add another allergy or are you done with allergies?",
                "display": f"**✅ Allergy Added Successfully**\n\n| Field | Details |\n|-------|----------|\n| **Allergy** | {allergy_name} |\n| **Severity** | {severity} |\n| **Reaction** | {reaction} |"
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't add the allergy. {error_message}",
                "display": f"**❌ Failed to Add Allergy**\n\n{error_message}"
            }
                              
    @staticmethod
    def format_remove_delete_medication_response(result):
        """Format the response for medication deletion into speech and display fields"""
        # Handle case where result is a string (likely an error message)
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't remove the medication. {result}",
                "display": f"**❌ Failed to Delete Medication**\n\n{result}"
            }
            
        if result and result.get('success'):
            medication_name = result.get('message', '').replace('Successfully removed ', '').title()
            
            return {
                "speech": f"I've successfully removed {medication_name} from your medication list. Is there anything else you would like to update?",
                "display": f"**✅ Medication Deleted**\n\n**{medication_name}** has been removed from your medications."
            }
        else:
            medication_query = "the medication"
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't remove {medication_query}. {error_message}",
                "display": f"**❌ Failed to Delete Medication**\n\n{error_message}"
            }
    
    @staticmethod
    def format_remove_delete_pharmacy_response(result):
        """Format the response for pharmacy deletion into speech and display fields"""
        # Handle case where result is a string (likely an error message)
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't remove the pharmacy. {result}",
                "display": f"**❌ Failed to Delete Pharmacy**\n\n{result}"
            }
        
        if result and result.get('success'):
            pharmacy_name = ""
            if 'deleted_pharmacy' in result and isinstance(result['deleted_pharmacy'], dict):
                pharmacy_name = result['deleted_pharmacy'].get('pharmacy_name', '').title()
            
            if not pharmacy_name:
                pharmacy_name = result.get('message', '').replace('Successfully removed ', '').title()
            
            return {
                "speech": f"I've successfully removed {pharmacy_name} from your pharmacy list. Is there anything else you would like to do?",
                "display": f"**✅ Pharmacy Deleted**\n\n**{pharmacy_name}** has been removed from your pharmacies."
            }
        else:
            pharmacy_query = "the pharmacy"
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't remove {pharmacy_query}. {error_message}",
                "display": f"**❌ Failed to Delete Pharmacy**\n\n{error_message}"
            }
    
    @staticmethod
    def format_search_pharmacy_response(result):
        """Format the response for pharmacy search into speech and display fields"""
        if result and result.get('success') and result.get('pharmacies'):
            pharmacies = result.get('pharmacies', [])
            count = len(pharmacies)
            
            speech = f"I found {count} {'pharmacy' if count == 1 else 'pharmacies'} matching your search. "
            if count > 0:
                speech += "Please tell me which one you'd like to add by saying the number (such as 'add the first one', 'select number 2', 'I want the 3rd one') or specify by name (like 'add WALGREENS DRUG STORE #02593')."
            
            display = f"**🔍 Search Results**\n\n**Found {count} {'pharmacy' if count == 1 else 'pharmacies'}:**\n\n"
            display += "| No. | Pharmacy Name | Address | Location | Phone |\n"
            display += "|----|---|---|---|---|\n"
            
            pharmacy_selection_map = []
            for idx, pharm in enumerate(pharmacies):
                pharmacy_id = pharm.get('pharmacy_id', '')
                info_logger.info(f"PHARMACY SELECTION MAP: Position #{idx + 1} (array index {idx}): '{pharm.get('pharmacy_name', '')}' → USE PHARMACY_ID: '{pharmacy_id}' (NOT {idx+1})")
                
                pharmacy_selection_map.append({
                    "position": idx + 1,
                    "array_index": idx,
                    "name": pharm.get('pharmacy_name', ''),
                    "pharmacy_id": pharmacy_id
                })
                
                pharmacy_name = pharm.get('pharmacy_name', '')
                pharmacy_address = pharm.get('pharmacy_address', '')
                pharmacy_location = f"{pharm.get('pharmacy_city', '')}, {pharm.get('pharmacy_state', '')} {pharm.get('pharmacy_zip', '')}"
                pharmacy_phone = format_phone_number(pharm.get('pharmacy_phone', ''))
                
                display += f"| {idx + 1} | **{pharmacy_name}** | {pharmacy_address} | {pharmacy_location} | `{pharmacy_phone}` |\n"
            response = {
                "speech": speech,
                "display": display,
                "_search_results": {
                    "pharmacies": pharmacies,
                    "pharmacy_selection_map": pharmacy_selection_map
                }
            }
            info_logger.info(f"PHARMACY SEARCH RESULTS ADDED TO RESPONSE: {json.dumps(pharmacy_selection_map)}")
            
            return response
        else:
            search_term = "your search"
            error_message = result.get('message', 'No results found') if result else 'No results found'
            
            return {
                "speech": f"I couldn't find any pharmacies matching {search_term}. {error_message} Please try another search term.",
                "display": f"**❌ No Results Found**\n\n{error_message}"
            }
            
    @staticmethod
    def format_search_medicine_response(result):
        """Format the response for medicine search into speech and display fields"""
        if result and result.get('success') and result.get('medications'):
            medicines = result.get('medications', [])
            count = len(medicines)
            
            speech = f"I found {count} {'medicine' if count == 1 else 'medicines'} matching your search. "
            if count > 0:
                speech += "Please tell me which one you'd like to add by saying the number (such as 'add the first one', 'select number 2', 'I want the 3rd one') or specify by name (like 'add Tylenol')."
            
            display = f"**🔍 Search Results**\n\n**Found {count} {'medicine' if count == 1 else 'medicines'}:**\n\n"
            display += "| No. | Medication Name | Generic Description | Controlled | Generic |\n"
            display += "|----|---|---|---|---|\n"
            
            medicine_selection_map = []
            for idx, med in enumerate(medicines):
                medicine_code = med.get('medication_id', '')
                medicine_name = med.get('medication_name', '')
                generic_description = med.get('generic_description', '')
                
                info_logger.info(f"MEDICINE SELECTION MAP: Position #{idx + 1} (array index {idx}): '{medicine_name}' → USE MEDICINE_CODE: '{medicine_code}' (NOT {idx+1})")
                
                medicine_selection_map.append({
                    "position": idx + 1,
                    "array_index": idx,
                    "name": medicine_name,
                    "medicine_code": medicine_code,
                    "generic_description": generic_description
                })
                
                controlled_status = '✅ Yes' if med.get('controlled', False) else '❌ No'
                generic_status = '✅ Yes' if med.get('generic', False) else '❌ No'
                
                display += f"| {idx + 1} | **{medicine_name}** | {generic_description} | {controlled_status} | {generic_status} |\n"
            
            response = {
                "speech": speech,
                "display": display,
                "_search_results": {
                    "medicines": medicines,
                    "medicine_selection_map": medicine_selection_map
                }
            }
            info_logger.info(f"MEDICINE SEARCH RESULTS ADDED TO RESPONSE: {json.dumps(medicine_selection_map)}")
            
            return response
        else:
            search_term = "your search"
            error_message = result.get('message', 'No results found') if result else 'No results found'
            
            return {
                "speech": f"I couldn't find any medicines matching {search_term}. {error_message} Please try another search term.",
                "display": f"**❌ No Results Found**\n\n{error_message}"
            }
    
    @staticmethod
    def format_add_pharmacy_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't add the pharmacy. {result}",
                "display": f"**❌ Failed to Add Pharmacy**\n\n{result}"
            }
            
        # Handle the direct success case from API
        if result.get("success") == True:
            return {
                "speech": "Great! I've added the pharmacy to your profile. Is there anything else you would like to do with your pharmacies?",
                "display": "**✅ Pharmacy Added Successfully**\n\nPharmacy has been successfully added to your profile."
            }
            
        # Legacy format with nested response
        response = result.get("response", {})
        if response.get("success"):
            return {
                "speech": "Great! I've added the pharmacy to your profile. Is there anything else you would like to do with your pharmacies?",
                "display": "**✅ Pharmacy Added Successfully**\n\nPharmacy has been successfully added to your profile."
            }
        else:
            error_message = result.get("message", "Unknown error occurred")
            if not error_message and response:
                error_message = response.get("message", "Unknown error occurred")

            return {
                "speech": f"I'm sorry, I couldn't add the pharmacy. {error_message}",
                "display": f"**❌ Failed to Add Pharmacy**\n\n{error_message}"
            }
    
    @staticmethod
    def format_medication_sig_response(result):
        """Format the response for medication SIG instructions into speech and display fields"""
        if result and result.get('success'):
            medication_name = result.get('medication_name', 'the medication')
            sig = result.get('sig', '')
            
            return {
                "speech": f"Thank you for providing the instructions for {medication_name}. Now, can you tell me what condition or diagnosis this medication is for? For example, is it for blood pressure, diabetes, heart condition, etc.?",
                "display": f"**✅ Instructions Recorded**\n\n**Medication:** {medication_name}\n\n**Instructions:** `{sig}`"
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't record the medication instructions. {error_message}",
                "display": f"**❌ Failed to Record Instructions**\n\n{error_message}"
            }
    
    @staticmethod
    def format_search_diagnosis_response(result):
        if result and result.get('success') and result.get('diagnoses'):
            diagnoses = result.get('diagnoses', [])
            count = len(diagnoses)
            speech = f"I found {count} {'diagnosis' if count == 1 else 'diagnoses'} matching your search. "
            if count > 0:
                speech += "Please tell me which one matches your condition by saying the number (such as 'first one', 'number 2', 'the 3rd one') or specify by name."
            
            display = f"**🔍 Search Results**\n\n**Found {count} {'diagnosis' if count == 1 else 'diagnoses'}:**\n\n"
            display += "| No. | Diagnosis Description | ICD-10 Code |\n"
            display += "|----|---|---|\n"
            
            diagnosis_selection_map = []
            for idx, diag in enumerate(diagnoses):
                diagnosis_code = diag.get('diagnosis_code', '')
                diagnosis_description = diag.get('diagnosis_description', '')
                
                info_logger.info(f"DIAGNOSIS SELECTION MAP: Position #{idx + 1} (array index {idx}): '{diagnosis_description}' → USE DIAGNOSIS_CODE: '{diagnosis_code}' (NOT {idx+1})")
                
                diagnosis_selection_map.append({
                    "position": idx + 1,
                    "array_index": idx,
                    "description": diagnosis_description,
                    "diagnosis_code": diagnosis_code
                })
                
                display += f"| {idx + 1} | **{diagnosis_description}** | `{diagnosis_code}` |\n"
            
            response = {
                "speech": speech,
                "display": display,
                "_search_results": {
                    "diagnoses": diagnoses,
                    "diagnosis_selection_map": diagnosis_selection_map
                }
            }
            info_logger.info(f"DIAGNOSIS SEARCH RESULTS ADDED TO RESPONSE: {json.dumps(diagnosis_selection_map)}")
            
            return response
        else:
            search_term = "your search"
            error_message = result.get('message', 'No results found') if result else 'No results found'
            
            return {
                "speech": f"I couldn't find any diagnoses matching {search_term}. {error_message} Please try another search term, or we can continue without adding a diagnosis.",
                "display": f"**❌ No Results Found**\n\n{error_message}"
            }
    
    @staticmethod
    def format_save_medication_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't save the medication. {result}",
                "display": f"**❌ Failed to Save Medication**\n\n{result}"
            }
            
        if result and result.get('success'):
            medication_name = result.get('message', '').replace('Successfully added ', '').title()
            
            return {
                "speech": f"Great! I've successfully added {medication_name} to your medications. Is there anything else you would like to add or modify in your medication list?",
                "display": f"**✅ Medication Added Successfully**\n\n**{medication_name}** has been added to your medications."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't save the medication. {error_message}",
                "display": f"**❌ Failed to Save Medication**\n\n{error_message}"
            }
    
    @staticmethod
    def format_get_family_history_response(result):
        
        if result and result.get('success') and result.get('family_history'):
            family_history = result.get('family_history', [])
            count = len(family_history)
            
            speech = f"I found {count} family history {'entry' if count == 1 else 'entries'} matching your search. "
            if count > 0:
                speech += "Please tell me which one you'd like to select by saying the number (such as 'select the first one', 'number 2', 'the 3rd one') or specify by name."
            
            display = f"Found {count} family history {'entry' if count == 1 else 'entries'}:\n\n"
            
            family_history_selection_map = []
            for idx, fh in enumerate(family_history):
                family_history_id = fh.get('family_history_id', '')
                disease_name = fh.get('disease_name', '')
                relationship = fh.get('relationship', '')
                
                family_history_selection_map.append({
                    "position": idx + 1,
                    "array_index": idx,
                    "disease_name": disease_name,
                    "relationship": relationship,
                    "family_history_id": family_history_id
                })
                
                display += (
                    f"{idx + 1}. {disease_name}\n"
                    f"   Relationship: {relationship}\n"
                    f"   Age at Onset: {fh.get('age_at_onset', 'Unknown')}\n"
                    f"   Description: {fh.get('description', 'N/A')}\n\n"
                )
            
            response = {
                "speech": speech,
                "display": display,
                "_search_results": {
                    "family_history": family_history,
                    "family_history_selection_map": family_history_selection_map
                }
            }
            return response
        else:
            search_term = "your search"
            error_message = result.get('message', 'No results found') if result else 'No results found'
            
            return {
                "speech": f"I couldn't find any family history matching {search_term}. {error_message} Please try another search term.",
                "display": f"No family history found: {error_message}"
            }

    @staticmethod
    def format_add_family_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't add the family history. {result}",
                "display": f"**❌ Failed to Add Family History**\n\n{result}"
            }
            
        if result and result.get('success'):
            disease_name = result.get('disease_name', 'the condition').title()
            relationship = result.get('relationship', 'family member').title()
            
            return {
                "speech": f"Great! I've successfully added {disease_name} for your {relationship} to your family history. Would you like to add another family history entry or are you done with family history?",
                "display": f"**✅ Family History Added**\n\n**{disease_name}** has been added to your family history.\n\n- **Relationship:** {relationship}"
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't add the family history. {error_message}",
                "display": f"**❌ Failed to Add Family History**\n\n{error_message}"
            }

    @staticmethod
    def format_remove_delete_family_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't remove the family history entry. {result}",
                "display": f"**❌ Failed to Delete Family History**\n\n{result}"
            }
            
        if result and result.get('success'):
            disease_name = result.get('disease_name', 'the family history entry').title()
            relationship = result.get('relationship', 'family member').title()
            
            return {
                "speech": f"I've successfully removed {disease_name} for your {relationship} from your family history. Is there anything else you would like to update?",
                "display": f"**✅ Family History Deleted**\n\n**{disease_name}** ({relationship}) has been removed from your family history."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't remove the family history entry. {error_message}",
                "display": f"**❌ Failed to Delete Family History**\n\n{error_message}"
            }

    @staticmethod
    def format_get_common_diseases_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't retrieve the common diseases list. {result}",
                "display": f"**❌ Failed to Get Common Diseases**\n\n{result}"
            }
        
        if result and isinstance(result, list) and len(result) > 0:
            count = len(result)
            
            speech = f"Here are {count} common diseases you can choose from for your family history. Please tell me which disease you'd like to add by saying the name or number."
            
            display = f"**🔍 Common Diseases**\n\n**{count} options available:**\n\n"
            
            for idx, disease in enumerate(result):
                disease_name = disease.get('diseaseName', 'Unknown disease')
                disease_code = disease.get('diseaseCode', '')
                display += f"{idx + 1}. **{disease_name}**\n   - Code: `{disease_code}`\n\n"
            
            return {
                "speech": speech,
                "display": display.strip()
            }
        else:
            return {
                "speech": "I'm sorry, I couldn't retrieve the common diseases list. Please try again.",
                "display": "**❌ No Common Diseases Available**\n\nPlease try again later."
            }

    @staticmethod
    def format_get_family_history_response(result):
        if result and isinstance(result, list) and len(result) > 0:
            count = len(result)
            
            speech = f"Here is your family history with {count} {'entry' if count == 1 else 'entries'}. "
            speech += "You can add new entries, update existing ones, or delete entries by telling me what you'd like to do."
            
            display = f"**👨‍👩‍👧‍👦 Your Family History**\n\n"
            display += "| No. | Condition | Relationship | Status |\n"
            display += "|----|---|---|---|\n"
            
            for idx, fh in enumerate(result, 1):
                condition = fh.get('disease_name', 'Unknown condition')
                relationship = fh.get('relationship', 'Unknown')
                deceased = fh.get('deceased', '')
                status = 'Deceased' if deceased == '1' else 'Alive'
                
                display += f"| {idx} | **{condition.title()}** | {relationship.title()} | {status} |\n"
            
            return {
                "speech": speech,
                "display": display.strip()
            }
        else:
            return {
                "speech": "You currently have no family history on record. Would you like to add some family history information?",
                "display": "**👨‍👩‍👧‍👦 Your Family History**\n\n⚠️ No family history on record."
            }
    
    @staticmethod
    def format_get_past_surgical_history_response(result):
        if result and isinstance(result, list) and len(result) > 0:
            count = len(result)
            
            speech = f"Here is your past surgical history with {count} {'entry' if count == 1 else 'entries'}. "
            speech += "You can add new entries, update existing ones, or delete entries by telling me what you'd like to do."
            
            display = f"**🏥 Your Past Surgical History**\n\n"
            display += "| No. | Surgery | Date | Place | Complications |\n"
            display += "|----|---|---|---|---|\n"
            
            for idx, surgery in enumerate(result, 1):
                surgery_name = surgery.get('surgery_name', 'Unknown surgery').title()
                surgery_date = surgery.get('surgery_date', 'Unknown')
                surgery_place = surgery.get('surgery_place', 'Unknown').title()
                complications = surgery.get('post_surgery_complications', 'None recorded').title()
                
                display += f"| {idx} | **{surgery_name}** | {surgery_date} | {surgery_place} | {complications} |\n"
            
            return {
                "speech": speech,
                "display": display.strip()
            }
        else:
            return {
                "speech": "You currently have no past surgical history on record. Would you like to add some surgical history information?",
                "display": "**🏥 Your Past Surgical History**\n\n⚠️ No past surgical history on record."
            }

    @staticmethod
    def format_save_past_surgical_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't add the surgical history. {result}",
                "display": f"**❌ Failed to Add Surgical History**\n\n{result}"
            }
            
        if result and result.get('success'):
            surgery_name = result.get('surgery_name', 'the surgery').title()
            surgery_date = result.get('surgery_date', '')
            surgery_place = result.get('surgery_place', '').title()
            
            return {
                "speech": f"Great! I've successfully added {surgery_name} from {surgery_date} to your past surgical history. Would you like to add another surgical history entry or are you done with surgical history?",
                "display": f"**✅ Surgical History Added**\n\n**{surgery_name}** has been added to your surgical history.\n\n- **Date:** {surgery_date}\n- **Place:** {surgery_place}"
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't add the surgical history. {error_message}",
                "display": f"**❌ Failed to Add Surgical History**\n\n{error_message}"
            }

    @staticmethod
    def format_delete_past_surgical_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't remove the surgical history entry. {result}",
                "display": f"**❌ Failed to Delete Surgical History**\n\n{result}"
            }
            
        if result and result.get('success'):
            surgery_name = result.get('surgery_name', 'the surgical history entry')
            
            return {
                "speech": f"I've successfully removed {surgery_name} from your past surgical history. Is there anything else you would like to update?",
                "display": f"**✅ Surgical History Deleted**\n\n**{surgery_name}** has been removed from your past surgical history."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't remove the surgical history entry. {error_message}",
                "display": f"**❌ Failed to Delete Surgical History**\n\n{error_message}"
            }

    @staticmethod
    def format_get_past_hospitalization_response(result):
      
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't retrieve your past hospitalization history. {result}",
                "display": f"**❌ Failed to Get Past Hospitalization**\n\n{result}"
            }
        
        if not result or len(result) == 0:
            return {
                "speech": "I see that you don't have any past hospitalization records on file. Would you like to add any hospitalization information?",
                "display": "**🏥 Your Past Hospitalization History**\n\n⚠️ No past hospitalization records found.\n\nWould you like to add any hospitalization information?"
            }
        
        count = len(result)
        speech_text = f"Here is your past hospitalization history with {count} {'entry' if count == 1 else 'entries'}. "
        speech_text += "Would you like to make any changes to your hospitalization history?"
        
        display_text = f"**🏥 Your Past Hospitalization History**\n\n"
        display_text += "| No. | Reason | Date | Duration | Comments |\n"
        display_text += "|----|---|---|---|---|\n"
        
        for i, hosp in enumerate(result, 1):
            reason = hosp.get('reason', 'Unknown reason')
            hosp_date = hosp.get('hosp_date', 'Unknown date')
            duration = hosp.get('duration', 'Unknown duration')
            comments = hosp.get('comments', 'None')
            
            display_text += f"| {i} | **{reason}** | {hosp_date} | {duration} | {comments} |\n"
        
        display_text += "\n---\n\n*Would you like to make any changes?*"
        
        return {
            "speech": speech_text,
            "display": display_text
        }

    @staticmethod
    def format_save_past_hospitalization_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't add the hospitalization. {result}",
                "display": f"**❌ Failed to Add Hospitalization**\n\n{result}"
            }
            
        if result and result.get('success'):
            reason = result.get('reason', 'the hospitalization')
            hosp_date = result.get('hosp_date', '')
            duration = result.get('duration', '')
            comment = result.get('comment', '')
            
            speech_text = f"Great! I've successfully added {reason} from {hosp_date} for {duration} to your past hospitalization history."
            if comment:
                speech_text += f" Comments: {comment}."
            speech_text += " Would you like to add another hospitalization entry or are you done with hospitalization history?"
            
            display_text = f"**✅ Hospitalization Added**\n\n**{reason}** has been added to your hospitalization history.\n\n- **Date:** {hosp_date}\n- **Duration:** {duration}"
            if comment:
                display_text += f"\n- **Comments:** {comment}"
            
            return {
                "speech": speech_text,
                "display": display_text
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't add the hospitalization. {error_message}",
                "display": f"**❌ Failed to Add Hospitalization**\n\n{error_message}"
            }

    @staticmethod
    def format_delete_past_hospitalization_response(result):
        """Format the response for deleting past hospitalization into speech and display fields"""
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't remove the hospitalization entry. {result}",
                "display": f"**❌ Failed to Delete Hospitalization**\n\n{result}"
            }
            
        if result and result.get('success'):
            reason = result.get('reason', 'the hospitalization entry')
            
            return {
                "speech": f"I've successfully removed {reason} from your past hospitalization history. Is there anything else you would like to update?",
                "display": f"**✅ Hospitalization Deleted**\n\n**{reason}** has been removed from your past hospitalization history."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't remove the hospitalization entry. {error_message}",
                "display": f"**❌ Failed to Delete Hospitalization**\n\n{error_message}"
            }

    @staticmethod
    def format_get_social_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't retrieve your social history. {result}",
                "display": f"**❌ Failed to Get Social History**\n\n{result}"
            }

        if not result or not any(result.values()):
            return {
                "speech": "I see that you don't have any social history records on file. Would you like to add your social history information? This helps your healthcare provider understand lifestyle factors that may affect your health.",
                "display": "**🏠 Your Social History**\n\n⚠️ No social history records found.\n\nWould you like to add your social history information?"
            }
        
        speech = "Here is your current social history information. You can update any of this information if needed."

        display = "**🏠 Your Social History**\n\n"
        
        # Format tobacco status
        tobacco_status = result.get('tobaccoStatus', '')
        if tobacco_status and '|' in tobacco_status:
            tobacco_display = tobacco_status.split('|')[1] if len(tobacco_status.split('|')) > 1 else tobacco_status
        else:
            tobacco_display = tobacco_status or 'Not specified'
        display += f"- **🚬 Tobacco Status:** {tobacco_display}\n"

        # Format alcohol usage
        alcohol_usage = result.get('alcoholDay', '') or 'Not specified'
        display += f"- **🍷 Alcohol Usage:** {alcohol_usage}\n"

        # Format drug use
        drug_use = result.get('drugUse', '') or 'Not specified'
        display += f"- **💊 Drug Use:** {drug_use}\n"

        # Format feels safe at home
        feels_safe = result.get('feelsSafe', '')
        if feels_safe == 'True':
            feels_safe_display = '✅ Yes'
        elif feels_safe == 'False':
            feels_safe_display = '❌ No'
        else:
            feels_safe_display = '⚠️ Not specified'
        display += f"- **✅ Feels Safe at Home:** {feels_safe_display}\n"
        
        display += "\n---\n\n*Would you like to make any changes to your social history?*"
        
        return {"speech": speech,"display": display}
    
    @staticmethod
    def format_save_social_history_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't save your social history. {result}",
                "display": f"**❌ Failed to Save Social History**\n\n{result}"
            }
            
        if result and result.get('success'):
            return {
                "speech": "Great! I've successfully saved your social history information. Is there anything else you would like to update in your social history?",
                "display": "**✅ Social History Saved**\n\nYour social history has been successfully updated."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't save your social history. {error_message}",
                "display": f"**❌ Failed to Save Social History**\n\n{error_message}"
            }
        
    @staticmethod
    def format_get_patient_insurance_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't retrieve your insurance information. {result}",
                "display": f"**❌ Failed to Get Insurance**\n\n{result}"
            }

        if not result or not any([result.get('primary'), result.get('secondary'), result.get('other')]):
            return {
                "speech": "I see that you don't have any insurance information on file. Would you like to add insurance plans? You can add Primary, Secondary, or Other insurance coverage.",
                "display": "**💳 Your Insurance Plans**\n\n⚠️ No insurance plans found.\n\n**Available to Add:** Primary, Secondary, Other"
            }
        
        speech = "Here are your current insurance plans. You can delete existing plans or add new ones if needed."
        display = "**💳 Your Insurance Plans**\n\n"
        
        # Format Primary Insurance
        if result.get('primary'):
            primary = result['primary']
            display += f"**🔷 Primary Insurance**\n"
            display += f"- **Name:** {primary.get('insurance_name', 'N/A')}\n"
            display += f"- **Policy Number:** `{primary.get('policy_number', 'N/A')}`\n"
            display += f"- **Relationship:** {primary.get('relationship', 'N/A')}\n"
            
            # Build complete address
            address_parts = []
            if primary.get('insurance_address'):
                address_parts.append(primary.get('insurance_address'))
            if primary.get('insurance_city'):
                address_parts.append(primary.get('insurance_city'))
            if primary.get('insurance_state'):
                address_parts.append(primary.get('insurance_state'))
            if primary.get('insurance_zip'):
                address_parts.append(primary.get('insurance_zip'))
            
            complete_address = ', '.join(filter(None, address_parts)) if address_parts else 'N/A'
            display += f"- **Address:** {complete_address}\n\n"
        
        # Format Secondary Insurance
        if result.get('secondary'):
            secondary = result['secondary']
            display += f"**🔶 Secondary Insurance**\n"
            display += f"- **Name:** {secondary.get('insurance_name', 'N/A')}\n"
            display += f"- **Policy Number:** `{secondary.get('policy_number', 'N/A')}`\n"
            display += f"- **Relationship:** {secondary.get('relationship', 'N/A')}\n"
            
            # Build complete address
            address_parts = []
            if secondary.get('insurance_address'):
                address_parts.append(secondary.get('insurance_address'))
            if secondary.get('insurance_city'):
                address_parts.append(secondary.get('insurance_city'))
            if secondary.get('insurance_state'):
                address_parts.append(secondary.get('insurance_state'))
            if secondary.get('insurance_zip'):
                address_parts.append(secondary.get('insurance_zip'))
            
            complete_address = ', '.join(filter(None, address_parts)) if address_parts else 'N/A'
            display += f"- **Address:** {complete_address}\n\n"
        
        # Format Other Insurance
        if result.get('other'):
            other = result['other']
            display += f"**🔸 Other Insurance**\n"
            display += f"- **Name:** {other.get('insurance_name', 'N/A')}\n"
            display += f"- **Policy Number:** `{other.get('policy_number', 'N/A')}`\n"
            display += f"- **Relationship:** {other.get('relationship', 'N/A')}\n"
            
            # Build complete address
            address_parts = []
            if other.get('insurance_address'):
                address_parts.append(other.get('insurance_address'))
            if other.get('insurance_city'):
                address_parts.append(other.get('insurance_city'))
            if other.get('insurance_state'):
                address_parts.append(other.get('insurance_state'))
            if other.get('insurance_zip'):
                address_parts.append(other.get('insurance_zip'))
            
            complete_address = ', '.join(filter(None, address_parts)) if address_parts else 'N/A'
            display += f"- **Address:** {complete_address}\n\n"
        
        # Show available slots
        available_slots = []
        if not result.get('primary'):
            available_slots.append("Primary")
        if not result.get('secondary'):
            available_slots.append("Secondary")
        if not result.get('other'):
            available_slots.append("Other")
        
        if available_slots:
            display += f"---\n\n**Available to Add:** {', '.join(available_slots)}"
        
        return {"speech": speech, "display": display.strip()}

    @staticmethod
    def format_delete_patient_insurance_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't delete the insurance. {result}",
                "display": f"**❌ Failed to Delete Insurance**\n\n{result}"
            }
            
        if result and result.get('success'):
            return {
                "speech": "I've successfully removed the insurance plan from your profile. Would you like to delete another insurance plan or add a new one?",
                "display": "**✅ Insurance Deleted**\n\nInsurance plan has been successfully removed from your profile."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't delete the insurance plan. {error_message}",
                "display": f"**❌ Failed to Delete Insurance**\n\n{error_message}"
            }

    @staticmethod
    def format_search_insurance_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't search for insurance plans. {result}",
                "display": f"**❌ Failed to Search Insurance**\n\n{result}"
            }

        if result and result.get('success') and result.get('insurances'):
            insurances = result.get('insurances', [])
            
            speech = f"I found {len(insurances)} insurance plans matching your search. Please tell me which insurance you want to add by saying the number or name."
            
            display = f"**🔍 Insurance Search Results**\n\n**{len(insurances)} plans found:**\n\n"
            display += "| No. | Insurance Name | ID | Address | Location |\n"
            display += "|----|---|---|---|---|\n"
            
            insurance_selection_map = []
            for idx, insurance in enumerate(insurances):
                insurance_name = insurance.get('insurance_name', '')
                insurance_id = insurance.get('insurance_id', '')
                insurance_address = insurance.get('insurance_address', '')
                insurance_city = insurance.get('insurance_city', '')
                insurance_state = insurance.get('insurance_state', '')
                insurance_location = f"{insurance_city}, {insurance_state}" if insurance_city and insurance_state else ""
                
                info_logger.info(f"INSURANCE SELECTION MAP: Position #{idx + 1} (array index {idx}): '{insurance_name}' → USE INSURANCE_ID: '{insurance_id}' (NOT {idx+1})")
                
                insurance_selection_map.append({
                    "position": idx + 1,
                    "array_index": idx,
                    "name": insurance_name,
                    "insurance_id": insurance_id
                })
                
                display += f"| {idx + 1} | **{insurance_name}** | `{insurance_id}` | {insurance_address} | {insurance_location} |\n"
            
            response = {
                "speech": speech,
                "display": display.strip(),
                "_search_results": {
                    "insurances": insurances,
                    "insurance_selection_map": insurance_selection_map
                }
            }
            info_logger.info(f"INSURANCE SEARCH RESULTS ADDED TO RESPONSE: {json.dumps(insurance_selection_map)}")
            
            return response
        else:
            error_message = result.get('message', 'No insurance plans found') if result else 'Search failed'
            
            return {
                "speech": f"I couldn't find any insurance plans matching your search. {error_message} Please try another search term.",
                "display": f"**❌ No Results Found**\n\n{error_message}"
            }

    @staticmethod
    def format_get_zip_city_state_response(result):

        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't look up the ZIP code. {result}",
                "display": f"**❌ Failed to Lookup ZIP Code**\n\n{result}"
            }
            
        if result and result.get('success'):
            zip_code = result.get('zip_code', '')
            city = result.get('city', '')
            state = result.get('state', '')
            
            return {
                "speech": f"Based on ZIP code {zip_code}, I found the city as {city}, {state}. Is this correct?",
                "display": f"**📍 ZIP Code Lookup**\n\n- **ZIP:** `{zip_code}`\n- **City:** {city}\n- **State:** {state}"
            }
        else:
            error_message = result.get('message', 'Invalid ZIP code') if result else 'ZIP lookup failed'
            
            return {
                "speech": f"I'm sorry, I couldn't look up that ZIP code. {error_message} Please provide a valid ZIP code.",
                "display": f"**❌ ZIP Code Lookup Failed**\n\n{error_message}"
            }

    @staticmethod
    def format_save_subscriber_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't save the subscriber information. {result}",
                "display": f"**❌ Failed to Save Subscriber**\n\n{result}"
            }
            
        if result and result.get('success'):
            guarantor_code = result.get('guarantor_code', '')
            
            return {
                "speech": "Great! I've successfully saved the subscriber information. Now I'll save the insurance plan with this subscriber information.",
                "display": f"**✅ Subscriber Information Saved**\n\nSubscriber information saved successfully.\n\n- **Guarantor Code:** `{guarantor_code}`"
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't save the subscriber information. {error_message}",
                "display": f"**❌ Failed to Save Subscriber**\n\n{error_message}"
            }

    @staticmethod
    def format_save_insurance_response(result):
        if isinstance(result, str):
            return {
                "speech": f"I'm sorry, I couldn't save the insurance plan. {result}",
                "display": f"**❌ Failed to Save Insurance**\n\n{result}"
            }
            
        if result and result.get('success'):
            return {
                "speech": "Excellent! I've successfully added the insurance plan to your profile. Would you like to add another insurance plan or are you done with insurance management?",
                "display": "**✅ Insurance Plan Added**\n\nInsurance plan has been successfully added to your profile."
            }
        else:
            error_message = result.get('message', 'Unknown error occurred') if result else 'Unknown error occurred'
            
            return {
                "speech": f"I'm sorry, I couldn't save the insurance plan. {error_message}",
                "display": f"**❌ Failed to Save Insurance**\n\n{error_message}"
            }


    @staticmethod
    def generate_response_v2(prompt: str, tools: list[types.Tool] = None, thinking_budget: Optional[int] = None):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "config/aiml-365220-b6aec5dba4a2.json"
            
            client = genai.Client(
                vertexai=True,
                project="aiml-365220",
                location="us-central1",
            )
            
            info_logger.info(f"Sending prompt with thinking budget: {thinking_budget}")
            model_name = "gemini-2.5-pro-preview-05-06"
            info_logger.info(f"Using model name: {model_name}")
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)]
                ),
            ]
            tools = tools
            generate_content_config = types.GenerateContentConfig(
                temperature=0.2,
                top_p=0.95,
                max_output_tokens=8192,
                tools=[tools]
            )
            model_start_time = time.time()
            info_logger.info(f"📡 MODEL REQUEST STARTED at {model_start_time}")
        
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=generate_content_config
                )
                    # 🕐 END TIMING - Calculate elapsed time
            model_end_time = time.time()
            model_response_time = model_end_time - model_start_time
            
            # 📊 LOG MODEL RESPONSE TIME
            info_logger.info(f"⏱️ MODEL RESPONSE TIME: {model_response_time:.3f} seconds ({model_response_time*1000:.1f}ms)")
            info_logger.info(f"📡 MODEL REQUEST COMPLETED at {model_end_time}")

            candidate = response.candidates[0]
            
            if not hasattr(candidate, 'content') or candidate.content is None or not hasattr(candidate.content, 'parts') or candidate.content.parts is None:
                finish_message = candidate.finish_message if hasattr(candidate, 'finish_message') else "No details available"
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else "Unknown reason"
                info_logger.warning(f"Response has no content.parts. Finish message: {finish_message}")
                info_logger.warning(f"Finish reason: {finish_reason}")
                return {
                    "speech": "I'm sorry, I encountered an issue processing your request. Please try again.",
                    "display": "There was a problem processing your request. Please try again."
                }
            
            parts = candidate.content.parts
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call is not None:
                    func = part.function_call
                    args = func.args
                    info_logger.info(f"Function call detected: {func.name} with args: {args}")

                    if func.name == "update_demo":
                        result = DBops.update_demo(**args)
                        result =GenerateResponse.format_update_demo_response(args, result)
                        info_logger.info(f"Result from DBops.update_demo: {result}")
                        return result
                    
                    elif func.name == "delete_patient_allergy":
                        # Delete the allergy
                        result = Allergies.delete_patient_allergy(**args, uid=str(uuid.uuid4()))
                        
                        if result.get("success"):
                            info_logger.info(f" Successfully deleted allergy {args.get('allergy_id')}")
                            
                            try:
                                info_logger.info("🔍 Fetching updated allergies after deletion...")
                                updated_allergies = Allergies.get_patient_allergies(
                                    patient_account=args.get("patient_account"),
                                    practice_code=args.get("practice_code"),
                                    uid=str(uuid.uuid4())
                                )
                                info_logger.info(f"🔍 Updated allergies response: {updated_allergies}")
                                
                                if updated_allergies and "patientAllergies" in updated_allergies:
                                    allergy_count = len(updated_allergies.get("patientAllergies", []))
                                    info_logger.info(f"Successfully fetched {allergy_count} remaining allergies")
                                else:
                                    info_logger.warning(f"Failed to fetch updated allergies: {updated_allergies}")
                                    updated_allergies = None
                                    
                            except Exception as e:
                                error_logger.error(f"Exception while fetching updated allergies: {str(e)}")
                                updated_allergies = None
                        else:
                            info_logger.error(f"Failed to delete allergy: {result}")
                            updated_allergies = None
                            
                        return GenerateResponse.format_delete_allergy_response(args, result, updated_allergies)

                    
                    elif func.name == "handle_remove_delete_medication":
                        result = handle_remove_delete_medication(**args)
                        result = GenerateResponse.format_remove_delete_medication_response(result)
                        info_logger.info(f"Result from handle_remove_delete_medication: {result}")  
                        return result
                    
                    elif func.name == "handle_remove_delete_pharmacy":
                        result = handle_remove_delete_pharmacy(**args)
                        formatted_result = GenerateResponse.format_remove_delete_pharmacy_response(result)
                        info_logger.info(f"Result from handle_remove_delete_pharmacy: {result}")
                        info_logger.info(f"Formatted result for remove_delete_pharmacy: {formatted_result}")    
                        return formatted_result

                    elif func.name == "handle_add_pharmacy":
                        result = handle_add_pharmacy(**args)
                        formatted_result = GenerateResponse.format_add_pharmacy_response(result)
                        info_logger.info(f"Result from handle_add_pharmacy: {result}")
                        info_logger.info(f"Formatted result for add_pharmacy: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_search_pharmacy":
                        result = handle_search_pharmacy(**args)
                        formatted_result = GenerateResponse.format_search_pharmacy_response(result)
                        info_logger.info(f"Result from handle_search_pharmacy: {result}")
                        info_logger.info(f"Formatted result for search_pharmacy: {formatted_result}")
                        return formatted_result


            if hasattr(response, 'thinking'):
                info_logger.info(f"Model thinking process: {response.thinking}")
            
            if hasattr(response, 'text'):
                text_content = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                text_content = response.candidates[0].text
            # else:
            #     return {
            #         "speech": "I'm sorry, I couldn't process your request.",
            #         "display": "No response content available."
            #     }
            
            try:
                cleaned_text = GenerateResponse.clean_response(text_content)
                parsed_response = json.loads(cleaned_text)
                
                if "speech" in parsed_response and "display" in parsed_response:
                    if isinstance(parsed_response["speech"], list):
                        parsed_response["speech"] = " ".join(parsed_response["speech"])
                    return parsed_response
                else:
                    return {
                        "speech": "I have some information for you.",
                        "display": cleaned_text
                    }
                    
            except json.JSONDecodeError:
                display_text = "" if text_content is None else text_content.strip()
                return {
                    "speech": "Here's the information you requested.",
                    "display": display_text
                }

        except Exception as e:
            error_logger.error(f"Error generating response: {e}")
            error_logger.error(f"Stack trace: {traceback.format_exc()}")
            raise ApplicationException(f"Gemini Response Error: {e}")
        
    @staticmethod
    def generate_response_v3(prompt: str ,tools: list[types.Tool] = None):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "config/aiml-365220-b6aec5dba4a2.json"
            
            client = genai.Client(
                vertexai=True,
                project="aiml-365220",
                location="us-central1",
            )
            
            model_name = "gemini-2.5-flash"
            info_logger.info(f"Using model name: {model_name}")
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)]
                ),
            ]
            tools = tools
            generate_content_config = types.GenerateContentConfig(
                temperature=0.3,
                top_p=0.95,
                max_output_tokens=8192,
                tools=tools if tools else []
            )
            
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=generate_content_config
                )

            candidate = response.candidates[0]
            if not hasattr(candidate, 'content') or candidate.content is None or not hasattr(candidate.content, 'parts') or candidate.content.parts is None:
                finish_message = candidate.finish_message if hasattr(candidate, 'finish_message') else "No details available"
                finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else "Unknown reason"
                info_logger.warning(f"Response has no content.parts. Finish message: {finish_message}")
                info_logger.warning(f"Finish reason: {finish_reason}")
                return {
                    "speech": "I'm sorry, I encountered an issue processing your request. Please try again.",
                    "display": "There was a problem processing your request. Please try again."
                }
            
            parts = candidate.content.parts
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call is not None:
                    func = part.function_call
                    args = func.args
                    info_logger.info(f"Function call detected: {func.name} with args: {args}")

                    if func.name == "update_demo":
                        result = DBops.update_demo(**args)
                        result =GenerateResponse.format_update_demo_response(args, result)
                        info_logger.info(f"Result from DBops.update_demo: {result}")
                        return result

                    elif func.name == "delete_patient_allergy":
                        # Delete the allergy
                        result = Allergies.delete_patient_allergy(**args, uid=str(uuid.uuid4()))
                        
                        if result.get("success"):
                            info_logger.info(f"✅ Successfully deleted allergy {args.get('allergy_id')}")
                            try:
                                info_logger.info("🔍 Fetching updated allergies after deletion...")
                                updated_allergies = Allergies.get_patient_allergies(
                                    patient_account=args.get("patient_account"),
                                    practice_code=args.get("practice_code"),
                                    uid=str(uuid.uuid4())
                                )
                                info_logger.info(f"🔍 Updated allergies response: {updated_allergies}")
                                if updated_allergies and "patientAllergies" in updated_allergies:
                                    allergy_count = len(updated_allergies.get("patientAllergies", []))
                                    info_logger.info(f"✅ Successfully fetched {allergy_count} remaining allergies")
                                else:
                                    info_logger.warning(f"⚠️ Failed to fetch updated allergies: {updated_allergies}")
                                    updated_allergies = None
                                    
                            except Exception as e:
                                error_logger.error(f"❌ Exception while fetching updated allergies: {str(e)}")
                                updated_allergies = None
                        else:
                            info_logger.error(f"❌ Failed to delete allergy: {result}")
                            updated_allergies = None
                            
                        return GenerateResponse.format_delete_allergy_response(args, result, updated_allergies)
                
                    elif func.name == "search_allergy":
                        uid = args.get('uid') or str(uuid.uuid4())
                        result = handle_search_allergy(
                            allergy_query=args.get('allergy_query'),
                            practice_code=args.get('practice_code'), 
                            patient_account=args.get('patient_account'),
                            uid=uid
                        )
                        formatted_result = GenerateResponse.format_search_allergy_response(result)
                        info_logger.info(f"Result from handle_search_allergy: {result}")
                        info_logger.info(f"Formatted result for search_allergy: {formatted_result}")
                        return formatted_result


                    elif func.name == "add_allergy":
                        uid = args.get('uid') or str(uuid.uuid4())
                        info_logger.info(f"add_allergy function called with args: {args}")
                        
                        result = handle_add_allergy(
                            allergy_code=args.get('allergy_code'),
                            allergy_name=args.get('allergy_name'),
                            severity=args.get('severity'),
                            reaction=args.get('reaction'),
                            allergy_type_id=args.get('allergy_type_id'), 
                            practice_code=args.get('practice_code'),
                            patient_account=args.get('patient_account'),
                            uid=uid
                        )
                        formatted_result = GenerateResponse.format_add_allergy_response(result)
                        info_logger.info(f"Result from handle_add_allergy: {result}")
                        info_logger.info(f"Formatted result for add_allergy: {formatted_result}")
                        return formatted_result
                
                    elif func.name == "handle_remove_delete_medication":
                        result = handle_remove_delete_medication(**args)
                        result = GenerateResponse.format_remove_delete_medication_response(result)
                        info_logger.info(f"Result from handle_remove_delete_medication: {result}")  
                        return result
                    
                    elif func.name == "handle_remove_delete_pharmacy":
                        result = handle_remove_delete_pharmacy(**args)
                        result=GenerateResponse.format_remove_delete_pharmacy_response(result)
                        info_logger.info(f"Result from handle_remove_delete_pharmacy: {result}")    
                        return result

                    elif func.name == "handle_add_pharmacy":
                        result = handle_add_pharmacy(**args)
                        formatted_result = GenerateResponse.format_add_pharmacy_response(result)
                        info_logger.info(f"Result from handle_add_pharmacy: {result}")
                        info_logger.info(f"Formatted result for add_pharmacy: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_search_pharmacy":
                        result = handle_search_pharmacy(**args)
                        formatted_result = GenerateResponse.format_search_pharmacy_response(result)
                        info_logger.info(f"Result from handle_search_pharmacy: {result}")
                        info_logger.info(f"Formatted result for search_pharmacy: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_search_medication":
                        result = handle_search_medication(**args)
                        formatted_result = GenerateResponse.format_search_medicine_response(result)
                        info_logger.info(f"Result from handle_search_medication: {result}")
                        info_logger.info(f"Formatted result for search_medication: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_get_medication_sig":
                        result = handle_get_medication_sig(**args)
                        formatted_result = GenerateResponse.format_medication_sig_response(result)
                        info_logger.info(f"Result from handle_get_medication_sig: {result}")
                        info_logger.info(f"Formatted result for get_medication_sig: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_search_diagnosis":
                        result = handle_search_diagnosis(**args)
                        formatted_result = GenerateResponse.format_search_diagnosis_response(result)
                        info_logger.info(f"Result from handle_search_diagnosis: {result}")
                        info_logger.info(f"Formatted result for search_diagnosis: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_save_medication":
                        result = handle_save_medication(**args)
                        formatted_result = GenerateResponse.format_save_medication_response(result)
                        info_logger.info(f"Result from handle_save_medication: {result}")
                        info_logger.info(f"Formatted result for save_medication: {formatted_result}")
                        return formatted_result

                    elif func.name == "handle_save_family_history":      
                        result = handle_save_family_history(**args)
                        formatted_result = GenerateResponse.format_add_family_history_response(result)
                        info_logger.info(f"Result from handle_save_family_history: {result}")
                        info_logger.info(f"Formatted result for save_family_history: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_delete_family_history":
                        result = handle_delete_family_history(**args)
                        formatted_result = GenerateResponse.format_remove_delete_family_history_response(result)
                        info_logger.info(f"Result from handle_delete_family_history: {result}")
                        info_logger.info(f"Formatted result for delete_family_history: {formatted_result}")
                        return formatted_result
                    elif func.name == "handle_get_family_history":
                        result = handle_get_family_history(**args)
                        formatted_result = GenerateResponse.format_get_family_history_response(result)
                        info_logger.info(f"Result from handle_get_family_history: {result}")
                        info_logger.info(f"Formatted result for get_family_history: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_get_common_diseases":
                        result = handle_get_common_diseases(**args)
                        formatted_result = GenerateResponse.format_get_common_diseases_response(result)
                        info_logger.info(f"Result from handle_get_common_diseases: {result}")
                        info_logger.info(f"Formatted result for get_common_diseases: {formatted_result}")
                        return formatted_result
                    

                    elif func.name == "handle_get_social_history":
                        result = handle_get_social_history(**args)
                        formatted_result = GenerateResponse.format_get_social_history_response(result)
                        info_logger.info(f"Result from handle_get_social_history: {result}")
                        info_logger.info(f"Formatted result for handle_get_social_history: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_save_social_history":
                        result = handle_save_social_history(**args)
                        formatted_result = GenerateResponse.format_save_social_history_response(result)
                        info_logger.info(f"Result from handle_save_social_history: {result}")
                        info_logger.info(f"Formatted result for handle_save_social_history: {formatted_result}")
                        return formatted_result

                    elif func.name == "handle_get_past_surgical_history":
                        result = handle_get_past_surgical_history(**args)
                        formatted_result = GenerateResponse.format_get_past_surgical_history_response(result)
                        info_logger.info(f"Result from handle_get_past_surgical_history: {result}")
                        info_logger.info(f"Formatted result for get_past_surgical_history: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_save_past_surgical_history":
                        result = handle_save_past_surgical_history(**args)
                        formatted_result = GenerateResponse.format_save_past_surgical_history_response(result)
                        info_logger.info(f"Result from handle_save_past_surgical_history: {result}")
                        info_logger.info(f"Formatted result for save_past_surgical_history: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_delete_past_surgical_history":
                        result = handle_delete_past_surgical_history(**args)
                        formatted_result = GenerateResponse.format_delete_past_surgical_history_response(result)
                        info_logger.info(f"Result from handle_delete_past_surgical_history: {result}")
                        info_logger.info(f"Formatted result for delete_past_surgical_history: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_get_past_hospitalization":
                        result = handle_get_past_hospitalization(**args)
                        formatted_result = GenerateResponse.format_get_past_hospitalization_response(result)
                        info_logger.info(f"Result from handle_get_past_hospitalization: {result}")
                        info_logger.info(f"Formatted result for get_past_hospitalization: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_save_past_hospitalization":
                        result = handle_save_past_hospitalization(**args)
                        formatted_result = GenerateResponse.format_save_past_hospitalization_response(result)
                        info_logger.info(f"Result from handle_save_past_hospitalization: {result}")
                        info_logger.info(f"Formatted result for save_past_hospitalization: {formatted_result}")
                        return formatted_result
                        
                    elif func.name == "handle_delete_past_hospitalization":
                        result = handle_delete_past_hospitalization(**args)
                        formatted_result = GenerateResponse.format_delete_past_hospitalization_response(result)
                        info_logger.info(f"Result from handle_delete_past_hospitalization: {result}")
                        info_logger.info(f"Formatted result for delete_past_hospitalization: {formatted_result}")
                        return formatted_result
                    
                    # Insurance handler functions
                    elif func.name == "handle_get_patient_insurance":
                        result = handle_get_patient_insurance(**args)
                        formatted_result = GenerateResponse.format_get_patient_insurance_response(result)
                        info_logger.info(f"Result from handle_get_patient_insurance: {result}")
                        info_logger.info(f"Formatted result for get_patient_insurance: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_delete_patient_insurance":
                        result = handle_delete_patient_insurance(**args)
                        formatted_result = GenerateResponse.format_delete_patient_insurance_response(result)
                        info_logger.info(f"Result from handle_delete_patient_insurance: {result}")
                        info_logger.info(f"Formatted result for delete_patient_insurance: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_search_insurance":
                        result = handle_search_insurance(**args)
                        formatted_result = GenerateResponse.format_search_insurance_response(result)
                        info_logger.info(f"Result from handle_search_insurance: {result}")
                        info_logger.info(f"Formatted result for search_insurance: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_get_zip_city_state":
                        result = handle_get_zip_city_state(**args)
                        formatted_result = GenerateResponse.format_get_zip_city_state_response(result)
                        info_logger.info(f"Result from handle_get_zip_city_state: {result}")
                        info_logger.info(f"Formatted result for get_zip_city_state: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_save_subscriber":
                        result = handle_save_subscriber(**args)
                        formatted_result = GenerateResponse.format_save_subscriber_response(result)
                        info_logger.info(f"Result from handle_save_subscriber: {result}")
                        info_logger.info(f"Formatted result for save_subscriber: {formatted_result}")
                        return formatted_result
                    
                    elif func.name == "handle_save_insurance":
                        result = handle_save_insurance(**args)
                        formatted_result = GenerateResponse.format_save_insurance_response(result)
                        info_logger.info(f"Result from handle_save_insurance: {result}")
                        info_logger.info(f"Formatted result for save_insurance: {formatted_result}")
                        return formatted_result
                   
                    
            if hasattr(response, 'thinking'):
                info_logger.info(f"Model thinking process: {response.thinking}")
            
            if hasattr(response, 'text'):
                text_content = response.text
            elif hasattr(response, 'candidates') and response.candidates:
                text_content = response.candidates[0].text
            
            try:
                cleaned_text = GenerateResponse.clean_response(text_content)
                parsed_response = json.loads(cleaned_text)
                
                if "speech" in parsed_response and "display" in parsed_response:
                    if isinstance(parsed_response["speech"], list):
                        parsed_response["speech"] = " ".join(parsed_response["speech"])
                    return parsed_response
                else:
                    return {
                        "speech": "I have some information for you.",
                        "display": cleaned_text
                    }
                    
            except json.JSONDecodeError:
                display_text = "" if text_content is None else text_content.strip()
                return {
                    "speech": "Here's the information you requested.",
                    "display": display_text
                }

        except Exception as e:
            error_logger.error(f"Error generating response: {e}")
            error_logger.error(f"Stack trace: {traceback.format_exc()}")
            raise ApplicationException(f"Gemini Response Error: {e}")
    



    @staticmethod
    async def generate_response_v3_stream(prompt: str, tools: list = None):
        try:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "config/aiml-365220-b6aec5dba4a2.json"
            
            # Initialize client in thread pool to avoid blocking
            def init_client():
                return genai.Client(
                    vertexai=True,
                    project="aiml-365220",
                    location="us-central1",
                )
            
            client = await asyncio.to_thread(init_client)
            model_name = "gemini-2.5-flash"
            info_logger.info(f"Using model name for streaming: {model_name}")
            
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)]
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                temperature=0.3,
                top_p=0.95,
                max_output_tokens=8192,
                tools=tools if tools else []
            )
            
            # Generate content stream in thread pool to avoid blocking
            def generate_stream():
                return client.models.generate_content_stream(
                    model=model_name,
                    contents=contents,
                    config=generate_content_config
                )
            
            response_stream = await asyncio.to_thread(generate_stream)
            info_logger.info(f"🔄 STREAMING VERIFICATION: Received response stream from model")
            
            # Process the stream with detailed logging
            chunk_count = 0
            info_logger.info(f"🎯 STREAMING VERIFICATION: Starting to iterate over response stream")
            
            for response in response_stream:
                chunk_count += 1
                info_logger.info(f"📦 STREAMING CHUNK #{chunk_count}: Processing chunk from model")
                candidate = response.candidates[0]
                if not hasattr(candidate, 'content') or candidate.content is None or not hasattr(candidate.content, 'parts') or candidate.content.parts is None:
                    finish_message = candidate.finish_message if hasattr(candidate, 'finish_message') else "No details available"
                    finish_reason = candidate.finish_reason if hasattr(candidate, 'finish_reason') else "Unknown reason"
                    info_logger.warning(f"Response has no content.parts. Finish message: {finish_message}")
                    info_logger.warning(f"Finish reason: {finish_reason}")
                    
                    error_response = {
                        "speech": "I'm sorry, I encountered an issue processing your request. Please try again.",
                        "display": "There was a problem processing your request. Please try again."
                    }
                    yield error_response
                    return
                
                parts = candidate.content.parts
                
                # Process function calls if present
                for part in parts:
                    if hasattr(part, 'function_call') and part.function_call is not None:
                        func = part.function_call
                        args = func.args
                        func_name = func.name  # Extract function name
                        info_logger.info(f"Function call detected in streaming mode: {func_name} with args: {args}")

                        # Execute function calls in thread pool to avoid blocking
                        async def execute_function_call(function_name, func_args):
                            def sync_function_call():
                                if function_name == "update_demo":
                                    result = DBops.update_demo(**func_args)
                                    return GenerateResponse.format_update_demo_response(func_args, result)

                                elif function_name == "delete_patient_allergy":
                                    result = Allergies.delete_patient_allergy(**func_args, uid=str(uuid.uuid4()))
                                    
                                    if result.get("success"):
                                        info_logger.info(f"✅ Successfully deleted allergy {func_args.get('allergy_id')}")
                                        try:
                                            info_logger.info("🔍 Fetching updated allergies after deletion...")
                                            updated_allergies = Allergies.get_patient_allergies(
                                                patient_account=func_args.get("patient_account"),
                                                practice_code=func_args.get("practice_code"),
                                                uid=str(uuid.uuid4())
                                            )
                                            info_logger.info(f"🔍 Updated allergies response: {updated_allergies}")
                                            if updated_allergies and "patientAllergies" in updated_allergies:
                                                allergy_count = len(updated_allergies.get("patientAllergies", []))
                                                info_logger.info(f"✅ Successfully fetched {allergy_count} remaining allergies")
                                            else:
                                                info_logger.warning(f"⚠️ Failed to fetch updated allergies: {updated_allergies}")
                                                updated_allergies = None
                                        except Exception as e:
                                            error_logger.error(f"❌ Exception while fetching updated allergies: {str(e)}")
                                            updated_allergies = None
                                    else:
                                        info_logger.error(f"❌ Failed to delete allergy: {result}")
                                        updated_allergies = None
                                        
                                    return GenerateResponse.format_delete_allergy_response(func_args, result, updated_allergies)
                            
                                elif function_name == "search_allergy":
                                    uid = func_args.get('uid') or str(uuid.uuid4())
                                    result = handle_search_allergy(
                                        allergy_query=func_args.get('allergy_query'),
                                        practice_code=func_args.get('practice_code'), 
                                        patient_account=func_args.get('patient_account'),
                                        uid=uid
                                    )
                                    return GenerateResponse.format_search_allergy_response(result)

                                elif function_name == "add_allergy":
                                    uid = func_args.get('uid') or str(uuid.uuid4())
                                    info_logger.info(f"add_allergy function called with args: {func_args}")
                                    
                                    result = handle_add_allergy(
                                        allergy_code=func_args.get('allergy_code'),
                                        allergy_name=func_args.get('allergy_name'),
                                        severity=func_args.get('severity'),
                                        reaction=func_args.get('reaction'),
                                        allergy_type_id=func_args.get('allergy_type_id'), 
                                        practice_code=func_args.get('practice_code'),
                                        patient_account=func_args.get('patient_account'),
                                        uid=uid
                                    )
                                    return GenerateResponse.format_add_allergy_response(result)
                            
                                elif function_name == "handle_remove_delete_medication":
                                    result = handle_remove_delete_medication(**func_args)
                                    result = GenerateResponse.format_remove_delete_medication_response(result)
                                    info_logger.info(f"Result from handle_remove_delete_medication: {result}")  
                                    return result
                                
                                elif function_name == "handle_remove_delete_pharmacy":
                                    result = handle_remove_delete_pharmacy(**args)
                                    result=GenerateResponse.format_remove_delete_pharmacy_response(result)
                                    info_logger.info(f"Result from handle_remove_delete_pharmacy: {result}")    
                                    return result

                                elif function_name == "handle_add_pharmacy":
                                    result = handle_add_pharmacy(**args)
                                    formatted_result = GenerateResponse.format_add_pharmacy_response(result)
                                    info_logger.info(f"Result from handle_add_pharmacy: {result}")
                                    info_logger.info(f"Formatted result for add_pharmacy: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_search_pharmacy":
                                    result = handle_search_pharmacy(**args)
                                    formatted_result = GenerateResponse.format_search_pharmacy_response(result)
                                    info_logger.info(f"Result from handle_search_pharmacy: {result}")
                                    info_logger.info(f"Formatted result for search_pharmacy: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_search_medication":
                                    result = handle_search_medication(**args)
                                    formatted_result = GenerateResponse.format_search_medicine_response(result)
                                    info_logger.info(f"Result from handle_search_medication: {result}")
                                    info_logger.info(f"Formatted result for search_medication: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_get_medication_sig":
                                    result = handle_get_medication_sig(**args)
                                    formatted_result = GenerateResponse.format_medication_sig_response(result)
                                    info_logger.info(f"Result from handle_get_medication_sig: {result}")
                                    info_logger.info(f"Formatted result for get_medication_sig: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_search_diagnosis":
                                    result = handle_search_diagnosis(**args)
                                    formatted_result = GenerateResponse.format_search_diagnosis_response(result)
                                    info_logger.info(f"Result from handle_search_diagnosis: {result}")
                                    info_logger.info(f"Formatted result for search_diagnosis: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_save_medication":
                                    result = handle_save_medication(**args)
                                    formatted_result = GenerateResponse.format_save_medication_response(result)
                                    info_logger.info(f"Result from handle_save_medication: {result}")
                                    info_logger.info(f"Formatted result for save_medication: {formatted_result}")
                                    return formatted_result

                                elif function_name == "handle_save_family_history":      
                                    result = handle_save_family_history(**args)
                                    formatted_result = GenerateResponse.format_add_family_history_response(result)
                                    info_logger.info(f"Result from handle_save_family_history: {result}")
                                    info_logger.info(f"Formatted result for save_family_history: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_delete_family_history":
                                    result = handle_delete_family_history(**args)
                                    formatted_result = GenerateResponse.format_remove_delete_family_history_response(result)
                                    info_logger.info(f"Result from handle_delete_family_history: {result}")
                                    info_logger.info(f"Formatted result for delete_family_history: {formatted_result}")
                                    return formatted_result
                                elif function_name == "handle_get_family_history":
                                    result = handle_get_family_history(**args)
                                    formatted_result = GenerateResponse.format_get_family_history_response(result)
                                    info_logger.info(f"Result from handle_get_family_history: {result}")
                                    info_logger.info(f"Formatted result for get_family_history: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_get_common_diseases":
                                    result = handle_get_common_diseases(**args)
                                    formatted_result = GenerateResponse.format_get_common_diseases_response(result)
                                    info_logger.info(f"Result from handle_get_common_diseases: {result}")
                                    info_logger.info(f"Formatted result for get_common_diseases: {formatted_result}")
                                    return formatted_result
                                

                                elif function_name == "handle_get_social_history":
                                    result = handle_get_social_history(**args)
                                    formatted_result = GenerateResponse.format_get_social_history_response(result)
                                    info_logger.info(f"Result from handle_get_social_history: {result}")
                                    info_logger.info(f"Formatted result for handle_get_social_history: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_save_social_history":
                                    result = handle_save_social_history(**args)
                                    formatted_result = GenerateResponse.format_save_social_history_response(result)
                                    info_logger.info(f"Result from handle_save_social_history: {result}")
                                    info_logger.info(f"Formatted result for handle_save_social_history: {formatted_result}")
                                    return formatted_result

                                elif function_name == "handle_get_past_surgical_history":
                                    result = handle_get_past_surgical_history(**args)
                                    formatted_result = GenerateResponse.format_get_past_surgical_history_response(result)
                                    info_logger.info(f"Result from handle_get_past_surgical_history: {result}")
                                    info_logger.info(f"Formatted result for get_past_surgical_history: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_save_past_surgical_history":
                                    result = handle_save_past_surgical_history(**args)
                                    formatted_result = GenerateResponse.format_save_past_surgical_history_response(result)
                                    info_logger.info(f"Result from handle_save_past_surgical_history: {result}")
                                    info_logger.info(f"Formatted result for save_past_surgical_history: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_delete_past_surgical_history":
                                    result = handle_delete_past_surgical_history(**args)
                                    formatted_result = GenerateResponse.format_delete_past_surgical_history_response(result)
                                    info_logger.info(f"Result from handle_delete_past_surgical_history: {result}")
                                    info_logger.info(f"Formatted result for delete_past_surgical_history: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_get_past_hospitalization":
                                    result = handle_get_past_hospitalization(**args)
                                    formatted_result = GenerateResponse.format_get_past_hospitalization_response(result)
                                    info_logger.info(f"Result from handle_get_past_hospitalization: {result}")
                                    info_logger.info(f"Formatted result for get_past_hospitalization: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_save_past_hospitalization":
                                    result = handle_save_past_hospitalization(**args)
                                    formatted_result = GenerateResponse.format_save_past_hospitalization_response(result)
                                    info_logger.info(f"Result from handle_save_past_hospitalization: {result}")
                                    info_logger.info(f"Formatted result for save_past_hospitalization: {formatted_result}")
                                    return formatted_result
                                    
                                elif function_name == "handle_delete_past_hospitalization":
                                    result = handle_delete_past_hospitalization(**args)
                                    formatted_result = GenerateResponse.format_delete_past_hospitalization_response(result)
                                    info_logger.info(f"Result from handle_delete_past_hospitalization: {result}")
                                    info_logger.info(f"Formatted result for delete_past_hospitalization: {formatted_result}")
                                    return formatted_result
                                
                                # Insurance handler functions
                                elif function_name == "handle_get_patient_insurance":
                                    result = handle_get_patient_insurance(**args)
                                    formatted_result = GenerateResponse.format_get_patient_insurance_response(result)
                                    info_logger.info(f"Result from handle_get_patient_insurance: {result}")
                                    info_logger.info(f"Formatted result for get_patient_insurance: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_delete_patient_insurance":
                                    result = handle_delete_patient_insurance(**args)
                                    formatted_result = GenerateResponse.format_delete_patient_insurance_response(result)
                                    info_logger.info(f"Result from handle_delete_patient_insurance: {result}")
                                    info_logger.info(f"Formatted result for delete_patient_insurance: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_search_insurance":
                                    result = handle_search_insurance(**args)
                                    formatted_result = GenerateResponse.format_search_insurance_response(result)
                                    info_logger.info(f"Result from handle_search_insurance: {result}")
                                    info_logger.info(f"Formatted result for search_insurance: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_get_zip_city_state":
                                    result = handle_get_zip_city_state(**args)
                                    formatted_result = GenerateResponse.format_get_zip_city_state_response(result)
                                    info_logger.info(f"Result from handle_get_zip_city_state: {result}")
                                    info_logger.info(f"Formatted result for get_zip_city_state: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_save_subscriber":
                                    result = handle_save_subscriber(**args)
                                    formatted_result = GenerateResponse.format_save_subscriber_response(result)
                                    info_logger.info(f"Result from handle_save_subscriber: {result}")
                                    info_logger.info(f"Formatted result for save_subscriber: {formatted_result}")
                                    return formatted_result
                                
                                elif function_name == "handle_save_insurance":
                                    result = handle_save_insurance(**args)
                                    formatted_result = GenerateResponse.format_save_insurance_response(result)
                                    info_logger.info(f"Result from handle_save_insurance: {result}")
                                    info_logger.info(f"Formatted result for save_insurance: {formatted_result}")
                                    return formatted_result

                                
                                else:
                                    info_logger.warning(f"Unknown function call in streaming mode: {function_name}")
                                    return {
                                        "speech": "I encountered an unknown function request. Please try again.",
                                        "display": f"Unknown function: {function_name}"
                                    }
                            
                            return await asyncio.to_thread(sync_function_call)
                        
                        # Execute the function call and yield the result
                        function_result = await execute_function_call(func_name, args)
                        info_logger.info(f"Function call result in streaming mode: {function_result}")
                        yield function_result
                        return
                
                # Process text response
                text_content = None
                if hasattr(response, 'text'):
                    text_content = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    text_content = response.candidates[0].text
                
                info_logger.info(f"🎯 STREAMING CHUNK TEXT: {text_content}")
                
                try:
                    # Clean the response to extract JSON from markdown code blocks
                    cleaned_text = GenerateResponse.clean_response(text_content)
                    info_logger.info(f"🧹 CLEANED TEXT: {cleaned_text}")
                    
                    # Try to parse as JSON
                    # parsed_response = json.loads(cleaned_text)
                    # info_logger.info(f"✅ PARSED JSON: {parsed_response}")
                    
                    # if "speech" in parsed_response and "display" in parsed_response:
                    #     if isinstance(parsed_response["speech"], list):
                    #         parsed_response["speech"] = " ".join(parsed_response["speech"])
                    #     yield parsed_response
                    # else:
                    yield {
                        "speech": cleaned_text if cleaned_text else "I have some information for you.",
                        "display": cleaned_text
                    }
                        
                except json.JSONDecodeError as e:
                    info_logger.warning(f"⚠️ JSON DECODE ERROR: {e}, raw text: {text_content}")
                    # Accumulate partial text for streaming response
                    if text_content and text_content.strip():
                        yield {
                            "speech": "",  # Don't duplicate speech in partial chunks
                            "display": text_content.strip()
                        }

        except Exception as e:
            error_logger.error(f"Error in streaming response generation: {e}")
            error_logger.error(f"Stack trace: {traceback.format_exc()}")
            yield {
                "speech": "I'm sorry, I encountered an error while processing your request. Please try again.",
                "display": f"Error: {str(e)}"
            }
    
    






   