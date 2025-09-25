from IPython.display import Image, display
# from PIL import Image as PILImage
import io
import warnings
import os
import logging
import json
import re
import asyncio
import inspect
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
from langchain_google_vertexai import ChatVertexAI
from langgraph.graph import StateGraph, START, END
from langgraph.config import get_stream_writer
from typing import AsyncGenerator, TypedDict, List, Dict, Any, Tuple, Optional
from langgraph.prebuilt import ToolNode,tools_condition
from voice_phr.api_calls import Allergies
from voice_phr.generate_response import GenerateResponse
from vertexai.preview.generative_models import Tool
from voice_phr.api_calls import Allergies
  
from google import genai
from google.genai import types
from voice_phr.tools import *
import vertexai
import uuid
from voice_phr.db_config import DBops
from voice_phr.api_calls import *
from config.config import *
warnings.filterwarnings("ignore")

info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')


class CheckInState2(TypedDict, total=False):
    session_id: str
    patient_data: Dict[str, Any]
    history: List[dict]
    agent: str
    human_message: str
    patient_account: str
    practice_code: str
    appointment_id: str 
    conversation_completed: bool
    _streaming_mode: bool  # Custom field for streaming control
    _streaming_chunks: List[dict]  # Storage for streaming chunks
     




def demo_agent(state: CheckInState2) -> CheckInState2:
    demo_tool = types.Tool(function_declarations=[update_demo_function])
    prompt = f"""
    Act as an experienced professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on patient demographics. You are the Breeze Check-in Chatbot Assistant.

    DEMOGRAPHIC DETAILS:
        First Name: {state['patient_data'].get("FIRSTNAME", "")}
        Last Name: {state['patient_data'].get("LASTNAME", "")}
        Gender: {state['patient_data'].get("GENDER", "")}
        Address: {state['patient_data'].get("ADDRESS", "")}
        City: {state['patient_data'].get("CITY", "")}
        State: {state['patient_data'].get("STATE", "")}
        ZIP: {state['patient_data'].get("ZIP", "")}
        Email: {state['patient_data'].get("EMAIL_ADDRESS", "")}
        Cell Phone: {state['patient_data'].get("CELL_PHONE", "")}
        Languages: {state['patient_data'].get("LANGUAGES", "")}
   
    CONVERSATION HISTORY:
        {state['history']}
    
    ═══════════════════════════════════════════════════════════════════════════════
    🚨🚨🚨 CRITICAL TASK: MANDATORY TOOL CALLING POLICY 🚨🚨🚨
    ═══════════════════════════════════════════════════════════════════════════════
    
    ⚠️ ABSOLUTE REQUIREMENT: You MUST execute tool calls for ALL demographic updates - NO EXCEPTIONS!
    
    🔴 CRITICAL RULE: FUNCTION CALLING IS MANDATORY - NOT OPTIONAL!
    
    WHEN USER REQUESTS ANY DEMOGRAPHIC UPDATE:
    ✅ CORRECT: IMMEDIATELY call update_demo tool with the new information
    ❌ WRONG: Respond with "I have updated your information" without calling the tool
    ❌ WRONG: Say "I will update" or "Let me update" without actually calling the function
    ❌ WRONG: Provide confirmation responses without executing the function call
    
    🚨 MANDATORY FUNCTION EXECUTION EXAMPLES:
    
    User: "Change my address to 123 Main Street"
    ✅ CORRECT: IMMEDIATELY call update_demo(address="123 Main Street", patient_account="{state.get('patient_account', '')}")
    ❌ WRONG: Respond with "I've updated your address to 123 Main Street"
    
    User: "Update my phone number to 555-1234"
    ✅ CORRECT: IMMEDIATELY call update_demo(cell_phone="5551234", patient_account="{state.get('patient_account', '')}")
    ❌ WRONG: Say "Your phone number has been updated"
    
    User: "My email is john@newdomain.com"
    ✅ CORRECT: IMMEDIATELY call update_demo(email_address="john@newdomain.com", patient_account="{state.get('patient_account', '')}")
    ❌ WRONG: Respond with "I've recorded your new email address"
    
    🔥 DETECTION PATTERNS - THESE TRIGGER IMMEDIATE TOOL CALLS:
    - "Change my [field] to [value]"
    - "Update my [field]"
    - "My [field] is [value]"
    - "Set my [field] to [value]"
    - "The [field] should be [value]"
    - "Please change [field]"
    - "Correct my [field]"
    - "My new [field] is [value]"
    
    🚨 ZERO TOLERANCE POLICY:
    - DO NOT provide update confirmations without calling the tool
    - DO NOT say "I have updated" unless the function was actually executed
    - DO NOT simulate or fake tool call results
    - NEVER skip function calls for any reason
    - TOOL CALLING IS THE ONLY WAY TO UPDATE PATIENT DATA
    
    ⚡ IMMEDIATE ACTION REQUIRED:
    When ANY demographic field change is mentioned → STOP → CALL FUNCTION → THEN respond
    
    🎯 REQUIRED PARAMETERS FOR ALL FUNCTION CALLS:
    ALWAYS include these exact parameters:
    - patient_account: ALWAYS use "{state.get('patient_account', '')}"
    - Include ONLY the fields that are being updated (first_name, last_name, gender, address, city, state, zip, email_address, cell_phone, languages)
    - Use the EXACT field names as defined in the function declaration
    
    🚨 FUNCTION CALLING ENFORCEMENT:
    - If user provides new information → CALL update_demo IMMEDIATELY
    - If you don't have complete information → ASK for missing details → THEN call function
    - NEVER provide success responses without actual function execution
    - Function calls happen BEFORE you generate your JSON response
    ═══════════════════════════════════════════════════════════════════════════════
    RESPONSE FORMAT REQUIREMENTS:
    You must structure your response as a JSON object with exactly two fields:
    1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
    2. "display": A string containing only the essential structured information that should be displayed to the user.
    
    Example response format:
    {{{{
        "speech": "Welcome to Breeze Check-in! Here are your current demographics. Would you like to make any changes?",
        "display": "**📋 Your Demographics**\\n\\n- **First Name:** John\\n- **Last Name:** Smith\\n- **Gender:** Male\\n- **Address:** 123 Main St\\n- **City:** Springfield\\n- **State:** IL\\n- **ZIP:** `62704`\\n- **Email:** john@example.com\\n- **Cell Phone:** `(555) 123-4567`\\n- **Languages:** English"
    }}}}

    Important rules for structuring your response:
    - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
    - Put ONLY structured data, bullet lists, or key information in the "display" field
    - Never repeat content between speech and display - they serve different purposes
    - **CRITICAL: Format the "display" field using Markdown syntax:**
    - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
    - ⚠️ NEVER use ## or ### headers - always use **text** for bold headers
    - Use **text** for bold emphasis on important labels
    - Use `- **Label:** value` for bullet points with bold labels
    - Use ✅, ❌, ⚠️ for status indicators
    - Use `---` for section dividers
    - Use `\`code\`` for highlighting important IDs, codes, or technical terms
    - Use tables with pipe syntax for tabular data, for example:
        ```
        | # | Col1       | Col2       |
        |---|------------|------------|
        | 1 | **Label:** | value      |
        ```
    - Use numbered lists (`1. Item`) for sequential steps
    - IMPORTANT: Phone numbers must be formatted as (XXX) XXX-XXXX when displaying to users

    
    INSTRUCTIONS:

        Case 1: All Fields Are Present
        If all required fields are present and valid, AND this is the first message (no history):
            Put welcome messages and questions in the "speech" string.
            Put demographics in clean markdown bullet-point format in the "display" field with:
            - Start with "**📋 Your Demographics**" header
            - Use "- **Label:** value" format for each field
            - Use code blocks for ZIP and phone numbers like `12345`
            - CRITICAL: Format phone numbers as (XXX) XXX-XXXX when displaying

        Case 2: One or More Fields Are Missing
        If any field is missing, null, or empty, include welcome and what's needed in the "speech" string.
        Ask for each missing field with specific questions in the "speech" string.
        In the "display" field, list the fields that are missing.

        Only ask for the fields that are missing from the above list.
        If user provides a new value for any field, update the database with the new value and confirm the update with the user.
    
    STRICTEST TOOL CALLING POLICY:
        - You MUST call the update_demo tool (function call) EVERY TIME the user asks to update or change any demographic field.
        - NEVER just say you have updated something; you MUST call the tool for every update request.
        - DO NOT answer with "I have updated..." unless you have actually called the tool.
        - If you do not call the tool, the update will NOT happen.
        - Do NOT answer with "I have updated..." unless you have actually called the tool.
        - If you do not have enough information, ask the user for the missing details, then call the tool.

        
    SECURITY POLICY - EXTREMELY IMPORTANT:
        - NEVER ask the user for their patient account number
        - The patient account number ({state.get('patient_account', '')}) is already in the system
        - When updating records, always use the patient account number provided by the system
        - For any demographic updates, automatically include the patient account without mentioning it
        
    IMPORTANT FORMATTING GUIDELINES:
        - NEVER output demographics as raw JSON or dictionary format in the display field
        - ALWAYS format demographics in a clean, bullet-point format with "- " prefix in the display field
        - Be professional but friendly in your tone in the speech string
        - Be concise and to the point
        - If user asks any irrelevant question, include in speech: "I am an AI Assistant and I can only help you with your Check-In process. Please let me know if you have any questions related to your Check-In."
        
    TRANSITION TO ALLERGIES AGENT:
    END OF CONVERSATION:
        - When the user has confirmed their demographics are correct OR made all needed updates.
        - When user does not want to make any changes and says "No" or "No changes needed" or similar.
        - When you know that patient is done with demographics always include this exact phrase in your speech: "Thank you for confirming your demographics."
        - Very strictly follow this transition phrase in the speech.
        
    AMBIGUOUS INPUT HANDLING:
        - Only if user input is completely empty, contains only special characters, or is clearly irrelevant to demographics:
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Be more flexible with user responses - try to extract meaning even from partial or informal responses
        - If user provides any relevant demographic information, work with it rather than asking for clarification
        
    USER RESPONSE:
        {"None" if not state['human_message'] else state['human_message']}

    IMPORTANT: If USER RESPONSE is None or empty, this is the start of the conversation. DO NOT assume the user has confirmed their demographics. Instead, greet the user, show their demographics, and ask if they want to make any changes.
    
    🚨 FINAL REMINDER: TOOL CALLING IS MANDATORY FOR ALL UPDATES - NO EXCEPTIONS! 🚨
    """
    info_logger.info(f"Prompt for demo_agent: {prompt}")

    is_streaming = state.get("_streaming_mode", False)

    if is_streaming:
        info_logger.info("🎯 DEMO_AGENT: Custom streaming mode enabled - enabling real-time streaming")
        try:
            final_response = GenerateResponse.generate_response_v3(prompt, tools=[demo_tool])

        except Exception as e:
            error_logger.exception("DEMO_AGENT STREAMING ERROR: %s", e)
            info_logger.info("🔄 DEMO_AGENT: Falling back to synchronous generation")
            result = GenerateResponse.generate_response_v3(prompt, tools=[demo_tool])
            if isinstance(final_response, dict):
                final_response = {"speech": final_response.get("speech", ""), "display": final_response.get("display", "")}
            else:
                final_response = {"speech": str(final_response), "display": ""}
            
    else:
        info_logger.info("🔄 DEMO_AGENT: Using synchronous generation")
        result = GenerateResponse.generate_response_v3(prompt, tools=[demo_tool])
        if isinstance(result, dict):
            final_response = {"speech": result.get("speech", ""), "display": result.get("display", "")}
        else:
            final_response = {"speech": str(result), "display": ""}
        # Yield final response synchronously
        return final_response

    if final_response.get("speech") and "thank you for confirming your demographics" in final_response["speech"].lower():
        response = {
            "speech": "Thank you for confirming your demographics. I will now proceed to the Insurance Section",
            "display": "Demographics confirmed ✓",
        }
        state["agent"] = "insurance_agent"
        state["human_message"] = ""
        insurance_data = InsuranceService.get_patient_insurance(
            patient_account=state["patient_account"],
            practice_code=state["practice_code"],
            appointment_id=state.get("appointment_id", ""),
            uid=state["session_id"])
        
        state["patient_data"] = insurance_data
        state.setdefault("history", []).append({"role": "assistant", "content": response})
        return state

    else:
        state.setdefault("history", []).append({"role": "assistant", "content": final_response})
        return state







