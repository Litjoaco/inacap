import re
import json
import functools
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from usuario.models import Usuario, RUBRO_CHOICES, SEDE_CHOICES, CARRERA_CHOICES
from usuario.forms import AdminUsuarioForm, AyudanteUsuarioForm, UsuarioForm
from .models import Reunion, EtiquetaPlantilla, Encuesta, RespuestaEncuesta, SoporteTicket, TicketRespuesta, GanadorSorteo
from .forms import ReunionForm, EtiquetaPlantillaForm, EncuestaForm, SoporteTicketAdminForm, TicketRespuestaForm
from django.urls import reverse
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.db.models import Q, F, Count, Avg, Sum
from django.utils import timezone
from django.views.decorators.http import require_POST
import openpyxl
from openpyxl.styles import Font

from django.contrib.auth.hashers import check_password

def formatear_rut_excel(rut_raw):
    """
    Formatea el RUT para Excel sin puntos pero con guion (ej: 12345678-9).
    """
    if not rut_raw:
        return 'Sin RUT'
    limpio = str(rut_raw).replace('.', '').replace(' ', '').strip().upper()
    if '-' in limpio:
        partes = limpio.split('-')
        return f"{partes[0]}-{partes[1]}"
    if len(limpio) >= 2:
        return f"{limpio[:-1]}-{limpio[-1]}"
    return limpio

def _flatten_choices(choices):
    """
    Función auxiliar para aplanar listas de tuplas anidadas (choices) a un diccionario.
    Ej: [('Grupo', (('k', 'v'),)), ('k2', 'v2')] -> {'k': 'v', 'k2': 'v2'}
    """
    flat_dict = {}
    for group_key, group_value in choices:
        if isinstance(group_value, (list, tuple)):
            for key, value in group_value:
                flat_dict[key] = value
        else:
            flat_dict[group_key] = group_value
    return flat_dict

# Create your views here.
def admin_required(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario_id = request.session.get('usuario_id')
        if not usuario_id:
            return redirect('login')

        try:
            usuario_actual = Usuario.objects.get(id=usuario_id)
            # Ahora, ni admin ni ayudante pueden acceder a vistas solo para superadmin (si las hubiera)
            if not usuario_actual.es_admin and not usuario_actual.es_ayudante:
                return redirect('inicio')
        except Usuario.DoesNotExist:
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper
    
def solo_admin_required(view_func):
    """
    Decorador que restringe el acceso SOLO a los usuarios que son administradores (`es_admin`).
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario_id = request.session.get('usuario_id')
        if not usuario_id:
            return redirect('login')
        usuario_actual = get_object_or_404(Usuario, id=usuario_id)
        if not usuario_actual.es_admin:
            messages.error(request, "No tienes permiso para realizar esta acción.")
            return redirect('panel-admin:panel_admin') # Redirige al panel principal si no es admin
        return view_func(request, *args, **kwargs)
    return wrapper

def totem_required(view_func):
    """
    Decorador que permite el acceso a usuarios de tipo Tótem (`es_totem`) o Administradores (`es_admin`).
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario_id = request.session.get('usuario_id')
        if not usuario_id:
            return redirect('login')
        usuario_actual = get_object_or_404(Usuario, id=usuario_id)
        if not usuario_actual.es_totem and not usuario_actual.es_admin:
            messages.error(request, "Esta sección es solo para terminales de tipo Tótem o Administradores.")
            return redirect('inicio')
        return view_func(request, *args, **kwargs)
    return wrapper

def privileged_user_required(view_func):
    """
    Decorador que permite el acceso a Administradores, Ayudantes y Tótems.
    Ideal para endpoints de API usados por diferentes roles.
    """
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        usuario_id = request.session.get('usuario_id')
        if not usuario_id:
            return redirect('login')
        try:
            usuario_actual = Usuario.objects.get(id=usuario_id)
            if not (usuario_actual.es_admin or usuario_actual.es_ayudante or usuario_actual.es_totem):
                return JsonResponse({'status': 'error', 'message': 'Permiso denegado.'}, status=403)
        except Usuario.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Usuario no encontrado.'}, status=403)
        return view_func(request, *args, **kwargs)
    return wrapper

@admin_required
def gestion_usuarios(request):
    usuario_actual = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    # La búsqueda y el filtrado ahora se manejan exclusivamente por AJAX.
    # Esta vista solo carga la página inicial con todos los usuarios.
    
    query = request.GET.get('q', '')
    rubro_filter = request.GET.get('rubro', '')

    usuarios = Usuario.objects.all().order_by('nombre', 'apellido')

    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) | 
            Q(email__icontains=query) | 
            Q(rut__icontains=query) |
            Q(institucion_empresa__icontains=query) |
            Q(telefono__icontains=query)
        )
    
    if rubro_filter:
        usuarios = usuarios.filter(rubro=rubro_filter)

    total_usuarios_count = Usuario.objects.count()
    total_estudiantes_count = Usuario.objects.filter(rubro='estudiante').count()
    total_externos_count = Usuario.objects.filter(rubro='externo').count()
    total_admins_count = Usuario.objects.filter(es_admin=True).count()

    return render(request, 'panel_admin_usuarios.html', {
        'usuarios': usuarios, 
        'query': query, 
        'rubro_filter': rubro_filter, 
        'usuario_actual': usuario_actual,
        'total_usuarios_count': total_usuarios_count,
        'total_estudiantes_count': total_estudiantes_count,
        'total_externos_count': total_externos_count,
        'total_admins_count': total_admins_count,
        'flat_rubro_choices': _flatten_choices(RUBRO_CHOICES),
    })

@admin_required
def buscar_usuarios_ajax(request):
    """
    Vista para manejar las peticiones AJAX de búsqueda de usuarios.
    """
    query = request.GET.get('q', '')
    rubro_filter = request.GET.get('rubro', '')

    usuarios = Usuario.objects.all().order_by('nombre', 'apellido')

    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) | 
            Q(email__icontains=query) | 
            Q(rut__icontains=query) |
            Q(institucion_empresa__icontains=query) |
            Q(telefono__icontains=query)
        )
    
    if rubro_filter:
        usuarios = usuarios.filter(rubro=rubro_filter)

    # Preparamos los datos para la respuesta JSON
    data = [{
        'id': u.id,
        'nombre': u.nombre,
        'apellido': u.apellido,
        'email': u.email,
        'rut': u.rut,
        'rubro': u.get_rubro_real_display if callable(getattr(u, 'get_rubro_real_display', None)) else (u.rubro or 'General'),
        'institucion_empresa': u.institucion_empresa or ('INACAP' if u.rubro != 'externo' else 'Particular'),
        'telefono': u.telefono or '',
        'cantidad_asistencias': u.cantidad_asistencias,
        'es_admin': u.es_admin,
        'foto_url': u.foto.url if u.foto else '/static/img/persn.jpg'
    } for u in usuarios]

    return JsonResponse({'usuarios': data})

@admin_required
def editar_usuario_admin(request, usuario_id):
    usuario_actual = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    usuario_a_editar = get_object_or_404(Usuario, id=usuario_id)

    if usuario_actual.es_admin:
        Formulario = AdminUsuarioForm
    else: # Si es ayudante
        Formulario = AyudanteUsuarioForm

    if request.method == 'POST':
        form = Formulario(request.POST, request.FILES, instance=usuario_a_editar)
        if form.is_valid():
            form.save()
            messages.success(request, f'¡Perfil de {usuario_a_editar.nombre} actualizado con éxito!')
            return redirect('panel-admin:gestion_usuarios')
    else:
        form = Formulario(instance=usuario_a_editar)

    return render(request, 'editar_perfil.html', {'form': form, 'usuario': usuario_a_editar})

@solo_admin_required
def eliminar_usuario(request, usuario_id):
    if request.method == 'POST':
        usuario_a_eliminar = get_object_or_404(Usuario, id=usuario_id)
        
        if usuario_a_eliminar.id == request.session.get('usuario_id'):
            messages.error(request, 'No puedes eliminar tu propia cuenta de administrador.')
            return redirect('panel-admin:gestion_usuarios')

        usuario_a_eliminar.delete()
        messages.success(request, f'Usuario {usuario_a_eliminar.email} eliminado correctamente.')
    # Redirigir al directorio si la acción vino de allí, si no, a la gestión de usuarios
    if 'from_directorio' in request.POST:
        return redirect('directorio_miembros')
    else:
        return redirect('panel-admin:gestion_usuarios')

@solo_admin_required
def toggle_destacado_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    usuario.destacado = not usuario.destacado
    usuario.save()
    return redirect('directorio_miembros')

