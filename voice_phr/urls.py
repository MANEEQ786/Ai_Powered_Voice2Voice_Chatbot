from django.urls import path
from . import views
from django.conf import settings  # Import settings
from django.conf.urls.static import static 

app_name = 'voice_phr'

urlpatterns = [
    # path("home/", views.Home.as_view() , name="Home"),
    path("", views.Test.as_view() , name="test"),
    path("ui/", views.StreamingUI.as_view(), name="streaming_ui"),
    path("get_ai_checkin", views.Get_Ai_CheckIn_Demographics.as_view() , name="AI_CheckIn"),
    path("get_ai_checkin_st", views.Get_Ai_CheckIn_Demographics_st.as_view() , name="AI_CheckIn_st"),
    path("get_logs/", views.GetLogs.as_view() , name="Logs"),
];
if settings.DEBUG:              
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)