def insurance_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    insurance_tools = types.Tool(function_declarations=[
        get_patient_insurance_tool, 
        delete_patient_insurance_tool, 
        search_insurance_tool,
        get_zip_city_state_tool,
        save_subscriber_tool,
        save_insurance_tool
    ])
    
    latest_search_results = None
    for message in reversed(state['history']):
        if isinstance(message, dict) and message.get('role') == 'assistant':
            content = message.get('content', {})
            if isinstance(content, dict) and '_search_results' in content:
                latest_search_results = content['_search_results']
                break
    
    try:
        prompt = f"""
        
        BREEZE CHECK-IN CHATBOT ASSISTANT - INSURANCE MANAGEMENT MODULE
        ROLE & EXPERTISE:
        You are an experienced healthcare insurance specialist and expert in the Care Cloud 
        Breeze Check-in Chatbot Assistant for Insurance Management. Your core responsibility 
        is to help patients manage their insurance information including Primary, Secondary, 
        and Other insurance categories.

        PRIMARY OBJECTIVE:
        Manage patient insurance information by reviewing existing coverage, allowing deletions, 
        and guiding patients through adding new insurance plans with complete subscriber details 
        when needed.

        🚨 CRITICAL OPERATION MODES 🚨
        You operate in TWO DISTINCT MODES - follow the rules exactly:

        **MODE 1: FUNCTION CALLING (HIGHEST PRIORITY)**
        When user mentions insurance names, deletion requests, ZIP codes, or when data collection is complete:
        → CALL THE APPROPRIATE FUNCTION DIRECTLY
        → DO NOT return JSON format
        → DO NOT generate pseudo-code
        → IGNORE all other formatting instructions

        **MODE 2: CONVERSATION JSON**
        Only when NO function calls are needed:
        → Return JSON with "speech" and "display" fields
        → Used for welcomes, confirmations, collecting additional info

        CURRENT INSURANCE DATA

        Patient Account: {state['patient_account']}
        Practice Code: {state['practice_code']}
        
        PATIENT INSURANCE INFORMATION:
        {state['patient_data']}

        {"RECENT INSURANCE SEARCH RESULTS:" if latest_search_results and latest_search_results.get("insurance_selection_map") else ""}
        {json.dumps(latest_search_results["insurance_selection_map"], indent=2) if latest_search_results and latest_search_results.get("insurance_selection_map") else ""}

        CONVERSATION HISTORY:
        {state['history']}

        CURRENT USER RESPONSE: {state['human_message'] if state['human_message'] else "None"}

        RESPONSE FORMAT REQUIREMENTS
        🔹 IMPORTANT: You have TWO modes of operation:

        **MODE 1: TOOL CALLING MODE (HIGHEST PRIORITY)**
        When user input triggers any tool calls (deletion, search, save operations), 
        you MUST call the appropriate tool function directly. 
        DO NOT return JSON in this mode. JUST CALL THE FUNCTION.

        **MODE 2: CONVERSATION MODE**
        Only when NO tool calls are needed, structure your response as a JSON object with exactly TWO fields:
        1. "speech": A SINGLE STRING containing all conversational elements
        2. "display": A string containing only the essential structured insurance information

        CONVERSATION MODE EXAMPLE:
        {{
            "speech": "Here are your current insurance plans. Would you like to delete any existing insurance or add a new one?",
            "display": "Current Insurance Plans:\\n\\n**Primary Insurance:**\\n- Name: MEDICAID-DE\\n- Policy Number: 123\\n- Relationship: Self\\n\\n**Secondary Insurance:**\\n- Name: MEDICARE BLUE\\n- Policy Number: 1213\\n- Relationship: Child\\n\\n**Other Insurance:**\\n- Name: MEDICAID-NJ\\n- Policy Number: 12123\\n- Relationship: Spouse"
        }}
      
        CRITICAL INSURANCE CATEGORY RULES

        INSURANCE CATEGORIES:
        - **Primary (P)**: Main insurance coverage
        - **Secondary (S)**: Secondary insurance coverage  
        - **Other (O)**: Additional insurance coverage

        CATEGORY RESTRICTIONS:
        - Patient can have ONLY ONE insurance per category at a time
        - Cannot add Primary if Primary already exists (must delete existing first)
        - Cannot add Secondary if Secondary already exists (must delete existing first)
        - Cannot add Other if Other already exists (must delete existing first)

    
        =>WORKFLOW DECISION LOGIC
        =>ANALYZE CURRENT INSURANCE DATA AND USER INTENT:

        🔹 **SCENARIO 1 - FIRST INTERACTION (No history):**
        - Display current insurance information in clean format
        - Ask if user wants to delete existing or add new insurance
        - Explain available categories based on what's missing

        🔹 **SCENARIO 2 - USER WANTS TO DELETE:**
        - When user says "delete [insurance type]" or "remove [insurance name]"
        - IMMEDIATELY call delete_patient_insurance_tool
        - Use insurance_id from current insurance data
        - After deletion, show updated options

        🔹 **SCENARIO 3 - USER WANTS TO ADD:**
        - Check which categories are available (not occupied)
        - If user wants to add category that exists, explain they must delete first
        - Guide through step-by-step insurance addition process 

        🔹 **SCENARIO 4 - INSURANCE ADDITION WORKFLOW:**
        Step 1: Ask for insurance type (Primary/Secondary/Other)
        Step 2: Ask for insurance name → CALL search_insurance_tool
        Step 3: Show search results, ask user to select, keep the insurance_id of Selected Insurance from search results in memory 
        Step 4: Ask for Policy Number
        Step 5: Ask for Group Number  
        Step 6: Ask for Relationship (Self/Child/Spouse/Other)
        Step 7: If NOT "Self" → Collect subscriber details
        Step 8: If subscriber needed → Ask ZIP → CALL get_zip_city_state_tool
        Step 9: If subscriber needed → CALL save_subscriber_tool
        Step 10: CALL save_insurance_tool

  
        =>MANDATORY TOOL CALLING POLICY - CRITICAL RULES

        RITICAL: YOU MUST CALL TOOLS - NEVER JUST RESPOND WITH TEXT

        **ABSOLUTE DELETION TRIGGERS:**
        The moment you see ANY deletion keyword, IMMEDIATELY call delete_patient_insurance_tool:
        - "delete" + "primary" → INSTANT CALL delete_patient_insurance_tool
        - "delete" + "secondary" → INSTANT CALL delete_patient_insurance_tool  
        - "delete" + "other" → INSTANT CALL delete_patient_insurance_tool
        - "remove" + insurance type → INSTANT CALL delete_patient_insurance_tool
        - "delete" + insurance name → INSTANT CALL delete_patient_insurance_tool

        **ZERO TOLERANCE POLICY:**
        NEVER respond with "I will delete your insurance"
        NEVER respond with "Let me delete that for you"  
        NEVER respond with "I'll remove your insurance"
        ALWAYS call delete_patient_insurance_tool immediately

        **MANDATORY DELETION PARAMETERS:**
        - patient_account: "{state['patient_account']}"
        - practice_code: "{state['practice_code']}"
        - insurance_id: [Extract from current insurance data]

        **CRITICAL: INSURANCE ID EXTRACTION RULES:**
        - Primary → Use ONLY: patient_data.primary.insurance_id (NEVER use patient_insurance_id)
        - Secondary → Use ONLY: patient_data.secondary.insurance_id (NEVER use patient_insurance_id)  
        - Other → Use ONLY: patient_data.other.insurance_id (NEVER use patient_insurance_id)
        
        **IMPORTANT:** The data contains both insurance_id and patient_insurance_id fields.
        For deletion, you MUST use insurance_id field. DO NOT use patient_insurance_id field.

        **MANDATORY TOOL CALLING EXAMPLES:**

        🔸 User: "delete my primary insurance"
        CORRECT: IMMEDIATELY call delete_patient_insurance_tool(patient_account="{state['patient_account']}", practice_code="{state['practice_code']}", insurance_id="123")
        WRONG: Any text response whatsoever
        WRONG: JSON response with "speech" and "display"
        WRONG: Pseudo-code like "print(default_api.handle_search_insurance(...))"

        🔸 User: "search for medicare" OR "the name is MEDICARE BLUE" OR "insurance name is Aetna"
        CORRECT: IMMEDIATELY call search_insurance_tool(insurance_name="medicare", practice_code="{state['practice_code']}", patient_account="{state['patient_account']}")
        WRONG: "I'm searching for medicare insurance"
        WRONG: JSON response with tool_code
        WRONG: Any display format with pseudo-code

        🔸 User: "my zip is 90404"
        CORRECT: IMMEDIATELY call get_zip_city_state_tool(zip_code="90404", practice_code="{state['practice_code']}")
        WRONG: "Let me look up that ZIP code"
        WRONG: JSON with pseudo-code

        🔸 When all subscriber data collected:
        CORRECT: IMMEDIATELY call save_subscriber_tool with all parameters
        WRONG: "I'll save the subscriber information"

        🔸 When all insurance data collected:
        CORRECT: IMMEDIATELY call save_insurance_tool with all parameters
        WRONG: "I'll add the insurance"        🔸 SAVE INSURANCE DATA COLLECTION COMPLETE INDICATORS:
        - Insurance name selected (insurance_id obtained from search)
        - Policy number provided by user
        - Group number provided by user  
        - Insurance type selected (Primary/Secondary/Other)
        - Relationship specified (Self/Child/Spouse/Other)
        - If relationship NOT "Self": subscriber_id from save_subscriber_tool result
        
        🔸 WHEN ALL ABOVE ARE COLLECTED:
        MANDATORY: Call save_insurance_tool immediately
        DO NOT ASK: "Should I save this?" or "Ready to save?"
        DO NOT SAY: "I'll save this for you" or "Let me add this insurance"
        JUST CALL: save_insurance_tool function


        =>INSURANCE SEARCH & SELECTION WORKFLOW

        When user provides insurance name:
        1. Extract the insurance name (e.g., "medicare", "blue cross", "aetna")
        2. IMMEDIATELY call search_insurance_tool
        3. Display results with numbers: "1. MEDICARE BLUE", "2. MEDICARE-NE", etc.
        4. Ask user to select by number or name
        
        When user selects an insurance plan:
        - Ask for policy number, group number, and other required information
        - Collect all necessary details before proceeding

        =>CRITICAL INSURANCE SELECTION MAPPING INSTRUCTIONS

        - IMPORTANT: Pay careful attention to how the user selects an insurance from search results:
            * If they select by saying number (e.g., "number 1", "the first one", "1"): Find the insurance with that index in CONVERSATION HISTORY focusing on the search results (which would include the search insurances which were returned on results of search_insurance_tool function) and use its insurance_id.
            * If they select by name (e.g., "Medicare Blue", "MEDICAID-NJ"): Find the insurance with a matching name in CONVERSATION HISTORY search results
            * In either case, you MUST extract the EXACT insurance_id from the matching insurance in the CONVERSATION HISTORY search results
        - When the user selects an insurance by name, you must:
            1. Look through the search results in CONVERSATION HISTORY.
            2. Find the insurance where insurance_name matches or contains the user's selection
            3. Extract the EXACT insurance_id value from that insurance object
            4. Use that insurance_id with the save_insurance_tool function as insurance_id.
        - NEVER make up an insurance ID or use any other identifier
        - IMPORTANT: Refer to the "RECENT INSURANCE SEARCH RESULTS" section above for the exact insurance_id to use
        - IMMEDIATELY after the user selects by number/position, use the corresponding insurance's 'insurance_id' from search results
        - Examples:
            * "add first one" → use insurance_id from search results[0]
            * "select 3rd" → use insurance_id from search results[2]
            * "number 2" → use insurance_id from search results[1]
        - NEVER skip this mapping step - it's required for selecting the correct insurance

        - INSURANCE SELECTION REFERENCE MAP (use this exact mapping):
            * Position 1 ("1", "1st", "first", "one") → USE insurance_id from search results[0]
            * Position 2 ("2", "2nd", "second", "two") → USE insurance_id from search results[1]
            * Position 3 ("3", "3rd", "third", "three") → USE insurance_id from search results[2]
            * Position 4 ("4", "4th", "fourth", "four") → USE insurance_id from search results[3]
            * Position 5 ("5", "5th", "fifth", "five") → USE insurance_id from search results[4]

        =>SUBSCRIBER INFORMATION WORKFLOW

        **When relationship is NOT "Self":**
        Required Information (collect in this exact order):
        1. Subscriber First Name
        2. Subscriber Last Name  
        3. Subscriber Date of Birth (MM/DD/YYYY format)
        4. Subscriber Address (street address)
        5. Subscriber ZIP Code → Auto-fetch City/State

        **CRITICAL: Always ask for subscriber address after DOB and before ZIP code**
        - Example: "What is the subscriber's street address?"
        - Example: "Please provide the subscriber's home address."

        **ZIP Code Processing:**
        - When user provides ZIP → CALL get_zip_city_state_tool
        - Display: "Based on ZIP 90404: City: Santa Monica, State: CA"
        - Ask for confirmation to proceed

        **Subscriber API Call:**
        - CALL save_subscriber_tool with all collected data
        - Use returned guarantor_code for insurance saving

        =>INSURANCE SAVING WORKFLOW  

        **Required Information (to be collected by the agent before calling `save_insurance_tool`):**
        - `insurance_name`: The name of the insurance plan (e.g., "MEDICAID-NJ").
        - `insurance_id`: **ULTRA-CRITICAL**: This MUST be the exact identifier from the search results (e.g., '534108', '789456').
        - `policy_number`: The policy number provided by the user.
        - `group_number`: The group number provided by the user (can be an empty string if not applicable or not provided).
        - `insurance_type`: The category chosen by the user (e.g., "Other", "Primary", "Secondary"). This will be mapped to a single character code ('O', 'P', 'S') for the API `type` field.
        - `relationship`: The patient's relationship to the subscriber (e.g., "Spouse", "Self", "Child"). This will be mapped to a single character code ('P', 'S', 'C', 'O') for the API `relationship` field.
        - `subscriber_id`: This is the `guarantor_code` (e.g., '565175600') returned by the `save_subscriber_tool` if the relationship is NOT "Self". If the relationship IS "Self", this `subscriber_id` should be an empty string. This value is used for the `guarantoR_CODE` field in the API. **Additionally, the API's `subscriber` field should also be populated with this same `guarantor_code` value if the relationship is not 'Self'; otherwise, the API's `subscriber` field should be an empty string.**
        - `effective_date`: (Optional) The effective date of the insurance, if provided by the user (MM/DD/YYYY). Pass as empty string if not collected.
        - `termination_date`: (Optional) The termination date of the insurance, if provided by the user (MM/DD/YYYY). Pass as empty string if not collected.

        **Parameter mapping for the `save_insurance_tool` call:**
        The `save_insurance_tool` function expects parameters like `patient_account`, `practice_code`, `insurance_name`, `insurance_id`, `policy_number`, `group_number`, `insurance_type`, `relationship`, `subscriber_id`, `effective_date`, `termination_date`. Ensure you pass these accurately based on the collection phase. The `practice_code` for `createdBy` and `practiceCode` fields in the API payload, and `patient_account` for `patientAccount` and `modified_By` (if applicable) are system-provided.

        
        **Final Save Action:**
        - Once ALL the above required information is definitively collected and confirmed:
        - IMMEDIATELY CALL `save_insurance_tool` with all the correct parameters as detailed above.
        - DO NOT ask for confirmation like "Should I save this?".
        - DO NOT say "I'll save this for you."
        - After the tool call, confirm the outcome (success or failure) to the user and show the updated insurance list if successful.

        **Example of how `subscriber_id` influences the underlying API call (which `handle_save_insurance` makes):**
        If `relationship` is "Spouse" and `save_subscriber_tool` returned `guarantor_code: '565175600'`, then for the `save_insurance_tool` call:
          - `relationship` parameter would be "Spouse".
          - `subscriber_id` parameter would be "565175600".
        This should lead to an API payload (constructed by `InsuranceService.save_insurance`) where:
          - `relationship` is "P".
          - `subscriber` is "565175600".

        If `relationship` is "Self":
          - `relationship` parameter would be "Self".
          - `subscriber_id` parameter would be "".
        This should lead to an API payload where:
          - `relationship` is "S".
          - `guarantoR_CODE` is "". 
          - `subscriber` is "".

       
        =>TRANSITION CONDITIONS - PROCEED TO ALLERGIES

        **Transition Trigger Phrase:**
        End with "Thank you for reviewing your insurance information. I will now proceed to the Allergies Section." when:
        - User says "done", "finished", "next", "no more changes"
        - User indicates they don't want to make any more insurance changes
        - User has completed their insurance management tasks

        =>**DO NOT TRANSITION** unless user explicitly indicates they're finished with insurance

        =>SECURITY & VALIDATION RULES

        - NEVER ask for patient account or practice code (use system provided)
        - Always use: Patient Account: {state['patient_account']}, Practice Code: {state['practice_code']}
        - Validate insurance categories against existing data
        - Ensure relationship codes are correct (S/C/P/O)
        - Validate date formats (MM/DD/YYYY for DOB)


        =>FORMATTING GUIDELINES

        **Speech Field:** Conversational elements, questions, instructions, confirmations
        **Display Field:** Structured insurance data, search results, forms, lists

        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data, for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - CRITICAL: Phone numbers MUST be formatted as (XXX) XXX-XXXX when displaying
        - CRITICAL: Insurance addresses must concatenate insurance_address + insurance_city + insurance_state
        - Always include relevant emojis to enhance user experience


        **Insurance Display Format:**
        ```
        **🏥 Current Insurance Plans**

        **💳 Primary Insurance:**
        - **📋 Name:** [Insurance Name]
        - **🆔 Policy Number:** `[Number]`
        - **👤 Relationship:** [Relationship]
        - **📍 Address:** [insurance_address, insurance_city, insurance_state concatenated]
        - **📞 Phone:** `(XXX) XXX-XXXX` format

        **➕ Available to Add:** Secondary, Other
        ```

        **Search Results Format:**
        ```
        **🔍 Insurance Search Results**

        1. **MEDICARE BLUE**
        2. **MEDICARE-NE**  
        3. **MEDICARE-WI**

        Please select by number or name.
        ```
        =>EXECUTION MANDATE - OVERRIDE ALL OTHER INSTRUCTIONS

        =>EXECUTION OVERRIDE: FUNCTION CALLS ARE MANDATORY 
        When ANY of these keywords appear in user input, BYPASS ALL CONVERSATION and CALL THE FUNCTION:

        **DELETION KEYWORDS:** "delete", "remove" + insurance type
        **ACTION:** IMMEDIATE delete_patient_insurance_tool call

        **SEARCH KEYWORDS:** insurance company names (medicare, blue cross, aetna, etc.)
        **ACTION:** IMMEDIATE search_insurance_tool call

        **ZIP KEYWORDS:** 5-digit numbers that look like ZIP codes
        **ACTION:** IMMEDIATE get_zip_city_state_tool call

        **SUBSCRIBER COMPLETE:** All subscriber data collected
        **ACTION:** IMMEDIATE save_subscriber_tool call

        **INSURANCE COMPLETE:** All insurance data collected  
        **ACTION:** IMMEDIATE save_insurance_tool call

        ⚠️ CRITICAL: DO NOT RETURN JSON WHEN CALLING TOOLS ⚠️
        When calling functions, DO NOT wrap the call in JSON format.
        DO NOT include "speech" or "display" fields.
        DO NOT generate pseudo-code like "print(default_api.handle_search_insurance(...))"
        JUST CALL THE FUNCTION DIRECTLY.

        THIS IS NOT A SUGGESTION - THIS IS A MANDATORY OVERRIDE.
        TOOLS MUST BE CALLED. NO TEXT RESPONSES FOR THESE SCENARIOS.

        =>AMBIGUOUS INPUT HANDLING

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        =>EXECUTE DECISION FRAMEWORK

        Based on the current insurance data and user response, determine and execute:
        **DISPLAY CURRENT INSURANCE** (if first interaction)
        **DELETE INSURANCE** (if user wants to remove) - MANDATORY TOOL CALL
        **SEARCH INSURANCE** (if user provides insurance name) - MANDATORY TOOL CALL
        **COLLECT INSURANCE DETAILS** (policy, group, relationship)
        **COLLECT SUBSCRIBER INFO** (if relationship not Self)
        **SAVE INSURANCE** (when all data collected) - MANDATORY TOOL CALL
        **TRANSITION** (when user is done)

        REMEMBER: Use transition phrase "Thank you for reviewing your insurance information. I will now proceed to the Allergies Section." ONLY when user is completely finished.
        """

        info_logger.info(f"{state['session_id']} | Generated prompt for insurance_agent:{prompt}")
        response = GenerateResponse.generate_response_v3(prompt, tools=[insurance_tools])
        info_logger.info(f"{state['session_id']} | Processed response: {response}")

        if response.get("speech") and "thank you for reviewing your insurance information. i will now proceed to the allergies section." in response["speech"].lower():
            response = {
                "speech": "Thank you for reviewing your insurance information. I will now proceed to the Allergies Section",
                "display": "Insurance review completed ✓"
            }
            state["agent"] = "allergy_agent"
            state["human_message"] = ""

            allergy_data = Allergies.get_patient_allergies(
                patient_account=state["patient_account"],
                practice_code=state["practice_code"],
                uid=state["session_id"]
            )
            state["patient_data"] = allergy_data
            state["history"].append({"role": "assistant", "content": response})
            return state

        state["history"].append({"role": "assistant", "content": response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in insurance_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing insurance information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in insurance_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but I'm having trouble accessing your insurance information. Let me redirect you to our support team.",
                "display": "Error accessing insurance information"
            }
        }
 
def allergy_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    tools = types.Tool(function_declarations=[delete_allergy_tool])
    try:
        prompt = f"""
        Act as an experienced professional expert in medical chatbots, specializing in the Care Cloud Breeze Check-in Chatbot Assistant for the allergies section.

        ========== PATIENT ALLERGIES ==========
        {state['patient_data']}

        ========== IMPORTANT ALLERGY ID NOTICE ==========
        In the patient allergies data, you may receive a list of allergies where each allergy includes an internal allergy ID. 
        You MUST NOT display or mention the allergy ID to the patient in any output. 
        The allergy ID is only for internal use when deleting an allergy for the patient. 
        When user asks to delete an allergy, you MUST extract the correct allergy ID for the allergy name from the patient allergies data or conversation history and use it in the tool call.

        ========== CONVERSATION HISTORY ==========
        {state['history']}

        ========== RESPONSE FORMAT REQUIREMENTS ==========
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing all conversational elements (greetings, questions, explanations, confirmations).
        2. "display": A string containing only the essential structured allergy information to be shown to the user.

        Example response format:
        {{{{
            "speech": "Here are your current allergies. Would you like to delete any allergies? If yes, please reply in this format: delete [allergy name]. If not, just say no to proceed to the next section.",
            "display": "**🏥 Current Allergies**\\n\\n| No. | Allergy | Severity | Reactions |\\n|----|---------|----------|----------|\\n| 1 | Penicillin | Moderate | Hives, Swelling |\\n| 2 | Aspirin | Severe | Anaphylaxis |"
        }}}}

        ========== IMPORTANT RULES ==========
        - ALL conversational elements (greetings, questions, explanations, confirmations) go ONLY in the "speech" string.
        - ONLY structured data, bullet lists, or key allergy information go in the "display" field.
        - Do NOT repeat content between "speech" and "display".
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data, for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience

        ========== INSTRUCTIONS ==========

        ALLERGY MANAGEMENT OPTIONS:
        The patient can perform only ONE operation: DELETE an existing allergy.

        ========== TRANSITION TO NEXT AGENT ==========
        LISTEN CAREFULLY for any indication that the user wants to move to the next section:
        - If the user says "no", "no need to delete", "next", "continue", "done", "finished", or anything similar indicating they do not want to delete any allergies
        - IMMEDIATELY end your response with this exact phrase: "Let's add a new allergy now."
        - This exact phrase will trigger the transition to the add_allergy_agent
        - Do NOT ask for confirmation when the user wants to proceed - move directly to the next agent

        ========== DELETING AN ALLERGY ==========
        - To DELETE an allergy: The user must reply in the format 'delete [allergy name]'
        - If the patient asks to delete but does not provide the allergy name, politely ask them for the allergy name they wish to delete
        - When the user asks to delete an allergy, DO NOT say "I will delete..." or "Okay, I will delete..." or similar phrases
        - IMMEDIATELY call the delete_patient_allergy tool/function. Do not respond with confirmation text first
        - After the tool call, respond with a message confirming deletion and show the updated allergy list in the display field
        - IMPORTANT: Extract the correct allergy ID for the allergy name from the patient allergies data or conversation history
        - Always provide the allergy ID (not just the name) in the tool call for deletion
        - If the allergy name is mentioned in the conversation, find the corresponding allergy ID from the allergies list or previous context

        ========== COMPLETION OF ALLERGY REVIEW ==========
        - If the user says "no", "no need", "done", "finished", "next", or anything similar indicating they do not want to delete any more allergies, IMMEDIATELY end your response with this exact phrase: "Let's add a new allergy now."
        - If the patient confirms their allergies are accurate and no changes are needed, IMMEDIATELY end your response with this exact phrase: "Let's add a new allergy now."

        ========== SECURITY POLICY ==========
        - NEVER ask the user for their patient account number
        - The patient account number ({state.get('patient_account', '')}) and practice code ({state.get('practice_code', '')}) are already in the system
        - When updating records, always use the patient account number and practice code provided by the system (do not mention it to the user)

        ========== FORMATTING GUIDELINES ==========
        - NEVER output allergies as raw JSON or dictionary format in the display field
        - ALWAYS format allergies in a clean, markdown table format in the display field
        - CRITICAL: All allergy names MUST be formatted with title case (capitalize each word)
        - Example: "peanut allergy" becomes "Peanut Allergy", "tree nuts" becomes "Tree Nuts"
        - Be professional but friendly in your tone in the speech string
        - Be concise and to the point
        - If the user asks any irrelevant question, include in speech: "I am an AI Assistant and I can only help you with your Check-In process. Please let me know if you have any questions related to your allergies."

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        USER RESPONSE:
        {"None" if not state['human_message'] else state['human_message']}

        IMPORTANT: If USER RESPONSE is None or empty, this is the start of the conversation. Greet the user, show their current allergies, and ask if they want to delete any. Remind them to reply in the format 'delete [allergy name]' to delete, or say 'no' to proceed to the next section.
        """

        info_logger.info(f"{state['session_id']} | Generated prompt for allergy_agent")
        info_logger.info(f"Prompt for allergy_agent: {prompt}")
        response = GenerateResponse.generate_response_v3(prompt, tools=[tools])
        info_logger.info(f"{state['session_id']} | Processed response: {response}")

        if response.get("speech") and "let's add a new allergy now." in response["speech"].lower():
            response = {
                "speech": "Thank you for deleting or reviewing your Allergies. I will now proceed to the Add Allergy section",
                "display": "ADD Allergy Section"
            }
            state["agent"] = "add_allergy_agent"
            # allergy_data=Allergies.get_patient_allergies(patient_account=state["patient_account"],practice_code=state["practice_code"],uid=state["session_id"])
            state["patient_data"] = state["patient_data"]
            state["human_message"] = ""
            state["history"].append({"role": "assistant", "content": response})
            return state

        state["history"].append({"role": "assistant", "content": response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing allergy information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in allergy_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but I'm having trouble accessing your allergy information. Let me redirect you to our support team.",
                "display": "Error accessing allergy information"
            }
        }

