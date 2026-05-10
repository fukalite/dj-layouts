from django.urls import path


urlpatterns = [
    path("", lambda request: __import__("django.http", fromlist=["HttpResponse"]).HttpResponse("dj-layouts example")),
]