@solo_admin_required
def toggle_visibilidad_usuario(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    # Un admin solo puede ocultar un perfil, no hacerlo público.
    if usuario.perfil_publico:
        usuario.perfil_publico = False
        usuario.save()
        messages.success(request, f'El perfil de {usuario.nombre} ha sido ocultado del directorio.')
    # Si ya es privado, no se hace nada.
    return redirect('directorio_miembros')

@solo_admin_required
def gestion_reuniones(request):
    if request.method == 'POST':
        form = ReunionForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Evento creado con éxito!')
            return redirect('panel-admin:gestion_reuniones')
    else:
        form = ReunionForm()

    now = timezone.now()
    reuniones_base = Reunion.objects.prefetch_related('interesados', 'asistentes').all()

    total_reuniones = reuniones_base.count()
    total_proximas = reuniones_base.filter(fecha__gte=now).count()
    total_pasadas = reuniones_base.filter(fecha__lt=now).count()

    reuniones_qs = reuniones_base

    q = request.GET.get('q', '').strip()
    mes = request.GET.get('mes', '').strip()
    fecha = request.GET.get('fecha', '').strip()

    # Filtro por Mes (YYYY-MM)
    if mes:
        try:
            partes_mes = mes.split('-')
            if len(partes_mes) == 2:
                reuniones_qs = reuniones_qs.filter(fecha__year=int(partes_mes[0]), fecha__month=int(partes_mes[1]))
        except Exception:
            pass

    # Filtro por Fecha Exacta (YYYY-MM-DD)
    if fecha:
        try:
            reuniones_qs = reuniones_qs.filter(fecha__date=fecha)
        except Exception:
            pass

    # Búsqueda por Texto o ID (#1 o 1) o Nombre de Mes
    if q:
        MESES_ES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
        query_id = None
        if q.startswith('#') and q[1:].isdigit():
            query_id = int(q[1:])
        elif q.isdigit():
            query_id = int(q)

        filtro_query = Q(detalle__icontains=q) | Q(ubicacion__icontains=q) | Q(direccion__icontains=q) | Q(descripcion__icontains=q)
        if query_id is not None:
            filtro_query |= Q(id=query_id)
        if q.lower() in MESES_ES:
            filtro_query |= Q(fecha__month=MESES_ES[q.lower()])

        reuniones_qs = reuniones_qs.filter(filtro_query)

    estado = request.GET.get('estado', 'todas')
    if estado == 'proximas':
        reuniones = reuniones_qs.filter(fecha__gte=now).order_by('fecha')
    elif estado == 'pasadas':
        reuniones = reuniones_qs.filter(fecha__lt=now).order_by('-fecha')
    else:
        reuniones = reuniones_qs.order_by('-fecha')

    return render(request, 'panel_admin_reuniones.html', {
        'form': form,
        'reuniones': reuniones,
        'total_reuniones': total_reuniones,
        'total_proximas': total_proximas,
        'total_pasadas': total_pasadas,
        'filtro_estado': estado,
        'filtro_q': q,
        'filtro_mes': mes,
        'filtro_fecha': fecha,
        'now': now,
    })

@solo_admin_required
def editar_reunion(request, reunion_id):
    reunion = get_object_or_404(Reunion, id=reunion_id)
    if request.method == 'POST':
        form = ReunionForm(request.POST, request.FILES, instance=reunion)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Evento actualizado con éxito!')
            return redirect('panel-admin:gestion_reuniones')
    else:
        form = ReunionForm(instance=reunion)
    
    return render(request, 'panel_admin_reunion_editar.html', {'form': form, 'reunion': reunion})

@solo_admin_required
def eliminar_reunion(request, reunion_id):
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        reunion.delete()
        messages.success(request, 'Evento eliminado correctamente.')
    return redirect('panel-admin:gestion_reuniones')

@admin_required # Ayudante puede ver la lista de reuniones para tomar asistencia
def control_asistencia(request):
    """
    Página de control y acreditación de asistencia con métricas, buscador y accesos directos.
    """
    ahora = timezone.now()
    reuniones = Reunion.objects.all().prefetch_related('asistentes', 'interesados').order_by('-fecha')
    
    total_asistencias = sum(r.asistentes.count() for r in reuniones)
    total_eventos = reuniones.count()
    proximo_evento = Reunion.objects.filter(fecha__gte=ahora).order_by('fecha').first()
    promedio_asistencia = round(total_asistencias / total_eventos, 1) if total_eventos > 0 else 0

    return render(request, 'panel_admin_control_asistencia.html', {
        'reuniones': reuniones,
        'ahora': ahora,
        'total_eventos': total_eventos,
        'total_asistencias': total_asistencias,
        'proximo_evento': proximo_evento,
        'promedio_asistencia': promedio_asistencia,
    })

@admin_required # Ayudante puede registrar asistencia
def registrar_asistencia(request, reunion_id):
    """
    Página para que el admin escanee QR y registre asistencia.
    """
    reunion = get_object_or_404(Reunion, id=reunion_id)
    
    if request.method == 'POST' and 'manual_add' in request.POST:
        usuario_id = request.POST.get('usuario_id')
        if usuario_id:
            usuario_a_agregar = get_object_or_404(Usuario, id=usuario_id)
            
            if not reunion.asistentes.filter(id=usuario_a_agregar.id).exists():
                reunion.asistentes.add(usuario_a_agregar)
                usuario_a_agregar.cantidad_asistencias = F('cantidad_asistencias') + 1
                usuario_a_agregar.save()
                
                # Si se debe imprimir etiqueta, preparamos la URL para la redirección.
                if reunion.imprimir_etiqueta_al_asistir:
                    redirect_url = f"{reverse('panel-admin:registrar_asistencia', args=[reunion_id])}?print_user={usuario_a_agregar.id}"
                    return redirect(redirect_url)
                else:
                    messages.success(request, f'Asistencia de {usuario_a_agregar.nombre} registrada manualmente.')
            else:
                messages.warning(request, f'{usuario_a_agregar.nombre} ya estaba registrado como asistente.')

            return redirect('panel-admin:registrar_asistencia', reunion_id=reunion_id)

    asistentes = reunion.asistentes.all().order_by('nombre')
    # Obtenemos todos los usuarios que no están en la lista de asistentes
    usuarios_no_asistentes = Usuario.objects.exclude(id__in=asistentes.values_list('id', flat=True)).order_by('nombre')

    return render(request, 'panel_admin_asistencia.html', {
        'reunion': reunion,
        'asistentes': asistentes,
        'usuarios_no_asistentes': usuarios_no_asistentes,
    })

@admin_required # Ayudante puede quitar asistencia
def quitar_asistencia(request, reunion_id, usuario_id):
    """
    Elimina a un usuario de la lista de asistentes de un evento.
    """
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario_a_quitar = get_object_or_404(Usuario, id=usuario_id)

        if reunion.asistentes.filter(id=usuario_a_quitar.id).exists():
            reunion.asistentes.remove(usuario_a_quitar)
            # Decrementamos el contador de asistencias del usuario de forma segura
            if usuario_a_quitar.cantidad_asistencias > 0:
                usuario_a_quitar.cantidad_asistencias = F('cantidad_asistencias') - 1
                usuario_a_quitar.save()
            messages.success(request, f'Se ha quitado la asistencia de {usuario_a_quitar.nombre}.')
    
    return redirect('panel-admin:registrar_asistencia', reunion_id=reunion_id)

@privileged_user_required # Admin, Ayudante y Tótem pueden usar el QR para marcar asistencia
def marcar_asistencia_qr(request, reunion_id, usuario_id):
    """
    Endpoint API para marcar la asistencia de un usuario a un evento.
    """
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario = get_object_or_404(Usuario, id=usuario_id)

        if reunion.asistentes.filter(id=usuario.id).exists():
            # Si ya existe, devolvemos un error y no hacemos nada más.
            return JsonResponse({
                'status': 'error', 
                'message': f'{usuario.nombre} ya se encuentra registrado en este evento.',
                'aforo_info': {
                    'tiene_limite': reunion.tiene_aforo_limitado(),
                    'aforo_maximo': reunion.aforo_maximo,
                    'total_asistentes': reunion.asistentes.count(),
                    'porcentaje_aforo': reunion.porcentaje_aforo(),
                    'aforo_completo': reunion.aforo_completo(),
                    'cupos_disponibles': reunion.cupos_disponibles()
                }
            }, status=409)

        if reunion.aforo_completo():
            return JsonResponse({
                'status': 'aforo_completo',
                'message': f'¡Aforo Máximo Alcanzado! Capacidad máxima: {reunion.aforo_maximo} personas.',
                'aforo_info': {
                    'tiene_limite': True,
                    'aforo_maximo': reunion.aforo_maximo,
                    'total_asistentes': reunion.asistentes.count(),
                    'porcentaje_aforo': 100,
                    'aforo_completo': True,
                    'cupos_disponibles': 0
                }
            }, status=409)

        # Si no existe, procedemos a registrarlo.
        reunion.asistentes.add(usuario)
        usuario.cantidad_asistencias = F('cantidad_asistencias') + 1
        usuario.save()
        usuario.refresh_from_db()

        print_url = reverse('imprimir_etiqueta', args=[usuario.id]) if reunion.imprimir_etiqueta_al_asistir else None
        return JsonResponse({
            'status': 'ok', 
            'message': f'Asistencia de {usuario.nombre} registrada.',
            'asistente': { 'id': usuario.id, 'nombre': usuario.nombre, 'apellido': usuario.apellido, 'rubro': usuario.get_rubro_real_display or '', 'foto_url': usuario.foto.url if usuario.foto else '/static/img/persn.jpg' },
            'print_url': print_url,
            'aforo_info': {
                'tiene_limite': reunion.tiene_aforo_limitado(),
                'aforo_maximo': reunion.aforo_maximo,
                'total_asistentes': reunion.asistentes.count(),
                'porcentaje_aforo': reunion.porcentaje_aforo(),
                'aforo_completo': reunion.aforo_completo(),
                'cupos_disponibles': reunion.cupos_disponibles()
            }
        })
            
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@solo_admin_required
def gestion_interesados(request):
    now = timezone.now()
    reuniones_base = Reunion.objects.prefetch_related('interesados').all()

    total_reuniones = reuniones_base.count()
    total_proximas = reuniones_base.filter(fecha__gte=now).count()
    total_pasadas = reuniones_base.filter(fecha__lt=now).count()

    reuniones_qs = reuniones_base

    q = request.GET.get('q', '').strip()
    mes = request.GET.get('mes', '').strip()
    fecha = request.GET.get('fecha', '').strip()

    # Filtro por Mes (YYYY-MM)
    if mes:
        try:
            partes_mes = mes.split('-')
            if len(partes_mes) == 2:
                reuniones_qs = reuniones_qs.filter(fecha__year=int(partes_mes[0]), fecha__month=int(partes_mes[1]))
        except Exception:
            pass

    # Filtro por Fecha Exacta (YYYY-MM-DD)
    if fecha:
        try:
            reuniones_qs = reuniones_qs.filter(fecha__date=fecha)
        except Exception:
            pass

    # Búsqueda por Texto o ID (#1 o 1) o Nombre de Mes
    if q:
        MESES_ES = {'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6, 'julio': 7, 'agosto': 8, 'septiembre': 9, 'setiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12}
        query_id = None
        if q.startswith('#') and q[1:].isdigit():
            query_id = int(q[1:])
        elif q.isdigit():
            query_id = int(q)

        filtro_query = (
            Q(detalle__icontains=q) |
            Q(ubicacion__icontains=q) |
            Q(interesados__nombre__icontains=q) |
            Q(interesados__apellido__icontains=q) |
            Q(interesados__email__icontains=q) |
            Q(interesados__rut__icontains=q)
        )
        if query_id is not None:
            filtro_query |= Q(id=query_id)
        if q.lower() in MESES_ES:
            filtro_query |= Q(fecha__month=MESES_ES[q.lower()])

        reuniones_qs = reuniones_qs.filter(filtro_query).distinct()

    estado = request.GET.get('estado', 'todas')
    if estado == 'proximas':
        reuniones = reuniones_qs.filter(fecha__gte=now).order_by('fecha')
    elif estado == 'pasadas':
        reuniones = reuniones_qs.filter(fecha__lt=now).order_by('-fecha')
    else:
        reuniones = reuniones_qs.order_by('-fecha')

    total_interesados = sum(r.interesados.count() for r in reuniones)

    return render(request, 'panel_admin_interesados.html', {
        'reuniones': reuniones,
        'total_interesados': total_interesados,
        'total_reuniones': total_reuniones,
        'total_proximas': total_proximas,
        'total_pasadas': total_pasadas,
        'filtro_estado': estado,
        'filtro_q': q,
        'filtro_mes': mes,
        'filtro_fecha': fecha,
        'now': now,
    })

@solo_admin_required
def gestion_encuestas(request):
    if request.method == 'POST':
        form = EncuestaForm(request.POST, request.FILES)
        if form.is_valid():
            encuesta = form.save()
            messages.success(request, f"¡Encuesta '{encuesta.titulo}' configurada y creada con éxito!")
            return redirect('panel-admin:gestion_encuestas')
    else:
        form = EncuestaForm()

    encuestas = Encuesta.objects.select_related('reunion').prefetch_related('respuestas').all().order_by('-creada_en')
    
    # Métricas y gráficas precargadas del dashboard general
    total_encuestas = encuestas.count()
    total_respuestas = RespuestaEncuesta.objects.count()
    
    promedio_general = RespuestaEncuesta.objects.aggregate(avg=Avg('puntuacion'))['avg'] or 0
    promedio_general = round(promedio_general, 1)

    # Distribución de estrellas global [1, 2, 3, 4, 5]
    distribucion_estrellas = [
        RespuestaEncuesta.objects.filter(puntuacion=i).count() for i in range(1, 6)
    ]
    modalidad_finalizar_count = encuestas.filter(modalidad_entrega='al_finalizar').count()
    modalidad_correo_count = encuestas.filter(modalidad_entrega='correo').count()

    positivas = sum(distribucion_estrellas[3:]) # 4 y 5 estrellas
    tasa_satisfaccion = round((positivas / total_respuestas * 100), 1) if total_respuestas > 0 else 0

    return render(request, 'panel_admin_encuestas.html', {
        'form': form,
        'encuestas': encuestas,
        'total_encuestas': total_encuestas,
        'total_respuestas': total_respuestas,
        'promedio_general': promedio_general,
        'tasa_satisfaccion': tasa_satisfaccion,
        'distribucion_estrellas': distribucion_estrellas,
        'modalidad_finalizar_count': modalidad_finalizar_count,
        'modalidad_correo_count': modalidad_correo_count,
    })

@solo_admin_required
def editar_encuesta(request, encuesta_id):
    encuesta = get_object_or_404(Encuesta, id=encuesta_id)
    if request.method == 'POST':
        form = EncuestaForm(request.POST, request.FILES, instance=encuesta)
        if form.is_valid():
            form.save()
            messages.success(request, f"¡Encuesta '{encuesta.titulo}' actualizada correctamente!")
            return redirect('panel-admin:gestion_encuestas')
    else:
        form = EncuestaForm(instance=encuesta)

    return render(request, 'panel_admin_editar_encuesta.html', {
        'form': form,
        'encuesta': encuesta
    })

@solo_admin_required
def toggle_activa_encuesta(request, encuesta_id):
    if request.method == 'POST':
        encuesta = get_object_or_404(Encuesta, id=encuesta_id)
        encuesta.activa = not encuesta.activa
        encuesta.save()
        estado_txt = "activada" if encuesta.activa else "desactivada"
        messages.success(request, f"La encuesta '{encuesta.titulo}' ha sido {estado_txt}.")
    return redirect('panel-admin:gestion_encuestas')

@solo_admin_required
def enviar_encuesta_correo_asistentes(request, encuesta_id):
    if request.method == 'POST':
        encuesta = get_object_or_404(Encuesta, id=encuesta_id)
        reunion = encuesta.reunion
        asistentes = reunion.asistentes.all()

        if not asistentes.exists():
            messages.warning(request, f"La reunión '{reunion.detalle}' no tiene asistentes acreditados para enviar la encuesta.")
            return redirect('panel-admin:gestion_encuestas')

        from django.core.mail import send_mail
        from django.conf import settings

        if encuesta.tipo_encuesta == 'externa':
            if encuesta.archivo_encuesta:
                url_encuesta = request.build_absolute_uri(encuesta.archivo_encuesta.url)
            elif encuesta.url_externa:
                url_encuesta = encuesta.url_externa
            else:
                url_encuesta = request.build_absolute_uri(reverse('responder_encuesta_directa', args=[reunion.id]))
            asunto_base = f"Encuesta de Satisfacción: {reunion.detalle}"
            texto_llamado = "Te invitamos a responder o revisar la encuesta oficial provista por los organizadores del evento:"
        else:
            url_encuesta = request.build_absolute_uri(reverse('responder_encuesta_directa', args=[reunion.id]))
            asunto_base = f"Tu opinión es importante: Encuesta de Satisfacción - {reunion.detalle}"
            texto_llamado = "Para seguir mejorando y ofrecerte actividades de mayor calidad, te invitamos a responder nuestra breve encuesta de satisfacción:"

        enviados = 0

        for a in asistentes:
            if a.email:
                asunto = asunto_base
                mensaje = (
                    f"Hola {a.nombre},\n\n"
                    f"Agradecemos enormemente tu participación en '{reunion.detalle}'.\n"
                    f"{texto_llamado}\n\n"
                    f"👉 Responder aquí: {url_encuesta}\n\n"
                    f"Solo te tomará un par de minutos.\n\n"
                    f"Atentamente,\n"
                    f"Equipo INACAP"
                )
                try:
                    send_mail(
                        asunto,
                        mensaje,
                        getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@inacap.cl'),
                        [a.email],
                        fail_silently=True
                    )
                    enviados += 1
                except Exception:
                    pass

        encuesta.enviada_por_correo = True
        encuesta.fecha_envio_correo = timezone.now()
        encuesta.save()

        messages.success(request, f"¡Encuesta enviada exitosamente por correo a {enviados} asistente(s) de '{reunion.detalle}'!")
    return redirect('panel-admin:gestion_encuestas')

@solo_admin_required
def ver_respuestas_encuesta(request, encuesta_id):
    encuesta = get_object_or_404(Encuesta.objects.select_related('reunion'), id=encuesta_id)
    respuestas_qs = encuesta.respuestas.select_related('usuario').all().order_by('-fecha_respuesta')
    
    filtro_estrellas = request.GET.get('estrellas')
    if filtro_estrellas and filtro_estrellas.isdigit():
        respuestas = respuestas_qs.filter(puntuacion=int(filtro_estrellas))
    else:
        respuestas = respuestas_qs

    total_respuestas = respuestas_qs.count()
    promedio = respuestas_qs.aggregate(avg=Avg('puntuacion'))['avg'] or 0
    promedio = round(promedio, 1)

    conteos_estrellas = [respuestas_qs.filter(puntuacion=i).count() for i in range(1, 6)]
    porcentajes_estrellas = [
        round((c / total_respuestas * 100), 1) if total_respuestas > 0 else 0
        for c in conteos_estrellas
    ]

    total_asistentes = encuesta.reunion.asistentes.count()
    tasa_respuesta = round((total_respuestas / total_asistentes * 100), 1) if total_asistentes > 0 else 0
    positivas = sum(conteos_estrellas[3:]) # 4 y 5 estrellas
    tasa_positiva = round((positivas / total_respuestas * 100), 1) if total_respuestas > 0 else 0
    total_comentarios = respuestas_qs.exclude(comentarios__isnull=True).exclude(comentarios__exact='').count()

    url_publica = request.build_absolute_uri(reverse('responder_encuesta_directa', args=[encuesta.reunion.id]))

    return render(request, 'panel_admin_ver_respuestas.html', {
        'encuesta': encuesta,
        'respuestas': respuestas,
        'total_respuestas': total_respuestas,
        'total_asistentes': total_asistentes,
        'tasa_respuesta': tasa_respuesta,
        'promedio': promedio,
        'conteos_estrellas': conteos_estrellas,
        'porcentajes_estrellas': porcentajes_estrellas,
        'tasa_positiva': tasa_positiva,
        'total_comentarios': total_comentarios,
        'filtro_estrellas': filtro_estrellas,
        'url_publica': url_publica,
    })

@solo_admin_required
def eliminar_encuesta(request, encuesta_id):
    if request.method == 'POST':
        encuesta = get_object_or_404(Encuesta, id=encuesta_id)
        titulo = encuesta.titulo
        encuesta.delete()
        messages.success(request, f"La encuesta '{titulo}' ha sido eliminada correctamente.")
    return redirect('panel-admin:gestion_encuestas')

@solo_admin_required
def toggle_destacado_respuesta(request, respuesta_id):
    if request.method == 'POST':
        respuesta = get_object_or_404(RespuestaEncuesta, id=respuesta_id)
        respuesta.destacado = not respuesta.destacado
        respuesta.save()
        messages.success(request, 'El estado de destacado del testimonio ha sido actualizado.')
        return redirect('panel-admin:ver_respuestas_encuesta', encuesta_id=respuesta.encuesta.id)
    return redirect('panel-admin:gestion_encuestas')

def responder_encuesta_publica(request, reunion_id):
    reunion = get_object_or_404(Reunion, id=reunion_id)
    if not hasattr(reunion, 'encuesta') or not reunion.encuesta.activa:
        return render(request, 'encuesta_no_disponible.html', {'reunion': reunion})

    encuesta = reunion.encuesta

    # Si es encuesta externa de otra entidad (Archivo subido o Enlace)
    if encuesta.tipo_encuesta == 'externa':
        if encuesta.url_externa:
            return redirect(encuesta.url_externa)
        elif encuesta.archivo_encuesta:
            return redirect(encuesta.archivo_encuesta.url)

    usuario_id = request.session.get('usuario_id')
    usuario_actual = Usuario.objects.filter(id=usuario_id).first() if usuario_id else None

    ya_respondio = False
    if usuario_actual:
        ya_respondio = encuesta.respuestas.filter(usuario=usuario_actual).exists()

    if request.method == 'POST':
        puntuacion = request.POST.get('puntuacion')
        comentarios = request.POST.get('comentarios', '').strip()
        es_anonimo = request.POST.get('es_anonimo') == 'on'

        # Identificación del usuario si no está logueado
        if not usuario_actual:
            identificador = request.POST.get('identificador', '').strip()
            from usuario.forms import validate_rut
            _, rut_limpio = validate_rut(identificador)
            usuario_candidato = Usuario.objects.filter(Q(rut=rut_limpio) | Q(email__iexact=identificador)).first() if identificador else None
            
            if usuario_candidato:
                usuario_actual = usuario_candidato
            else:
                nombre_inv = request.POST.get('nombre_invitado', '').strip() or 'Participante'
                email_inv = request.POST.get('email_invitado', '').strip()
                import uuid
                rut_temp = f"ENC-{uuid.uuid4().hex[:8].upper()}"
                usuario_actual = Usuario.objects.create(
                    rut=rut_temp,
                    nombre=nombre_inv,
                    apellido='',
                    email=email_inv or f"anonimo_{uuid.uuid4().hex[:6]}@inacap.cl",
                    rubro='externo',
                    institucion_empresa='Participante Evento'
                )

        if not puntuacion or not puntuacion.isdigit():
            messages.error(request, "Por favor selecciona una calificación con estrellas (de 1 a 5).")
        elif usuario_actual and encuesta.respuestas.filter(usuario=usuario_actual).exists():
            messages.warning(request, "Ya has registrado tu respuesta para esta encuesta. ¡Muchas gracias por tu opinión!")
            ya_respondio = True
        else:
            puntos = max(1, min(5, int(puntuacion)))
            RespuestaEncuesta.objects.create(
                encuesta=encuesta,
                usuario=usuario_actual,
                puntuacion=puntos,
                comentarios=comentarios,
                es_anonimo=es_anonimo
            )
            return render(request, 'encuesta_agradecimiento.html', {
                'reunion': reunion,
                'encuesta': encuesta,
                'puntuacion': puntos
            })

    return render(request, 'encuesta_publica.html', {
        'reunion': reunion,
        'encuesta': encuesta,
        'usuario_actual': usuario_actual,
        'ya_respondio': ya_respondio
    })

@admin_required # Ayudante puede ver y responder tickets
def gestion_soporte(request):
    tickets = SoporteTicket.objects.all().order_by('-fecha_creacion')
    return render(request, 'panel_admin_soporte.html', {'tickets': tickets})

@admin_required # Ayudante puede ver y responder tickets
def ver_ticket_soporte(request, ticket_id):
    ticket = get_object_or_404(SoporteTicket, id=ticket_id)
    admin_usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))

    if request.method == 'POST':
        if 'actualizar_estado' in request.POST:
            estado_form = SoporteTicketAdminForm(request.POST, instance=ticket)
            if estado_form.is_valid():
                estado_form.save()
                messages.success(request, 'El estado del ticket ha sido actualizado.')
                return redirect('panel-admin:ver_ticket_soporte', ticket_id=ticket.id)
        
        if 'enviar_respuesta' in request.POST:
            respuesta_form = TicketRespuestaForm(request.POST, request.FILES)
            if respuesta_form.is_valid():
                respuesta = respuesta_form.save(commit=False)
                respuesta.ticket = ticket
                respuesta.usuario = admin_usuario
                respuesta.save()
                messages.success(request, 'Tu respuesta ha sido enviada.')
                return redirect('panel-admin:ver_ticket_soporte', ticket_id=ticket.id)

    estado_form = SoporteTicketAdminForm(instance=ticket)
    respuesta_form = TicketRespuestaForm()
    
    contexto = {
        'ticket': ticket,
        'estado_form': estado_form,
        'respuesta_form': respuesta_form,
        'admin_usuario': admin_usuario,
    }
    return render(request, 'panel_admin_ver_ticket.html', contexto)