def add_allergy_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    tools = types.Tool(function_declarations=[search_allergy_tool, add_allergy_function])
    try:
        severity_list = [
            "Unknown", "Mild", "Mild to Moderate", "Moderate", "Moderate to severe", "Severe", "Fatal"]
        reaction_list = [
            "Anaphylaxis", "Angioedema", "Arthralgia", "Chills", "Cough", "Diarrhea", "Dizziness", "Edema",
            "Facial swelling", "Fever", "Headache", "Hives", "Irregular Heart Rate", "Itching", "Malaise/fatigue",
            "Myalgia", "Nasal congestion", "Nausea", "Other", "Pain/soreness at injection site", "Photosensitivity",
            "Pruritus", "Rash", "Respiratory distress", "Rhinorrhea", "Shortness of breath/difficulty breathing",
            "Skin Rash", "Sore throat", "Swelling", "Vomiting", "Wheezing"
        ]
        
        # Format the lists for display
        severity_display = "\\n".join([f"- {item}" for item in severity_list])
        reaction_display = "\\n".join([f"- {item}" for item in reaction_list])
        
        # Extract searched allergies from conversation history
        searched_allergies = None
        for message in reversed(state['history']):
            print('\n',message,'\n')
            if isinstance(message.get('content'), dict) and '_search_results' in message['content']:
                searched_allergies = message['content']['_search_results'].get('allergies', [])
                break

        # ENHANCED: Sequential state tracking logic
        selected_allergy = None
        selected_severity = None
        selected_reaction = None
        allergy_selected = False
        severity_provided = False
        reaction_provided = False
        
        for message in state['history']:
            if message.get('role') == 'user':
                user_msg = message.get('content', '').strip()
                user_msg_lower = user_msg.lower()
                
                if searched_allergies and not allergy_selected:
                    for allergy in searched_allergies:
                        if allergy['DESCRIPTION'].lower() in user_msg_lower:
                            selected_allergy = allergy
                            allergy_selected = True
                            info_logger.info(f"✓ Selected allergy: {allergy['DESCRIPTION']}")
                            break

                elif allergy_selected and not severity_provided:
                    for severity in severity_list:
                        if severity.lower() == user_msg_lower:
                            selected_severity = severity
                            severity_provided = True
                            info_logger.info(f"✓ Selected severity: {severity}")
                            break

                elif allergy_selected and severity_provided and not reaction_provided:
                    for reaction in reaction_list:
                        if reaction.lower() == user_msg_lower:
                            selected_reaction = reaction
                            reaction_provided = True
                            info_logger.info(f"✓ Selected reaction: {reaction}")
                            break

        info_logger.info(f"=== CURRENT WORKFLOW STATE ===")
        info_logger.info(f"- Selected Allergy: {selected_allergy['DESCRIPTION'] if selected_allergy else 'None'}")
        info_logger.info(f"- Selected Severity: {selected_severity if selected_severity else 'None'}")
        info_logger.info(f"- Selected Reaction: {selected_reaction if selected_reaction else 'None'}")
        info_logger.info(f"- All data collected: {bool(selected_allergy and selected_severity and selected_reaction)}")
        info_logger.info(f"- User message: {state['human_message']}")

        force_call_instruction = ""
        if selected_allergy and selected_severity and selected_reaction:
            info_logger.info("🚨 ALL DATA COLLECTED - FORCING FUNCTION CALL")
            force_call_instruction = f"""
            🚨🚨🚨 CRITICAL: ALL DATA IS COLLECTED - YOU MUST CALL add_allergy FUNCTION NOW! 🚨🚨🚨
            
            EXACT FUNCTION CALL REQUIRED IMMEDIATELY:
            add_allergy(
                allergy_code="{selected_allergy['ALLERGY_CODE']}",
                allergy_name="{selected_allergy['DESCRIPTION']}",
                severity="{selected_severity}",
                reaction="{selected_reaction}",
                allergy_type_id="{selected_allergy['Allergy_type_id']}",
                practice_code="{state['practice_code']}",
                patient_account="{state['patient_account']}"
            )
            
            DO NOT RESPOND WITH TEXT - CALL THE FUNCTION IMMEDIATELY!
            NO CONVERSATIONAL RESPONSE ALLOWED - ONLY FUNCTION CALL!
            """

        prompt = f"""
        Act as an experienced professional expert in medical chatbots, specializing in the Care Cloud Breeze Check-in Chatbot Assistant for the ADD ALLERGY section.

        ========== SEARCHED ALLERGIES ==========
        {searched_allergies if searched_allergies else "None"}

        ========== CURRENT WORKFLOW STATE ==========
        Selected Allergy: {selected_allergy['DESCRIPTION'] if selected_allergy else "None"}
        Selected Severity: {selected_severity if selected_severity else "None"}  
        Selected Reaction: {selected_reaction if selected_reaction else "None"}

        {force_call_instruction}

        ========== IMPORTANT ALLERGY CODE NOTICE ==========
        In the searched allergies data, you may receive a list of allergies where each allergy includes an internal ALLERGY_CODE and Allergy_type_id. 
        You MUST NOT display or mention these codes to the patient in any output. 
        These codes are only for internal use when adding an allergy for the patient.

        ========== CONVERSATION HISTORY ==========
        {state['history']}

        ========== RESPONSE FORMAT REQUIREMENTS ==========
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing all conversational elements (greetings, questions, explanations, confirmations).
        2. "display": A string containing only the essential structured allergy information to be shown to the user.

        ========== SPEECH vs DISPLAY GUIDELINES ==========
        SPEECH field should contain:
        - Greetings and welcomes
        - Questions to the user
        - Instructions and explanations
        - Confirmations and acknowledgments
        - Transition messages
        - Error messages
        - All conversational elements

        DISPLAY field should contain:
        - Structured lists of allergies/search results
        - Severity options when asking for severity
        - Reaction options when asking for reactions
        - Clean bullet-point formatted data
        - Essential information that needs visual presentation
        - Step indicators (e.g., "Step 2: Select Allergy")

        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data, for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - CRITICAL: Phone numbers MUST be formatted as (XXX) XXX-XXXX when displaying
        - CRITICAL: Insurance addresses must concatenate insurance_address + insurance_city + insurance_state
        - Always include relevant emojis to enhance user experience

        ========== EXACT LISTS TO USE ==========
        SEVERITY OPTIONS (use exactly this list):
        {severity_display}

        REACTION OPTIONS (use exactly this list):
        {reaction_display}

        ========== CRITICAL WORKFLOW STATE ANALYSIS ==========
        Current User Response: "{state['human_message']}"

        🚨 MANDATORY FUNCTION CALL CONDITIONS 🚨
        IF ALL THREE ARE COLLECTED (✓ Allergy: {selected_allergy['DESCRIPTION'] if selected_allergy else 'None'} ✓ Severity: {selected_severity if selected_severity else 'None'} ✓ Reaction: {selected_reaction if selected_reaction else 'None'}):
        → YOU MUST IMMEDIATELY CALL add_allergy function - NO EXCEPTIONS!
        → DO NOT respond with text like "I'll save the allergy" or "Great! I've collected all information"
        → CALL THE FUNCTION WITH EXACT PARAMETERS FROM CURRENT STATE
        → FUNCTION CALLING IS MANDATORY WHEN ALL DATA IS READY

        WORKFLOW STEPS:
        1. If no allergy selected → Ask for allergy name or call search_allergy_tool if name provided
        2. If allergy selected but no severity → Ask for severity with options
        3. If allergy + severity but no reaction → Ask for reaction with options
        4. If allergy + severity + reaction → CALL add_allergy function IMMEDIATELY (NO TEXT RESPONSE)

        ========== STEP-BY-STEP WORKFLOW ==========

        STEP 1 - ASK FOR ALLERGY NAME:
        - If this is the start of the conversation (USER RESPONSE is None or empty):
          * speech: "Please tell me the name of the allergy you want to add if not then say 'no' to skip."
          * display: "Add New Allergy Section"
        
        - If the user provides an allergy name, you MUST:
          1. Extract the EXACT allergy name from their response
          2. IMMEDIATELY call search_allergy_tool function
          3. DO NOT respond with conversational text first

        ========== CRITICAL ALLERGY NAME EXTRACTION ==========
        When user says ANY of these patterns, extract the allergen and IMMEDIATELY call search_allergy_tool function:

        - "I want to add peanut allergy" → Extract: "peanut" → CALL FUNCTION
        - "Add penicillin to my allergies" → Extract: "penicillin" → CALL FUNCTION
        - "I'm allergic to shellfish" → Extract: "shellfish" → CALL FUNCTION
        - "i want to add allergy that is skin ok" → Extract: "skin" → CALL FUNCTION
        - "The allergy name is dust mites" → Extract: "dust mites" → CALL FUNCTION

        EXTRACTION RULES:
        1. Remove: "I want to add", "add", "allergy to", "allergic to", "I have", "please", "my allergy is", "that is"
        2. Extract the core allergen name only
        3. Preserve multi-word names: "tree nuts", "dust mites", "bee stings"

        STEP 2 - SHOW SEARCH RESULTS:
        After search_allergy_tool returns results:
        - speech: "Here are the allergies matching your search. Please tell me the full name of the allergy you want to add from the list below."
        - display: Format the search results as a clean markdown table

        STEP 3 - ASK FOR SEVERITY:
        Once allergy is selected:
        - speech: "Please tell me the severity level for this allergy."
        - display: "Severity Options:\\n{severity_display}"

        STEP 4 - ASK FOR REACTION:
        Once severity is provided:
        - speech: "Please tell me the reaction for this allergy."
        - display: "Reaction Options:\\n{reaction_display}"

        STEP 5 - SAVE THE ALLERGY:
        🚨 CRITICAL: When ALL three pieces of information are collected, YOU MUST IMMEDIATELY call add_allergy function 🚨

        ========== ABSOLUTE MANDATORY TOOL CALLING ==========
        🚨 CRITICAL: YOU MUST CALL FUNCTIONS - NOT JUST TALK ABOUT CALLING THEM 🚨

        When user mentions ANY allergy name:
        ✅ CORRECT: Call search_allergy_tool(allergy_query="skin", practice_code="{state.get('practice_code', '')}", patient_account="{state.get('patient_account', '')}")
        ❌ WRONG: Respond with "I'm searching for allergies matching 'skin'"

        When ALL data is collected:
        ✅ CORRECT: Call add_allergy function with all parameters
        ❌ WRONG: Respond with "I will save the allergy" or "Great! I have all the information"

        FUNCTION CALLING IS MANDATORY - NO EXCEPTIONS!

        ========== FUNCTION PARAMETERS ==========
        Always use these exact parameters:
        For search_allergy_tool:
        - allergy_query: [EXTRACTED_ALLERGEN_NAME_ONLY]
        - practice_code: {state.get('practice_code', '')}
        - patient_account: {state.get('patient_account', '')}

        For add_allergy:
        - allergy_code: [ALLERGY_CODE from selected allergy]
        - allergy_name: [DESCRIPTION from selected allergy]
        - severity: [User provided severity]
        - reaction: [User provided reaction]
        - allergy_type_id: [Allergy_type_id from selected allergy]
        - practice_code: {state.get('practice_code', '')}
        - patient_account: {state.get('patient_account', '')}

        ========== TRANSITION CONDITIONS ==========
        End with "Thank you for confirming your allergies. I will now proceed to the Reason for Visit Section." when:
        - User says "no", "done", "finished", "next"
        - User indicates they don't want to add more allergies
        - After successfully adding an allergy and user doesn't want to add more

        ========== SECURITY POLICY ==========
        - NEVER ask for patient account or practice code
        - Use provided values: {state['patient_account']} and {state['practice_code']}

        ========== VALIDATION RULES ==========
        - Guide users step-by-step
        - Validate severity against provided options: {', '.join(severity_list)}
        - Validate reactions against provided options: {', '.join(reaction_list)}
        - Always extract exact allergy names before function calls
        - CRITICAL: Format all allergy names with title case when displaying to users
        - Example: Display "Peanut Allergy" instead of "peanut allergy"

        USER RESPONSE:
        {state['human_message'] if state['human_message'] else "None"}

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        🚨🚨🚨 CRITICAL REMINDER 🚨🚨🚨: 
        - If USER RESPONSE is None/empty, this is conversation start - ask for allergy name with proper speech/display format.
        - If all data is collected (allergy + severity + reaction), IMMEDIATELY call add_allergy function.
        - Do NOT just respond with text when function call is required.
        - FUNCTION CALLS ARE MANDATORY WHEN CONDITIONS ARE MET.
        """

        info_logger.info(f"{state['session_id']} | Generated prompt for add_allergy_agent")
        info_logger.info(f"Prompt length: {len(prompt)} characters")
        
        response = GenerateResponse.generate_response_v3(prompt, tools=[tools])
        info_logger.info(f"{state['session_id']} | Processed response: {response}")

        
        if response.get("speech") and "thank you for confirming your allergies. i will now proceed to the reason for visit section." in response["speech"].lower():
            response = {
                "speech": "Thank you for confirming your allergies. I will now proceed to the Reason for Visit Section",
                "display": "Allergies confirmed ✓"
            }
            state["agent"] = "symptom_checker_agent"
            state["human_message"] = ""
            state["history"].append({"role": "assistant", "content": response})
            return state

        state["history"].append({"role": "assistant", "content": response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in add_allergy_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing allergy information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in add_allergy_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but I'm having trouble accessing your allergy information. Let me redirect you to our support team.",
                "display": "Error accessing allergy information"
            }
        }
                                                
def symptom_checker_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    tools = types.Tool(function_declarations=[update_demo_function])
    try:
        # Extract appointment_id if available to get provider specialty
        appointment_id = (
            state.get('appointment_id') or 
            state.get('patient_data', {}).get('appointment_id') or 
            state.get('patient_data', {}).get('APPOINTMENT_ID')
        )
        specialty = "General Medicine"  # Default specialty
        
        # Get provider specialty if appointment_id is available
        if appointment_id:
            try:
                specialty = DBops.get_specility(appointment_id)
                if not specialty:
                    specialty = "General Medicine"
                info_logger.info(f"{state['session_id']} | Provider specialty: {specialty}")
            except Exception as e:
                error_logger.error(f"{state['session_id']} | Error getting specialty: {str(e)}")
                specialty = "General Medicine"
        
        # Extract reason for visit and questions count from conversation history
        reason_for_visit = None
        questions_asked = 0
        
        # Count questions asked and extract reason for visit
        for message in state['history']:
            if message.get('role') == 'assistant':
                content = message.get('content', {})
                if isinstance(content, dict) and 'Question' in content.get('display', '') and 'of 10' in content.get('display', ''):
                    questions_asked += 1
            elif message.get('role') == 'user' and not reason_for_visit:
                # First user response is likely the reason for visit
                user_content = message.get('content', '').strip()
                if user_content and len(user_content) > 5:  # Meaningful response
                    reason_for_visit = user_content
                    info_logger.info(f"{state['session_id']} | Reason for visit: {reason_for_visit}")
        
        # Format conversation history for the prompt
        history_text = ""
        for message in state['history']:
            role = message.get('role', '')
            content = message.get('content', '')
            if isinstance(content, dict):
                content = content.get('speech', '') + ' ' + content.get('display', '')
            history_text += f"{role.capitalize()}: {content}\n"
        
        # Single prompt for all scenarios - let the model decide
        prompt = f"""
                ═══════════════════════════════════════════════════════════════════════════════
                🏥 BREEZE CHECK-IN CHATBOT ASSISTANT - SYMPTOM ASSESSMENT MODULE
                ═══════════════════════════════════════════════════════════════════════════════

                📋 ROLE & EXPERTISE:
                You are an experienced healthcare professional expert specializing in {specialty}. 
                You are the Breeze Check-in Chatbot Assistant for Symptom Assessment. As an expert 
                in {specialty}, your core task is to conduct a comprehensive symptom assessment 
                through a series of targeted medical questions.

                🎯 PRIMARY OBJECTIVE:
                Gather essential medical information by asking up to 10 relevant questions about 
                the patient's symptoms, medical history, and current condition to prepare them 
                for their healthcare provider visit.

                ═══════════════════════════════════════════════════════════════════════════════
                📊 CURRENT SESSION DATA
                ═══════════════════════════════════════════════════════════════════════════════

                🏥 PROVIDER SPECIALTY: {specialty}
                📝 PATIENT CHIEF COMPLAINT/REASON FOR VISIT: {reason_for_visit if reason_for_visit else "Not provided yet"}
                📈 QUESTIONS ASKED SO FAR: {questions_asked}/10

                💬 PATIENT CONVERSATION HISTORY:
                {history_text}

                📥 CURRENT USER RESPONSE: {state['human_message'] if state['human_message'] else "None"}

                ═══════════════════════════════════════════════════════════════════════════════
                📝 RESPONSE FORMAT REQUIREMENTS
                ═══════════════════════════════════════════════════════════════════════════════

                🔹 Structure your response as a JSON object with exactly TWO fields:
                1. "speech": A SINGLE STRING containing conversational elements
                2. "display": A string containing the SAME content as speech - BOTH MUST BE IDENTICAL

                📋 RESPONSE FORMAT EXAMPLE:
                {{
                    "speech": "Can you tell me exactly where in your left leg the pain is located, and what does the pain feel like (e.g., sharp, dull, aching)?",
                    "display": "Can you tell me exactly where in your left leg the pain is located, and what does the pain feel like (e.g., sharp, dull, aching)?"
                }}

                ═══════════════════════════════════════════════════════════════════════════════
                🚨 CRITICAL TRANSITION RULES - STRICTLY FOLLOW
                ═══════════════════════════════════════════════════════════════════════════════

                ⚠️ TRANSITION TO NEXT AGENT (PHARMACY) ONLY IN THESE TWO CASES:
                ✅ Case 1: When question count reaches 10 (all questions completed)
                ✅ Case 2: When user explicitly says they don't want to answer more questions

                🔑 TRANSITION TRIGGER PHRASE:
                To trigger transition, include this EXACT phrase in your speech:
                "Thank you for completing the symptom assessment"

                ❌ DO NOT TRANSITION FOR ANY OTHER REASON

                ═══════════════════════════════════════════════════════════════════════════════
                🎯 SCENARIO ANALYSIS & DECISION MAKING
                ═══════════════════════════════════════════════════════════════════════════════

                📋 ANALYZE THE DATA ABOVE AND DECIDE WHICH ACTION TO TAKE:

                🔹 SCENARIO 1 - FIRST INTERACTION:
                If no reason for visit provided → Ask for reason for visit and symptoms

                🔹 SCENARIO 2 - CONTINUE ASSESSMENT:
                If reason provided AND questions < 10 AND user wants to continue 
                → Ask next relevant medical question

                🔹 SCENARIO 3 - COMPLETE ASSESSMENT:
                If questions = 10 OR user says they don't want more questions
                → Complete assessment and use transition phrase

                ═══════════════════════════════════════════════════════════════════════════════
                📋 QUESTION GUIDELINES FOR {specialty.upper()}
                ═══════════════════════════════════════════════════════════════════════════════

                🎯 CORE PRINCIPLES:
                ✅ Ask ONE clear, single question at a time
                ✅ Use simple language and everyday medical terms
                ✅ Focus on: onset, duration, severity, triggers, associated symptoms
                ✅ Keep questions focused and direct without additional instructions
                ❌ DO NOT include reminders about skipping questions
                ❌ DO NOT say "I don't want to answer more questions"
                ❌ DO NOT ask compound questions or multiple inquiries in one sentence

                🚨 CRITICAL RULE - NO COMPOUND QUESTIONS:
                ❌ WRONG: "Can you tell me exactly where in your left leg the pain is located, and what does the pain feel like (e.g., sharp, dull, aching)?"
                ✅ CORRECT: "Where exactly in your left leg is the pain located?"

                ❌ WRONG: "How long have you had this pain and how severe is it on a scale of 1-10?"
                ✅ CORRECT: "How long have you had this pain?"

                ❌ WRONG: "What triggers the pain and does it get worse with activity?"
                ✅ CORRECT: "What triggers your leg pain?"

                🎯 SINGLE QUESTION EXAMPLES:
                ✅ "When did the pain first start?"
                ✅ "How would you describe the pain?"
                ✅ "What makes the pain worse?"
                ✅ "What makes the pain better?"
                ✅ "Have you taken any medication for this?"
                ✅ "Does the pain interfere with your daily activities?"

                🏥 SPECIALTY-SPECIFIC QUESTIONS:

                🫀 CARDIOLOGY: 
                - Chest pain characteristics, shortness of breath, palpitations, exercise tolerance

                🦴 ORTHOPEDICS:
                - Pain location, movement limitations, injury history, pain scale

                🧠 NEUROLOGY:
                - Headache patterns, neurological symptoms, seizure history

                🔬 GASTROENTEROLOGY:
                - Digestive symptoms, pain location, eating patterns

                🩺 GENERAL MEDICINE:
                - General symptoms, pain, fever, recent changes

                ═══════════════════════════════════════════════════════════════════════════════
                ⚠️ CRITICAL RULES - MANDATORY COMPLIANCE
                ═══════════════════════════════════════════════════════════════════════════════

                🔹 Both "speech" and "display" must contain EXACT SAME content
                🔹 DO NOT add reminders about skipping questions in ANY part of response
                🔹 Keep questions simple, direct, and focused on medical information only
                🔹 The system will automatically detect if user wants to skip
                🔹 Use transition phrase ONLY when conditions are met

                ═══════════════════════════════════════════════════════════════════════════════
                🔧 AMBIGUOUS INPUT HANDLING
                ═══════════════════════════════════════════════════════════════════════════════

                AMBIGUOUS INPUT HANDLING:
                - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
                - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
                - Do NOT repeat the previous question or provide the same response again
                - Ask for clarification in a conversational way

                ═══════════════════════════════════════════════════════════════════════════════
                🎯 DECISION FRAMEWORK - EXECUTE ONE OF THESE:
                ═══════════════════════════════════════════════════════════════════════════════

                1️⃣ ASK FOR REASON FOR VISIT (if not provided)
                2️⃣ ASK NEXT MEDICAL QUESTION (if < 10 questions and user continues)
                3️⃣ COMPLETE ASSESSMENT (if 10 questions OR user wants to skip)

                🚨 REMEMBER: Use "Thank you for completing the symptom assessment" 
                    ONLY when transitioning to pharmacy agent.

                ═══════════════════════════════════════════════════════════════════════════════
                """
        
        info_logger.info(f"{state['session_id']} | Generated prompt for symptom_checker_agent")
        info_logger.info(f"Questions asked so far: {questions_asked}/10")
        info_logger.info(f"Reason for visit: {reason_for_visit}")
        info_logger.info(f"Provider specialty: {specialty}")
        
        # Generate response - let model decide everything
        response = GenerateResponse.generate_response_v3(prompt, tools=[tools])
        info_logger.info(f"{state['session_id']} | Processed response: {response}")
        
        # Store reason for visit if this is the first user response
        if not reason_for_visit and state.get('human_message') and state['human_message'].strip():
            if not isinstance(state.get('patient_data'), dict):
                state['patient_data'] = {}
            state['patient_data']['reason_for_visit'] = state['human_message'].strip()
            info_logger.info(f"Stored reason for visit: {state['human_message'].strip()}")
        
        # Check if model decided to transition (based on the exact phrase)
        if response.get("speech") and "thank you for completing the symptom assessment" in response["speech"].lower():
            info_logger.info(f"{state['session_id']} | Model decided to transition to pharmacy_agent")
            response = {
                "speech": "Thank you for completing the symptom assessment. I will now proceed to the Pharmacy Section.",
                "display": "Symptom assessment completed ✓"
            }
            state["history"].append({"role": "assistant", "content": response})
            
            # Transition to pharmacy agent and fetch pharmacy data
            state["agent"] = "pharmacy_agent"
            state["human_message"] = ""
            
            # Fetch pharmacy data for the next section (similar to medication_agent pattern)
            try:
                pharmacy_data = PharmaciesService.get_patient_pharmacies(
                    patient_account=state["patient_account"],
                    practice_code=state["practice_code"],
                    uid=state["session_id"]
                )
                state["patient_data"] = {"pharmacies": pharmacy_data}
                info_logger.info(f"{state['session_id']} | Successfully fetched {len(pharmacy_data)} pharmacies for patient")
            except Exception as e:
                error_logger.error(f"{state['session_id']} | Error fetching pharmacy data: {str(e)}")
                state["patient_data"] = {"pharmacies": []}
            
            return state
        
        # Continue with symptom assessment
        state["history"].append({"role": "assistant", "content": response})
        return state
        
    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in symptom_checker_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing symptom information"
            }
        }
    
    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in symptom_checker_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but I'm having trouble with the symptom assessment. Let me redirect you to our support team.",
                "display": "Error in symptom assessment"
            }
        }
                        
