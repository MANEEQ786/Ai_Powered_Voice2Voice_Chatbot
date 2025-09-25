import re
import json
import logging

error_logger = logging.getLogger('api_request_error')
info_logger = logging.getLogger('api_request_info')
 
 
log_info = lambda x:  info_logger.info(x)
log_error = lambda x:  error_logger.error(x)
 
modes = {
    'error': log_error,
    'info': log_info
}
 
def log(mode, uid, message = None):
    log_message = f"[{uid}] | {message or ''}"
    logger = modes.get(mode,info_logger)
    logger(log_message)
 
def log_request(uid, request):
    method = request.method
    url = request.path
    headers = request.headers
    remote_address = request.META.get('REMOTE_ADDR')
    request_log = f"{method} on {url} from {remote_address} having headers: {headers}"
   
    log_message = f"[{uid}] | {request_log}"
    logger = modes.get('info',info_logger)
    logger(log_message)

def clean_json_response(response: str, uid: str):
    try:
        json_regex = r'(\{.*\}|\[.*\])'
        matches = re.findall(json_regex, response, re.DOTALL)
        
        if not matches:
            raise ValueError("No valid JSON object found in the response.")

        
        cleaned_response = matches[0]
        
        cleaned_response = re.sub(r'\s+', ' ', cleaned_response)
        cleaned_response = re.sub(r"'", '', cleaned_response)
        
        cleaned_response = re.sub(r',\s*([\]}])', r'\1', cleaned_response)
        
        cleaned_response = re.sub(r'{\s*,', '{', cleaned_response)
        cleaned_response = re.sub(r'\[\s*,', '[', cleaned_response)
        
        
        cleaned_response = re.sub(r'(?<!\\)\\(?!["\\/bfnrtu])', '', cleaned_response)
        
        cleaned_response = re.sub(r'\b0+(\d+)', r'\1', cleaned_response)
        
        cleaned_response = re.sub(r'\/\/.*|\/\*.*\*\/', '', cleaned_response, flags=re.MULTILINE)
        
        cleaned_response = re.sub(r'[\x00-\x1F\x7F]', '', cleaned_response)


        cleaned_response = re.sub(r'\{([^\{\}\[\]]+)\{', r'{\1,{', cleaned_response)
        cleaned_response = re.sub(r'\}([^\{\}\[\]]+)\}', r'},\1}', cleaned_response)
        
        return json.loads(cleaned_response)

    except json.JSONDecodeError as e:
        log('error',uid,f"JSONDecodeError: {e}")
        return None
    except ValueError as ve:
        log('error',uid,f"ValueError: {ve}")
        return None
    except Exception as e:
        log('error',uid,f"Unexpected error: {e}")
        return None