@totem_required
def totem_seleccionar_reunion(request):
    """
    Vista para que el usuario Tótem seleccione la reunión que va a gestionar.
    """
    reuniones_proximas = Reunion.objects.filter(fecha__gte=timezone.now()).order_by('fecha')
    contexto = {
        'reuniones': reuniones_proximas,
        'usuario': get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    }
    return render(request, 'totem_seleccionar_reunion.html', contexto)

@totem_required
def totem_escaner(request, reunion_id):
    """
    Vista de escaneo para el Tótem, bloqueada y a pantalla completa.
    """
    reunion = get_object_or_404(Reunion, id=reunion_id)
    # Pasamos el token CSRF explícitamente para que esté disponible en el JavaScript
    return render(request, 'totem_escaner.html', {'reunion': reunion})

@totem_required
def totem_verify_exit(request):
    """
    Endpoint API para verificar la contraseña del usuario Tótem y permitir la salida.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            password = data.get('password')
            usuario_totem = get_object_or_404(Usuario, id=request.session.get('usuario_id'))

            # Usamos check_password para comparar la contraseña en texto plano con la hasheada en la BD
            if check_password(password, usuario_totem.password): 
                return JsonResponse({'status': 'ok'})
            else:
                return JsonResponse({'status': 'error', 'message': 'Contraseña incorrecta'}, status=401)
        except (json.JSONDecodeError, KeyError):
            return JsonResponse({'status': 'error', 'message': 'Petición inválida'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@admin_required # Ayudante puede ver estadísticas (con lógica interna para restringir)
def estadisticas_admin(request):
    """
    Muestra la página de estadísticas, permitiendo una vista general
    o una vista detallada por reunión.
    """
    reuniones_para_filtro = Reunion.objects.all().order_by('-fecha')
    reunion_seleccionada_id_str = request.GET.get('reunion_id', None)
    usuario_actual = get_object_or_404(Usuario, id=request.session.get('usuario_id'))

    rubros_dict = _flatten_choices(RUBRO_CHOICES)

    contexto = {
        'reuniones_para_filtro': reuniones_para_filtro,
        'usuario_actual': usuario_actual,
        'reunion_seleccionada_id': None,
        'reunion_seleccionada': None,
        'total_usuarios': 0,
        'total_reuniones': 0,
        'total_asistencias': 0,
        'promedio_satisfaccion': 0,
        'labels_reuniones': [],
        'data_asistencia': [],
        'data_conversion': [],
        'labels_puntuacion': [],
        'data_puntuacion': [],
        'labels_rubro': [],
        'data_rubro': [],
    }

    reunion_seleccionada_id = None
    # Si es ayudante y no se especifica reunión, se fuerza la primera de la lista.
    if usuario_actual.es_ayudante and not reunion_seleccionada_id_str and reuniones_para_filtro:
        reunion_seleccionada_id = reuniones_para_filtro.first().id
    elif reunion_seleccionada_id_str and reunion_seleccionada_id_str.isdigit():
        reunion_seleccionada_id = int(reunion_seleccionada_id_str)

    contexto['reunion_seleccionada_id'] = reunion_seleccionada_id

    if reunion_seleccionada_id:
        reunion = get_object_or_404(Reunion, id=reunion_seleccionada_id)
        contexto['reunion_seleccionada'] = reunion
        asistentes = reunion.asistentes.all()
        interesados = reunion.interesados.all()
        contexto['total_asistencias'] = asistentes.count()
        contexto['data_conversion'] = [interesados.count(), asistentes.count()]

        if hasattr(reunion, 'encuesta'):
            respuestas = reunion.encuesta.respuestas.all()
            contexto['promedio_satisfaccion'] = respuestas.aggregate(avg=Avg('puntuacion'))['avg'] or 0
            puntuaciones = respuestas.values('puntuacion').annotate(cantidad=Count('id')).order_by('puntuacion')
            contexto['labels_puntuacion'] = [f"{p['puntuacion']} Estrellas" for p in puntuaciones]
            contexto['data_puntuacion'] = [p['cantidad'] for p in puntuaciones]

        top_rubros = asistentes.filter(rubro__isnull=False).exclude(rubro__exact='').values('rubro').annotate(cantidad=Count('id')).order_by('-cantidad')[:5]
        contexto['labels_rubro'] = [rubros_dict.get(r['rubro'], r['rubro']) for r in top_rubros]
        contexto['data_rubro'] = [r['cantidad'] for r in top_rubros]

    elif usuario_actual.es_admin:
        contexto['total_usuarios'] = Usuario.objects.count()
        contexto['total_reuniones'] = Reunion.objects.count()
        contexto['total_asistencias'] = Usuario.objects.aggregate(total=Sum('cantidad_asistencias'))['total'] or 0
        contexto['promedio_satisfaccion'] = RespuestaEncuesta.objects.aggregate(avg=Avg('puntuacion'))['avg'] or 0
        
        # Gráfico de Asistencia a últimas reuniones
        reuniones_recientes = Reunion.objects.annotate(num_asistentes=Count('asistentes')).order_by('-fecha')[:10][::-1] # Invertido para orden cronológico
        contexto['labels_reuniones'] = [r.detalle for r in reuniones_recientes]
        contexto['data_asistencia'] = [r.num_asistentes for r in reuniones_recientes]
        
        # Gráfico de Rubros (general)
        top_rubros = Usuario.objects.filter(rubro__isnull=False).exclude(rubro__exact='').values('rubro').annotate(cantidad=Count('id')).order_by('-cantidad')[:5]
        contexto['labels_rubro'] = [rubros_dict.get(r['rubro'], r['rubro']) for r in top_rubros]
        contexto['data_rubro'] = [r['cantidad'] for r in top_rubros]

    return render(request, 'panel_admin_estadisticas.html', contexto)

@admin_required # Ayudante puede exportar (con lógica interna para restringir)
def exportar_estadisticas_excel(request):
    """
    Exporta las estadísticas clave a un archivo Excel (.xlsx). Si se proporciona
    un `reunion_id`, exporta las estadísticas de ese evento. De lo contrario,
    exporta las estadísticas generales.
    """
    reunion_id = request.GET.get('reunion_id')
    usuario_actual = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    workbook = openpyxl.Workbook()
    bold_font = Font(bold=True, size=12)
    filename = "estadisticas_inacap.xlsx" # Actualizado el nombre del archivo

    if usuario_actual.es_ayudante and not reunion_id:
        messages.error(request, "No tienes permiso para exportar estadísticas generales.")
        return redirect('panel-admin:estadisticas_admin')

    rubros_dict = _flatten_choices(RUBRO_CHOICES)
    sedes_dict = _flatten_choices(SEDE_CHOICES)
    carreras_dict = _flatten_choices(CARRERA_CHOICES)

    if reunion_id and reunion_id.isdigit():
        reunion = get_object_or_404(Reunion, id=reunion_id)
        filename = f"estadisticas_{reunion.detalle.replace(' ', '_').lower()}_{reunion.fecha.strftime('%Y%m%d')}.xlsx"

        asistentes = reunion.asistentes.all()
        interesados = reunion.interesados.all()

        # Hoja de Resumen del Evento
        sheet_resumen = workbook.active
        sheet_resumen.title = "Resumen Evento"
        sheet_resumen['A1'] = f"Estadísticas del Evento: {reunion.detalle}"
        sheet_resumen['A1'].font = Font(bold=True, size=14)

        promedio_satisfaccion = 0
        if hasattr(reunion, 'encuesta'):
            promedio_satisfaccion = reunion.encuesta.respuestas.aggregate(avg=Avg('puntuacion'))['avg'] or 0

        resumen_data = [
            ("Interesados", interesados.count()),
            ("Asistentes", asistentes.count()),
            ("Satisfacción Promedio", f"{promedio_satisfaccion:.2f} / 5" if promedio_satisfaccion else "N/A")
        ]
        for i, (label, value) in enumerate(resumen_data, start=3):
            sheet_resumen[f'A{i}'] = label
            sheet_resumen[f'B{i}'] = value
            sheet_resumen[f'A{i}'].font = bold_font

        # Hoja de Lista de Asistentes
        sheet_asistentes = workbook.create_sheet(title="Lista de Asistentes")
        sheet_asistentes.append(['N°', 'RUT', 'Nombre', 'Apellido', 'Email', 'Rol / Perfil', 'Empresa u Organización'])
        for cell in sheet_asistentes[1]: cell.font = bold_font
        for idx, asistente in enumerate(asistentes.order_by('nombre', 'apellido'), start=1):
            rol_txt = asistente.get_rubro_real_display() if hasattr(asistente, 'get_rubro_real_display') and callable(asistente.get_rubro_real_display) else (asistente.rubro or 'General')
            empresa_txt = asistente.institucion_empresa or ('INACAP' if asistente.rubro != 'externo' else 'Particular')
            sheet_asistentes.append([
                idx,
                formatear_rut_excel(asistente.rut),
                asistente.nombre,
                asistente.apellido,
                asistente.email,
                rol_txt,
                empresa_txt
            ])

        # Hoja de Roles por Evento
        sheet_rubros_reunion = workbook.create_sheet(title="Roles por Evento")
        sheet_rubros_reunion.append(['Rol', 'Cantidad de Usuarios'])
        for cell in sheet_rubros_reunion[1]: cell.font = bold_font
        top_rubros_reunion = asistentes.filter(rubro__isnull=False).exclude(rubro__exact='').values('rubro').annotate(cantidad=Count('id')).order_by('-cantidad')
        for item in top_rubros_reunion:
            sheet_rubros_reunion.append([rubros_dict.get(item['rubro'], item['rubro']), item['cantidad']])

        # Hoja de Empresas por Evento
        sheet_empresas_reunion = workbook.create_sheet(title="Empresas por Evento")
        sheet_empresas_reunion.append(['Empresa / Organización', 'Cantidad de Usuarios'])
        for cell in sheet_empresas_reunion[1]: cell.font = bold_font
        top_empresas_reunion = asistentes.filter(institucion_empresa__isnull=False).exclude(institucion_empresa__exact='').values('institucion_empresa').annotate(cantidad=Count('id')).order_by('-cantidad')
        for item in top_empresas_reunion:
            sheet_empresas_reunion.append([item['institucion_empresa'], item['cantidad']])

    elif usuario_actual.es_admin:
        total_usuarios = Usuario.objects.count()
        total_reuniones = Reunion.objects.count()
        total_asistencias = Usuario.objects.aggregate(total=Sum('cantidad_asistencias'))['total'] or 0
        promedio_satisfaccion = RespuestaEncuesta.objects.aggregate(avg=Avg('puntuacion'))['avg'] or 0

        reuniones_asistencia = Reunion.objects.annotate(num_asistentes=Count('asistentes')).order_by('-fecha')
        distribucion_puntuacion = RespuestaEncuesta.objects.values('puntuacion').annotate(cantidad=Count('id')).order_by('puntuacion')
        usuarios_por_rubro_qs = Usuario.objects.filter(rubro__isnull=False).exclude(rubro__exact='').values('rubro').annotate(cantidad=Count('id')).order_by('-cantidad')
        sheet_resumen = workbook.active
        sheet_resumen.title = "Resumen General"
        sheet_resumen['A1'] = "Estadísticas Generales"
        sheet_resumen['A1'].font = Font(bold=True, size=14)
        
        resumen_data = [
            ("Usuarios Totales", total_usuarios),
            ("Eventos Totales", total_reuniones),
            ("Asistencias Totales", total_asistencias),
            ("Satisfacción Promedio", f"{promedio_satisfaccion:.2f} / 5" if promedio_satisfaccion else "N/A")
        ]
        for i, (label, value) in enumerate(resumen_data, start=3):
            sheet_resumen[f'A{i}'] = label
            sheet_resumen[f'B{i}'] = value
            sheet_resumen[f'A{i}'].font = bold_font

        # Hoja de Asistencia por Evento
        sheet_asistencia = workbook.create_sheet(title="Asistencia por Evento")
        sheet_asistencia.append(['Evento', 'Fecha', 'Nº de Asistentes'])
        for cell in sheet_asistencia[1]: cell.font = bold_font
        for reunion in reuniones_asistencia:
            sheet_asistencia.append([reunion.detalle, reunion.fecha.strftime('%d-%m-%Y'), reunion.num_asistentes])

        # Hoja de Roles (anteriormente Rubros)
        sheet_rubros = workbook.create_sheet(title="Usuarios por Rol")
        sheet_rubros.append(['Rol', 'Cantidad de Usuarios'])
        for cell in sheet_rubros[1]: cell.font = bold_font
        for item in usuarios_por_rubro_qs:
            nombre_rubro = rubros_dict.get(item['rubro'], item['rubro'])
            sheet_rubros.append([nombre_rubro, item['cantidad']])

        # Hoja de Satisfacción
        sheet_satisfaccion = workbook.create_sheet(title="Distribución de Satisfacción")
        sheet_satisfaccion.append(['Puntuación (Estrellas)', 'Cantidad de Votos'])
        for cell in sheet_satisfaccion[1]: cell.font = bold_font
        for item in distribucion_puntuacion:
            sheet_satisfaccion.append([f"{item['puntuacion']} Estrellas", item['cantidad']])

    # Ajustar ancho de columnas en todas las hojas
    for sheet in workbook.worksheets:
        for col in sheet.columns:
            max_length = 0
            column = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except: pass
            adjusted_width = (max_length + 2)
            sheet.column_dimensions[column].width = adjusted_width

    # 3. Preparar la respuesta HTTP
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)

    return response

@admin_required
def ruleta_ganador(request):
    """
    Vista para la ruleta de sorteo de ganadores.
    """
    reuniones = Reunion.objects.annotate(
        num_asistentes=Count('asistentes'),
        num_interesados=Count('interesados')
    ).order_by('-fecha')
    ganadores_recientes = GanadorSorteo.objects.select_related('ganador').all()[:15]

    contexto = {
        'reuniones': reuniones,
        'ganadores_recientes': ganadores_recientes,
    }
    return render(request, 'panel_admin_ruleta.html', contexto)

@admin_required
def obtener_participantes_ruleta(request):
    """
    Endpoint API para obtener los participantes para la ruleta.
    """
    reunion_id = request.GET.get('reunion_id')
    participantes_qs = None

    if not reunion_id:
        return JsonResponse({'error': 'No se especificó un grupo de participantes.'}, status=400)

    if reunion_id == 'todos':
        participantes_qs = Usuario.objects.filter(es_admin=False, es_ayudante=False, es_totem=False)
    elif reunion_id.isdigit():
        reunion = get_object_or_404(Reunion, id=reunion_id)
        participantes_qs = reunion.asistentes.all()
        # Si no hay asistentes en check-in, cargar los interesados
        if not participantes_qs.exists() and reunion.interesados.exists():
            participantes_qs = reunion.interesados.all()
    
    if participantes_qs is None:
        return JsonResponse({'participantes': []})

    # Preparamos los datos para la ruleta serializables en JSON
    participantes_data = []
    for p in participantes_qs:
        nombre_corto = p.nombre.split(' ')[0] if p.nombre else "Participante"
        if len(nombre_corto) > 12:
            nombre_corto = nombre_corto[:11] + '.'

        rubro_display = "General"
        if hasattr(p, 'get_rubro_real_display') and callable(p.get_rubro_real_display):
            rubro_display = p.get_rubro_real_display()
        elif p.rubro:
            rubro_display = str(p.rubro)

        foto_url = p.foto.url if p.foto else '/static/img/persn.jpg'

        participantes_data.append({
            'id': p.id,
            'nombre_completo': f"{p.nombre} {p.apellido}",
            'nombre_corto': nombre_corto,
            'rut_fmt': p.rut_formateado() if hasattr(p, 'rut_formateado') else p.rut,
            'rubro': rubro_display,
            'foto_url': foto_url
        })

    return JsonResponse({'participantes': participantes_data})

@solo_admin_required
@admin_required
def registrar_ganador_sorteo(request):
    """
    Endpoint API para guardar el ganador de un sorteo en la base de datos y retornar datos completos.
    """
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            ganador_id = data.get('ganador_id')
            fuente_id = data.get('fuente_id')
            ganador = get_object_or_404(Usuario, id=ganador_id)
            
            if fuente_id == 'todos':
                fuente_texto = "Todos los Usuarios Registrados"
            elif str(fuente_id).isdigit():
                reunion = get_object_or_404(Reunion, id=fuente_id)
                fuente_texto = f"Evento: {reunion.detalle}"
            else:
                fuente_texto = "Sorteo General"
            
            registro = GanadorSorteo.objects.create(ganador=ganador, fuente_participantes=fuente_texto)
            
            rubro_str = "General"
            if hasattr(ganador, 'get_rubro_real_display') and callable(ganador.get_rubro_real_display):
                rubro_str = ganador.get_rubro_real_display()
            elif ganador.rubro:
                rubro_str = str(ganador.rubro)

            foto_url = ganador.foto.url if ganador.foto else '/static/img/persn.jpg'

            return JsonResponse({
                'status': 'ok',
                'message': 'Ganador registrado con éxito.',
                'ganador': {
                    'nombre_completo': f"{ganador.nombre} {ganador.apellido}",
                    'fuente': fuente_texto,
                    'rubro': rubro_str,
                    'foto_url': foto_url,
                    'fecha': registro.fecha_sorteo.strftime('%d/%m/%Y'),
                    'hora': registro.fecha_sorteo.strftime('%H:%M hrs')
                }
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error al registrar ganador: {str(e)}'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

@solo_admin_required
@require_POST
def limpiar_historial_sorteos(request):
    """
    Elimina todos los registros del historial de ganadores.
    Restringido exclusivamente a administradores y solo por método POST.
    """
    GanadorSorteo.objects.all().delete()
    messages.success(request, 'El historial de ganadores ha sido limpiado.')
    return redirect('panel-admin:ruleta_ganador')

@admin_required
def gestion_plantillas_etiqueta(request):
    """
    Vista para crear y listar plantillas de etiquetas para los eventos INACAP.
    """
    if request.method == 'POST':
        form = EtiquetaPlantillaForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Plantilla de credencial/etiqueta creada con éxito!')
            return redirect('panel-admin:gestion_plantillas_etiqueta')
    else:
        form = EtiquetaPlantillaForm()

    plantillas = EtiquetaPlantilla.objects.all().order_by('nombre')
    elementos_display_map = dict(EtiquetaPlantillaForm.ELEMENTOS_CHOICES)
    for plantilla in plantillas:
        plantilla.orden_elementos_display = [elementos_display_map.get(e, e.replace('_', ' ')) for e in (plantilla.orden_elementos or [])]

    contexto = {
        'form': form,
        'plantillas': plantillas,
    }
    return render(request, 'panel_admin_plantillas_etiqueta.html', contexto)

@admin_required
def editar_plantilla_etiqueta(request, plantilla_id):
    """
    Vista para editar una plantilla de etiqueta existente.
    """
    plantilla = get_object_or_404(EtiquetaPlantilla, id=plantilla_id)
    if request.method == 'POST':
        form = EtiquetaPlantillaForm(request.POST, request.FILES, instance=plantilla)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Plantilla actualizada con éxito!')
            return redirect('panel-admin:gestion_plantillas_etiqueta')
    else:
        form = EtiquetaPlantillaForm(instance=plantilla)
    
    return render(request, 'panel_admin_plantilla_etiqueta_editar.html', {'form': form, 'plantilla': plantilla})

@admin_required
def eliminar_plantilla_etiqueta(request, plantilla_id):
    """
    Vista para eliminar una plantilla de etiqueta.
    """
    if request.method == 'POST':
        plantilla = get_object_or_404(EtiquetaPlantilla, id=plantilla_id)
        plantilla.delete()
        messages.success(request, 'Plantilla eliminada correctamente.')
    return redirect('panel-admin:gestion_plantillas_etiqueta')

@admin_required
def gestion_asistentes(request):
    """
    Página que lista las reuniones para seleccionar y ver sus asistentes.
    """
    reuniones = Reunion.objects.annotate(num_asistentes=Count('asistentes')).order_by('-fecha')
    total_acreditados = sum(r.num_asistentes for r in reuniones)
    return render(request, 'panel_admin_gestion_asistentes.html', {
        'reuniones': reuniones,
        'total_eventos': reuniones.count(),
        'total_acreditados': total_acreditados,
    })

@admin_required
def ver_asistentes_reunion(request, reunion_id):
    """
    Muestra una lista paginada de los asistentes de una reunión específica con búsqueda.
    """
    reunion = get_object_or_404(Reunion, id=reunion_id)
    asistentes_list = reunion.asistentes.all().order_by('nombre', 'apellido')

    query = request.GET.get('q', '')
    if query:
        asistentes_list = asistentes_list.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(rut__icontains=query) |
            Q(email__icontains=query) |
            Q(carrera__icontains=query) |
            Q(sede__icontains=query)
        )

    paginator = Paginator(asistentes_list, 20)
    page_number = request.GET.get('page')
    try:
        asistentes_page = paginator.page(page_number)
    except PageNotAnInteger:
        asistentes_page = paginator.page(1)
    except EmptyPage:
        asistentes_page = paginator.page(paginator.num_pages)

    return render(request, 'panel_admin_ver_asistentes.html', {
        'reunion': reunion,
        'asistentes': asistentes_page,
        'query': query,
    })

@admin_required
def exportar_asistentes_reunion_excel(request, reunion_id):
    """
    Exporta la lista de asistentes de una reunión específica a Excel con diseño institucional INACAP.
    Formato de RUT sin puntos pero con guion (ej: 12345678-9).
    """
    reunion = get_object_or_404(Reunion, id=reunion_id)
    query = request.GET.get('q', '').strip()

    asistentes = reunion.asistentes.all().order_by('apellido', 'nombre')
    if query:
        asistentes = asistentes.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(rut__icontains=query) |
            Q(email__icontains=query) |
            Q(institucion_empresa__icontains=query)
        )

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Asistentes"
    filename = f"asistentes_{reunion.detalle.replace(' ', '_').lower()}.xlsx"

    from openpyxl.styles import PatternFill, Alignment, Border, Side
    header_fill = PatternFill(start_color="B70420", end_color="B70420", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Arial", size=10, color="000000")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")
    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = ['N°', 'RUT', 'Nombre', 'Apellido', 'Email', 'Rol / Perfil', 'Empresa u Organización', 'Teléfono']
    sheet.append(headers)
    sheet.row_dimensions[1].height = 28

    for col_num, header_text in enumerate(headers, 1):
        cell = sheet.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    for idx, a in enumerate(asistentes, start=1):
        rol_txt = a.get_rubro_real_display() if hasattr(a, 'get_rubro_real_display') and callable(a.get_rubro_real_display) else (a.rubro or 'General')
        empresa_txt = a.institucion_empresa or ('INACAP' if a.rubro != 'externo' else 'Particular')
        rut_fmt = formatear_rut_excel(a.rut)

        sheet.append([
            idx,
            rut_fmt,
            a.nombre,
            a.apellido,
            a.email,
            rol_txt,
            empresa_txt,
            a.telefono or 'No registrado'
        ])

        row_idx = idx + 1
        sheet.row_dimensions[row_idx].height = 20
        for col_idx in range(1, len(headers) + 1):
            cell = sheet.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx in [1, 2, 8]:
                cell.alignment = center_align
            else:
                cell.alignment = left_align

    col_widths = {
        "A": 6,   # N°
        "B": 16,  # RUT
        "C": 18,  # Nombre
        "D": 18,  # Apellido
        "E": 28,  # Email
        "F": 18,  # Rol
        "G": 28,  # Empresa u Organización
        "H": 18,  # Teléfono
    }
    for col_letter, width in col_widths.items():
        sheet.column_dimensions[col_letter].width = width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    workbook.save(response)
    return response

def reunion_publica(request, reunion_id):
    """
    Vista pública para mostrar los detalles de un evento/reunión y permitir inscripción o consulta.
    """
    reunion = get_object_or_404(Reunion, id=reunion_id)
    ahora = timezone.now()
    es_pasada = reunion.fecha < ahora
    
    esta_inscrito = False
    if request.user.is_authenticated:
        esta_inscrito = reunion.interesados.filter(id=request.user.id).exists()
    
    total_interesados = reunion.interesados.count()
    
    encuesta = getattr(reunion, 'encuesta', None)
    if encuesta and not encuesta.activa:
        encuesta = None

    contexto = {
        'reunion': reunion,
        'es_pasada': es_pasada,
        'inscripciones_cerradas': es_pasada,
        'ya_interesado': esta_inscrito,
        'esta_inscrito': esta_inscrito,
        'total_interesados': total_interesados,
        'encuesta': encuesta,
    }
    return render(request, 'reunion_publica.html', contexto)

def inscribirse_reunion(request, reunion_id):
    """
    Flujo de inscripción ágil y sin fricción:
    1. Identificación por RUT.
    2. Si ya existe: saludo y confirmación en 1 clic.
    3. Si es nuevo: registro rápido de 4 datos sin contraseña.
    4. Muestra el código QR directamente en pantalla con opción de descarga.
    """
    from usuario.forms import validate_rut, RegistroRapidoForm
    from django.core.mail import EmailMessage
    
    reunion = get_object_or_404(Reunion, id=reunion_id)
    ahora = timezone.now()
    if reunion.fecha < ahora:
        return render(request, 'inscripcion_reunion.html', {
            'reunion': reunion,
            'paso': 'cerrado',
            'mensaje': 'Este evento ya ha finalizado y no se aceptan nuevas inscripciones.'
        })

    if request.method == 'POST':
        accion = request.POST.get('accion')

        # PASO 1: VALIDACIÓN DE RUT
        if accion == 'verificar_rut':
            rut_input = request.POST.get('rut', '').strip()
            es_valido, rut_o_error = validate_rut(rut_input)

            if not es_valido:
                return render(request, 'inscripcion_reunion.html', {
                    'reunion': reunion,
                    'paso': 'ingresar_rut',
                    'error': rut_o_error,
                    'rut_ingresado': rut_input
                })

            rut_limpio = rut_o_error
            usuario = Usuario.objects.filter(rut=rut_limpio).first()

            if usuario:
                # El usuario ya existe en la base de datos (o carga masiva)
                esta_inscrito = reunion.interesados.filter(id=usuario.id).exists()
                if esta_inscrito:
                    return render(request, 'inscripcion_reunion.html', {
                        'reunion': reunion,
                        'paso': 'ya_inscrito',
                        'usuario': usuario,
                    })
                else:
                    # Mostrar pantalla de confirmación en 1 clic
                    return render(request, 'inscripcion_reunion.html', {
                        'reunion': reunion,
                        'paso': 'confirmar_1clic',
                        'usuario': usuario,
                    })
            else:
                # Usuario nuevo: formulario rápido sin contraseña
                form_rapido = RegistroRapidoForm()
                return render(request, 'inscripcion_reunion.html', {
                    'reunion': reunion,
                    'paso': 'registro_rapido',
                    'rut': rut_limpio,
                    'form': form_rapido
                })

        # PASO 2A: CONFIRMACIÓN EN 1 CLIC (USUARIO EXISTENTE)
        elif accion == 'confirmar_1clic':
            usuario_id = request.POST.get('usuario_id')
            usuario = get_object_or_404(Usuario, id=usuario_id)

            reunion.interesados.add(usuario)

            # Enviar correo opcional con QR
            try:
                fecha_local = timezone.localtime(reunion.fecha)
                asunto = f'Inscripción Confirmada: {reunion.detalle} - INACAP'
                mensaje = f"""Hola {usuario.nombre} {usuario.apellido},

