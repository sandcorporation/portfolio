from django.conf import settings
from django.contrib import admin
from django.urls import path

from core import shell
from core.api import api

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("api/", api.urls),
    # HTML shell routes: Django fills per-route meta, React takes over in the browser.
    path("", shell.home, name="home"),
    path("work/<slug:slug>", shell.work, name="work"),
    path("robots.txt", shell.robots_txt),
    path("sitemap.xml", shell.sitemap_xml),
    path("p/<slug:slug>", shell.proposal, name="proposal"),
]
