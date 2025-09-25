from rest_framework.views import APIView
from django.http import JsonResponse
from django.http import HttpResponse
from rest_framework.response import Response
import secrets
from django.conf import settings
import json, os, zipfile
from voice_phr.api_calls import DemographicsService
from voice_phr.agents import checkin_endpoint 
import logging
from typing import Dict, Any
from voice_phr.utils.custom_exception import ApplicationException




import json
import asyncio  
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from voice_phr.agents import checkin_endpoint_stream
from django.shortcuts import render
from django.views.generic import TemplateView

info_logger = logging.getLogger('api_info')
error_logger = logging.getLogger('api_error')

class Test(APIView):
    def get(self, request, format=None):
        return JsonResponse({"Response":"AI Powered CheckIn Forms is working fine"})

class StreamingUI(TemplateView):
    template_name = 'index.html'

class GetLogs(APIView):
    def get(self, request):
        try:
            uid = secrets.token_hex(5)
            method = request.method
            url = request.path
            headers = request.headers
            remote_address = request.META.get('REMOTE_ADDR')
            request_log = f"{method} on {url} from {remote_address} having headers: {headers}"
            info_logger.info(f'request uid:{uid}')
            info_logger.info(f"[{uid}] | {request_log}")
            DOWNLOAD_TOKEN = 'Ds@098765'
            token = request.GET.get('token')  # Get token from query parameters
            if token != DOWNLOAD_TOKEN:
                error_logger.error(f'{uid} | Unauthorized status=401')
                return HttpResponse('Unauthorized', status=401)
            path = 'API_LOGS'
            directory = os.path.join(settings.BASE_DIR, path)
            files_to_download = os.listdir(path)
            zip_filename = 'AI_Powered_CheckIn_Logs.zip'
            response = HttpResponse(content_type='application/zip')
            response['Content-Disposition'] = f'attachment; filename={zip_filename}'

            with zipfile.ZipFile(response, 'w') as zip_file:
                for file_name in files_to_download:
                    file_path = os.path.join(directory, file_name)
                    if os.path.exists(file_path):
                        zip_file.write(file_path, arcname=file_name)
            return response
        except Exception as e:
            error_logger.error(f'{uid} | {e}')
            raise ApplicationException()

def serialize_response(response):
    """Convert any non-serializable objects in the response to serializable formats."""
    if isinstance(response, dict):
        result = {}
        for key, value in response.items():
            if key == "message" and hasattr(value, "content"):
                # Handle AIMessage objects by extracting their content
                result[key] = {"role": getattr(value, "role", "assistant"), "content": value.content}
            elif key == "message" and isinstance(value, dict) and "content" in value:
                # Message is already a dict with content
                result[key] = value
            else:
                result[key] = serialize_response(value)
        return result
    elif isinstance(response, list):
        return [serialize_response(item) for item in response]
    else:
        return response

class Get_Ai_CheckIn_Demographics(APIView):
    def get(self, request):
        return Response({"status": "Failure", "message": "GET method not allowed"}, status=400)
    
    def post(self, request, format=None):
        uid = secrets.token_hex(5)
        info_logger.info(f"{uid} | New request received")
        info_logger.info(f"{uid} | Request data: {request.data}")
        try:
            session_id = request.data.get('session_id')
            if session_id:
                info_logger.info(f"{uid} | Continuing session: {session_id}")
                response = request.data.get('response')
                practice_code = request.data.get('PRACTICE_CODE')
                if practice_code:
                    info_logger.info(f"{uid} | Practice code provided in continued session: {practice_code}")
                if not response:
                    error_msg = "Response is required for continuing conversation"
                    error_logger.error(f"{uid} | {error_msg}")
                    return JsonResponse({"error": error_msg}, status=400)
                
                try:
                    chat_response = checkin_endpoint(session_id=session_id, response=response)
                    
                    serialized_response = serialize_response(chat_response)
                    info_logger.info(f"{uid} | Chat response generated and serialized")
                    return JsonResponse(serialized_response, status=200)
                except ValueError as ve:
                    error_msg = str(ve)
                    error_logger.error(f"{uid} | Session error: {error_msg}")
                    return JsonResponse({"error": error_msg}, status=404)
            
            required_fields = ['PATIENT_ACCOUNT', 'APPOINTMENT_ID', 'DOB', 'FIRST_NAME', 'LAST_NAME', 'PRACTICE_CODE']
            
            for field in required_fields:
                if field not in request.data:
                    error_msg = f"Missing required field: {field}"
                    error_logger.error(f"{uid} | {error_msg}")
                    return JsonResponse({"error": error_msg}, status=400)

            try:
                clean_demographics = DemographicsService.process_demographics_data(request_data=request.data, uid=uid)
                info_logger.info(f"{uid} | Demographics processed")
            except Exception as e:
                error_logger.error(f"{uid} | Error processing demographics: {str(e)}")
                return JsonResponse(
                    {"error": "Error processing demographics data"},
                    status=500
                )

            chat_response = checkin_endpoint(patient_data=clean_demographics)
            serialized_response = serialize_response(chat_response)
            info_logger.info(f"{uid} | Initial chat response serialized")
            return JsonResponse(serialized_response, status=200)

        except ValueError as ve:
            error_msg = str(ve)
            error_logger.error(f"{uid} | ValueError: {error_msg}")
            return JsonResponse({"error": error_msg}, status=400)
            
        except Exception as e:
            error_msg = "An unexpected error occurred"
            error_logger.error(f"{uid} | Error: {str(e)}", exc_info=True)
            return JsonResponse({"error": error_msg}, status=500)
        