¡Tu inscripción ha sido confirmada con éxito!

Detalles del Evento:
----------------------------------------
Evento: {reunion.detalle}
Fecha: {fecha_local.strftime('%d/%m/%Y')}
Hora: {fecha_local.strftime('%H:%M')} hrs
Lugar: {reunion.ubicacion}{f' - {reunion.direccion}' if reunion.direccion else ''}

Ingreso al evento:
Presenta tu código QR adjunto en este correo o tu cédula de identidad en la entrada.

¡Te esperamos!
INACAP
"""
                email = EmailMessage(asunto, mensaje, settings.DEFAULT_FROM_EMAIL, [usuario.email])
                if usuario.qr_code and os.path.exists(usuario.qr_code.path):
                    email.attach_file(usuario.qr_code.path)
                email.send(fail_silently=True)
            except Exception as e:
                print(f"Error correo: {e}")

            return render(request, 'inscripcion_reunion.html', {
                'reunion': reunion,
                'paso': 'exito',
                'usuario': usuario
            })

        # PASO 2B: REGISTRO RÁPIDO (USUARIO NUEVO)
        elif accion == 'procesar_registro_rapido':
            rut = request.POST.get('rut')
            form = RegistroRapidoForm(request.POST)

            if form.is_valid():
                nuevo_usuario = form.save(rut=rut)
                nuevo_usuario.refresh_from_db()
                reunion.interesados.add(nuevo_usuario)

                # Enviar correo con QR
                try:
                    fecha_local = timezone.localtime(reunion.fecha)
                    asunto = f'Bienvenido e Inscripción Confirmada: {reunion.detalle} - INACAP'
                    mensaje = f"""Hola {nuevo_usuario.nombre} {nuevo_usuario.apellido},

