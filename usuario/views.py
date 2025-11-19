from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .forms import UsuarioForm, EditarUsuarioForm, RespuestaEncuestaForm, CambiarPasswordForm, LoginForm
from .models import CARRERA_CHOICES, SEDE_CHOICES, Usuario, RUBRO_CHOICES
from paneladm.models import Reunion, Encuesta, RespuestaEncuesta, SoporteTicket, TicketRespuesta
from paneladm.forms import SoporteTicketForm, TicketRespuestaForm, ReunionForm
from django.contrib.auth.hashers import check_password
from django.utils import timezone
from django.db.models import Q
import random

def login_required(view_func):
    """
    Decorador personalizado para verificar que el usuario ha iniciado sesión.
    """
    def wrapper(request, *args, **kwargs):
        if 'usuario_id' not in request.session:
            messages.error(request, 'Debes iniciar sesión para acceder a esta página.')
            return redirect('login')
        return view_func(request, *args, **kwargs)
    return wrapper

def login(request):
    if 'usuario_id' in request.session:
        return redirect('inicio')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            try:
                usuario = Usuario.objects.get(email=email)
                if check_password(password, usuario.password):
                    request.session['usuario_id'] = usuario.id
                    messages.success(request, f'¡Bienvenido de vuelta, {usuario.nombre}!')
                    
                    # --- LÓGICA DE REDIRECCIÓN POR ROL ---
                    if usuario.es_totem:
                        return redirect('totem_seleccionar_reunion')
                    return redirect('inicio')
                else:
                    messages.error(request, 'La contraseña es incorrecta.')
            except Usuario.DoesNotExist:
                messages.error(request, 'No existe un usuario con ese correo electrónico.')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

def registro(request):
    if request.method == 'POST':
        form = UsuarioForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Usuario creado con éxito!')
            return redirect('login') # Si es válido, redirige a login
        # Si el formulario NO es válido, se renderiza la misma página
        # pero el 'form' ahora contiene los errores y los datos anteriores.
    else:
        form = UsuarioForm()
    return render(request, 'registro.html', {'form': form})


def perfil(request):
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return redirect('login')
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == 'POST' and 'responder_encuesta' in request.POST:
        form_respuesta = RespuestaEncuestaForm(request.POST)
        if form_respuesta.is_valid():
            encuesta_id = request.POST.get('encuesta_id')
            encuesta = get_object_or_404(Encuesta, id=encuesta_id)
            respuesta = form_respuesta.save(commit=False)
            respuesta.encuesta = encuesta
            respuesta.usuario = usuario
            respuesta.save()
            
            messages.success(request, '¡Gracias por tu respuesta!')
            return redirect('perfil')

    reuniones_asistidas = usuario.reuniones_asistidas.all()
    encuestas_pendientes = []
    for reunion in reuniones_asistidas:
        if hasattr(reunion, 'encuesta') and reunion.encuesta.activa and not reunion.encuesta.respuestas.filter(usuario=usuario).exists():
            encuestas_pendientes.append(reunion.encuesta)

    form_respuesta = RespuestaEncuestaForm()
    return render(request, 'perfil.html', {
        'usuario': usuario, 'encuestas_pendientes': encuestas_pendientes, 'form_resp_encuesta': form_respuesta
    })

def editar_perfil(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, request.FILES, instance=usuario)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Perfil actualizado con éxito!')
            return redirect('perfil')
    else:
        form = EditarUsuarioForm(instance=usuario)
    return render(request, 'editar_perfil.html', {'form': form, 'usuario': usuario})

def perfil_publico(request, usuario_id):
    usuario = get_object_or_404(Usuario, id=usuario_id)
    return render(request, 'perfil_publico.html', {'usuario': usuario})

def imprimir_etiqueta(request, usuario_id):
    """
    Vista que muestra solo la etiqueta de un usuario para impresión directa.
    """
    usuario = get_object_or_404(Usuario, id=usuario_id)
    return render(request, 'etiqueta_imprimir.html', {'usuario': usuario})

def inicio(request):
    usuario_id = request.session.get('usuario_id')
    usuario = None
    if usuario_id:
        try:
            usuario = Usuario.objects.get(id=usuario_id)
        except Usuario.DoesNotExist:
            pass

    reuniones_proximas = Reunion.objects.filter(fecha__gte=timezone.now()).order_by('fecha')
    now = timezone.now()
    for reunion in reuniones_proximas:
        delta = reunion.fecha.date() - now.date()
        reunion.dias_restantes = delta.days

    testimonios = RespuestaEncuesta.objects.filter(destacado=True).exclude(comentarios__exact='').order_by('-fecha_respuesta')
    total_usuarios = Usuario.objects.count()
    total_reuniones = Reunion.objects.count()
    contexto = {
        'usuario': usuario,
        'reuniones': reuniones_proximas,
        'testimonios': testimonios,
        'total_usuarios': total_usuarios,
        'total_reuniones': total_reuniones,
    }
    return render(request, 'inicio.html', contexto)

