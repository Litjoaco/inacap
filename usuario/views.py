import functools
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.template.loader import render_to_string
from django.core.mail import send_mail
from .forms import PasswordResetRequestForm, SetNewPasswordForm

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from .forms import UsuarioForm, EditarUsuarioForm, RespuestaEncuestaForm, CambiarPasswordForm, LoginForm
from .models import CARRERA_CHOICES, SEDE_CHOICES, Usuario, RUBRO_CHOICES
from paneladm.models import Reunion, Encuesta, RespuestaEncuesta, SoporteTicket, TicketRespuesta
from paneladm.forms import SoporteTicketForm, TicketRespuestaForm, ReunionForm
from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone
from django.db.models import Q
from django.core.cache import cache
import random

def login_required(view_func):
    """
    Decorador personalizado para verificar que el usuario ha iniciado sesión.
    """
    @functools.wraps(view_func)
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
                    # Mitigación de fijación de sesión
                    request.session.cycle_key()
                    request.session['usuario_id'] = usuario.id
                    messages.success(request, f'¡Bienvenido de vuelta, {usuario.nombre}!')
                    
                    if usuario.es_totem:
                        return redirect('totem_seleccionar_reunion')
                    return redirect('inicio')
                else:
                    messages.error(request, 'Correo o contraseña incorrectos.')
            except Usuario.DoesNotExist:
                # Mensaje genérico para mitigar enumeración de usuarios
                messages.error(request, 'Correo o contraseña incorrectos.')
    else:
        form = LoginForm()
    return render(request, 'login.html', {'form': form})

def registro(request):
    if request.method == 'POST':
        form = UsuarioForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            messages.success(request, '¡Usuario registrado con éxito!')
            return redirect('inicio')
    else:
        initial_data = {}
        rut_param = request.GET.get('rut')
        if rut_param:
            initial_data['rut'] = rut_param
        form = UsuarioForm(initial=initial_data)
    return render(request, 'registro.html', {'form': form})

@login_required
def perfil(request):
    usuario_id = request.session.get('usuario_id')
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

@login_required
def editar_perfil(request, usuario_id):
    session_uid = request.session.get('usuario_id')
    usuario_actual = get_object_or_404(Usuario, id=session_uid)

    # Protección IDOR: Solo el propio usuario o un administrador pueden editar este perfil
    if session_uid != usuario_id and not usuario_actual.es_admin:
        messages.error(request, 'No tienes permiso para modificar este perfil.')
        return redirect('perfil')

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

def imprimir_etiqueta(request, usuario_id, reunion_id=None):
    """
    Vista que muestra la etiqueta de un usuario con soporte para plantillas personalizadas.
    """
    usuario = get_object_or_404(Usuario, id=usuario_id)
    reunion = None
    plantilla = None
    
    if reunion_id:
        reunion = Reunion.objects.filter(id=reunion_id).first()
        if reunion:
            plantilla = reunion.plantilla_etiqueta

    if not plantilla:
        plantilla = {
            'orden_elementos': ['nombre_completo', 'carrera', 'sede', 'asistencias']
        }

    context = {
        'usuario': usuario,
        'reunion': reunion,
        'plantilla': plantilla,
    }
    return render(request, 'etiqueta_imprimir.html', context)

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

@login_required
def registrar_interes(request, reunion_id):
    usuario_id = request.session.get('usuario_id')
    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario = get_object_or_404(Usuario, id=usuario_id)
        reunion.interesados.add(usuario)
        messages.success(request, f'¡Genial! Has mostrado interés en "{reunion.detalle}".')
    return redirect('inicio')

def toggle_interes(request, reunion_id):
    """
    Registra o quita el interés de un usuario en una reunión (AJAX).
    """
    from django.http import JsonResponse
    usuario_id = request.session.get('usuario_id')
    if not usuario_id:
        return JsonResponse({'status': 'error', 'message': 'Debes iniciar sesión para mostrar interés.'}, status=401)

    if request.method == 'POST':
        reunion = get_object_or_404(Reunion, id=reunion_id)
        usuario = get_object_or_404(Usuario, id=usuario_id)

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

    # Métricas y estadísticas para el panel
    total_usuarios = Usuario.objects.count()
    total_reuniones = Reunion.objects.count()
    proximos_eventos = Reunion.objects.filter(fecha__gte=timezone.now()).count()
    tickets_abiertos = SoporteTicket.objects.filter(estado='abierto').count()

    context = {
        'usuario': usuario_actual,
        'total_usuarios': total_usuarios,
        'total_reuniones': total_reuniones,
        'proximos_eventos': proximos_eventos,
        'tickets_abiertos': tickets_abiertos,
    }
    return render(request, 'panel_admin.html', context)

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
                # Contraseña hasheada de forma segura
                usuario.password = make_password(nueva_password)
                usuario.save(update_fields=['password'])
                request.session.cycle_key()
                messages.success(request, '¡Contraseña actualizada con éxito!')
                return redirect('perfil')
    else:
        form = CambiarPasswordForm()
    
    contexto = {
        'form': form,
        'usuario': usuario
    }
    return render(request, 'cambiar_password.html', contexto)