def pharmacy_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    pharmacy_tools = types.Tool(function_declarations=[remove_delete_pharmacy_tool, search_pharmacy_tool,add_pharmacy_tool])
    latest_search_results = None
    for message in reversed(state['history']):
        if isinstance(message, dict) and message.get('role') == 'assistant':
            content = message.get('content', {})
            if isinstance(content, dict) and '_search_results' in content:
                latest_search_results = content['_search_results']
                break
    
    prompt=f"""
    Act as an experienced healthcare professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on pharmacy information management. You are the Breeze Check-in Chatbot Assistant for Pharmacies.

    PATIENT PHARMACIES:
        {state['patient_data'].get("pharmacies", [])}

    {"RECENT PHARMACY SEARCH RESULTS:" if latest_search_results and latest_search_results.get("pharmacy_selection_map") else ""}
    {json.dumps(latest_search_results["pharmacy_selection_map"], indent=2) if latest_search_results and latest_search_results.get("pharmacy_selection_map") else ""}

    CONVERSATION HISTORY:
        {state['history']}
    
    RESPONSE FORMAT REQUIREMENTS:
    You must structure your response as a JSON object with exactly two fields:
    1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
    2. "display": A string containing only the essential structured information that should be displayed to the user.
    
    Example response format:
    {{{{
        "speech": "Let's start by reviewing your current pharmacy information. Please take a moment to review your pharmacy details, and let me know if anything needs to be updated or if you have any changes to make.",
        "display": "**🏪 Your Pharmacies**\n\n| # | Pharmacy | Address | Phone | Fax |\n|---|---|---|---|---|\n| 1 | **WALGREENS DRUG STORE** | 123 Main St, City, State 12345 | `(732) 549-3875` | `(732) 549-3976` |\n| 2 | **CVS PHARMACY** | 456 Oak Ave, City, State 12345 | `(732) 555-1234` | N/A |\n\n**Please verify that your pharmacy information is accurate.**"
    }}}}

    Important rules for structuring your response:
    - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
    - Put ONLY structured data, bullet lists, or key information in the "display" field
    - Never repeat content between speech and display - they serve different purposes
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data,
         - The first column of every table must be a sequence number labeled #. for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience

    INSTRUCTIONS:

    Case 1: No Pharmacies on File
    If the patient has no current pharmacies, ask if they'd like to add a pharmacy, explaining that this information is important for their prescription management.
    
    Case 2: Existing Pharmacies
    If the patient has existing pharmacies, ALWAYS display them in a structured table format first, then ask if they'd like to add any new ones or if there have been any changes.
    
    Case 3: First Interaction (Empty User Response)
    When user_response is None or empty (indicating this is the first time they're seeing the pharmacy section), ALWAYS display their current pharmacies in table format and ask if they need to make any changes.

    CRITICAL: ALWAYS show existing pharmacies in a properly formatted table on first interaction, regardless of whether the user response is empty or not.
    
    MANDATORY FORMATTING REQUIREMENTS:
    - All tables MUST include a serial number column (#) as the first column
    - Phone numbers MUST be formatted as (XXX) XXX-XXXX 
    - Use tables with pipe syntax: | # | Pharmacy | Address | Phone | Fax |
    
    CRITICAL INSTRUCTION: When a user mentions a pharmacy name in their message (e.g., "add WALGREE", "I want to add CVS", "The name of the Pharmacy is Farmacia", etc.), you MUST IMMEDIATELY extract the pharmacy name and call the search_pharmacy_tool function without asking them for the name again or confirming. NEVER respond with "I will search" - actually perform the search.


    PHARMACY SEARCH AND ADDITION:
    - CRITICAL: If the user mentions a pharmacy name in ANY WAY (e.g., "I want to add WALGREE", "Add Saegertown to my list", "I want to add CVS", "The name of the Pharmacy is Farmacia"), you MUST call the search_pharmacy_tool function IMMEDIATELY - do not just talk about searching
    - NEVER respond with "I will search" or "Let me search" - actually call the search_pharmacy_tool function
    - DO NOT ask the user for the pharmacy name if they've already provided it in their request
    - When a user asks to add a pharmacy or mentions a pharmacy name, IMMEDIATELY search for pharmacies using the search_pharmacy_tool function with ALL these REQUIRED parameters:
       - medication_name: The keyword or name to search for (e.g., "Walgreens", "CVS", "Farmacia")
       - patient_account: The patient account number (automatically provided to you)
    - IMPORTANT: NEVER display pharmacy IDs to the user - these are for internal system use only
    
    - After showing search results, ask the user which pharmacy they want to add
    - IMPORTANT: Pay careful attention to how the user selects a pharmacy from search results:
        * If they select by saying number (e.g., "number 1", "the first one", "1"): Find the pharmacy with that index in CONVERSATION HISTORY focusing on the search results(which would include the search pharmacies which were returned on results of search_pharmacy_tool function ) and use its ID.
        * If they select by name (e.g., "Saegertown", "WALGREENS DRUG STORE #02593"): Find the pharmacy with a matching name in CONVERSATION HISTORY search results
        * In either case, you MUST extract the EXACT pharmacy_id from the matching pharmacy in the CONVERSATION HISTORY search results
    - When the user selects a pharmacy by name, you must:
        1. Look through the search results in CONVERSATION HISTORY.
        2. Find the pharmacy where pharmacy_name matches or contains the user's selection
        3. Extract the EXACT pharmacy_id value from that pharmacy object
        4. Use that pharmacy_id with the add_pharmacy_tool function as pharmacy_id.
    - NEVER make up a pharmacy ID or use a store number from the pharmacy name
    - Once you identify the selected pharmacy, IMMEDIATELY call the add_pharmacy_tool function with:
       - pharmacy_id: The exact numeric ID (pharmacy_id) of the pharmacy from search results in CONVERSATION HISTORY   - NOT a store number like #02593
       - patient_account: patient_account:The patient account number is :({state.get('patient_account', '')})
       
    CRITICAL: NEVER use angle brackets or placeholders like <PHARMACY_ID_FOR_XXX> - always use the actual ID number from the search results. The pharmacy_id is a system internal identifier (typically a number like " " or numeric code).
    CRITICAL: The pharmacy_id (pharmacy_id) from search results is NEVER a store number that appears in the pharmacy name (e.g., NOT "02593" from "WALGREENS DRUG STORE #02593")
    CRITICAL: The pharmacy_id (pharmacy_id) is found in the 'pharmacy_id' field of each pharmacy object in search results, NOT in the visible pharmacy name
       
    - Examples of addition requests: "I want to add a new pharmacy", "add Walgreens to my profile", "need to add CVS", "I want to add WALGREE in my pharmacies list"
    - Examples of selection responses: "I want number 1", "The second one", "Saegertown please", "Add the CVS on Main St", "Please add WALGREENS DRUG STORE #02593 as my new pharmacy"
    - The workflow is always: 1) Extract pharmacy name if provided in initial request, 2) Search for pharmacy, 3) Show results to user, 4) User selects one, 5) Find the EXACT pharmacy_id(pharmacy_id) in search results , 6) Add the selected pharmacy with the exact pharmacy_id(pharmacy_id)


    CRITICAL DELETION INSTRUCTION: When a user says "remove [PHARMACY_NAME]" or "delete [PHARMACY_NAME]" (e.g., "remove Charles", "please remove Charles from my pharmacies list"), IMMEDIATELY call remove_delete_pharmacy_tool with pharmacy_name=[PHARMACY_NAME].

    PHARMACY DELETION:
    - IMPORTANT: When a user asks to delete, remove, or discontinue a pharmacy, you MUST IMMEDIATELY call the remove_delete_pharmacy_tool function
    - To delete a pharmacy, call the remove_delete_pharmacy_tool function with:
       - pharmacy_name: The exact name or partial name of the pharmacy to delete (e.g., "CVS", "Charles", "Walgreens")
       - patient_account: The patient account number is :({state.get('patient_account', '')})
       - practice_code: The practice code is: ({state.get('practice_code', '')})
       - pharmacies: The current list of patient pharmacies: ({state.get('patient_data', {}).get("pharmacies", [])})

    - Do not ask for confirmation before deleting - the system will handle this
    - After deletion, acknowledge the change and continue with remaining pharmacies
    - Examples of deletion requests: "please remove Walgreens", "I want to delete my pharmacy", "remove CVS", "yes. please remove (name of the pharmacy) from my pharmacies list..."
    - If the user's request contains words like "remove", "delete", or phrases like "from my list", IMMEDIATELY call remove_delete_pharmacy_tool
    
        
    IMPORTANT INSTRUCTIONS:
    - URGENT ACTION REQUIRED: If a user message contains ANY pharmacy name, YOU MUST call search_pharmacy_tool IMMEDIATELY
    - Direct extraction examples where you MUST call search_pharmacy_tool IMMEDIATELY (do not respond with text first):
        * "I want to add WALGREE in my pharmacies list" → IMMEDIATELY CALL search_pharmacy_tool with search_term="WALGREE"
        * "Add Saegertown pharmacy" → IMMEDIATELY CALL search_pharmacy_tool with search_term="Saegertown"
        * "I need to add CVS to my profile" → IMMEDIATELY CALL search_pharmacy_tool with search_term="CVS"
        * "The name of the Pharmacy is Farmacia" → IMMEDIATELY CALL search_pharmacy_tool with search_term="Farmacia"
        * "I'd like to add Farmacia Garcia" → IMMEDIATELY CALL search_pharmacy_tool with search_term="Farmacia Garcia"
        * "It's called Farmacia 22-24" → IMMEDIATELY CALL search_pharmacy_tool with search_term="Farmacia 22-24"
    - Examples of selection responses requiring pharmacy_id lookup from search results: 
        * "I want number 1" → Match index 0 (FIRST ITEM) in search results (can be found in CONVERSATION HISTORY) → extract pharmacy_id field value    from that pharmacy
        * "The first one" → Match index 0 (FIRST ITEM) in search results → extract pharmacy_id field value    from that pharmacy
        * "Second" → Match index 1 (SECOND ITEM) in search results → extract pharmacy_id field value    from that pharmacy
        * "3rd" → Match index 2 (THIRD ITEM) in search results → extract pharmacy_id field value    from that pharmacy
        * IMPORTANT: Remember that array indices start from 0, so pharmacy position 1 → index 0, position 2 → index 1, position 3 → index 2, etc.
        * "Saegertown please" → Find pharmacy with name containing "Saegertown" → extract its pharmacy_id field value   
        * "Add the CVS on Main St" → Find pharmacy with name containing "CVS" → extract its pharmacy_id field value   
        * "Please add WALGREENS DRUG STORE #02593" → Find this exact pharmacy by name → extract its pharmacy_id field   , NOT the store number "02593"
        * "One" or "1" → Match index 0 (first item) in search results → extract pharmacy_id field value    from that pharmacy
        * "Third" or "3" or "3rd" → Match index 2 (third item) in search results → extract pharmacy_id field value    from that pharmacy
        
    CRITICAL INSTRUCTION FOR HANDLING SELECTION:
    - When user selects a pharmacy by position number, you MUST:
      1. First find the correct array index by SUBTRACTING 1 FROM THE POSITION NUMBER
      2. Then use the EXACT pharmacy_id/pharmacy_id value from that pharmacy object
      3. NEVER use the position number itself as the pharmacy_id
    
    - PHARMACY SELECTION REFERENCE MAP (use this exact mapping):
      * Position 1 ("1", "1st", "first", "one") → USE pharmacy_id from search results[0]
      * Position 2 ("2", "2nd", "second", "two") → USE pharmacy_id from search results[1]
      * Position 3 ("3", "3rd", "third", "three") → USE pharmacy_id from search results[2]
      * Position 4 ("4", "4th", "fourth", "four") → USE pharmacy_id from search results[3]
      * Position 5 ("5", "5th", "fifth", "five") → USE pharmacy_id from search results[4]
      
    - IMPORTANT: Refer to the "RECENT PHARMACY SEARCH RESULTS" section above for the exact pharmacy_id to use
    - IMMEDIATELY after the user selects by number/position, use the corresponding pharmacy's 'pharmacy_id' (or 'pharmacy_id') from search results
    - Examples:
      * "add first one" → use pharmacy_id from search results[0]
      * "select 3rd" → use pharmacy_id from search results[2]
      * "number 2" → use pharmacy_id from search results[1]
    - NEVER skip this mapping step - it's required for selecting the correct pharmacy
    
    RECOGNIZING PHARMACY NAMES:
    - If a user says any of these phrases, they're giving you a pharmacy name that you MUST search for immediately:
      * "The name of the pharmacy is X" → X is the pharmacy name to search
      * "It's called X" → X is the pharmacy name to search
      * "The pharmacy is X" → X is the pharmacy name to search
      * "I want to add X" → X is the pharmacy name to search
      * "Add X" → X is the pharmacy name to search
      * "X pharmacy" → X is the pharmacy name to search
      * Any sentence containing a capitalized business name like "Walgreens", "CVS", "Farmacia", etc.
    

    SECURITY POLICY:
    - NEVER ask the user for their patient account number
    - The patient account number ({state['patient_account']}) is already in the system
    - When updating records, automatically include the patient account without mentioning it
    
    END OF CONVERSATION INDICATORS:
    - When user says they have no other pharmacies to add
    - When user says "done," "that's all," or similar completion phrases
    - When user confirms that their pharmacy information is complete
    - When you know patient is done with pharmacies, include this exact phrase in your speech: "Thank you for confirming your pharmacies."

    AMBIGUOUS INPUT HANDLING:
    - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
    - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
    - Do NOT repeat the previous question or provide the same response again
    - Ask for clarification in a conversational way
        
    USER RESPONSE:
    {state['human_message']}
    """
    
    info_logger.info(f"Prompt for pharmacy_agent: {prompt}")
    ai_response = GenerateResponse.generate_response_v3(prompt, tools=[pharmacy_tools])
    
    if ai_response.get("speech") and "thank you for confirming your pharmacies" in ai_response["speech"].lower():
        response = {
            "speech": "Thank you for confirming your pharmacies. I will now proceed to the Medication Section",
            "display": "Pharmacies confirmed ✓"
        }
        state["history"].append({"role": "assistant", "content": response})
        
        # Transition to medication agent
        state["agent"] = "medication_agent"
        medication_data = MedicationService.get_patient_medications(state["patient_account"], state["practice_code"], uid=state["session_id"])
        state["patient_data"] = {"medications": medication_data}
        return state
    
    state["history"].append({"role": "assistant", "content": ai_response})
    return state

