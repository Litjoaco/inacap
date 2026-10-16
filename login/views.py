from django.shortcuts import render, redirect
from .forms import LoginForm
from usuario.models import Usuario
from django.contrib.auth.hashers import check_password
from django.contrib import messages
from django.contrib.auth import authenticate
from django.core.cache import cache

def login_usuario(request):
    mensaje = ""
    ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
    if ip:
        ip = ip.split(',')[0].strip()
    lockout_key = f"login_attempts_{ip or 'unknown'}"

    if request.method == "POST":
        form = LoginForm(request.POST)

        # Rate limiting: máximo 5 intentos fallidos en 5 minutos por IP
        intentos = cache.get(lockout_key, 0)
        if intentos >= 5:
            mensaje = "Demasiados intentos de acceso fallidos. Por seguridad, tu acceso está temporalmente pausado por 5 minutos."
            return render(request, 'login.html', {'form': form, 'mensaje': mensaje})

        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # 'authenticate' ahora funciona con el modelo Usuario gracias a AUTH_USER_MODEL
            usuario = authenticate(request, username=email, password=password)

            if usuario is not None:
                cache.delete(lockout_key)
                request.session.cycle_key()
                request.session['usuario_id'] = usuario.id
                request.session['usuario_foto_url'] = usuario.foto.url if usuario.foto else None
                messages.success(request, f'¡Bienvenido de vuelta, {usuario.nombre}!')

                if usuario.es_admin or usuario.es_ayudante:
                    return redirect('panel-admin:panel_admin')
                if usuario.es_totem:
                    return redirect('panel-admin:totem_seleccionar_reunion')
                
                return redirect('inicio') # Redirección por defecto para usuarios normales
            else:
                cache.set(lockout_key, intentos + 1, timeout=300)
                intentos_restantes = max(0, 5 - (intentos + 1))
                if intentos_restantes > 0 and intentos + 1 >= 3:
                    mensaje = f"Email o contraseña incorrectos. Te quedan {intentos_restantes} intento(s) antes del bloqueo temporal."
                else:
                    mensaje = "Email o contraseña incorrectos."
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form, 'mensaje': mensaje})

def logout_usuario(request):
    request.session.flush()
    messages.success(request, 'Has cerrado sesión exitosamente.')
    return redirect('inicio')