def async_generator_to_sync_iter(async_gen_func, *args, **kwargs):
    """Utility function to convert async generator to sync iterator, suitable for WSGI (sync) request handlers that need to stream async generator output."""
    agen = async_gen_func(*args, **kwargs)

    def iterator():
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            while True:
                try:
                    item = loop.run_until_complete(agen.__anext__())
                except StopAsyncIteration:
                    break
                yield item
        finally:
            try:
                loop.run_until_complete(agen.aclose())
            except Exception:
                pass
            loop.close()

    return iterator()

def create_sse_response(generator):
    """Create a StreamingHttpResponse with proper SSE headers"""
    def sse_generator():
        try:
            for item in generator:
                if isinstance(item, str):
                    # print(f"Yielding SSE item: {item}")
                    yield item
                else:
                    import json
                    yield f"data: {json.dumps(item)}\n\n"
        except Exception as e:
            import json
            error_response = {"status": "error", "message": str(e)}
            yield f"data: {json.dumps(error_response)}\n\n"
    
    response = StreamingHttpResponse(sse_generator(), content_type="text/event-stream")
    response['Cache-Control'] = 'no-cache'
    response['Access-Control-Allow-Origin'] = '*'
    response['Access-Control-Allow-Headers'] = 'Content-Type, Cache-Control'
    response['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    print("sending response")
    return response

@method_decorator(csrf_exempt, name='dispatch')
class Get_Ai_CheckIn_Demographics_st(View):

    def get(self, request):
        return JsonResponse({"status": "Failure", "message": "GET method not allowed"}, status=400)

    def post(self, request: HttpRequest) -> HttpResponse:
        uid = secrets.token_hex(5)
        info_logger.info(f"{uid} | New request received")
        info_logger.info(f"{uid} | Request headers: {dict(request.headers)}")
        
        try:
            import json
            request_data = json.loads(request.body.decode('utf-8'))
        except Exception as e:
            error_logger.error(f"{uid} | Failed to parse request body: {e}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)
            
        info_logger.info(f"{uid} | Request data: {request_data}")

        wants_stream = False
        accept = request.META.get("HTTP_ACCEPT", "")
        info_logger.info(f"{uid} | Accept header: {accept}")
        if "text/event-stream" in accept:
            wants_stream = True
        if isinstance(request_data, dict) and request_data.get("stream") is True:
            wants_stream = True
        info_logger.info(f"{uid} | Wants stream: {wants_stream}")

        try:
            session_id = request_data.get('session_id')
            if session_id:
                info_logger.info(f"{uid} | Continuing session: {session_id}")
                response_text = request_data.get('response')
                practice_code = request_data.get('PRACTICE_CODE')
                if practice_code:
                    info_logger.info(f"{uid} | Practice code provided in continued session: {practice_code}")
                if not response_text:
                    error_msg = "Response is required for continuing conversation"
                    error_logger.error(f"{uid} | {error_msg}")
                    return JsonResponse({"error": error_msg}, status=400)

                if wants_stream:
                    # stream the async generator for continuing session
                    sync_iter = async_generator_to_sync_iter(checkin_endpoint_stream,
                        {"PRACTICE_CODE": practice_code} ,     
                        response_text,
                        session_id
                    )
                    return create_sse_response(sync_iter)

                # non-streaming behavior (existing)
                try:
                    chat_response = checkin_endpoint(session_id=session_id, response=response_text)
                    serialized_response = serialize_response(chat_response)
                    info_logger.info(f"{uid} | Chat response generated and serialized")
                    return JsonResponse(serialized_response, status=200)
                except ValueError as ve:
                    error_msg = str(ve)
                    error_logger.error(f"{uid} | Session error: {error_msg}")
                    return JsonResponse({"error": error_msg}, status=404)

            required_fields = ['PATIENT_ACCOUNT', 'APPOINTMENT_ID', 'DOB', 'FIRST_NAME', 'LAST_NAME', 'PRACTICE_CODE']
            for field in required_fields:
                if field not in request_data:
                    error_msg = f"Missing required field: {field}"
                    error_logger.error(f"{uid} | {error_msg}")
                    return JsonResponse({"error": error_msg}, status=400)

            try:
                clean_demographics = DemographicsService.process_demographics_data(request_data=request_data, uid=uid)
                info_logger.info(f"{uid} | Demographics processed")
            except Exception as e:
                error_logger.error(f"{uid} | Error processing demographics: {str(e)}")
                return JsonResponse({"error": "Error processing demographics data"}, status=500)

            if wants_stream:
                sync_iter = async_generator_to_sync_iter(
                    checkin_endpoint_stream,
                    clean_demographics,   # patient_data
                    None,                 # response_text
                    None                  # session_id (new session)
                )
                return create_sse_response(sync_iter)

            # non-streaming: original sync path
            chat_response = checkin_endpoint(patient_data=clean_demographics)
            serialized_response = serialize_response(chat_response)
            info_logger.info(f"{uid} | Initial chat response serialized")
            return JsonResponse(serialized_response, status=200)

        except ValueError as ve:
            error_msg = str(ve)
            error_logger.error(f"{uid} | ValueError: {error_msg}")
            return JsonResponse({"error": error_msg}, status=400)

        except Exception as e:
            error_msg = "An unexpected error occurred"
            error_logger.error(f"{uid} | Error: {str(e)}", exc_info=True)
            return JsonResponse({"error": error_msg}, status=500)

    def options(self, request):
        """Handle CORS preflight request"""
        response = HttpResponse()
        response['Access-Control-Allow-Origin'] = '*'
        response['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
        response['Access-Control-Allow-Headers'] = 'Content-Type, Accept'
        return response

    def get(self, request):
        return render(request, 'streaming_ui.html')