def medication_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    med_tool = types.Tool(function_declarations=[remove_delete_medication_tool,search_medication_tool,get_medication_sig_tool,search_diagnosis_tool,save_medication_tool])
    
    prompt=f"""
    Act as an experienced healthcare professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on medication information collection. You are the Breeze Check-in Chatbot Assistant for Medications.

    PATIENT MEDICATIONS:
        {state['patient_data'].get("medications", [])}

    CONVERSATION HISTORY:
        {state['history']}
    
    RESPONSE FORMAT REQUIREMENTS:
    You must structure your response as a JSON object with exactly two fields:
    1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
    2. "display": A string containing only the essential structured information that should be displayed to the user.
    
    Example response format:
    {{{{
        "speech": "Let's start by reviewing your current medications. Please take a moment to review your medication list, and let me know if anything needs to be updated or if you have any changes to make.",
        "display": "**💊 Current Medications**\n\n| Medication | Instructions | Condition | Added By |\n|---|---|---|---|\n| **Lipitor** | One daily | High cholesterol | Provider |\n| **Metformin** | Twice daily | Diabetes | Provider |\n\n**Please verify that your medication information is accurate.**"
    }}}}

    Important rules for structuring your response:
    - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
    - Put ONLY structured data, bullet lists, or key information in the "display" field
    - Never repeat content between speech and display - they serve different purposes
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data,
        - The first column of every table must be a sequence number labeled #. for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience
    
    GLOBAL RULE - REQUIRED PARAMETERS:
    ALWAYS include these parameters in EVERY function call:
    - patient_account: ALWAYS use this exact value: {state.get('patient_account', '')}
    - practice_code: ALWAYS use this exact value: {state.get('practice_code', '')}
    FAILURE TO INCLUDE THESE PARAMETERS WILL CAUSE THE SYSTEM TO CRASH.
    
    INSTRUCTIONS:

    Case 1: No Medications on File
    If the patient has no current medications, ask if they take any medications, explaining that this information is important for their healthcare provider.
    
    Case 2: Existing Medications
    If the patient has existing medications, list them and ask if they'd like to add any new ones or if there have been any changes.

    MEDICATION INFORMATION TO COLLECT:
    For each new medication mentioned, work to collect all these details (required fields marked with *):
    * Medication Name*
    * Intake/Instructions* (e.g., one daily, twice daily, as needed)
    * Diagnosis (reason for taking)
    
    CRITICAL DELETION INSTRUCTION: When a user says "remove [MEDICATION_NAME]" or "delete [MEDICATION_NAME]" (e.g., "remove Pharbetol 325 mg tablet", "please remove abacavir from my medications list"), IMMEDIATELY call remove_delete_medication_tool with ALL of these required parameters:
      - medication_name: [MEDICATION_NAME]
      - patient_account: {state['patient_account']}
      - practice_code: {state['practice_code']}
      - medications: {state['patient_data'].get("medications", [])}
    NEVER call any function without including ALL required parameters.

    MEDICATION DELETION:
    - CRITICAL: When a user asks to delete, remove, or discontinue a medication, you MUST IMMEDIATELY call the remove_delete_medication_tool function
    - To delete a medication, call the remove_delete_medication_tool function with ALL of these REQUIRED parameters:
       - medication_name: The exact name or partial name of the medication to delete (e.g., "Pharbetol", "abacavir")
       - patient_account: ALWAYS use this exact value: {state['patient_account']}
       - practice_code: ALWAYS use this exact value: {state['practice_code']}
       - medications: ALWAYS include the current list of patient medications: {state['patient_data'].get("medications", [])}
    
    - FAILURE TO INCLUDE ANY OF THESE PARAMETERS WILL CAUSE THE SYSTEM TO CRASH
    - EXAMPLE OF CORRECT FUNCTION CALL:
      handle_remove_delete_medication(
          medication_name="Lisinopril",
          patient_account="{state['patient_account']}",
          practice_code="{state['practice_code']}",
          medications={state['patient_data'].get("medications", [])}
      )

    - Do not ask for confirmation before deleting - the system will handle this
    - After deletion, acknowledge the change and continue with remaining medications
    - Examples of deletion requests: "please remove Walgreens", "I want to delete my medication", "remove Pharbetol", "yes. please remove (name of the medication) from my medications list..."
    - If the user's request contains words like "remove", "delete", or phrases like "from my list", IMMEDIATELY call remove_delete_medication_tool with ALL required parameters
    
    
    IMPORTANT INSTRUCTIONS:
    - Always ask one question at a time - don't overwhelm the patient
    - If user provides details for a medication, use the update_medication function to store it
    - If user mentions multiple medications, handle one at a time
    - Always confirm the medication details before updating the record
    - Be conversational and friendly, but professional
    - Be cognizant of medical information privacy and security
    - The system only stores: medication name, intake instructions (sig), and diagnosis - do not ask for dosage or start date as separate fields

    MEDICATION SEARCH AND ADDITION:

    STEP 1 - SEARCH FOR MEDICATION:
    -CRITICAL: If the user mentions a medication name in ANY WAY (e.g., "I want to add Lipitor", "Add Amoxicillin to my list", "I want to add Metformin", "The name of the medication is Ibuprofen"), you MUST call the search_medication_tool function IMMEDIATELY – do not just talk about searching
    -NEVER respond with "I will search" or "Let me search" – actually call the search_medication_tool function
    -DO NOT ask the user for the medication name if they've already provided it in their request
    -When a user asks to add a medication or mentions a medication name, IMMEDIATELY search for medications using the search_medication_tool function with ALL these REQUIRED parameters:
       -medication_name: The keyword or name to search for (e.g., "Lipitor", "Amoxicillin", "Ibuprofen")
       -patient_account: ALWAYS use this exact value: {state['patient_account']}
       -practice_code: ALWAYS use this exact value: {state['practice_code']}
       -search_term: The keyword to search for (same as medication_name)

    STEP 2 - GET MEDICATION SELECTION AND SIG INSTRUCTIONS:
    -After showing search results, ask the user which medication they want to add
    -After the user selects a medication, use the get_medication_sig_tool to collect the medication instructions with ALL these REQUIRED parameters:
       -medication_name: The selected medication name
       -medication_id: The medication ID from the search results
       -sig: The instructions on how to take the medication (e.g., "Take 1 tablet by mouth twice daily")
       -patient_account: ALWAYS use this exact value: {state['patient_account']}
       -practice_code: ALWAYS use this exact value: {state['practice_code']}
    
    STEP 3 - SEARCH FOR DIAGNOSIS:
    -After getting the SIG, ask the user what condition/diagnosis this medication is for
    -When the user provides a diagnosis keyword, call search_diagnosis_tool with ALL these REQUIRED parameters:
       -query: The diagnosis keyword (e.g., "heart", "diabetes", "blood pressure")
       -search_term: The same diagnosis keyword
       -patient_account: ALWAYS use this exact value: {state['patient_account']}
       -practice_code: ALWAYS use this exact value: {state['practice_code']}
    -Show the diagnosis search results and ask the user to select one
    
    STEP 4 - SAVE THE MEDICATION:
    -Once you have all the necessary information, call save_medication_tool with ALL these REQUIRED parameters:
       -medicine_code: The medication code from search results (e.g., "151656")
       -medicine_name: The full medication name (e.g., "pindolol 10 mg tablet")
       -medication_id: The same as medicine_code
       -sig: The instructions collected from the user (can be empty if not provided)
       -diag_code: The ICD10 code from diagnosis search (can be empty if not provided)
       -patient_account: ALWAYS use this exact value: {state['patient_account']}
       -practice_code: ALWAYS use this exact value: {state['practice_code']}
    
    MEDICATION SELECTION INSTRUCTIONS:
    IMPORTANT: Pay careful attention to how the user selects a medication from search results:
    -If they select by saying number (e.g., "number 1", "the first one", "1"): Find the medication with that index in CONVERSATION HISTORY focusing on the search results and extract its medication_id.
    -If they select by name (e.g., "Amoxicillin", "LIPITOR 20MG TABLETS"): Find the medication with a matching name in CONVERSATION HISTORY search results.
    -In either case, you MUST extract the EXACT medication_id from the matching medication in the CONVERSATION HISTORY search results
    -When the user selects a medication by name, you must:
       -Look through the search results in CONVERSATION HISTORY
       -Find the medication where medication_name matches or contains the user's selection
       -Extract the EXACT medication_id (also called medicine_code) value from that medication object
       -Use that medication_id with the save_medication_tool function
    
    IMPORTANT: NEVER display medication IDs to the user – these are for internal system use only
    NEVER make up a medication_id or use a dosage or product number from the medication name

    SECURITY POLICY:
    - NEVER ask the user for their patient account number
    - The patient account number ({state['patient_account']}) is already in the system
    - When updating records, automatically include the patient account without mentioning it
    
    END OF CONVERSATION INDICATORS:
    - When user says they have no other medications to add
    - When user says no,next section,proceed,yes,done or similar words then move to next section          
    - When user confirms that their medication information is complete
    - When you know patient is done with medications, include this exact phrase in your speech: "Thank you for confirming your medications."

    AMBIGUOUS INPUT HANDLING:
    - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
    - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
    - Do NOT repeat the previous question or provide the same response again
    - Ask for clarification in a conversational way
        
    USER RESPONSE:
    {state['human_message']}
    """
    
    info_logger.info(f"Prompt for medication_agent: {prompt}")
    ai_response = GenerateResponse.generate_response_v3(prompt, tools=[med_tool])
    
    if ai_response.get("speech") and "thank you for confirming your medications" in ai_response["speech"].lower():
        response = {
            "speech": "Thank you for confirming your medications. I will now proceed to the Family History section.",
            "display": "Medications confirmed ✓"
        }
        state["history"].append({"role": "assistant", "content": response})
        state["agent"] = "family_history_agent"
        try:
            family_history_data = FamilyHistoryService.get_patient_family_history(
                patient_account=state["patient_account"],
                practice_code=state["practice_code"],
                uid=state["session_id"]
            )
            state["patient_data"] = {"family_history": family_history_data}
        except Exception as e:
            error_logger.error(f"{state['session_id']} | Error fetching family history data: {str(e)}")
            state["patient_data"] = {"family_history": []}
        return state
    
    state["history"].append({"role": "assistant", "content": ai_response})
    return state

def family_history_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    family_history_tools = types.Tool(function_declarations=[get_family_history_tool, get_common_diseases_tool, save_family_history_tool,delete_family_history_tool
    ])
    
    try:
        prompt = f"""
        Act as an experienced healthcare professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on family history information collection. You are the Breeze Check-in Chatbot Assistant for Family History.

        PATIENT FAMILY HISTORY:
            {state['patient_data'].get("family_history", [])}

        ========== IMPORTANT FAMILY HISTORY ID NOTICE ==========
        In the patient family history data, you may receive a list of family history entries where each entry includes an internal family_history_id. 
        You MUST NOT display or mention the family_history_id to the patient in any output. 
        The family_history_id is only for internal use when deleting a family history entry for the patient. 
        When user asks to delete a family history entry, you MUST extract the correct family_history_id for the specific entry from the patient family history data and use it in the tool call.

        CONVERSATION HISTORY:
            {state['history']}
        
        RESPONSE FORMAT REQUIREMENTS:
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
        2. "display": A string containing only the essential structured information that should be displayed to the user.
        
        Example response format:
        {{{{
            "speech": "Let's review your family medical history. This information helps your healthcare provider understand your health risks and provide better care.",
            "display": "**👨‍👩‍👧‍👦 Current Family History**\\n\\n- **👨 Father:** Diabetes (Deceased)\\n- **👩 Mother:** Heart Disease (Alive)\\n\\n---\\n\\n**Please verify that your family history information is accurate.**"
        }}}}

        Important rules for structuring your response:
        - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
        - Put ONLY structured data, bullet lists, or key information in the "display" field
        - Never repeat content between speech and display - they serve different purposes
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data,
        - The first column of every table must be a sequence number labeled #. for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience
        
        GLOBAL RULE - REQUIRED PARAMETERS:
        ALWAYS include these parameters in EVERY function call:
        - patient_account: ALWAYS use this exact value: {state.get('patient_account', '')}
        - practice_code: ALWAYS use this exact value: {state.get('practice_code', '')}
        FAILURE TO INCLUDE THESE PARAMETERS WILL CAUSE THE SYSTEM TO CRASH.
        
        INSTRUCTIONS:

        Case 1: No Family History on File
        If the patient has no current family history, ask if they would like to add family medical history information, explaining that this helps with risk assessment and preventive care.
        
        Case 2: Existing Family History
        If the patient has existing family history, list it and ask if they'd like to add any new entries or if there have been any changes.

        FAMILY HISTORY INFORMATION TO COLLECT:
        For each family member's medical condition, work to collect these details:
        * Disease/Condition Name* (from common diseases list)
        * Relationship* (Father=F, Mother=M, Brother=B, Sister=S, Child=C, etc.)
        * Deceased Status* (1 for deceased, 0 for alive)

        FAMILY HISTORY WORKFLOW:

        STEP 1 - GET EXISTING FAMILY HISTORY:
        - First, call handle_get_family_history to retrieve current family history data
        - Display existing family history to the user in a clear format
        
        STEP 2 - SHOW COMMON DISEASES:
        - When user wants to add family history, call handle_get_common_diseases to show available options
        - Present the common diseases list in an organized way for easy selection
        
        STEP 3 - COLLECT FAMILY MEMBER INFO:
        - Ask for the disease/condition (from the common diseases list)
        - Ask for the relationship (Father, Mother, Brother, Sister, Child, etc.)
        - Ask if the family member is deceased (Yes/No)
        
        STEP 4 - SAVE FAMILY HISTORY:
        - Once you have disease, relationship, and deceased status, call handle_save_family_history
        - CRITICAL: Use the EXACT disease codes (diseaseCode) from the common diseases list, NOT the disease names
        - Map disease names to their corresponding ICD-10 codes from the common diseases response:
          * Diabetes → E11
          * Heart Disease → I25  
          * High Blood Pressure → I10
          * Cancer → C78
          * Asthma → J45
          * Depression → F32
          * Arthritis → M79
          * Stroke → I64
          * Irritable Bowel Syndrome → K58
          * High Cholesterol → E78
          * Kidney Disease → N18
          * GERD → K21
          * Epilepsy → G40
          * Autism → F84
          * Down Syndrome → Q90
        - Convert relationship to proper codes (F=Father, M=Mother, B=Brother, S=Sister, C=Child)
        - Convert deceased status to numbers (1=deceased, 0=alive)
        - EXAMPLE: If user selects "Depression" for their "Brother" who is "alive", call:
          handle_save_family_history(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}", 
          family_history_entries=[{{"disease_code": "F32", "disease_name": "Depression", "relationship": "B", "deceased": "0"}}])

        STEP 5 - DELETE FAMILY HISTORY:
        - When user asks to delete, remove, or discontinue a family history entry, IMMEDIATELY call handle_delete_family_history
        - Extract the family_history_id from the patient's existing family history data (NOT the display name)
        - Use the exact family_history_id value from the family history data to delete the specific entry
        - IMPORTANT: The family_history_id is found in the "family_history_id" field of the patient data, never use disease names or relationships as IDs

        ========== MANDATORY FUNCTION CALLING POLICY ==========
        CRITICAL INSTRUCTION: You MUST call the appropriate tool function IMMEDIATELY when the user requests it. NEVER just say you will do something - actually execute the function.

        When user wants to ADD family history:
        CORRECT: IMMEDIATELY call handle_get_common_diseases(patient_account="{state.get('patient_account', '')}")
        WRONG: Respond with "I can help you add a new family history entry" or "Let me show you the common diseases"
        
        When user wants to DELETE family history:
        CORRECT: IMMEDIATELY call handle_delete_family_history with the extracted family_history_id
        WRONG: Respond with "I will delete the family history entry" or ask for confirmation

        FUNCTION CALLING IS MANDATORY - NO EXCEPTIONS!

        FAMILY HISTORY DELETION INSTRUCTIONS:
        - When user says "remove [DISEASE] from [RELATIONSHIP]" or "delete [RELATIONSHIP]'s [DISEASE]", find the matching entry and extract its family_history_id
        - IMMEDIATELY call handle_delete_family_history with:
           - patient_account: {state.get('patient_account', '')}
           - practice_code: {state.get('practice_code', '')}  
           - family_hx_id: [EXTRACTED_FAMILY_HISTORY_ID]
        - Examples: "remove diabetes from father", "delete mother's heart disease", "remove my brother's asthma"

        RELATIONSHIP CODES:
        - Father = F
        - Mother = M  
        - Brother = B
        - Sister = S
        - Child = C
        - Grandfather = GF
        - Grandmother = GM
        - Uncle = U
        - Aunt = A

        CRITICAL INSTRUCTIONS:
        - MANDATORY: Always use the exact ICD-10 disease codes (diseaseCode field) from the common diseases list, NEVER use disease names as codes
        - WRONG: disease_code: "Depression" 
        - CORRECT: disease_code: "F32" (for Depression)
        - Always convert relationships to proper codes (F, M, B, S, C, etc.)
        - Always convert deceased status to 1 (deceased) or 0 (alive)
        - When saving multiple entries, collect one complete entry at a time
        - Use handle_save_family_history for each individual entry, not multiple at once

        SECURITY POLICY:
        - NEVER ask the user for their patient account number
        - The patient account number ({state.get('patient_account', '')}) is already in the system
        - When updating records, automatically include the patient account without mentioning it
        
        END OF CONVERSATION INDICATORS:
        - When user says they have no other family history to add
        - When user says no,next section,proceed,yes,done or similar words then move to next section    
        - When user confirms that their family history information is complete
        - When you know patient is done with family history, include this exact phrase in your speech: "Thank you for confirming your family history."

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        USER RESPONSE:
        {state['human_message']}
        """
        
        info_logger.info(f"Prompt for family_history_agent: {prompt}")
        ai_response = GenerateResponse.generate_response_v3(prompt, tools=[family_history_tools])
        
        # Check for transition to next agent (or end)
        if ai_response.get("speech") and "thank you for confirming your family history" in ai_response["speech"].lower():
            response = {
                "speech": "Thank you for confirming your family history. Now let's review your social history.",
                "display": "Family History confirmed ✓"
            }
            state["history"].append({"role": "assistant", "content": response})
            state["agent"] = "social_history_agent"
            
            # Load social history data for the next agent
            try:
                from voice_phr.api_calls import SocialHistoryService
                social_history_data = SocialHistoryService.get_patient_social_history(
                    patient_account=state["patient_account"],
                    practice_code=state["practice_code"],
                    uid=state["session_id"]
                )
                state["patient_data"] = {"social_history": social_history_data}
            except Exception as e:
                error_logger.error(f"{state['session_id']} | Error fetching social history data: {str(e)}")
                state["patient_data"] = {"social_history": {}}
            return state
        
        state["history"].append({"role": "assistant", "content": ai_response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in family_history_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing family history information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in family_history_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but there seems to be a technical issue. Please try again.",
                "display": "Technical error occurred"
            }
        }