def password_reset_request(request):
    if request.method == 'POST':
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            associated_users = Usuario.objects.filter(email__iexact=email)
            if associated_users.exists():
                for user in associated_users:
                    token = default_token_generator.make_token(user)
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    
                    reset_url = request.build_absolute_uri(
                        reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
                    )
                    
                    subject = 'Restablecimiento de contraseña - Eventos INACAP'
                    message = render_to_string('password_reset_email.html', {
                        'user': user,
                        'reset_url': reset_url,
                    })
                    
                    send_mail(subject, message, None, [user.email])

            messages.success(request, 'Si tu correo electrónico está en nuestra base de datos, recibirás un enlace para restablecer tu contraseña en breve.')
            return redirect('login')
    else:
        form = PasswordResetRequestForm()
    
    return render(request, 'password_reset_request.html', {'form': form})

def password_reset_confirm(request, uidb64=None, token=None):
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = Usuario.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, Usuario.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            form = SetNewPasswordForm(request.POST, user=user)
            if form.is_valid():
                user.set_password(form.cleaned_data['new_password1'])
                user.save()
                messages.success(request, 'Tu contraseña ha sido restablecida. Ahora puedes iniciar sesión.')
                return redirect('login')
        else:
            form = SetNewPasswordForm(user=user)
        return render(request, 'password_reset_confirm.html', {'form': form, 'validlink': True})
    else:
        messages.error(request, 'El enlace de restablecimiento de contraseña no es válido o ha expirado.')
        return render(request, 'password_reset_confirm.html', {'validlink': False})

def landing_reuniones(request):
    """
    Landing pública que lista los eventos y reuniones de INACAP.
    """
    now = timezone.now()
    reuniones_proximas = Reunion.objects.filter(fecha__gte=now).order_by('fecha')
    reuniones_pasadas = Reunion.objects.filter(fecha__lt=now).order_by('-fecha')
    contexto = {
        'reuniones_proximas': reuniones_proximas,
        'reuniones_pasadas': reuniones_pasadas,
    }
    return render(request, 'landing_reuniones.html', contexto)

from django.http import JsonResponse

def _ofuscar_email(email):
    """
    Ofusca el correo electrónico para prevenir raspado masivo de datos (ej: j***s@inacap.cl).
    """
    if not email or '@' not in email:
        return ''
    partes = email.split('@', 1)
    usuario_str = partes[0]
    dominio = partes[1]
    if len(usuario_str) <= 2:
        usuario_ofuscado = usuario_str[0] + '*'
    else:
        usuario_ofuscado = usuario_str[0] + '*' * (len(usuario_str) - 2) + usuario_str[-1]
    return f"{usuario_ofuscado}@{dominio}"

def consultar_qr_rut(request):
    """
    Permite a cualquier alumno o invitado consultar y ver su código QR ingresando su RUT.
    Incluye limitación de tasa (rate-limit) por IP para mitigar recolección masiva (scraping).
    """
    if request.method == 'POST':
        import json
        from usuario.forms import validate_rut

        # Rate Limiting por IP: máx 10 consultas por minuto
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ip:
            ip = ip.split(',')[0].strip()
        cache_key = f"rate_limit_qr_{ip or 'unknown'}"
        intentos = cache.get(cache_key, 0)
        if intentos >= 10:
            return JsonResponse({
                'status': 'error',
                'mensaje': 'Has superado el límite de consultas por minuto. Por favor, intenta nuevamente más tarde.'
            }, status=429)
        cache.set(cache_key, intentos + 1, timeout=60)

        try:
            data = json.loads(request.body)
            rut_input = data.get('rut', '').strip()
        except:
            rut_input = request.POST.get('rut', '').strip()

        es_valido, rut_o_error = validate_rut(rut_input)
        if not es_valido:
            return JsonResponse({'status': 'error', 'mensaje': rut_o_error})

        rut_limpio = rut_o_error
        usuario = Usuario.objects.filter(rut=rut_limpio).first()

        if usuario:
            qr_url = usuario.qr_code.url if usuario.qr_code else None
            return JsonResponse({
                'status': 'ok',
                'nombre': f"{usuario.nombre} {usuario.apellido}",
                'rut': usuario.rut,
                'email': _ofuscar_email(usuario.email),
                'rol': usuario.get_rubro_real_display() if callable(getattr(usuario, 'get_rubro_real_display', None)) else (usuario.rubro or 'General'),
                'empresa': usuario.institucion_empresa or ('INACAP' if usuario.rubro != 'externo' else 'Particular'),
                'qr_url': qr_url
            })
        else:
            return JsonResponse({
                'status': 'not_found',
                'mensaje': 'No se encontraron registros con este RUT. Puedes inscribirte en cualquier evento para generar tu código.'
            })

    return JsonResponse({'status': 'error', 'mensaje': 'Método no permitido'}, status=405)