def registrar_interes(request, reunion_id):
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        messages.error(request, 'Debes iniciar sesión para mostrar interés en una reunión.')
        return redirect('login')
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario = get_object_or_404(Usuario, id=usuario_id)
        reunion.interesados.add(usuario)
        messages.success(request, f'¡Genial! Has mostrado interés en "{reunion.detalle}".')
    return redirect('inicio')


@login_required
def toggle_interes(request, reunion_id):
    """
    Registra o quita el interés de un usuario en una reunión (AJAX).
    """
    from django.http import JsonResponse
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))

        if usuario in reunion.asistentes.all():
            return JsonResponse({'status': 'error', 'message': 'Tu asistencia ya está confirmada.'}, status=400)

        if usuario in reunion.interesados.all():
            reunion.interesados.remove(usuario)
            return JsonResponse({'status': 'removed', 'message': 'Interés quitado.'})
        else:
            reunion.interesados.add(usuario)
            return JsonResponse({'status': 'added', 'message': 'Interés registrado.'})
    return JsonResponse({'status': 'error', 'message': 'Método no permitido.'}, status=405)

def panel_admin(request):
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return redirect('login')
    try:
        usuario_actual = Usuario.objects.get(id=usuario_id)
        if not usuario_actual.es_admin and not usuario_actual.es_ayudante:
            return redirect('inicio')
    except Usuario.DoesNotExist:
        return redirect('login')

    return render(request, 'panel_admin.html', {'usuario': usuario_actual})

@login_required
def configuracion(request):
    """
    Muestra la página de configuración del usuario.
    """
    usuario_id = request.session.get('usuario_id')
    usuario = get_object_or_404(Usuario, id=usuario_id)

    if request.method == 'POST':
        usuario.perfil_publico = request.POST.get('perfil_publico') == 'true'
        usuario.save(update_fields=['perfil_publico'])
        messages.success(request, 'Tu configuración de privacidad ha sido actualizada.')
        return redirect('configuracion')

    contexto = {
        'usuario': usuario
    }
    return render(request, 'configuracion.html', contexto)

@login_required
def cambiar_password(request):
    usuario_id = request.session.get('usuario_id')
    usuario = get_object_or_404(Usuario, id=usuario_id)
    if request.method == 'POST':
        form = CambiarPasswordForm(request.POST)
        if form.is_valid():
            password_actual = form.cleaned_data['password_actual']
            nueva_password = form.cleaned_data['nueva_password']

            if not check_password(password_actual, usuario.password):
                messages.error(request, 'La contraseña actual es incorrecta.')
            else:
                from django.contrib.auth.hashers import make_password
                usuario.password = nueva_password
                usuario.save()
                messages.success(request, '¡Contraseña actualizada con éxito!')
                return redirect('configuracion')
    else:
        form = CambiarPasswordForm()
    
    contexto = {
        'form': form,
        'usuario': usuario
    }
    return render(request, 'cambiar_password.html', contexto)

@login_required
def eliminar_cuenta(request):
    if request.method == 'POST':
        usuario_id = request.session.get('usuario_id')
        usuario = get_object_or_404(Usuario, id=usuario_id)
        usuario.delete()
        request.session.flush()
        messages.success(request, 'Tu cuenta ha sido eliminada permanentemente.')
        return redirect('inicio')
    return redirect('configuracion')

@login_required
def crear_ticket_soporte(request):
    usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    if request.method == 'POST':
        form = SoporteTicketForm(request.POST)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.usuario = usuario
            ticket.save()
            messages.success(request, 'Tu ticket de soporte ha sido enviado. Te responderemos pronto.')
            return redirect('ver_ticket_usuario', ticket_id=ticket.id)
    else:
        form = SoporteTicketForm()
    
    contexto = {
        'form': form,
        'usuario': usuario
    }
    return render(request, 'crear_ticket.html', contexto)

@login_required
def mis_tickets(request):
    usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    tickets = SoporteTicket.objects.filter(usuario=usuario).order_by('-fecha_creacion')
    return render(request, 'mis_tickets.html', {'usuario': usuario, 'tickets': tickets})

