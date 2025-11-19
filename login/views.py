from django.shortcuts import render, redirect
from .forms import LoginForm
from usuario.models import Usuario
from django.contrib.auth.hashers import check_password
from django.contrib import messages
from django.contrib.auth import authenticate

def login_usuario(request):
    mensaje = ""
    if request.method == "POST":
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']

            # --- Lógica de autenticación unificada ---
            # 'authenticate' ahora funciona con el modelo Usuario gracias a AUTH_USER_MODEL
            usuario = authenticate(request, username=email, password=password)

            if usuario is not None:
                request.session['usuario_id'] = usuario.id
                request.session['usuario_foto_url'] = usuario.foto.url if usuario.foto else None
                messages.success(request, f'¡Bienvenido de vuelta, {usuario.nombre}!')

                # --- LÓGICA DE REDIRECCIÓN POR ROL ---
                if usuario.es_admin or usuario.es_ayudante:
                    return redirect('panel-admin:panel_admin')
                if usuario.es_totem:
                    return redirect('panel-admin:totem_seleccionar_reunion')
                
                return redirect('inicio') # Redirección por defecto para usuarios normales
            else:
                mensaje = "Email o contraseña incorrectos."
    else:
        form = LoginForm()

    return render(request, 'login.html', {'form': form, 'mensaje': mensaje})

def logout_usuario(request):
    request.session.flush()
    messages.success(request, 'Has cerrado sesión exitosamente.')
    return redirect('inicio')