¡Bienvenido a los eventos de INACAP! Tu inscripción se ha completado exitosamente.

Detalles del Evento:
----------------------------------------
Evento: {reunion.detalle}
Fecha: {fecha_local.strftime('%d/%m/%Y')}
Hora: {fecha_local.strftime('%H:%M')} hrs
Lugar: {reunion.ubicacion}{f' - {reunion.direccion}' if reunion.direccion else ''}

Adjuntamos tu credencial QR para acceder al evento.

¡Te esperamos!
INACAP
"""
                    email = EmailMessage(asunto, mensaje, settings.DEFAULT_FROM_EMAIL, [nuevo_usuario.email])
                    if nuevo_usuario.qr_code and os.path.exists(nuevo_usuario.qr_code.path):
                        email.attach_file(nuevo_usuario.qr_code.path)
                    email.send(fail_silently=True)
                except Exception as e:
                    print(f"Error correo: {e}")

                return render(request, 'inscripcion_reunion.html', {
                    'reunion': reunion,
                    'paso': 'exito',
                    'usuario': nuevo_usuario
                })
            else:
                return render(request, 'inscripcion_reunion.html', {
                    'reunion': reunion,
                    'paso': 'registro_rapido',
                    'rut': rut,
                    'form': form
                })

    # GET Inicial
    return render(request, 'inscripcion_reunion.html', {
        'reunion': reunion,
        'paso': 'ingresar_rut'
    })

# ASISTENTE DE CARGA MASIVA EN 3 PASOS (ESTILO EDUTEKA / INACAP)
import json
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from django.contrib.auth.hashers import make_password
from django.views.decorators.http import require_POST
from django.db import transaction
from usuario.forms import validate_rut

@admin_required
def carga_masiva_usuarios_view(request):
    """Renderiza el Asistente Interactivo de Carga Masiva de Usuarios en 3 pasos."""
    usuario_actual = Usuario.objects.filter(id=request.session.get('usuario_id')).first()
    context = {
        'usuario_actual': usuario_actual,
    }
    return render(request, 'panel_admin_carga_masiva_usuarios.html', context)

@admin_required
def descargar_plantilla_usuarios_excel(request):
    """Genera y descarga la plantilla oficial Excel (.xlsx) para la carga masiva."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Nomina_INACAP"

    # Estilos oficiales INACAP
    header_fill = PatternFill(start_color="B70420", end_color="B70420", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    sample_font = Font(name="Arial", size=10, italic=True, color="475569")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = ["RUT", "Nombre", "Apellido", "Email", "Empresa_u_Organizacion", "Telefono", "Rol"]
    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_num, header_text in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    ejemplos = [
        ["12.345.678-5", "Juan", "Pérez", "juan.perez@inacap.cl", "INACAP", "+56912345678", "Estudiante"],
        ["11.111.111-1", "María", "González", "maria.gonzalez@inacap.cl", "INACAP", "+56987654321", "Docente"],
        ["22.222.222-2", "Carlos", "Silva", "carlos.silva@empresa.cl", "Empresa XYZ SpA", "+56955544332", "Externo"],
    ]

    for row_idx, fila in enumerate(ejemplos, start=2):
        ws.append(fila)
        ws.row_dimensions[row_idx].height = 22
        for col_idx in range(1, len(headers) + 1):
            c = ws.cell(row=row_idx, column=col_idx)
            c.font = sample_font
            c.alignment = left_align
            c.border = thin_border

    col_widths = {"A": 18, "B": 18, "C": 18, "D": 32, "E": 22, "F": 32, "G": 18, "H": 15}
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="Plantilla_Carga_Masiva_INACAP.xlsx"'
    wb.save(response)
    return response

@admin_required
@require_POST
def api_analizar_carga_masiva_usuarios(request):
    """
    PASO 1 -> PASO 2:
    Analiza el archivo subido, valida datos en memoria y retorna filas para previsualización interactiva.
    """
    archivo = request.FILES.get('archivo')
    if not archivo:
        return JsonResponse({'error': 'No se seleccionó ningún archivo.'}, status=400)

    # Validaciones de seguridad en carga de archivo
    if not archivo.name.lower().endswith(('.xlsx', '.xls')):
        return JsonResponse({'error': 'Formato no permitido. Solo se aceptan archivos Excel (.xlsx).'}, status=400)

    # Límite de 10 MB para prevenir agotamiento de memoria
    if archivo.size > 10 * 1024 * 1024:
        return JsonResponse({'error': 'El archivo excede el tamaño máximo permitido de 10 MB.'}, status=400)

    try:
        wb = openpyxl.load_workbook(archivo, data_only=True)
        ws = wb.active

        headers = {}
        for col_idx, cell in enumerate(ws[1], start=1):
            val = str(cell.value or '').strip().lower()
            if 'rut' in val:
                headers['rut'] = col_idx
            elif 'nombre' in val and 'apellido' not in val:
                headers['nombre'] = col_idx
            elif 'apellido' in val:
                headers['apellido'] = col_idx
            elif 'email' in val or 'correo' in val:
                headers['email'] = col_idx
            elif 'empresa' in val or 'organizacion' in val or 'institucion' in val:
                headers['empresa'] = col_idx
            elif 'telefono' in val or 'celular' in val or 'fono' in val:
                headers['telefono'] = col_idx
            elif 'rol' in val or 'rubro' in val:
                headers['rol'] = col_idx

        if 'rut' not in headers or 'nombre' not in headers or 'email' not in headers:
            return JsonResponse({
                'error': 'El archivo Excel no contiene las columnas obligatorias: RUT, Nombre y Email.'
            }, status=400)

        filas_analizadas = []
        ruts_vistos = set()
        emails_vistos = set()

        for row_num in range(2, ws.max_row + 1):
            row = ws[row_num]
            rut_raw = str(row[headers['rut'] - 1].value or '').strip()
            nombre = str(row[headers['nombre'] - 1].value or '').strip() if 'nombre' in headers else ''
            apellido = str(row[headers['apellido'] - 1].value or '').strip() if 'apellido' in headers else ''
            email = str(row[headers['email'] - 1].value or '').strip().lower() if 'email' in headers else ''
            empresa = str(row[headers['empresa'] - 1].value or '').strip() if 'empresa' in headers else ''
            telefono = str(row[headers['telefono'] - 1].value or '').strip() if 'telefono' in headers else ''
            rol = str(row[headers['rol'] - 1].value or '').strip() if 'rol' in headers else ''

            if not rut_raw and not nombre and not email:
                continue # Fila vacía

            errores = []
            advertencias = []

            # Validación de RUT
            es_valido, rut_limpio = validate_rut(rut_raw)
            if not rut_raw:
                errores.append("RUT obligatorio ausente.")
            elif not es_valido:
                errores.append(f"RUT no válido: {rut_limpio}")
            else:
                if rut_limpio in ruts_vistos:
                    advertencias.append("RUT duplicado dentro del mismo archivo.")
                ruts_vistos.add(rut_limpio)

            # Validación de Nombre
            if not nombre:
                errores.append("Nombre obligatorio ausente.")

            # Validación de Email
            if not email:
                errores.append("Email obligatorio ausente.")
            elif '@' not in email or '.' not in email:
                errores.append("Formato de correo electrónico inválido.")
            else:
                if email in emails_vistos:
                    advertencias.append("Email duplicado en este archivo.")
                emails_vistos.add(email)

            # Comprobar si ya existe en la base de datos
            usuario_existente = None
            if es_valido:
                usuario_existente = Usuario.objects.filter(rut=rut_limpio).first()
            if not usuario_existente and email:
                usuario_existente = Usuario.objects.filter(email=email).first()

            if usuario_existente:
                advertencias.append(f"Usuario ya existe ({usuario_existente.nombre} {usuario_existente.apellido}) - Se actualizará información.")

            estado = 'error' if errores else ('advertencia' if advertencias else 'valido')

            filas_analizadas.append({
                'index': len(filas_analizadas) + 1,
                'fila_original': row_num,
                'rut': rut_raw,
                'rut_limpio': rut_limpio if es_valido else rut_raw,
                'nombre': nombre,
                'apellido': apellido,
                'email': email,
                'empresa': empresa or ('INACAP' if rol.lower() != 'externo' else 'Particular'),
                'telefono': telefono,
                'rol': rol or 'estudiante',
                'estado': estado,
                'errores': errores,
                'advertencias': advertencias,
                'existe_en_bd': bool(usuario_existente)
            })

        return JsonResponse({
            'success': True,
            'total_filas': len(filas_analizadas),
            'filas': filas_analizadas
        })

    except Exception as e:
        return JsonResponse({'error': f'Error al leer el archivo Excel: {str(e)}'}, status=500)

@admin_required
@require_POST
def api_procesar_carga_masiva_usuarios(request):
    """
    PASO 2 -> PASO 3:
    Guarda en base de datos de manera atómica todos los usuarios validados y confirmados.
    """
    try:
        data = json.loads(request.body.decode('utf-8'))
        filas = data.get('filas', [])
        politica_duplicados = data.get('politica_duplicados', 'actualizar')
    except Exception as e:
        return JsonResponse({'error': 'Datos JSON inválidos.'}, status=400)

    if not filas:
        return JsonResponse({'error': 'No hay filas para procesar.'}, status=400)

    creados_count = 0
    actualizados_count = 0
    omitidos_count = 0

    try:
        with transaction.atomic():
            for item in filas:
                rut_raw = str(item.get('rut', '')).strip()
                nombre = str(item.get('nombre', '')).strip()
                apellido = str(item.get('apellido', '')).strip()
                email = str(item.get('email', '')).strip().lower()
                empresa = str(item.get('empresa', '')).strip()
                telefono = str(item.get('telefono', '')).strip()
                rol = str(item.get('rol', '')).strip() or 'estudiante'
                institucion_empresa = empresa or ('INACAP' if rol.lower() != 'externo' else 'Particular')

                es_valido, rut_limpio = validate_rut(rut_raw)
                if not es_valido or not nombre or not email:
                    omitidos_count += 1
                    continue

                usuario = Usuario.objects.filter(rut=rut_limpio).first()
                if not usuario:
                    usuario = Usuario.objects.filter(email=email).first()

                if usuario:
                    if politica_duplicados == 'actualizar':
                        usuario.nombre = nombre
                        usuario.apellido = apellido
                        usuario.email = email
                        usuario.rut = rut_limpio
                        usuario.institucion_empresa = institucion_empresa
                        if telefono:
                            usuario.telefono = telefono
                        if rol:
                            usuario.rubro = rol.lower()
                        usuario.save()
                        actualizados_count += 1
                    else:
                        omitidos_count += 1
                else:
                    nuevo_user = Usuario(
                        rut=rut_limpio,
                        nombre=nombre,
                        apellido=apellido,
                        email=email,
                        telefono=telefono,
                        rubro=rol.lower(),
                        institucion_empresa=institucion_empresa,
                        es_admin=False,
                        es_ayudante=False
                    )
                    # Contraseña por defecto: RUT sin DV
                    password_default = rut_limpio[:-1] if len(rut_limpio) > 1 else 'Inacap2026!'
                    nuevo_user.password = make_password(password_default)
                    nuevo_user.save()
                    creados_count += 1

    except Exception as e:
        return JsonResponse({'error': f'Error durante la importación: {str(e)}'}, status=500)

    return JsonResponse({
        'success': True,
        'creados': creados_count,
        'actualizados': actualizados_count,
        'omitidos': omitidos_count,
        'total_procesados': creados_count + actualizados_count
    })

@admin_required
def exportar_usuarios_excel(request):
    """
    Exporta la nómina completa de usuarios a un archivo Excel (.xlsx) con diseño institucional INACAP.
    Soporta filtros aplicados (búsqueda, sede, carrera, rubro).
    """
    from datetime import datetime
    
    # Obtener filtros si vienen por GET
    query = request.GET.get('q', '').strip()
    rubro = request.GET.get('rubro', '').strip()
    sede = request.GET.get('sede', '').strip()
    carrera = request.GET.get('carrera', '').strip()

    usuarios = Usuario.objects.all()

    if query:
        usuarios = usuarios.filter(
            Q(nombre__icontains=query) |
            Q(apellido__icontains=query) |
            Q(email__icontains=query) |
            Q(rut__icontains=query) |
            Q(telefono__icontains=query)
        )
    if rubro:
        usuarios = usuarios.filter(rubro=rubro)
    if sede:
        usuarios = usuarios.filter(sede=sede)
    if carrera:
        usuarios = usuarios.filter(carrera=carrera)

    usuarios = usuarios.order_by('apellido', 'nombre')

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Usuarios_INACAP"

    # Estilos institucionales
    header_fill = PatternFill(start_color="B70420", end_color="B70420", fill_type="solid")
    header_font = Font(name="Arial", size=11, bold=True, color="FFFFFF")
    regular_font = Font(name="Arial", size=10, color="000000")
    center_align = Alignment(horizontal="center", vertical="center")
    left_align = Alignment(horizontal="left", vertical="center")

    thin_border = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    headers = [
        "N°", "RUT", "Nombre Completo", "Email", "Rol / Perfil", "Empresa u Organización", "Teléfono", "Asistencias", "Es Admin"
    ]
    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_num, header_text in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center_align
        cell.border = thin_border

    # Escribir filas de usuarios
    for idx, u in enumerate(usuarios, start=1):
        rol_txt = u.get_rubro_real_display() if hasattr(u, 'get_rubro_real_display') and callable(u.get_rubro_real_display) else (u.rubro or 'General')
        empresa_txt = u.institucion_empresa or ('INACAP' if u.rubro != 'externo' else 'Particular')
        row_data = [
            idx,
            formatear_rut_excel(u.rut),
            f"{u.nombre} {u.apellido}",
            u.email,
            rol_txt,
            empresa_txt,
            u.telefono or 'No registrado',
            u.cantidad_asistencias,
            "Sí" if u.es_admin else "No"
        ]
        ws.append(row_data)
        row_idx = idx + 1
        ws.row_dimensions[row_idx].height = 20
        
        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.font = regular_font
            cell.border = thin_border
            if col_idx in [1, 2, 8, 9]:
                cell.alignment = center_align
            else:
                cell.alignment = left_align

    # Anchos de columna
    col_widths = {
        "A": 6,   # N°
        "B": 16,  # RUT
        "C": 26,  # Nombre Completo
        "D": 32,  # Email
        "E": 20,  # Rol
        "F": 28,  # Empresa u Organización
        "G": 18,  # Teléfono
        "H": 14,  # Asistencias
        "I": 12,  # Es Admin
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    fecha_str = datetime.now().strftime("%Y%m%d_%H%M")
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="Nomina_Usuarios_INACAP_{fecha_str}.xlsx"'
    wb.save(response)
    return response

from django.core.mail import EmailMultiAlternatives

@solo_admin_required
def enviar_correo_masivo_interesados(request, reunion_id):
    """
    Envía un correo masivo institucional con la Firma Digital Oficial 60 Años INACAP.
    """
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        asunto = request.POST.get('asunto', '').strip()
        mensaje = request.POST.get('mensaje', '').strip()

        if not asunto or not mensaje:
            return JsonResponse({'status': 'error', 'message': 'El asunto y mensaje son obligatorios.'}, status=400)

        interesados_emails = list(reunion.interesados.exclude(email='').values_list('email', flat=True))
        if not interesados_emails:
            return JsonResponse({'status': 'error', 'message': 'No hay correos registrados para este evento.'}, status=400)

        usuario_actual = getattr(request, 'usuario_actual', None)
        if not usuario_actual:
            u_id = request.session.get('usuario_id')
            usuario_actual = Usuario.objects.filter(id=u_id).first()

        remitente_nombre = f"{usuario_actual.nombre} {usuario_actual.apellido}" if usuario_actual else "Dirección de Comunicaciones"
        remitente_cargo = "Administrador de Eventos y Encuentros" if (usuario_actual and usuario_actual.es_admin) else "Coordinador de Eventos"
        remitente_sede = usuario_actual.get_sede_real_display() if usuario_actual and usuario_actual.sede else "Sede Central"
        remitente_telefono = usuario_actual.telefono if (usuario_actual and usuario_actual.telefono) else "(56) 2 2429 8000"

        fecha_str = reunion.fecha.strftime('%d/%m/%Y a las %H:%M hrs')
        ubicacion_str = reunion.ubicacion or f'INACAP {remitente_sede}'
        base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000').rstrip('/')
        link_evento = f"{base_url}{reverse('panel-admin:reunion_publica', args=[reunion.id])}"
        logo_url = f"{base_url}/static/img/Logo_60anos.png"

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Verdana, Geneva, sans-serif; font-size: 10pt; color: #222222; margin: 0; padding: 0; background-color: #f8f9fa; }}
                .email-container {{ max-width: 620px; margin: 20px auto; background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; overflow: hidden; }}
                .header-bar {{ background: linear-gradient(135deg, #B70420, #8B0014); padding: 18px 24px; color: #ffffff; text-align: center; }}
                .content-body {{ padding: 26px 30px; line-height: 1.6; font-size: 10pt; color: #333333; }}
                .event-card {{ background-color: #f8fafc; border-left: 4px solid #B70420; padding: 14px 18px; margin: 18px 0; border-radius: 4px; }}
                .btn-cta {{ background-color: #B70420; color: #ffffff !important; padding: 11px 22px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 10pt; display: inline-block; }}
                .signature-container {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #e2e8f0; font-family: Verdana, Geneva, sans-serif; font-size: 10pt; color: #222222; line-height: 1.45; }}
                .footer-legal {{ background-color: #f1f5f9; padding: 12px 20px; text-align: center; font-size: 8.5pt; color: #64748b; border-top: 1px solid #e2e8f0; }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header-bar">
                    <h2 style="margin: 0; font-size: 16pt; font-weight: bold; font-family: Verdana, sans-serif;">INACAP</h2>
                    <p style="margin: 3px 0 0; opacity: 0.9; font-size: 9pt;">60 Anos Transformando Vidas</p>
                </div>
                
                <div class="content-body">
                    <h3 style="color: #111827; margin-top: 0; font-size: 12pt; border-bottom: 2px solid #fee2e2; padding-bottom: 8px;">
                        {reunion.detalle}
                    </h3>
                    
                    <div class="event-card">
                        <p style="margin: 0 0 6px 0;"><strong>Fecha y Hora:</strong> {fecha_str}</p>
                        <p style="margin: 0;"><strong>Ubicacion:</strong> {ubicacion_str}</p>
                    </div>
                    
                    <div style="white-space: pre-line; margin: 20px 0;">
{mensaje}
                    </div>
                    
                    <div style="text-align: center; margin: 26px 0;">
                        <a href="{link_evento}" class="btn-cta">
                            Ver Ficha y Credencial del Evento
                        </a>
                    </div>

                    <!-- FIRMA DIGITAL OFICIAL INACAP (60 ANOS) -->
                    <div class="signature-container">
                        <strong>{remitente_nombre}</strong><br>
                        {remitente_cargo}<br>
                        INACAP Sede {remitente_sede}<br>
                        {ubicacion_str}<br>
                        Telefono: {remitente_telefono}<br>
                        <a href="https://www.inacap.cl" target="_blank" style="color: #B70420; text-decoration: none;">www.inacap.cl</a><br><br>
                        <img src="{logo_url}" alt="INACAP | 60 ANOS" style="height: 48px; max-width: 220px; display: block; margin-top: 6px;">
                    </div>
                </div>

                <div class="footer-legal">
                    (c) 2026 INACAP | Direccion de Comunicaciones y Marketing. Has recibido este correo por estar pre-inscrito(a) en este evento institucional.
                </div>
            </div>
        </body>
        </html>
        """

        plain_text = f"""{reunion.detalle}
Fecha: {fecha_str}
Ubicacion: {ubicacion_str}

{mensaje}

Ver evento: {link_evento}

--
{remitente_nombre}
{remitente_cargo}
INACAP Sede {remitente_sede}
Telefono: {remitente_telefono}
www.inacap.cl"""

        try:
            from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'INACAP Eventos <eventos@inacap.cl>')
            email_msg = EmailMultiAlternatives(
                subject=asunto,
                body=plain_text,
                from_email=from_email,
                to=[from_email],
                bcc=interesados_emails
            )
            email_msg.attach_alternative(html_content, 'text/html')
            email_msg.send(fail_silently=False)

            return JsonResponse({
                'status': 'ok',
                'message': f'¡Correo masivo enviado exitosamente a {len(interesados_emails)} pre-inscrito(s)!',
                'total_enviados': len(interesados_emails)
            })
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Error al procesar envío: {str(e)}'}, status=500)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


def extraer_datos_carnet_o_qr(texto):
    """
    Extrae información completa desde el escaneo de Cédula de Identidad chilena
    (código de barras PDF417, MRZ o QR) o credencial de INACAP.
    Retorna: (user_id, rut_limpio, nombre, apellido)
    """
    if not texto:
        return None, None, '', ''
    
    texto = str(texto).strip()

    # 1. URL de credencial INACAP: .../etiqueta/15/ o .../usuario/15/
    url_id_match = re.search(r'/(?:etiqueta|perfil|imprimir-etiqueta|usuario)/(\d+)/?', texto)
    if url_id_match:
        return int(url_id_match.group(1)), None, '', ''

    # 2. Formato MRZ (Machine Readable Zone) en Cédula de Identidad chilena (3 líneas al reverso)
    if 'IDCHL' in texto or '<<' in texto:
        mrz_run = re.search(r'IDCHL([0-9]{7,8})([0-9Kk])', texto)
        mrz_names = re.search(r'([A-ZÁÉÍÓÚÑ]+)<([A-ZÁÉÍÓÚÑ]+)<<([A-ZÁÉÍÓÚÑ<]+)', texto)
        rut = None
        nombre = ''
        apellido = ''
        if mrz_run:
            rut = f"{mrz_run.group(1)}-{mrz_run.group(2).upper()}"
        if mrz_names:
            apellido = f"{mrz_names.group(1)} {mrz_names.group(2)}".strip().title()
            nombre = mrz_names.group(3).replace('<', ' ').strip().title()
        if rut:
            return None, rut, nombre, apellido

    # 3. Formato PDF417 chileno tradicional con campos delimitados (RUN=...,APELLIDO1,APELLIDO2,NOMBRES...)
    m_run = re.search(r'(?:RUN|RUT)[=:]\s*([0-9]{1,2}(?:\.[0-9]{3}){2}[-‐‑]?[0-9kK]|[0-9]{7,8}[-‐‑]?[0-9kK])', texto, re.IGNORECASE)
    if m_run:
        clean = re.sub(r'[^0-9K]', '', m_run.group(1).upper())
        rut = f"{clean[:-1]}-{clean[-1]}"
        nombre = ''
        apellido = ''
        parts = [p.strip() for p in re.split(r'[,;\t\r\n]+', texto) if p.strip()]
        if len(parts) >= 4 and any('RUN' in p.upper() for p in parts[:2]):
            run_idx = 0 if 'RUN' in parts[0].upper() else 1
            if len(parts) >= run_idx + 4:
                apellido = f"{parts[run_idx + 1]} {parts[run_idx + 2]}".title()
                nombre = parts[run_idx + 3].title()
        return None, rut, nombre, apellido

    # 4. Parámetro en URL: RUN=... o rut=... (Ej: Portal SIDIV del Registro Civil)
    m_param = re.search(r'[?&](?:RUN|RUT)=([0-9]{7,8}[-‐‑]?[0-9kK])', texto, re.IGNORECASE)
    if m_param:
        clean = re.sub(r'[^0-9K]', '', m_param.group(1).upper())
        return None, f"{clean[:-1]}-{clean[-1]}", '', ''

    # 5. Formato estándar de RUT con o sin puntos (ej: 12.345.678-9 o 12345678-9)
    m_rut = re.search(r'(?:\b|^)([0-9]{1,2}(?:\.[0-9]{3}){2}[-‐‑][0-9kK]|[0-9]{7,8}[-‐‑][0-9kK])(?:\b|$)', texto, re.IGNORECASE)
    if m_rut:
        clean = re.sub(r'[^0-9K]', '', m_rut.group(1).upper())
        return None, f"{clean[:-1]}-{clean[-1]}", '', ''

    # 6. ID numérico corto (ID de base de datos)
    if texto.isdigit() and len(texto) <= 6:
        return int(texto), None, '', ''

    # 7. Cadena numérica o alfanumérica de lector de carnet (ej: 123456789 o 012345678K)
    clean_digits = re.sub(r'[^0-9kK]', '', texto).upper()
    clean_digits = clean_digits.lstrip('0')
    if 8 <= len(clean_digits) <= 9:
        return None, f"{clean_digits[:-1]}-{clean_digits[-1]}", '', ''

    return None, None, '', ''

def extraer_rut_o_id(texto):
    uid, rut, _, _ = extraer_datos_carnet_o_qr(texto)
    return uid, rut

@privileged_user_required
def marcar_asistencia_escaner_universal(request, reunion_id):
    """
    Endpoint inteligente que procesa el escaneo tanto de Cédulas de Identidad chilenas como de Códigos QR.
    Acredita la asistencia, registra al participante si viene desde el carnet y entrega la URL de impresión de su etiqueta.
    """
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        
        try:
            data = json.loads(request.body)
            raw_input = data.get('codigo_o_rut', '') or data.get('scanned_text', '')
            usuario_id_param = data.get('usuario_id')
        except:
            raw_input = request.POST.get('codigo_o_rut', '') or request.POST.get('scanned_text', '')
            usuario_id_param = request.POST.get('usuario_id')

        usuario = None
        user_id, rut_limpio, carnet_nombre, carnet_apellido = (None, None, '', '')

        if usuario_id_param and str(usuario_id_param).isdigit():
            usuario = Usuario.objects.filter(id=int(usuario_id_param)).first()
        
        if not usuario and raw_input:
            user_id, rut_limpio, carnet_nombre, carnet_apellido = extraer_datos_carnet_o_qr(raw_input)
            if user_id:
                usuario = Usuario.objects.filter(id=user_id).first()
            elif rut_limpio:
                clean_digits = re.sub(r'[^0-9K]', '', rut_limpio.upper())
                usuario = Usuario.objects.filter(
                    Q(rut__iexact=rut_limpio) | 
                    Q(rut__icontains=clean_digits[:-1]) |
                    Q(rut__iexact=f"{clean_digits[:-1]}-{clean_digits[-1]}")
                ).first()

        if not usuario:
            rut_sugerido = rut_limpio or raw_input or ''
            return JsonResponse({
                'status': 'not_found',
                'message': f'La persona con RUT {rut_sugerido} no se encuentra registrada en el sistema.',
                'rut_sugerido': rut_sugerido,
                'nombre_sugerido': carnet_nombre,
                'apellido_sugerido': carnet_apellido,
                'registro_url': f'/registro/?rut={rut_sugerido}' if rut_sugerido else '/registro/'
            }, status=404)

        # Generar URL de impresión de etiqueta
        print_url = reverse('imprimir_etiqueta_reunion', args=[reunion.id, usuario.id])

        rubro_display = "Participante"
        if hasattr(usuario, 'get_rubro_real_display') and callable(usuario.get_rubro_real_display):
            rubro_display = usuario.get_rubro_real_display()
        elif usuario.rubro:
            rubro_display = str(usuario.rubro)

        sede_display = usuario.get_sede_real_display() if hasattr(usuario, 'get_sede_real_display') else str(usuario.sede or 'INACAP')
        carrera_display = usuario.get_carrera_real_display() if hasattr(usuario, 'get_carrera_real_display') else str(usuario.carrera or '')

        asistente_info = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'nombre_completo': f"{usuario.nombre} {usuario.apellido}",
            'rut': usuario.rut_formateado() if hasattr(usuario, 'rut_formateado') else usuario.rut,
            'rubro': rubro_display,
            'sede': sede_display,
            'carrera': carrera_display,
            'foto_url': usuario.foto.url if usuario.foto else '/static/img/persn.jpg',
            'asistencias': usuario.cantidad_asistencias
        }

        ya_estaba = reunion.asistentes.filter(id=usuario.id).exists()
        aforo_data = {
            'tiene_limite': reunion.tiene_aforo_limitado(),
            'aforo_maximo': reunion.aforo_maximo,
            'total_asistentes': reunion.asistentes.count(),
            'porcentaje_aforo': reunion.porcentaje_aforo(),
            'aforo_completo': reunion.aforo_completo(),
            'cupos_disponibles': reunion.cupos_disponibles()
        }

        if ya_estaba:
            return JsonResponse({
                'status': 'already_registered',
                'message': f'{usuario.nombre} {usuario.apellido} ya se encuentra acreditado(a) en este evento.',
                'asistente': asistente_info,
                'print_url': print_url,
                'debe_imprimir': True,
                'aforo_info': aforo_data
            }, status=200)

        # Si el aforo está completo y no se solicita sobrecupo expreso
        force_overcapacity = False
        if isinstance(data, dict):
            force_overcapacity = str(data.get('force_overcapacity', 'false')).lower() in ['true', '1', 'on']
        else:
            force_overcapacity = str(request.POST.get('force_overcapacity', 'false')).lower() in ['true', '1', 'on']

        if reunion.aforo_completo() and not force_overcapacity:
            return JsonResponse({
                'status': 'aforo_completo',
                'message': f'¡Aforo Máximo Alcanzado! La sala ha alcanzado su límite de {reunion.aforo_maximo} personas.',
                'aforo_maximo': reunion.aforo_maximo,
                'total_asistentes': reunion.asistentes.count(),
                'cupos_disponibles': 0,
                'asistente': asistente_info,
                'aforo_info': aforo_data
            }, status=409)

        # Registrar asistencia
        reunion.asistentes.add(usuario)
        usuario.cantidad_asistencias = F('cantidad_asistencias') + 1
        usuario.save(update_fields=['cantidad_asistencias'])
        usuario.refresh_from_db()
        asistente_info['asistencias'] = usuario.cantidad_asistencias

        # Aforo actualizado post-registro
        aforo_actualizado = {
            'tiene_limite': reunion.tiene_aforo_limitado(),
            'aforo_maximo': reunion.aforo_maximo,
            'total_asistentes': reunion.asistentes.count(),
            'porcentaje_aforo': reunion.porcentaje_aforo(),
            'aforo_completo': reunion.aforo_completo(),
            'cupos_disponibles': reunion.cupos_disponibles()
        }

        return JsonResponse({
            'status': 'ok',
            'message': f'¡Asistencia acreditada con éxito para {usuario.nombre} {usuario.apellido}!',
            'asistente': asistente_info,
            'print_url': print_url,
            'debe_imprimir': True,
            'aforo_info': aforo_actualizado
        }, status=200)

    return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)


@privileged_user_required
def crear_usuario_rapido_asistencia(request, reunion_id):
    """
    Endpoint para que el operador de asistencia cree un nuevo usuario rápidamente
    y lo acredite de inmediato en el evento actual.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Método no permitido'}, status=405)

    reunion = get_object_or_404(Reunion, id=reunion_id)

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except Exception:
            data = {}
    else:
        data = request.POST.copy()

    # Asegurar términos aceptados para alta administrativa rápida
    if isinstance(data, dict):
        data['acepta_terminos'] = True
    else:
        data = data.copy()
        data['acepta_terminos'] = True

    marcar_asistencia = str(data.get('marcar_asistencia', 'true')).lower() in ['true', '1', 'on']
    force_overcapacity = str(data.get('force_overcapacity', 'false')).lower() in ['true', '1', 'on']

    # Si se desea marcar asistencia y el aforo ya está lleno sin sobrecupo forzado
    if marcar_asistencia and reunion.aforo_completo() and not force_overcapacity:
        return JsonResponse({
            'status': 'aforo_completo',
            'message': f'No es posible acreditar automáticamente: ¡Aforo Máximo Alcanzado! ({reunion.aforo_maximo} personas).',
            'aforo_maximo': reunion.aforo_maximo,
            'total_asistentes': reunion.asistentes.count(),
            'cupos_disponibles': 0,
            'aforo_info': {
                'tiene_limite': True,
                'aforo_maximo': reunion.aforo_maximo,
                'total_asistentes': reunion.asistentes.count(),
                'porcentaje_aforo': 100,
                'aforo_completo': True,
                'cupos_disponibles': 0
            }
        }, status=409)

    form = UsuarioForm(data)
    if form.is_valid():
        usuario = form.save()

        # Acreditar asistencia al evento
        if marcar_asistencia:
            if not reunion.asistentes.filter(id=usuario.id).exists():
                reunion.asistentes.add(usuario)
                usuario.cantidad_asistencias = F('cantidad_asistencias') + 1
                usuario.save(update_fields=['cantidad_asistencias'])
                usuario.refresh_from_db()

        rubro_display = "Participante"
        if hasattr(usuario, 'get_rubro_real_display') and callable(usuario.get_rubro_real_display):
            rubro_display = usuario.get_rubro_real_display()
        elif usuario.rubro:
            rubro_display = str(usuario.rubro)

        sede_display = usuario.get_sede_real_display() if hasattr(usuario, 'get_sede_real_display') else str(usuario.sede or 'INACAP')
        carrera_display = usuario.get_carrera_real_display() if hasattr(usuario, 'get_carrera_real_display') else str(usuario.carrera or '')

        asistente_info = {
            'id': usuario.id,
            'nombre': usuario.nombre,
            'apellido': usuario.apellido,
            'nombre_completo': f"{usuario.nombre} {usuario.apellido}",
            'rut': usuario.rut_formateado() if hasattr(usuario, 'rut_formateado') else usuario.rut,
            'rubro': rubro_display,
            'sede': sede_display,
            'carrera': carrera_display,
            'foto_url': usuario.foto.url if usuario.foto else '/static/img/persn.jpg',
            'asistencias': usuario.cantidad_asistencias
        }

        print_url = reverse('imprimir_etiqueta_reunion', args=[reunion.id, usuario.id]) if reunion.imprimir_etiqueta_al_asistir else reverse('imprimir_etiqueta', args=[usuario.id])

        return JsonResponse({
            'status': 'ok',
            'message': f'¡Participante {usuario.nombre} {usuario.apellido} creado y acreditado con éxito!',
            'asistente': asistente_info,
            'print_url': print_url,
            'aforo_info': {
                'tiene_limite': reunion.tiene_aforo_limitado(),
                'aforo_maximo': reunion.aforo_maximo,
                'total_asistentes': reunion.asistentes.count(),
                'porcentaje_aforo': reunion.porcentaje_aforo(),
                'aforo_completo': reunion.aforo_completo(),
                'cupos_disponibles': reunion.cupos_disponibles()
            }
        })
    else:
        primer_error = None
        for campo, errores in form.errors.items():
            if errores:
                primer_error = f"{campo.capitalize()}: {errores[0]}"
                break
        return JsonResponse({
            'status': 'error',
            'errors': form.errors,
            'message': primer_error or 'Por favor verifica los campos ingresados.'
        }, status=400)

