from django.urls import path
from . import views
from usuario import views as usuario_views

app_name = 'panel-admin'

urlpatterns = [
    path('', usuario_views.panel_admin, name='panel_admin'),
    path('usuarios/buscar/', views.buscar_usuarios_ajax, name='buscar_usuarios_ajax'),
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/carga-masiva/', views.carga_masiva_usuarios_view, name='carga_masiva_usuarios'),
    path('usuarios/carga-masiva/analizar/', views.api_analizar_carga_masiva_usuarios, name='api_analizar_carga_masiva_usuarios'),
    path('usuarios/carga-masiva/procesar/', views.api_procesar_carga_masiva_usuarios, name='api_procesar_carga_masiva_usuarios'),
    path('usuarios/carga-masiva-excel/', views.api_procesar_carga_masiva_usuarios, name='carga_masiva_usuarios_excel'),
    path('usuarios/descargar-plantilla-excel/', views.descargar_plantilla_usuarios_excel, name='descargar_plantilla_usuarios_excel'),
    path('usuarios/exportar-excel/', views.exportar_usuarios_excel, name='exportar_usuarios_excel'),
    path('usuarios/editar/<int:usuario_id>/', views.editar_usuario_admin, name='editar_usuario_admin'),
    path('usuarios/toggle-destacado/<int:usuario_id>/', views.toggle_destacado_usuario, name='toggle_destacado_usuario'),
    path('usuarios/toggle-visibilidad/<int:usuario_id>/', views.toggle_visibilidad_usuario, name='toggle_visibilidad_usuario'),
    path('usuarios/eliminar/<int:usuario_id>/', views.eliminar_usuario, name='eliminar_usuario'),
    
    # Eventos y Reuniones
    path('reuniones/', views.gestion_reuniones, name='gestion_reuniones'),
    path('reuniones/editar/<int:reunion_id>/', views.editar_reunion, name='editar_reunion'),
    path('reuniones/eliminar/<int:reunion_id>/', views.eliminar_reunion, name='eliminar_reunion'),
    
    # Asistencia y Participantes
    path('asistencia/', views.control_asistencia, name='control_asistencia'),
    path('reuniones/<int:reunion_id>/asistencia/', views.registrar_asistencia, name='registrar_asistencia'),
    path('reuniones/<int:reunion_id>/quitar-asistencia/<int:usuario_id>/', views.quitar_asistencia, name='quitar_asistencia'),
    path('reuniones/<int:reunion_id>/marcar-asistencia/<int:usuario_id>/', views.marcar_asistencia_qr, name='marcar_asistencia_qr'),
    path('reuniones/<int:reunion_id>/escanear-universal/', views.marcar_asistencia_escaner_universal, name='marcar_asistencia_escaner_universal'),
    path('reuniones/<int:reunion_id>/crear-usuario-rapido/', views.crear_usuario_rapido_asistencia, name='crear_usuario_rapido_asistencia'),
    path('asistentes/', views.gestion_asistentes, name='gestion_asistentes'),
    path('asistentes/<int:reunion_id>/', views.ver_asistentes_reunion, name='ver_asistentes_reunion'),
    path('asistentes/<int:reunion_id>/exportar-excel/', views.exportar_asistentes_reunion_excel, name='exportar_asistentes_reunion_excel'),
    path('interesados/', views.gestion_interesados, name='gestion_interesados'),
    path('interesados/<int:reunion_id>/enviar-correo/', views.enviar_correo_masivo_interesados, name='enviar_correo_masivo_interesados'),
    
    # Encuestas y Soporte
    path('encuestas/', views.gestion_encuestas, name='gestion_encuestas'),
    path('encuestas/<int:encuesta_id>/editar/', views.editar_encuesta, name='editar_encuesta'),
    path('encuestas/<int:encuesta_id>/toggle-activa/', views.toggle_activa_encuesta, name='toggle_activa_encuesta'),
    path('encuestas/<int:encuesta_id>/enviar-correo/', views.enviar_encuesta_correo_asistentes, name='enviar_encuesta_correo_asistentes'),
    path('encuestas/<int:encuesta_id>/respuestas/', views.ver_respuestas_encuesta, name='ver_respuestas_encuesta'),
    path('encuestas/eliminar/<int:encuesta_id>/', views.eliminar_encuesta, name='eliminar_encuesta'),
    path('encuestas/responder/<int:reunion_id>/', views.responder_encuesta_publica, name='responder_encuesta_publica'),
    path('respuestas/toggle-destacado/<int:respuesta_id>/', views.toggle_destacado_respuesta, name='toggle_destacado_respuesta'),
    path('soporte/', views.gestion_soporte, name='gestion_soporte'),
    path('soporte/<int:ticket_id>/', views.ver_ticket_soporte, name='ver_ticket_soporte'),
    path('estadisticas/', views.estadisticas_admin, name='estadisticas_admin'),
    path('estadisticas/exportar-excel/', views.exportar_estadisticas_excel, name='exportar_estadisticas_excel'),
    
    # Modo Tótem
    path('totem/seleccionar-reunion/', views.totem_seleccionar_reunion, name='totem_seleccionar_reunion'),
    path('totem/escaner/<int:reunion_id>/', views.totem_escaner, name='totem_escaner'),
    path('totem/verify-exit/', views.totem_verify_exit, name='totem_verify_exit'),

    # Ruleta de Sorteos
    path('ruleta/', views.ruleta_ganador, name='ruleta_ganador'),
    path('ruleta/obtener-participantes/', views.obtener_participantes_ruleta, name='obtener_participantes_ruleta'),
    path('ruleta/registrar-ganador/', views.registrar_ganador_sorteo, name='registrar_ganador_sorteo'),
    path('ruleta/limpiar-historial/', views.limpiar_historial_sorteos, name='limpiar_historial_sorteos'),
    
    # URLs Públicas de Reuniones
    path('reunion/<int:reunion_id>/publica/', views.reunion_publica, name='reunion_publica'),
    path('reunion/<int:reunion_id>/inscribirse/', views.inscribirse_reunion, name='inscribirse_reunion'),
    
    # Plantillas de Etiquetas
    path('plantillas-etiqueta/', views.gestion_plantillas_etiqueta, name='gestion_plantillas_etiqueta'),
    path('plantillas-etiqueta/editar/<int:plantilla_id>/', views.editar_plantilla_etiqueta, name='editar_plantilla_etiqueta'),
    path('plantillas-etiqueta/eliminar/<int:plantilla_id>/', views.eliminar_plantilla_etiqueta, name='eliminar_plantilla_etiqueta'),
]
