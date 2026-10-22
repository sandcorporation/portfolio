from django.conf import settings
from django.contrib import admin
from django.urls import path

from core import shell
from core.api import api
from mcpserver.views import mcp_endpoint
from oauth.bearer import protected_resource_metadata

urlpatterns = [
    path(settings.ADMIN_PATH, admin.site.urls),
    path("api/", api.urls),
    # Remote MCP (resource server for sandcorp-auth). RFC 9728 clients may also ask the
    # path-suffixed metadata URL for the /mcp resource, so both answer the same document.
    path("mcp", mcp_endpoint, name="mcp"),
    path(".well-known/oauth-protected-resource", protected_resource_metadata),
    path(".well-known/oauth-protected-resource/mcp", protected_resource_metadata),
    # HTML shell routes: Django fills per-route meta, React takes over in the browser.
    path("", shell.home, name="home"),
    path("work/<slug:slug>", shell.work, name="work"),
    path("robots.txt", shell.robots_txt),
    path("sitemap.xml", shell.sitemap_xml),
    path("p/<slug:slug>", shell.proposal, name="proposal"),
]