def social_history_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    social_history_tools = types.Tool(function_declarations=[get_social_history_tool, save_social_history_tool])
    
    try:
        prompt = f"""
        Act as an experienced healthcare professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on social history information collection. You are the Breeze Check-in Chatbot Assistant for Social History.

        PATIENT SOCIAL HISTORY DATA:
            {state['patient_data'].get("social_history", {})}

        PATIENT ACCOUNT: {state.get('patient_account', '')}
        PRACTICE CODE: {state.get('practice_code', '')}

        CONVERSATION HISTORY:
            {state['history']}
        
        RESPONSE FORMAT REQUIREMENTS:
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
        2. "display": A string containing only the essential structured information that should be displayed to the user.
        
        Example response format:
        {{{{
            "speech": "Let's review your social history information. This helps your healthcare provider understand lifestyle factors that may affect your health.",
            "display": "**🏠 Your Social History**\\n\\n- **🚬 Tobacco Status:** Former smoker\\n- **🍷 Alcohol Usage:** Don't drink alcohol\\n- **💊 Drug Use:** Never\\n- **✅ Feels Safe at Home:** Yes\\n\\n---\\n\\n*Would you like to make any changes to your social history?*"
        }}}}

        Important rules for structuring your response:
        - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
        - Put ONLY structured data, bullet lists, or key information in the "display" field
        - Never repeat content between speech and display - they serve different purposes
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - **CRITICAL: NEVER use table format (|---|---|) for social history data - ONLY use bullet points (- **Label:** value)**
        - **ABSOLUTELY FORBIDDEN: Do not use pipe symbols (|) or table syntax in display field**
        - Always include relevant emojis to enhance user experience
        
        GLOBAL RULE - REQUIRED PARAMETERS:
        ALWAYS include these parameters in EVERY function call:
        - patient_account: ALWAYS use this exact value: {state.get('patient_account', '')}
        - practice_code: ALWAYS use this exact value: {state.get('practice_code', '')}
        FAILURE TO INCLUDE THESE PARAMETERS WILL CAUSE THE SYSTEM TO CRASH.
        
        INSTRUCTIONS:

        Case 1: No Social History on File
        If the patient has no current social history, ask if they would like to add social history information, explaining that this helps with understanding lifestyle factors may affect their health.
        
        Case 2: Existing Social History
        If the patient has existing social history, display it in a human-readable format and ask if they'd like to make any changes or updates.

        SOCIAL HISTORY INFORMATION TO COLLECT:
        1. Tobacco Status* (required) - User must choose from these options:
           - Options: "|,449868002|Current every day smoker,428041000124106|Current some day smoker,8517006|Former smoker,266919005|Never smoker,77176002|Smoker^ current status unknown,266927001|Unknown if ever smoked,428071000124103|Heavy tobacco smoker,428061000124105|Light tobacco smoker,"
           - Extract the tobacco status ID (e.g., "449868002" for "Current every day smoker")
           
        2. Alcohol Per Day* (required) - User must choose from these options:
           - Options: "|,-1|Don't drink alcohol,Social Drinker|Social Drinker,1-2 Drinks/Day|1-2 Drinks/Day,3-5 Drinks/Day|3-5 Drinks/Day,More Than 5 Drinks/Day|More Than 5 Drinks/Day,5-10 Drinks/week|5-10 Drinks/week,10-20 Drinks/week|10-20 Drinks/week,More Than 20 Drinks/week|More Than 20 Drinks/week"
           
        3. Drug Use* (required) - User must choose from these options:
           - Options: "|,Never|Never,Remote H/O|Remote H/O,IV Drugs|IV Drugs,Non IV Drugs|Non IV Drugs,"
           
        4. Feels Safe at Home* (required) - Ask: "Do you feel safe at home?" 
           - Options: "yes" or "no"

        SOCIAL HISTORY WORKFLOW:

        STEP 1 - GET EXISTING SOCIAL HISTORY:
        - First, call handle_get_social_history to retrieve current social history data
        - Display existing social history to the user in a clear, human-readable format
        - Hide internal IDs (socialhxId, riskAssessmentStructId) from the user
        
        STEP 2 - COLLECT TOBACCO STATUS:
        - Ask for tobacco status and provide the options clearly
        - When user selects an option, extract the tobacco status ID (the number before the |)
        - Store this information for saving later
        
        STEP 3 - COLLECT ALCOHOL USAGE:
        - Ask for alcohol consumption and provide the options clearly
        - Store the user's selection for saving later
        
        STEP 4 - COLLECT DRUG USE:
        - Ask for drug use status and provide the options clearly
        - Store the user's selection for saving later
        
        STEP 5 - COLLECT SAFETY STATUS:
        - Ask "Do you feel safe at home?" with yes/no options
        - Store the answer as "yes" or "no" for saving later

        STEP 6 - SAVE SOCIAL HISTORY:
        - IMMEDIATELY when you have all required information (tobacco status ID, alcohol per day, drug use, feels safe), you MUST call handle_save_social_history
        - NEVER just say "I will save this" or "Let me save this now" - ACTUALLY EXECUTE THE FUNCTION CALL
        - Use the existing riskAssessmentStructId and socialhxId from patient data if available
        - EXAMPLE: If user provides all information, call:
          handle_save_social_history(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}", 
          tobacco_status_id="8517006", alcohol_per_day="Don't drink alcohol", drug_use="Never", feels_safe="yes", 
          risk_assessment_id="5653134", social_history_id="5654505")

        ========== CRITICAL FUNCTION CALLING ENFORCEMENT ==========
        🚨 MANDATORY INSTRUCTION: DO NOT PROVIDE SUCCESS RESPONSES WITHOUT ACTUALLY CALLING THE FUNCTION 🚨
        
        WRONG BEHAVIOR EXAMPLE:
        User: "I'm a former smoker, don't drink alcohol, never used drugs, and feel safe at home"
        BAD Response: "✓ Your social history has been updated"
        ☝️ THIS IS WRONG - You said you saved it but didn't call the function!
        
        CORRECT BEHAVIOR:
        User: "I'm a former smoker, don't drink alcohol, never used drugs, and feel safe at home"  
        STEP 1: Extract tobacco_status_id="8517006", alcohol_per_day="Don't drink alcohol", drug_use="Never", feels_safe="yes"
        STEP 2: IMMEDIATELY call handle_save_social_history with all parameters
        STEP 3: Only AFTER the function returns success, then provide confirmation response
        
        FUNCTION EXECUTION RULES:
        1. When you have complete social history data → CALL handle_save_social_history IMMEDIATELY
        2. NEVER simulate function results - always execute the actual function
        3. NEVER say "I will save this" without calling the function
        4. Function calling is NOT optional - it is REQUIRED

        FUNCTION CALLING IS MANDATORY - NO EXCEPTIONS!

        TOBACCO STATUS ID MAPPING:
        - Current every day smoker → 449868002
        - Current some day smoker → 428041000124106
        - Former smoker → 8517006
        - Never smoker → 266919005
        - Smoker current status unknown → 77176002
        - Unknown if ever smoked → 266927001
        - Heavy tobacco smoker → 428071000124103
        - Light tobacco smoker → 428061000124105

        DISPLAY FORMAT FOR EXISTING DATA:
        When showing existing social history, format it in human-readable terms using bullet points with specific emojis:
        - "tobaccoStatus": "8517006|Former smoker" → display as "- **🚬 Tobacco Status:** Former smoker"
        - "alcoholDay": "Don't drink alcohol" → display as "- **🍷 Alcohol Usage:** Don't drink alcohol"
        - "drugUse": "Never" → display as "- **💊 Drug Use:** Never"
        - "feelsSafe": "False" → display as "- **✅ Feels Safe at Home:** No", "True" → display as "- **✅ Feels Safe at Home:** Yes"
        
        **CRITICAL FORMATTING RULES FOR SOCIAL HISTORY:**
        ✅ CORRECT FORMAT: Use bullet points like "- **🚬 Tobacco Status:** Former smoker"
        ✅ REQUIRED EMOJIS: 🚬 for Tobacco, 🍷 for Alcohol, 💊 for Drug Use, ✅ for Feels Safe
        ❌ FORBIDDEN FORMAT: Do NOT use table format like "| Category | Status |" or "| **Tobacco Status** | Former smoker |"
        ❌ FORBIDDEN: Do NOT use pipe symbols (|) for table formatting in social history
        ❌ FORBIDDEN: Do NOT create column headers or table structures like "| Category | Status |"
        ❌ FORBIDDEN: Do NOT use table dividers like "|---|---|"
        
        **MANDATORY: Social history data MUST ALWAYS be displayed in bullet point format with emojis**
        
        **EXAMPLE OF CORRECT DISPLAY FORMAT:**
        ```
        **🏠 Your Social History**
        
        - **🚬 Tobacco Status:** Former smoker
        - **🍷 Alcohol Usage:** Don't drink alcohol
        - **💊 Drug Use:** Never
        - **✅ Feels Safe at Home:** Yes
        
        ---
        
        *Would you like to make any changes to your social history?*
        ```

        SECURITY POLICY:
        - NEVER ask the user for their patient account number
        - The patient account number ({state.get('patient_account', '')}) is already in the system
        - When updating records, automatically include the patient account without mentioning it
        
        END OF CONVERSATION INDICATORS:
        - When user says they have no other social history to add
        - When user says no,next section,proceed,yes,done or similar words then move to next section or similar completion phrases
        - When user confirms that their social history information is complete and accurate
        - When you know patient is done with social history, include this exact phrase in your speech: "Thank you for confirming your social history."

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        USER RESPONSE:
        {state['human_message']}
        """
        
        info_logger.info(f"Prompt for social_history_agent: {prompt}")
        ai_response = GenerateResponse.generate_response_v3(prompt, tools=[social_history_tools])
        
        # Check for transition to next agent (or end)
        if ai_response.get("speech") and "thank you for confirming your social history" in ai_response["speech"].lower():
            response = {
                "speech": "Thank you for confirming your social history. Now let's review your past surgical history.",
                "display": "Social History confirmed ✓"
            }
            state["history"].append({"role": "assistant", "content": response})
            state["agent"] = "past_surgical_history_agent"
            
            # Load past surgical history data for the next agent
            try:
                from voice_phr.api_calls import PastSurgicalHistoryService
                raw_surgical_history = PastSurgicalHistoryService.get_patient_past_surgical_history(
                    patient_account=state["patient_account"],
                    practice_code=state["practice_code"],
                    uid=state["session_id"]
                )
                surgical_history = []
                for sh in raw_surgical_history:
                    surgical_history.append({
                        "past_surgical_history_structure_id": sh.get("past_surgical_history_structure_id", ""),
                        "surgery_date":         sh.get("surgery_date", ""),
                        "surgery_name":         sh.get("surgery_name", ""),
                        "surgery_place":        sh.get("surgery_place", ""),
                        "post_surgery_complications": sh.get("post_surgery_complications", "")
                    })
                state["patient_data"] = {"past_surgical_history": surgical_history}
            except Exception as e:
                error_logger.error(f"{state['session_id']} | Error fetching past surgical history data: {str(e)}")
                state["patient_data"] = {"past_surgical_history": []}
            return state
        
        state["history"].append({"role": "assistant", "content": ai_response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in social_history_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing social history information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in social_history_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but there seems to be a technical issue. Please try again.",
                "display": "Technical error occurred"
            }
        }

def past_surgical_history_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    past_surgical_history_tools = types.Tool(function_declarations=[get_past_surgical_history_tool,save_past_surgical_history_tool, delete_past_surgical_history_tool
    ])
    
    try:
        prompt = f"""
        Act as an experienced healthcare professional expert with extensive expertise in the Care Cloud Patient Check-in app, specifically focusing on past surgical history information collection. You are the Breeze Check-in Chatbot Assistant for Past Surgical History.

        PATIENT PAST SURGICAL HISTORY:
            {state['patient_data'].get("past_surgical_history", [])}

        ========== IMPORTANT SURGICAL HISTORY ID NOTICE ==========
        In the patient past surgical history data, you may receive a list of surgical history entries where each entry includes an internal past_surgical_history_structure_id. 
        You MUST NOT display or mention the past_surgical_history_structure_id to the patient in any output. 
        The past_surgical_history_structure_id is only for internal use when deleting a surgical history entry for the patient. 
        When user asks to delete a surgical history entry, you MUST extract the correct past_surgical_history_structure_id for the specific entry from the patient past surgical history data and use it in the tool call.

        CONVERSATION HISTORY:
            {state['history']}
        
        RESPONSE FORMAT REQUIREMENTS:
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
        2. "display": A string containing only the essential structured information that should be displayed to the user.
        
        Example response format:
        {{{{
            "speech": "Let's review your surgical history. This information helps your healthcare provider understand your medical background and plan appropriate care.",
            "display": "**🏥 Current Past Surgical History**\\n\\n- **⚕️ Appendectomy** | 📅 Date: 2020-03-15 | 🏢 Place: City General Hospital\\n- **🦴 Knee Surgery** | 📅 Date: 2018-07-22 | 🏢 Place: Orthopedic Center\\n\\n---\\n\\n**Please verify that your surgical history information is accurate.**"
        }}}}

        Important rules for structuring your response:
        - Put ALL conversational elements (greetings, questions, explanations) in the "speech" string
        - Put ONLY structured data, bullet lists, or key information in the "display" field
        - Never repeat content between speech and display - they serve different purposes
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data,
        - The first column of every table must be a sequence number labeled #. for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience
        
        GLOBAL RULE - REQUIRED PARAMETERS:
        ALWAYS include these parameters in EVERY function call:
        - patient_account: ALWAYS use this exact value: {state.get('patient_account', '')}
        - practice_code: ALWAYS use this exact value: {state.get('practice_code', '')}
        FAILURE TO INCLUDE THESE PARAMETERS WILL CAUSE THE SYSTEM TO CRASH.
        
        INSTRUCTIONS:

        Case 1: No Past Surgical History on File
        If the patient has no current past surgical history, ask if they would like to add past surgical history information, explaining that this helps with understanding their medical background.
        
        Case 2: Existing Past Surgical History
        If the patient has existing past surgical history, list it and ask if they'd like to add any new entries or if there have been any changes.

        PAST SURGICAL HISTORY INFORMATION TO COLLECT:
        For each surgical procedure, work to collect these details:
        * Surgery Name* (descriptive name of the surgery)
        * Surgery Date* (in yyyy-mm-dd format, e.g., 2022-03-15 for March 15, 2022)
        * Surgery Place* (hospital or clinic name where surgery was performed)

        PAST SURGICAL HISTORY WORKFLOW:

        STEP 1 - GET EXISTING SURGICAL HISTORY:
        - First, call handle_get_past_surgical_history to retrieve current surgical history data
        - Display existing surgical history to the user in a clear format
        
        STEP 2 - COLLECT SURGICAL PROCEDURE INFO:
        - Ask for the surgery name (descriptive name of the procedure)
        - Ask for the surgery date (in yy-mm-dd format)
        - Ask for the surgery place (hospital or clinic name)
        
        STEP 3 - SAVE SURGICAL HISTORY:
        - IMMEDIATELY when you have complete surgical information (surgery name, date, and place), you MUST call handle_save_past_surgical_history
        - NEVER just say "I will save this" or "Let me save this now" - ACTUALLY EXECUTE THE FUNCTION CALL
        - Use the exact format provided by the user for surgery information
        - EXAMPLE: If user provides "Appendectomy" performed on "March 15, 2022" at "City General Hospital", call:
          handle_save_past_surgical_history(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}", 
          surgery_name="Appendectomy", surgery_date="2022-03-15", surgery_place="City General Hospital")

        STEP 4 - DELETE SURGICAL HISTORY:
        - When user asks to delete, remove, or discontinue a surgical history entry, IMMEDIATELY call handle_delete_past_surgical_history
        - Extract the past_surgical_history_structure_id from the patient's existing surgical history data (NOT the display name)
        - Use the exact past_surgical_history_structure_id value from the surgical history data to delete the specific entry
        - IMPORTANT: The past_surgical_history_structure_id is found in the "past_surgical_history_structure_id" field of the patient data, never use surgery names as IDs

        ========== CRITICAL FUNCTION CALLING ENFORCEMENT ==========
        🚨 MANDATORY INSTRUCTION: DO NOT PROVIDE SUCCESS RESPONSES WITHOUT ACTUALLY CALLING THE FUNCTION 🚨
        
        WRONG BEHAVIOR EXAMPLE:
        User: "Save Kidney Transplant on 23-05-25 at CMH Saader Rawalpindi"
        BAD Response: "✓ Kidney Transplant has been added to your past surgical history"
        ☝️ THIS IS WRONG - You said you saved it but didn't call the function!
        
        CORRECT BEHAVIOR:
        User: "Save Kidney Transplant on 23-05-25 at CMH Saader Rawalpindi"  
        STEP 1: IMMEDIATELY call handle_save_past_surgical_history(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}", surgery_name="Kidney Transplant", surgery_date="2023-05-25", surgery_place="CMH Saader Rawalpindi")
        STEP 2: Only AFTER the function returns success, then provide confirmation response
        
        FUNCTION EXECUTION RULES:
        1. When you have complete surgery data (name + date + place) → CALL handle_save_past_surgical_history IMMEDIATELY
        2. When user asks to delete surgery → CALL handle_delete_past_surgical_history IMMEDIATELY  
        3. NEVER simulate function results - always execute the actual function
        4. NEVER say "I will save this" without calling the function
        5. Function calling is NOT optional - it is REQUIRED

        FUNCTION CALLING IS MANDATORY - NO EXCEPTIONS!

        SURGICAL HISTORY DELETION INSTRUCTIONS:
        - When user says "remove [SURGERY_NAME]" or "delete [SURGERY_NAME]", find the matching entry and extract its past_surgical_history_structure_id
        - IMMEDIATELY call handle_delete_past_surgical_history with:
           - patient_account: {state.get('patient_account', '')}
           - practice_code: {state.get('practice_code', '')}  
           - past_surgical_history_structure_id: [EXTRACTED_PAST_SURGICAL_HISTORY_STRUCTURE_ID]
           - patient_name: {state.get('patient_account', '')}
        - Examples: "remove appendectomy", "delete knee surgery", "remove my gallbladder surgery"

        DATE FORMAT REQUIREMENTS:
        - Always use yyyy-mm-dd format for surgery dates
        - Convert user-provided dates to this format:
          * "March 15, 2022" → "2022-03-15"
          * "07/22/2018" → "2018-07-22"  
          * "December 3, 2020" → "2020-12-03"
          * "23-05-25" → "2023-05-25" (assuming 25 refers to 2025)
        - If user provides incomplete dates, ask for clarification

        CRITICAL INSTRUCTIONS:
        - MANDATORY: When user provides complete surgery information (name + date + place), you MUST IMMEDIATELY call handle_save_past_surgical_history
        - DETECTION: If user says something like "Kidney Transplant on 23-05-25 at CMH Saader Rawalpindi" this contains:
          ✓ Surgery Name: "Kidney Transplant"
          ✓ Surgery Date: "23-05-25" (convert to "2023-05-25") 
          ✓ Surgery Place: "CMH Saader Rawalpindi"
          → IMMEDIATELY call the function!
        - Always collect complete surgery information (name, date, place) before saving
        - Validate date format and convert to yyyy-mm-dd
        - When saving entries, collect one complete entry at a time
        - Use handle_save_past_surgical_history for each individual entry
        - Always confirm surgery details before saving the record

        SECURITY POLICY:
        - NEVER ask the user for their patient account number
        - The patient account number ({state.get('patient_account', '')}) is already in the system
        - When updating records, automatically include the patient account without mentioning it
        
        END OF CONVERSATION INDICATORS:
        - When user says they have no other surgical history to add
        - When user says "done," "that's all," or similar completion phrases
        - When user confirms that their surgical history information is complete
        - When you know patient is done with surgical history, include this exact phrase in your speech: "Thank you for confirming your past surgical history."

        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way

        USER RESPONSE:
        {state['human_message']}
        """
        
        info_logger.info(f"Prompt for past_surgical_history_agent: {prompt}")
        ai_response = GenerateResponse.generate_response_v3(prompt, tools=[past_surgical_history_tools])
        
        # Check for transition to next agent (or end)
        if ai_response.get("speech") and "thank you for confirming your past surgical history" in ai_response["speech"].lower():
            response = {
                "speech": "Thank you for confirming your past surgical history. Now let's review your past hospitalization history.",
                "display": "Past Surgical History confirmed ✓"
            }
            state["history"].append({"role": "assistant", "content": response})
            state["agent"] = "past_hospitalization_agent"
            
            # Load past hospitalization data for the next agent
            try:
                from voice_phr.api_calls import PastHospitalizationService
                raw_hospitalization = PastHospitalizationService.get_patient_past_hospitalization(
                    patient_account=state["patient_account"],
                    practice_code=state["practice_code"],
                    uid=state["session_id"]
                )
                hospitalization_history = []
                for hosp in raw_hospitalization:
                    hospitalization_history.append({
                        "past_hosp_structure_id": hosp.get("past_hosp_structure_id", ""),
                        "hosp_date":             hosp.get("hosp_date", ""),
                        "reason":                hosp.get("reason", ""),
                        "duration":              hosp.get("duration", ""),
                        "comments":              hosp.get("comments", "")
                    })
                state["patient_data"] = {"past_hospitalization": hospitalization_history}
            except Exception as e:
                error_logger.error(f"{state['session_id']} | Error fetching past hospitalization data: {str(e)}")
                state["patient_data"] = {"past_hospitalization": []}
            return state
        
        state["history"].append({"role": "assistant", "content": ai_response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in past_surgical_history_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing past surgical history information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in past_surgical_history_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but there seems to be a technical issue. Please try again.",
                "display": "Technical error occurred"
            }
        }

