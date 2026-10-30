from django.contrib import admin
from django.urls import path, include, re_path
from usuario import views as usuario_views
from paneladm import views as panel_views
from django.conf import settings
from django.views.static import serve

urlpatterns = [
    path('consultar-qr-rut/', usuario_views.consultar_qr_rut, name='consultar_qr_rut'),
    path('admin/', admin.site.urls),
    path('', usuario_views.inicio, name='inicio'),
    path('registro/', usuario_views.registro, name='registro'),
    path('login/', include('login.urls')),              
    path('encuesta/<int:reunion_id>/', panel_views.responder_encuesta_publica, name='responder_encuesta_directa'),
    path('panel-admin/', include('paneladm.urls', namespace='panel-admin')),
    path('', include('usuario.urls')), # Incluye las URLs de la app 'usuario' (perfil, config, etc.)
]

# Servir archivos multimedia (logos, plantillas, etc.) y estáticos en local y producción
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': settings.STATIC_DIR}),
]

