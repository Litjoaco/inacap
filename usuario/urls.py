from django.urls import path
from . import views

urlpatterns = [
    path('reuniones/', views.landing_reuniones, name='landing_reuniones'),
    path('perfil/', views.perfil, name='perfil'),
    path('perfil/editar/<int:usuario_id>/', views.editar_perfil, name='editar_perfil'),
    path('etiqueta/<int:usuario_id>/', views.imprimir_etiqueta, name='imprimir_etiqueta'),
    path('reunion/<int:reunion_id>/etiqueta/<int:usuario_id>/', views.imprimir_etiqueta, name='imprimir_etiqueta_reunion'),
    path('reunion/<int:reunion_id>/toggle-interes/', views.toggle_interes, name='toggle_interes'),
    path('configuracion/cambiar-password/', views.cambiar_password, name='cambiar_password'),
    path('password-reset/', views.password_reset_request, name='password_reset_request'),
    path('reset/<uidb64>/<token>/', views.password_reset_confirm, name='password_reset_confirm'),
]