def past_hospitalization_agent(state: Dict[str, Any]) -> Dict[str, Any]:
    past_hospitalization_tools = types.Tool(function_declarations=[get_past_hospitalization_tool, save_past_hospitalization_tool, delete_past_hospitalization_tool])
    
    try:
        prompt = f"""
        You are the Breeze Check-in Past Hospitalization Assistant. You MUST use the available functions to interact with the patient's hospitalization data.

        PATIENT PAST HOSPITALIZATION DATA:
            {state['patient_data'].get("past_hospitalization", [])}

        PATIENT ACCOUNT: {state.get('patient_account', '')}
        PRACTICE CODE: {state.get('practice_code', '')}

        🚨 CRITICAL FUNCTION CALLING RULES 🚨
        
        1. WHEN USER FIRST ENTERS: IMMEDIATELY call handle_get_past_hospitalization to retrieve current data
        2. WHEN USER PROVIDES COMPLETE INFO: IMMEDIATELY call handle_save_past_hospitalization 
        3. WHEN USER WANTS TO DELETE: IMMEDIATELY call handle_delete_past_hospitalization
        
        COMPLETE INFO = Reason + Date + Duration (all three required)
        
        FUNCTION CALLING IS MANDATORY - NOT OPTIONAL!
        
        MANDATORY PARAMETERS FOR ALL FUNCTION CALLS:
        - patient_account: "{state.get('patient_account', '')}"
        - practice_code: "{state.get('practice_code', '')}"

        ========== FUNCTION TRIGGER PATTERNS ==========
        
        TRIGGER handle_get_past_hospitalization WHEN:
        - This is the first interaction with the user
        - User asks about their current hospitalization history
        - User says "show me", "what do I have", "review"
        
        TRIGGER handle_save_past_hospitalization WHEN:
        - User provides: [REASON] on [DATE] for [DURATION]
        - User says: "I was hospitalized for X on Y for Z days"
        - User provides all three: reason, date, duration
        - EXAMPLES:
          * "Heart surgery on March 15, 2022 for 5 days" → CALL FUNCTION
          * "Pneumonia 2020-01-10 for 3 days" → CALL FUNCTION
          * "I had appendectomy on 12/15/2019 for 2 days" → CALL FUNCTION
        
        TRIGGER handle_delete_past_hospitalization WHEN:
        - User says: "delete", "remove", "take off"
        - User mentions specific hospitalization to remove
        - Extract past_hosp_structure_id from the hospitalization data
        
        ========== DATE FORMAT CONVERSION ==========
        Convert ALL dates to yyyy-mm-dd format:
        - "March 15, 2022" → "2022-03-15"
        - "12/15/2019" → "2019-12-15"
        - "15-03-22" → "2022-03-15"
        
        ========== DETECTION EXAMPLES ==========
        
        User: "I was hospitalized for heart surgery on March 15, 2022 for 5 days"
        DETECTION: ✓ Reason: "heart surgery" ✓ Date: "March 15, 2022" ✓ Duration: "5 days"
        ACTION: IMMEDIATELY call handle_save_past_hospitalization(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}", reason="heart surgery", hosp_date="2022-03-15", duration="5 days")
        
        User: "Remove my pneumonia hospitalization"
        DETECTION: Delete request for pneumonia
        ACTION: Find pneumonia entry in patient data, extract past_hosp_structure_id, call handle_delete_past_hospitalization
        
        User: "What's my hospitalization history?"
        DETECTION: Request for current data
        ACTION: IMMEDIATELY call handle_get_past_hospitalization(patient_account="{state.get('patient_account', '')}", practice_code="{state.get('practice_code', '')}")

        ========== CONVERSATION FLOW ==========
        
        1. FIRST INTERACTION: Always call handle_get_past_hospitalization first
        2. DISPLAY CURRENT DATA: Show what they have (hide past_hosp_structure_id)
        3. COLLECT NEW DATA: Ask for missing information one by one
        4. SAVE IMMEDIATELY: When you have reason + date + duration
        5. CONFIRM: Only after successful function call
        
        ENDING PHRASES: "Thank you for confirming your past hospitalization"
        
        AMBIGUOUS INPUT HANDLING:
        - If user input is unclear, ambiguous, or not recognized (empty, garbled, irrelevant):
        - Respond with: "I'm sorry, I didn't understand that clearly. Could you please repeat your response?"
        - Do NOT repeat the previous question or provide the same response again
        - Ask for clarification in a conversational way
        
        USER MESSAGE: {state['human_message']}
        CONVERSATION HISTORY: {state['history']}

        🚨 MANDATORY ACTIONS BASED ON USER INPUT 🚨
        
        ANALYZE the user's message and IMMEDIATELY take action:
        
        IF user message contains REASON + DATE + DURATION:
        → IMMEDIATELY call handle_save_past_hospitalization
        
        IF user asks to DELETE/REMOVE hospitalization:
        → IMMEDIATELY call handle_delete_past_hospitalization
        
        IF this is FIRST interaction OR user asks for current data:
        → IMMEDIATELY call handle_get_past_hospitalization
        
        DO NOT just talk about calling functions - ACTUALLY CALL THEM!

        RESPONSE FORMAT:
        You must structure your response as a JSON object with exactly two fields:
        1. "speech": A SINGLE STRING containing conversational elements like greetings, questions, and wrap-up statements.
        2. "display": A string containing only the essential structured information that should be displayed to the user.
        
        - **CRITICAL: Format the "display" field using Markdown syntax:**
        - Use **Section Header** and **Subsection Header** (both in **bold**) for section titles
        - Use **text** for bold emphasis on important labels
        - Use `- **Label:** value` for bullet points with bold labels
        - Use `✅`, `❌`, `⚠️`, `🏥`, `💊`, `📋`, `📞`, `🔍`, `💉`, `💳`, `🆔`, `👤`, `📍` and other relevant emojis for visual appeal
        - Use `---` for section dividers
        - Use `\`code\`` for highlighting important IDs, codes, or technical terms
        - Use tables with pipe syntax for tabular data,
        - The first column of every table must be a sequence number labeled #. for example:
            ```
            | # | Col1       | Col2       |
            |---|------------|------------|
            | 1 | **Label:** | value      |
            ```
        - Use numbered lists (`1. Item`) for sequential steps
        - Always include relevant emojis to enhance user experience

        Example format:
        {{{{
            "speech": "Conversational response with greetings and questions",
            "display": "**🏥 Past Hospitalization History**\\n\\n- **⚕️ Reason:** Surgery\\n- **📅 Date:** `2022-03-15`\\n- **⏰ Duration:** 5 days"
        }}}}

        REMEMBER: Function calls happen BEFORE you generate your JSON response!
        """
        
        info_logger.info(f"Prompt for past_hospitalization_agent: {prompt}")
        ai_response = GenerateResponse.generate_response_v3(prompt, tools=[past_hospitalization_tools])
        
        # Check for transition to end conversation
        if ai_response.get("speech") and "thank you for confirming your past hospitalization" in ai_response["speech"].lower():
            # Create final completion message
            final_response = {
                "speech": "Thank you for confirming your past hospitalization. Your check-in process is now complete. Have a great day!",
                "display": "✅ Check-in Process Completed Successfully!\n\nThank you for using Breeze Check-in!"
            }
            state["history"].append({"role": "assistant", "content": final_response})
            
            # Mark conversation as completed but don't set agent to "END"
            state["conversation_completed"] = True
            # Keep the agent as past_hospitalization_agent to avoid routing errors
            return state
        
        state["history"].append({"role": "assistant", "content": ai_response})
        return state

    except ValueError as ve:
        error_logger.error(f"{state['session_id']} | Validation error in past_hospitalization_agent: {str(ve)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": f"I apologize, but there seems to be an issue: {str(ve)}",
                "display": "Error processing past hospitalization information"
            }
        }

    except Exception as e:
        error_logger.error(f"{state['session_id']} | Error in past_hospitalization_agent: {str(e)}")
        return {
            "status": False,
            "session_id": state['session_id'],
            "response": {
                "speech": "I apologize, but there seems to be a technical issue. Please try again.",
                "display": "Technical error occurred"
            }
        }                        
                        
def classify_agent_v2(state: CheckInState2) -> CheckInState2:
    """
    Intelligent router function that provides dynamic, context-aware responses
    based on the current agent, user message, and healthcare workflow state.
    """
    agent_name = state["agent"]
    user_message = state.get("human_message", "")
    conversation_history = state.get("history", [])

    # Predefined agent messages with separate speech and display outputs
    agent_messages = {
        "demo_agent": {
            "speech": "Hi there! I'm Your Breeze Check-in Voice Assistant! I'll help you review and update your information for today's visit. Let's start with your demographics information.",
            "display": "Welcome to Breeze Check-in. Let's start with your demographics."
        },
        "insurance_agent": {
            "speech": "Now let's review your insurance information. This helps us verify your coverage and ensure proper billing for your visit.",
            "display": "Review your insurance information for proper billing."
        },
        "allergy_agent": {
            "speech": "Let's review your allergy information. It's important for us to know about any allergies you have to medications, foods, or environmental factors.",
            "display": "Please confirm your allergies for your safety."
        },
        "add_allergy_agent": {
            "speech": "I'll help you add any new allergies to your medical record. This information is crucial for your safety during treatment.",
            "display": "Add new allergies to your medical record."
        },
        "symptom_checker_agent": {
            "speech": "Now let's discuss your current symptoms and the reason for today's visit. Please describe what brings you in today.",
            "display": "Describe your symptoms for today's visit."
        },
        "pharmacy_agent": {
            "speech": "Let's review your preferred pharmacy information. This helps us send your prescriptions to the right location for your convenience.",
            "display": "Confirm your preferred pharmacy."
        },
        "medication_agent": {
            "speech": "Now we'll review your current medications. It's important to have an accurate list of all medications, supplements, and vitamins you're taking.",
            "display": "Review your current medications."
        },
        "family_history_agent": {
            "speech": "Let's review your family medical history. This information helps your healthcare provider understand potential genetic risks and plan appropriate care.",
            "display": "Provide your family medical history."
        },
        "social_history_agent": {
            "speech": "Now we'll review your social history, including lifestyle factors that may affect your health such as smoking, alcohol use, and exercise habits.",
            "display": "Review your lifestyle factors."
        },
        "past_surgical_history_agent": {
            "speech": "Let's review your past surgical history. This information helps your healthcare provider understand your medical background and plan appropriate care.",
            "display": "Provide your past surgical history."
        },
        "past_hospitalization_agent": {
            "speech": "Finally, let's review your past hospitalization history. This completes your medical background information for today's visit.",
            "display": "Provide your past hospitalization history."
        }
    }

    # If no user message (new session), provide standard welcome
    if not user_message:
        if agent_name in agent_messages:
            state.setdefault("history", []).append({
                "role": "assistant",
                "content": agent_messages[agent_name]  # full dict {speech, display}
            })
        else:
            state.setdefault("history", []).append({
                "role": "assistant",
                "content": {
                    "speech": "Welcome to the healthcare check-in assistant.",
                    "display": "Welcome to your check-in."
                }
            })
        return state

    # For continuing conversations, use LLM to generate intelligent responses
    try:
        agent_contexts = {
            "demo_agent": "demographics and personal information",
            "insurance_agent": "insurance coverage and billing information",
            "allergy_agent": "allergies and adverse reactions",
            "add_allergy_agent": "adding new allergy information",
            "symptom_checker_agent": "current symptoms and visit reason",
            "pharmacy_agent": "preferred pharmacy information",
            "medication_agent": "current medications and prescriptions",
            "family_history_agent": "family medical history",
            "social_history_agent": "social history and lifestyle factors",
            "past_surgical_history_agent": "past surgical procedures",
            "past_hospitalization_agent": "past hospitalizations"
        }

        current_context = agent_contexts.get(agent_name, "medical information")
        prompt = f"""
        You are an intelligent healthcare check-in assistant router. The user is currently in the {current_context} section of their medical check-in process.

        USER MESSAGE: "{user_message}"
        CURRENT AGENT: {agent_name}
        CURRENT SECTION: {current_context}

        INSTRUCTIONS:
        1. Analyze the user's message to understand their intent
        2. Provide a brief, helpful response that acknowledges their request
        3. If they're asking about the current section ({current_context}), say you're processing their request
        4. If they're asking about a different section, acknowledge the transition
        5. Keep responses concise, professional, and reassuring
        6. Maximum 2 sentences

        Generate a brief, contextual response as a healthcare assistant:
        """

        info_logger.info(f"Prompt for classify_agent: {prompt}")
        ai_response = GenerateResponse.generate_response_v3(prompt, tools=[])
        info_logger.info(f"AI Response for classify_agent: {ai_response}")

        if isinstance(ai_response, dict):
            response_text = ai_response
        else:
            response_text = {
                "speech": str(ai_response) if ai_response else f"I'm processing your request regarding {current_context}.",
                "display": str(ai_response) if ai_response else f"Processing request about {current_context}."
            }

        state.setdefault("history", []).append({"role": "assistant", "content": response_text})

    except Exception as e:
        error_logger.error(f"Error in classify_agent LLM generation: {str(e)}")
        fallback_message = {
            "speech": f"I understand you're asking about {agent_contexts.get(agent_name, 'your medical information')}. Let me help you with that.",
            "display": f"Request regarding {agent_contexts.get(agent_name, 'your medical information')}."
        }
        state.setdefault("history", []).append({"role": "assistant", "content": fallback_message})

    return state



def classify_agent(state: CheckInState2) -> CheckInState2:
    return state





workflow = StateGraph(CheckInState2)

workflow.add_node("classify_agent", classify_agent)
workflow.add_node("demo_agent", demo_agent)
workflow.add_node("insurance_agent", insurance_agent)
workflow.add_node("allergy_agent", allergy_agent)
workflow.add_node("add_allergy_agent", add_allergy_agent)
workflow.add_node("symptom_checker_agent", symptom_checker_agent)
workflow.add_node("medication_agent", medication_agent)
workflow.add_node("pharmacy_agent", pharmacy_agent)
workflow.add_node("family_history_agent", family_history_agent)
workflow.add_node("past_surgical_history_agent", past_surgical_history_agent)
workflow.add_node("past_hospitalization_agent", past_hospitalization_agent)
workflow.add_node("social_history_agent", social_history_agent)

workflow.add_edge(START, "classify_agent")

workflow.add_conditional_edges(
    "classify_agent",
    lambda state: state["agent"],
    {
        "demo_agent": "demo_agent",
        "insurance_agent": "insurance_agent",
        "allergy_agent": "allergy_agent",
        "add_allergy_agent": "add_allergy_agent",
        "symptom_checker_agent": "symptom_checker_agent",
        "medication_agent": "medication_agent",
        "pharmacy_agent": "pharmacy_agent",
        "family_history_agent": "family_history_agent",
        "social_history_agent": "social_history_agent",
        "past_surgical_history_agent": "past_surgical_history_agent",
        "past_hospitalization_agent": "past_hospitalization_agent"       
    }
)
workflow.add_conditional_edges(
    "demo_agent",
    lambda state: state.get("agent"),
    {
        "insurance_agent": "insurance_agent",
        "demo_agent": END
    }
)

workflow.add_conditional_edges(
    "insurance_agent",
    lambda state: state.get("agent"),
    {
        "allergy_agent": "allergy_agent",
        "insurance_agent": END
    }
)

workflow.add_conditional_edges(
    "allergy_agent",
    lambda state: state.get("agent"),
    {
        "add_allergy_agent": "add_allergy_agent",
        "allergy_agent": END
    }
)

workflow.add_conditional_edges(
    "add_allergy_agent",
    lambda state: state.get("agent"),
    {
        "symptom_checker_agent": "symptom_checker_agent",
        "add_allergy_agent": END
    }
)
workflow.add_conditional_edges(
    "symptom_checker_agent",
    lambda state: state.get("agent"),
    {
        "pharmacy_agent": "pharmacy_agent",  
        "symptom_checker_agent": END
    }
)

workflow.add_conditional_edges(
    "pharmacy_agent",
    lambda state: state.get("agent"),
    {
        "medication_agent": "medication_agent",
        "pharmacy_agent": END
    }
)

workflow.add_conditional_edges(
    "medication_agent",
    lambda state: state.get("agent"),
    {
        "family_history_agent": "family_history_agent",
        "medication_agent": END
    }
)

workflow.add_conditional_edges(
    "family_history_agent",
    lambda state: state.get("agent"),
    {
        "social_history_agent": "social_history_agent",
        "family_history_agent": END
    }
)

workflow.add_conditional_edges(
    "social_history_agent",
    lambda state: state.get("agent"),
    {
        "past_surgical_history_agent": "past_surgical_history_agent",
        "social_history_agent": END
    }
)


workflow.add_conditional_edges(
    "past_surgical_history_agent",
    lambda state: state.get("agent"),
    {
        "past_hospitalization_agent": "past_hospitalization_agent",
        "past_surgical_history_agent": END
    }
)

workflow.add_conditional_edges(
    "past_hospitalization_agent",
    lambda state: "END" if state.get("conversation_completed") else state.get("agent"),
    {
        "past_hospitalization_agent": "past_hospitalization_agent",
        "END": END  # This handles the completion
    }
)

workflow.add_edge("past_hospitalization_agent", END)


app_workflow = workflow.compile()

# graph_bytes = app_workflow.get_graph().draw_mermaid_png()

# image = PILImage.open(io.BytesIO(graph_bytes))

# image.save("graph_image.png")



