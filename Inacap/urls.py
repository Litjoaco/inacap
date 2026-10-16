from django.contrib import admin
from django.urls import path, include
from usuario import views as usuario_views
from paneladm import views as panel_views
from django.conf import settings
from django.conf.urls.static import static

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

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