@login_required
def ver_ticket_usuario(request, ticket_id):
    usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))
    ticket = get_object_or_404(SoporteTicket, id=ticket_id, usuario=usuario) # Seguridad: solo el dueño puede ver

    if request.method == 'POST':
        respuesta_form = TicketRespuestaForm(request.POST, request.FILES)
        if respuesta_form.is_valid():
            respuesta = respuesta_form.save(commit=False)
            respuesta.ticket = ticket
            respuesta.usuario = usuario
            respuesta.save()
            messages.success(request, 'Tu respuesta ha sido enviada.')
            return redirect('ver_ticket_usuario', ticket_id=ticket.id)

    respuesta_form = TicketRespuestaForm()
    contexto = {
        'ticket': ticket,
        'respuesta_form': respuesta_form,
        'usuario': usuario,
    }
    return render(request, 'ver_ticket_usuario.html', contexto)

@login_required
def directorio_miembros(request):
    usuario_id = request.session.get('usuario_id')
    usuario_actual = get_object_or_404(Usuario, id=usuario_id) # El que está viendo la página

    query = request.GET.get('q', '')
    rubro_filter = request.GET.get('rubro', '') # Ahora es rol_filter
    sede_filter = request.GET.get('sede', '')
    carrera_filter = request.GET.get('carrera', '')

    # Los usuarios solo ven perfiles públicos. El admin ve todos.
    # Nota: `request.user_is_admin` no está definido en este contexto. Asumo que es una variable de contexto o middleware.
    # Para mayor seguridad, se debería verificar `usuario_actual.es_admin`.
    if usuario_actual.es_admin: # Asumiendo que request.user_is_admin es equivalente a usuario_actual.es_admin
        # El admin ve a todos los usuarios (no admins), ordenando por destacado y luego por visibilidad
        miembros = Usuario.objects.filter(es_admin=False).order_by('-destacado', '-perfil_publico', 'nombre')
    else:
        miembros = Usuario.objects.filter(perfil_publico=True, es_admin=False).order_by('-destacado', 'nombre')

    if query:
        # Incluimos búsqueda en sede y carrera también
        miembros = miembros.filter(
            Q(nombre__icontains=query) | 
            Q(apellido__icontains=query) |
            Q(rut__icontains=query) |
            Q(sede__icontains=query) |
            Q(sede_otro__icontains=query) |
            Q(carrera__icontains=query) |
            Q(carrera_otro__icontains=query)
        )
    
    if rubro_filter:
        miembros = miembros.filter(rubro__iexact=rubro_filter)
    if sede_filter:
        miembros = miembros.filter(sede__iexact=sede_filter)
    if carrera_filter:
        miembros = miembros.filter(carrera__iexact=carrera_filter)

    contexto = {
        'usuario': usuario_actual,
        'miembros': miembros,
        'RUBRO_CHOICES': RUBRO_CHOICES,
        'SEDE_CHOICES': SEDE_CHOICES,
        'CARRERA_CHOICES': CARRERA_CHOICES,
    }
    return render(request, 'directorio.html', contexto)

@login_required
def mis_reuniones(request):
    """
    Muestra al usuario un resumen de su actividad en las reuniones.
    """
    usuario = get_object_or_404(Usuario, id=request.session.get('usuario_id'))

    # Reuniones futuras en las que el usuario ha mostrado interés O ya es asistente.
    # Usamos Q para combinar ambas consultas y .distinct() para evitar duplicados.
    reuniones_futuras_actividad = Reunion.objects.filter(
        Q(interesados=usuario) | Q(asistentes=usuario),
        fecha__gte=timezone.now()
    ).distinct().order_by('fecha')

    # Historial de reuniones a las que el usuario ha asistido
    # Usamos select_related para optimizar y evitar consultas extra en el bucle de la plantilla
    reuniones_asistidas = usuario.reuniones_asistidas.filter(fecha__lt=timezone.now()).order_by('-fecha').select_related('encuesta')

    # Obtenemos los IDs de las encuestas que el usuario ya ha respondido
    encuestas_respondidas_ids = set(RespuestaEncuesta.objects.filter(usuario=usuario).values_list('encuesta_id', flat=True))

    contexto = {
        'usuario': usuario,
        'reuniones_interesado': reuniones_futuras_actividad,
        'reuniones_asistidas': reuniones_asistidas,
        'encuestas_respondidas_ids': encuestas_respondidas_ids,
    }
    return render(request, 'mis_reuniones.html', contexto)