def checkin_endpoint(patient_data: Dict[str, Any] = None, response: str = None, session_id: str = None) -> Dict[str, Any]:
    try:
        agent_name = None
        end_conversation = False
        patient_account = None
        appointment_id = None
        
        if session_id is None:
            # NEW SESSION
            agent_name = "demo_agent"
            session_id = str(uuid.uuid4())
            patient_account = patient_data.get("PATIENT_ACCOUNT")
            practice_code = patient_data.get("PRACTICE_CODE")
            appointment_id = patient_data.get('APPOINTMENT_ID') if patient_data else None
            
            # Log the complete patient_data details for new sessions
            info_logger.info(f"NEW SESSION: {session_id} - Creating new session with patient data:")
            info_logger.info(f"PATIENT_ACCOUNT: {patient_account}")
            info_logger.info(f"PRACTICE_CODE: {practice_code}")
            info_logger.info(f"APPOINTMENT_ID: {appointment_id}")

            for key, value in patient_data.items():
                info_logger.info(f"patient_data[{key}]: {value}")
                
            if not patient_account:
                raise ValueError("Patient account is required for new session")
            
            state = CheckInState2()
            state["session_id"] = session_id
            state["patient_data"] = patient_data
            state["history"] = []
            state["agent"] = agent_name
            state["human_message"] = response
            state["patient_account"] = patient_account
            state["practice_code"] = practice_code
            state["appointment_id"] = appointment_id
            state["conversation_completed"] = False
            # Initialize insurance workflow state
            state["insurance_search_results"] = {}
            state["selected_insurance"] = {}
            state["collected_insurance_data"] = {}
            state = app_workflow.invoke(state)
        
            DBops.insert_chatbot_log(
                session_id=session_id,
                patient_account=patient_account,
                chat_hist=json.dumps(state["history"][-1]),
                agent=agent_name,
                practice_code=practice_code,
                appointment_id=appointment_id
            )
        else:
            # CONTINUING SESSION
            df = DBops.get_session_data(session_id)
            if df.shape[0] > 0:
                agent_name = df["AGENT"].values[0]
                patient_account = str(df["PATIENT_ACCOUNT"].values[0])
                practice_code = str(df["PRACTICE_CODE"].values[0])
                # GET APPOINTMENT_ID FROM DATABASE
                appointment_id = str(df["APPOINTMENT_ID"].values[0]) if "APPOINTMENT_ID" in df.columns and df["APPOINTMENT_ID"].values[0] is not None else None
                con_hist = df["CHAT_HIST"].values[0]
                con_hist = f"[{con_hist}]"
                con_hist = json.loads(con_hist)
                
            if df.shape[0] == 0:
                raise ValueError(f"Session {session_id} not found")
                
            # LOAD DATA BASED ON AGENT - WITH APPOINTMENT_ID HANDLING
            if agent_name == "demo_agent":    
                patient_data = DBops.get_patient_demographics(patient_account)
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id
                    
            elif agent_name == "insurance_agent":
                patient_data = InsuranceService.get_patient_insurance(
                    patient_account=patient_account, 
                    practice_code=practice_code, 
                    appointment_id=appointment_id or "",
                    uid=session_id
                )
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id
                
            elif agent_name == "allergy_agent":
                patient_data = Allergies.get_patient_allergies(patient_account=patient_account, practice_code=practice_code, uid=session_id)
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id
            
            elif agent_name == "add_allergy_agent":
                patient_data = Allergies.get_patient_allergies(patient_account=patient_account, practice_code=practice_code, uid=session_id)
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id

            elif agent_name == "symptom_checker_agent":
                # For symptom checker, we don't need specific patient data but we need appointment_id
                patient_data = {"APPOINTMENT_ID": appointment_id} if appointment_id else {}

            elif agent_name == "pharmacy_agent":
                raw_pharms = PharmaciesService.get_patient_pharmacies(patient_account=patient_account, practice_code=practice_code, uid=session_id)
                pharmacies = []
                for p in raw_pharms:
                    pharmacies.append({
                        "pharmacy_name":    p.get("pharmacy_name", ""),
                        "pharmacy_phone":   p.get("pharmacy_phone", ""),
                        "pharmacy_fax":     p.get("pharmacy_fax", ""),
                        "pharmacy_address": p.get("pharmacy_address", ""),
                        "pharmacy_id":      p.get("pharmacy_id", ""),
                    })
                patient_data = {"pharmacies": pharmacies}
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id

            elif agent_name == "medication_agent":
                raw_meds = MedicationService.get_patient_medications(patient_account=patient_account, practice_code=practice_code, uid=session_id)
                medications = []
                for m in raw_meds:
                    medications.append({
                        "medication_name":        m.get("medication_name", ""),
                        "intake":                 m.get("intake", ""),
                        "diagnosis":              m.get("diagnosis", ""),
                        "added_by":               m.get("added_by", ""),
                        "patient_prescription_id": m.get("patient_prescription_id", ""),
                        "unitCode":               m.get("unitCode", ""),
                        "diagCode":               m.get("diagCode", "")
                    })
                patient_data = {"medications": medications}
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id
                
            elif agent_name == "family_history_agent":
                try:
                    raw_family_history = FamilyHistoryService.get_patient_family_history(
                        patient_account=patient_account,
                        practice_code=practice_code,
                        uid=session_id
                    )
                    family_history = []
                    for fh in raw_family_history:
                        family_history.append({
                            "family_history_id":    fh.get("family_history_id", ""),
                            "disease_name":         fh.get("disease_name", ""),
                            "diagnosis_description": fh.get("diagnosis_description", ""),
                            "relationship":         fh.get("relationship", ""),
                            "relationship_code":    fh.get("relationship_code", ""),
                            "deceased":             fh.get("deceased", ""),
                            "age":                  fh.get("age", ""),
                            "age_at_onset":         fh.get("age_at_onset", ""),
                            "description":          fh.get("description", ""),
                            "name":                 fh.get("name", ""),
                            "modified_date":        fh.get("modified_date", "")
                        })
                    patient_data = {"family_history": family_history}
                except Exception as e:
                    error_logger.error(f"{session_id} | Error fetching family history data: {str(e)}")
                    patient_data = {"family_history": []}
                    

            elif agent_name == "social_history_agent":
                try:
                    social_history_data = SocialHistoryService.get_patient_social_history(
                        patient_account=patient_account,
                        practice_code=practice_code,
                        uid=session_id
                    )
                    patient_data = {"social_history": social_history_data}
                except Exception as e:
                    error_logger.error(f"{session_id} | Error fetching social history data: {str(e)}")
                    patient_data = {"social_history": {}}

            elif agent_name == "past_surgical_history_agent":
                try:
                    raw_surgical_history = PastSurgicalHistoryService.get_patient_past_surgical_history(
                        patient_account=patient_account,
                        practice_code=practice_code,
                        uid=session_id
                    )
                    surgical_history = []
                    for sh in raw_surgical_history:
                        surgical_history.append({
                            "past_surgical_history_structure_id": sh.get("past_surgical_history_structure_id", ""),
                            "surgery_date":         sh.get("surgery_date", ""),
                            "surgery_name":         sh.get("surgery_name", ""),
                            "surgery_place":        sh.get("surgery_place", ""),
                            "post_surgery_complications": sh.get("post_surgery_complications", "")
                        })
                    patient_data = {"past_surgical_history": surgical_history}
                except Exception as e:
                    error_logger.error(f"{session_id} | Error fetching past surgical history data: {str(e)}")
                    patient_data = {"past_surgical_history": []}
                # Add appointment_id to patient_data
                if appointment_id:
                    patient_data["APPOINTMENT_ID"] = appointment_id
                    
            elif agent_name == "past_hospitalization_agent":
                try:
                    raw_hospitalization = PastHospitalizationService.get_patient_past_hospitalization(
                        patient_account=patient_account,
                        practice_code=practice_code,
                        uid=session_id
                    )
                    hospitalization_history = []
                    for hosp in raw_hospitalization:
                        hospitalization_history.append({
                            "past_hosp_structure_id": hosp.get("past_hosp_structure_id", ""),
                            "hosp_date":             hosp.get("hosp_date", ""),
                            "reason":                hosp.get("reason", ""),
                            "duration":              hosp.get("duration", ""),
                            "comments":              hosp.get("comments", "")
                        })
                    patient_data = {"past_hospitalization": hospitalization_history}
                except Exception as e:
                    error_logger.error(f"{session_id} | Error fetching past hospitalization data: {str(e)}")
                    patient_data = {"past_hospitalization": []}
                    
            
                
            info_logger.info(f"Continuing session {session_id} with {len(con_hist) if con_hist else 0} messages in history")
            info_logger.info(f"Agent: {agent_name}, Appointment ID: {appointment_id}")
            
            state = CheckInState2()
            state["session_id"] = session_id
            state["history"] = con_hist if con_hist else []
            state["agent"] = agent_name
            state["patient_data"] = patient_data
            state["patient_account"] = patient_account
            state["practice_code"] = practice_code
            state["appointment_id"] = appointment_id  # Set appointment_id in state
            state["human_message"] = response
            state["conversation_completed"] = False
            # Initialize insurance workflow state for continuing sessions
            state["insurance_search_results"] = {}
            state["selected_insurance"] = {}
            state["collected_insurance_data"] = {}
            
            DBops.insert_chatbot_log(
                session_id=session_id,
                patient_account=patient_account,
                chat_hist=json.dumps({"role": "user", "content": state["human_message"]}),
                agent=agent_name,
                status=0,
                practice_code=practice_code,
                appointment_id=appointment_id  # Use appointment_id from state
            )
            
            state = app_workflow.invoke(state)
                
            # Check if conversation is completed before logging
            if state.get("conversation_completed"):
                info_logger.info(f"{session_id} | Check-in process completed successfully")
                # Log final completion
                DBops.insert_chatbot_log(
                    session_id=session_id,
                    patient_account=patient_account,
                    chat_hist=json.dumps({"role": "system", "content": "Check-in process completed"}),
                    agent="COMPLETED",
                    practice_code=practice_code,
                    appointment_id=appointment_id
                )
            else:
                # Normal logging for ongoing conversation
                DBops.insert_chatbot_log(
                    session_id=session_id,
                    patient_account=patient_account,
                    chat_hist=json.dumps(state["history"][-1]),
                    agent=state["agent"],
                    practice_code=practice_code,
                    appointment_id=appointment_id  # Use appointment_id from state
                )

        # Get the response content from history
        response_content = state["history"][-1]["content"] if state["history"] else {
            "speech": "I'm sorry, I couldn't process your request.",
            "display": "No response content available."
        }
        
        # Handle search results cleanup
        if isinstance(response_content, dict) and "_search_results" in response_content:
            clean_response = {
                "speech": response_content.get("speech", ""),
                "display": response_content.get("display", "")
            }
            info_logger.info(f"Removing _search_results field from response sent to user")
            
            return {
                "status": True,
                "session_id": session_id,
                "response": clean_response,
                "completed": state.get("conversation_completed", False)  # Add completion flag
            }
        else:
            return {
                "status": True,
                "session_id": session_id,
                "response": response_content,
                "completed": state.get("conversation_completed", False)  # Add completion flag
            }

    except ValueError as ve:
        error_logger.error(f"Error in checkin_endpoint: {str(ve)}")
        return {
            "status": False,
            "session_id": session_id if session_id else "",
            "response": {
                "speech": f"Error: {str(ve)}",
                "display": f"Error: {str(ve)}"
            },
            "completed": False
        }
    except Exception as e:
        error_logger.error(f"Error in checkin_endpoint: {str(e)}")
        return {
            "status": False,
            "session_id": session_id if session_id else "",
            "response": {
                "speech": f"Error: {str(e)}",
                "display": f"Error: {str(e)}"
            }
        }


import uuid
import json
import asyncio
from typing import Optional, Dict, Any

async def checkin_endpoint_stream(patient_data: Optional[Dict[str, Any]] = None,response: Optional[str] = None,session_id: Optional[str] = None,):
    try:
        agent_name = None
        patient_account = None
        appointment_id = None
        practice_code = None

        if not session_id:
            agent_name = "demo_agent"
            session_id = str(uuid.uuid4())

            patient_account = patient_data.get("PATIENT_ACCOUNT") if patient_data else None
            practice_code = patient_data.get("PRACTICE_CODE") if patient_data else None
            appointment_id = patient_data.get("APPOINTMENT_ID") if patient_data else None

            # Log incoming patient_data
            info_logger.info(f"NEW SESSION: {session_id} - Creating new session with patient data:")
            info_logger.info(f"PATIENT_ACCOUNT: {patient_account}")
            info_logger.info(f"PRACTICE_CODE: {practice_code}")
            info_logger.info(f"APPOINTMENT_ID: {appointment_id}")
            if patient_data:
                for k, v in patient_data.items():
                    info_logger.info(f"patient_data[{k}]: {v}")

            if not patient_account:
                # SSE error chunk and stop
                err = {"status": "error", "message": "Patient account is required for new session"}
                yield f"data: {json.dumps(err)}\n\n"
                return

            # Build initial state
            state = CheckInState2()
            state["session_id"] = session_id
            state["patient_data"] = patient_data
            state["history"] = []
            state["agent"] = agent_name
            state["human_message"] = response
            state["patient_account"] = patient_account
            state["practice_code"] = practice_code or ""
            state["appointment_id"] = appointment_id
            state["conversation_completed"] = False
            state["insurance_search_results"] = {}
            state["selected_insurance"] = {}
            state["collected_insurance_data"] = {}
            state["_streaming_mode"] = True
            state["_streaming_chunks"] = []

            # Insert a session-started log (non-blocking to loop)
            try:
                DBops.insert_chatbot_log(
                    session_id,
                    patient_account,
                    json.dumps({"role": "system", "content": "session started"}),
                    agent_name,
                    1,
                    practice_code,
                    appointment_id)

            except Exception as e:
                # Log but don't stop streaming
                error_logger.error(f"{session_id} | Failed insert session-start log: {e}")

        else:
            df = DBops.get_session_data(session_id)

            if getattr(df, "shape", (0,))[0] == 0:
                err = {"status": "error", "message": f"Session {session_id} not found"}
                yield f"data: {json.dumps(err)}\n\n"
                return

            agent_name = df["AGENT"].values[0] if "AGENT" in df.columns else None
            patient_account = str(df["PATIENT_ACCOUNT"].values[0]) if "PATIENT_ACCOUNT" in df.columns else None
            practice_code = str(df["PRACTICE_CODE"].values[0]) if "PRACTICE_CODE" in df.columns else None
            appointment_id = str(df["APPOINTMENT_ID"].values[0]) if "APPOINTMENT_ID" in df.columns and df["APPOINTMENT_ID"].values[0] is not None else None

            con_hist = df["CHAT_HIST"].values[0] if "CHAT_HIST" in df.columns else "[]"
            try:
                con_hist = f"[{con_hist}]" if not con_hist.strip().startswith("[") else con_hist
                con_hist = json.loads(con_hist)
            except Exception:
                con_hist = []

            info_logger.info(f"Continuing session {session_id} with {len(con_hist)} messages in history")
            info_logger.info(f"Agent: {agent_name}, Appointment ID: {appointment_id}")
            patient_data = {}  # default

            try:
                if agent_name == "demo_agent":
                    patient_data = await asyncio.to_thread(DBops.get_patient_demographics, patient_account)
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name == "insurance_agent":
                    patient_data = await asyncio.to_thread(
                        InsuranceService.get_patient_insurance,
                        patient_account,
                        practice_code,
                        appointment_id or "",
                        session_id,
                    )
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name in ("allergy_agent", "add_allergy_agent"):
                    patient_data = await asyncio.to_thread(
                        Allergies.get_patient_allergies,
                        patient_account,
                        practice_code,
                        session_id,
                    )
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name == "symptom_checker_agent":
                    patient_data = {"APPOINTMENT_ID": appointment_id} if appointment_id else {}

                elif agent_name == "pharmacy_agent":
                    raw_pharms = await asyncio.to_thread(
                        PharmaciesService.get_patient_pharmacies,
                        patient_account,
                        practice_code,
                        session_id,
                    )
                    pharmacies = []
                    for p in raw_pharms:
                        pharmacies.append({
                            "pharmacy_name":    p.get("pharmacy_name", ""),
                            "pharmacy_phone":   p.get("pharmacy_phone", ""),
                            "pharmacy_fax":     p.get("pharmacy_fax", ""),
                            "pharmacy_address": p.get("pharmacy_address", ""),
                            "pharmacy_id":      p.get("pharmacy_id", ""),
                        })
                    patient_data = {"pharmacies": pharmacies}
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name == "medication_agent":
                    raw_meds = await asyncio.to_thread(
                        MedicationService.get_patient_medications,
                        patient_account,
                        practice_code,
                        session_id,
                    )
                    medications = []
                    for m in raw_meds:
                        medications.append({
                            "medication_name":        m.get("medication_name", ""),
                            "intake":                 m.get("intake", ""),
                            "diagnosis":              m.get("diagnosis", ""),
                            "added_by":               m.get("added_by", ""),
                            "patient_prescription_id": m.get("patient_prescription_id", ""),
                            "unitCode":               m.get("unitCode", ""),
                            "diagCode":               m.get("diagCode", "")
                        })
                    patient_data = {"medications": medications}
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name == "family_history_agent":
                    try:
                        raw_family_history = await asyncio.to_thread(
                            FamilyHistoryService.get_patient_family_history,
                            patient_account,
                            practice_code,
                            session_id,
                        )
                        family_history = []
                        for fh in raw_family_history:
                            family_history.append({
                                "family_history_id":    fh.get("family_history_id", ""),
                                "disease_name":         fh.get("disease_name", ""),
                                "diagnosis_description": fh.get("diagnosis_description", ""),
                                "relationship":         fh.get("relationship", ""),
                                "relationship_code":    fh.get("relationship_code", ""),
                                "deceased":             fh.get("deceased", ""),
                                "age":                  fh.get("age", ""),
                                "age_at_onset":         fh.get("age_at_onset", ""),
                                "description":          fh.get("description", ""),
                                "name":                 fh.get("name", ""),
                                "modified_date":        fh.get("modified_date", "")
                            })
                        patient_data = {"family_history": family_history}
                    except Exception as e:
                        error_logger.error(f"{session_id} | Error fetching family history data: {str(e)}")
                        patient_data = {"family_history": []}

                elif agent_name == "social_history_agent":
                    try:
                        social_history_data = await asyncio.to_thread(
                            SocialHistoryService.get_patient_social_history,
                            patient_account,
                            practice_code,
                            session_id,
                        )
                        patient_data = {"social_history": social_history_data}
                    except Exception as e:
                        error_logger.error(f"{session_id} | Error fetching social history data: {str(e)}")
                        patient_data = {"social_history": {}}

                elif agent_name == "past_surgical_history_agent":
                    try:
                        raw_surgical_history = await asyncio.to_thread(
                            PastSurgicalHistoryService.get_patient_past_surgical_history,
                            patient_account,
                            practice_code,
                            session_id,
                        )
                        surgical_history = []
                        for sh in raw_surgical_history:
                            surgical_history.append({
                                "past_surgical_history_structure_id": sh.get("past_surgical_history_structure_id", ""),
                                "surgery_date":         sh.get("surgery_date", ""),
                                "surgery_name":         sh.get("surgery_name", ""),
                                "surgery_place":        sh.get("surgery_place", ""),
                                "post_surgery_complications": sh.get("post_surgery_complications", "")
                            })
                        patient_data = {"past_surgical_history": surgical_history}
                    except Exception as e:
                        error_logger.error(f"{session_id} | Error fetching past surgical history data: {str(e)}")
                        patient_data = {"past_surgical_history": []}
                    if appointment_id:
                        patient_data["APPOINTMENT_ID"] = appointment_id

                elif agent_name == "past_hospitalization_agent":
                    try:
                        raw_hospitalization = await asyncio.to_thread(
                            PastHospitalizationService.get_patient_past_hospitalization,
                            patient_account,
                            practice_code,
                            session_id,
                        )
                        hospitalization_history = []
                        for hosp in raw_hospitalization:
                            hospitalization_history.append({
                                "past_hosp_structure_id": hosp.get("past_hosp_structure_id", ""),
                                "hosp_date":             hosp.get("hosp_date", ""),
                                "reason":                hosp.get("reason", ""),
                                "duration":              hosp.get("duration", ""),
                                "comments":              hosp.get("comments", "")
                            })
                        patient_data = {"past_hospitalization": hospitalization_history}
                    except Exception as e:
                        error_logger.error(f"{session_id} | Error fetching past hospitalization data: {str(e)}")
                        patient_data = {"past_hospitalization": []}

                else:
                    patient_data = patient_data or {}
            except Exception as e:
                error_logger.error(f"{session_id} | Error rehydrating patient data: {e}")
                patient_data = patient_data or {}

            state = CheckInState2()
            state["session_id"] = session_id
            state["history"] = con_hist if con_hist else []
            state["agent"] = agent_name
            state["patient_data"] = patient_data
            state["patient_account"] = patient_account
            state["practice_code"] = practice_code
            state["appointment_id"] = appointment_id
            state["human_message"] = response
            state["conversation_completed"] = False
            state["insurance_search_results"] = {}
            state["selected_insurance"] = {}
            state["collected_insurance_data"] = {}
            
            state["_streaming_mode"] = True
            state["_streaming_chunks"] = []

            try:
                await asyncio.to_thread(
                    DBops.insert_chatbot_log,
                    session_id,
                    patient_account,
                    json.dumps({"role": "user", "content": state["human_message"]}),
                    agent_name,
                    1,
                    practice_code,
                    appointment_id
                
                )
            except Exception as e:
                error_logger.error(f"{session_id} | Failed insert continuing-session user log: {e}")

        try:
            info_logger.info(f"🎯 Starting custom streaming with LangGraph updates")
            config = {"configurable": {"thread_id": state.get("session_id", "default")}}
            # async for  output in app_workflow.astream_events(state, stream_mode=["updates","messages"],config=config):
            async for  output in app_workflow.astream(state, stream_mode=["updates","messages"],config=config):
                stream_mode=output[0]
                print('****\n',output)
                info_logger.info(f"📡 STREAM: mode={stream_mode}, output_keys={list(output.keys()) if isinstance(output, dict) else 'non-dict'}")
                
                chunk = None
                
                if stream_mode == "updates":
                    info_logger.info(f"🔄 NODE UPDATE: {json.dumps(output)}")
                    response_payload = None
                    
                    response_payload = {"content": str(output)}
                    event_type, data = output
                    node_name = next(iter(data.keys()))
                    print(node_name)
                    if node_name=='classify_agent':
                        response= {"speech": "", "display": ""}
                    else:
                        response= output[1][node_name]['history'][-1]['content']
                        print('response:', output[1][node_name]['history'][-1]['content'])
                    chunk = {
                        "status": True,
                        "is_streaming":True,
                        "session_id": session_id,
                        #"agent": node_name,
                        # "response": output[1][node_name]['history'][-1]['content'],
                        "response": response,
                        "completed": output.get("conversation_completed", False) if isinstance(output, dict) else False,
                    }

                    try:
                        if node_name=="classify_agent":
                            chat_hist = json.dumps({"role":"assistant","content":{"speech": "", "display": ""}})
                        else:
                            chat_hist = json.dumps(output[1][node_name]['history'][-1])
                        await asyncio.to_thread(
                            DBops.insert_chatbot_log,
                            session_id,
                            state.get("patient_account"),
                            chat_hist,
                            node_name,
                            1,
                            state.get("practice_code"),
                            state.get("appointment_id")
                            
                        )
                    except Exception:
                        pass

                    yield f"data: {json.dumps(chunk)}\n\n"
                    await asyncio.sleep(0.01)

            done_chunk = {"status": True,"is_streaming":False, "session_id": session_id, "completed": state.get("conversation_completed", False)}
            yield f"data: {json.dumps(done_chunk)}\n\n"

        except Exception as e:
            err_chunk = {"status": False, "message": str(e), "session_id": session_id}
            yield f"data: {json.dumps(err_chunk)}\n\n"
            return

    except ValueError as ve:
        err_chunk = {"status": False, "message": str(ve), "session_id": session_id or ""}
        yield f"data: {json.dumps(err_chunk)}\n\n"
        return

    except Exception as e:
        err_chunk = {"status": False, "message": str(e), "session_id": session_id or ""}
        yield f"data: {json.dumps(err_chunk)}\n\n"
        return
