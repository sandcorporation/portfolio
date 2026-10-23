from django.conf import settings
from django.contrib import admin
from django.urls import path

from core import github_readme, shell
from core.api import api
from mcpserver.views import mcp_endpoint
from oauth import login as oauth_login
from oauth.bearer import protected_resource_metadata

# No password form: the admin login page is the sandcorp-auth start (issue #29).
admin.site.login = oauth_login.admin_login  # type: ignore[method-assign]

urlpatterns = [
    # sandcorp-auth login for the admin (before admin.site.urls, whose catch-all would 404 them).
    path(f"{settings.ADMIN_PATH}oauth/login/", oauth_login.start, name="admin_oauth_start"),
    path(
        f"{settings.ADMIN_PATH}oauth/callback/", oauth_login.callback, name="admin_oauth_callback"
    ),
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
    path("github/readme/personal.md", github_readme.personal, name="github_readme_personal"),
    path("github/readme/org.md", github_readme.org, name="github_readme_org"),
    path("robots.txt", shell.robots_txt),
    path("sitemap.xml", shell.sitemap_xml),
    path("blog/feed.xml", shell.blog_feed, name="blog_feed"),
    path("p/<slug:slug>", shell.proposal, name="proposal"),
    path("p/<slug:slug>/lock", shell.proposal_lock, name="proposal_lock"),
    path("p/<slug:slug>/media/<int:media_id>", shell.proposal_media, name="proposal_media"),
    path("p/<slug:slug>/tab", shell.proposal_tab, name="proposal_tab"),
    path("p/<slug:slug>/pdf", shell.proposal_pdf, name="proposal_pdf"),
    path("preview/<str:token>", shell.proposal_preview, name="proposal_preview"),
    path(
        "preview/<str:token>/media/<int:media_id>",
        shell.proposal_preview_media,
        name="proposal_preview_media",
    ),
    path("print/<str:token>", shell.proposal_print, name="proposal_print"),
    path(
        "print/<str:token>/media/<int:media_id>",
        shell.proposal_print_media,
        name="proposal_print_media",
    ),
]
