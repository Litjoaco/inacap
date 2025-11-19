# En c:\Users\joaqu\Desktop\Ecosistema\Ecosistema\Ecosistema\usuario\forms.py

from django import forms
from .models import Usuario
from django.contrib.auth.hashers import make_password
from paneladm.models import RespuestaEncuesta
import re

def validate_rut(rut):
    """
    Valida un RUT chileno.
    Retorna (True, "RUT limpio") si es válido, o (False, "Mensaje de error") si no lo es.
    """
    rut_limpio = str(rut).upper().replace(".", "").replace("-", "")
    
    if not rut_limpio[:-1].isdigit() or not (rut_limpio[-1].isdigit() or rut_limpio[-1] == 'K'):
        return False, "El RUT debe contener solo números y, si corresponde, una 'K' al final."

    # Si el RUT viene formateado (ej: 12.345.678-9), el último caracter es el DV.
    # Si viene limpio (ej: 123456789), también.
    body = rut_limpio[:-1]
    dv = rut_limpio[-1]

    try:
        reversed_body = map(int, reversed(body))
        factors = [2, 3, 4, 5, 6, 7] * (len(body) // 6 + 1)
        s = sum(digit * factor for digit, factor in zip(reversed_body, factors))
        res = 11 - (s % 11)
        
        calculated_dv = str(res) if res < 10 else ('0' if res == 11 else 'K')

        if dv == calculated_dv:
            return True, rut_limpio
        else:
            return False, "El RUT ingresado no es válido (dígito verificador incorrecto)."
    except ValueError:
        return False, "Formato de RUT incorrecto."

class LoginForm(forms.Form):
    email = forms.EmailField(label="Correo Electrónico", widget=forms.EmailInput(attrs={'class': 'form-control', 'autocomplete': 'email'}))
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'}))


class UsuarioForm(forms.ModelForm):
    TIPO_USUARIO_CHOICES = [
        ('inacap', 'Soy de Inacap'),
        ('externo', 'Soy Externo')
    ]
    tipo_usuario = forms.ChoiceField(
        choices=TIPO_USUARIO_CHOICES,
        widget=forms.RadioSelect,
        label="Origen",
        required=True
    )

    class Meta:
        model = Usuario
        # Simplificamos los campos para que coincidan con la plantilla de registro.
        # Los campos como sede, carrera, etc., se llenarán al editar el perfil.
        fields = [
            'nombre', 'apellido', 'rut', 'email',
            'tipo_usuario', 'rubro', 'institucion_empresa',
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            # El widget de tipo_usuario se define en el campo mismo.
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'institucion_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de tu institución o empresa'}),
        }
        labels = {
            'rubro': 'Tu Rol en Inacap',
            'institucion_empresa': 'Institución o Empresa'
        }

    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        is_valid, message_or_rut = validate_rut(rut)
        if not is_valid:
            raise forms.ValidationError(message_or_rut)

        # Verificar si el RUT ya existe en la base de datos
        if Usuario.objects.filter(rut=message_or_rut).exists():
            raise forms.ValidationError("Ya existe un usuario con este RUT.")

        return message_or_rut

    def clean_email(self):
        # Usamos .lower() para una comparación insensible a mayúsculas/minúsculas
        email = self.cleaned_data.get('email').lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo electrónico.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        tipo_usuario = cleaned_data.get('tipo_usuario')
        rubro = cleaned_data.get('rubro')
        institucion_empresa = cleaned_data.get('institucion_empresa')

        if tipo_usuario == 'inacap' and not rubro:
            self.add_error('rubro', 'Debes seleccionar tu rol en Inacap.')
        elif tipo_usuario == 'externo' and not institucion_empresa:
            self.add_error('institucion_empresa', 'Debes especificar el nombre de tu institución o empresa.')

        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)

        # Establecer la contraseña como el RUT sin dígito verificador
        rut_limpio = self.cleaned_data.get('rut', '')
        if rut_limpio:
            password_por_defecto = rut_limpio[:-1]
            usuario.password = make_password(password_por_defecto)

        if commit:
            usuario.save()
        return usuario

class EditarUsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            'nombre', 'apellido', 'rut', 'email', 'telefono',
            'sede', 'sede_otro', 'carrera', 'carrera_otro',
            'rubro', 'rubro_otro',
            'foto'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'rubro_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu rol aquí'}),
            'sede': forms.Select(attrs={'class': 'form-select'}),
            'sede_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu sede aquí'}),
            'carrera': forms.Select(attrs={'class': 'form-select'}),
            'carrera_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu carrera aquí'}),
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'd-none'}),
        }

    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        is_valid, message_or_rut = validate_rut(rut)
        if not is_valid:
            raise forms.ValidationError(message_or_rut)
        
        # Al editar, debemos excluir al propio usuario de la verificación de duplicados.
        # 'self.instance' es el objeto de usuario que se está editando.
        if self.instance:
            if Usuario.objects.filter(rut=message_or_rut).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError("Ya existe otro usuario con este RUT.")
        elif Usuario.objects.filter(rut=message_or_rut).exists():
             raise forms.ValidationError("Ya existe un usuario con este RUT.")

        return message_or_rut

    def clean(self):
        cleaned_data = super().clean()
        sede = cleaned_data.get("sede")
        sede_otro = cleaned_data.get("sede_otro")
        if sede == 'otro' and not sede_otro:
            self.add_error('sede_otro', 'Debes especificar tu sede si seleccionas "Otra Sede".')
        carrera = cleaned_data.get("carrera")
        carrera_otro = cleaned_data.get("carrera_otro")
        if carrera == 'otro' and not carrera_otro:
            self.add_error('carrera_otro', 'Debes especificar tu carrera si seleccionas "Otra Carrera / Especialidad".')
        return cleaned_data

class AyudanteUsuarioForm(EditarUsuarioForm):
    """Formulario para que los ayudantes editen usuarios, sin campos sensibles."""
    class Meta(EditarUsuarioForm.Meta):
        # Hereda los campos de EditarUsuarioForm y añade 'cantidad_asistencias'.
        # Se redefine el widget para que sea un campo de número estándar.
        fields = EditarUsuarioForm.Meta.fields + ['cantidad_asistencias']
        widgets = EditarUsuarioForm.Meta.widgets.copy()
        widgets['cantidad_asistencias'] = forms.NumberInput(attrs={'class': 'form-control'})


class AdminUsuarioForm(forms.ModelForm):
    # Hacemos el campo de contraseña no requerido y añadimos un placeholder
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Dejar en blanco para no cambiar'}), required=False)

    class Meta:
        model = Usuario
        # Para el admin, incluimos todos los campos del usuario normal MÁS los roles y 'cantidad_asistencias'
        fields = ['nombre', 'apellido', 'rut', 'email', 'telefono',
                  'sede', 'sede_otro', 'carrera', 'carrera_otro',
                  'rubro', 'rubro_otro',
                  'password', 'foto', 'es_admin', 'es_ayudante', 'es_totem', 'cantidad_asistencias']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'rubro_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu rol aquí'}),
            'sede': forms.Select(attrs={'class': 'form-select'}),
            'sede_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu sede aquí'}),
            'carrera': forms.Select(attrs={'class': 'form-control'}),
            'carrera_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu carrera aquí'}),
            'rut': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
            'foto': forms.ClearableFileInput(attrs={'class': 'd-none'}),
            'es_admin': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_ayudante': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'es_totem': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email')
        # self.instance es el objeto Usuario que se está editando.
        # Excluimos al propio usuario de la búsqueda de emails duplicados.
        if Usuario.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo electrónico.")
        return email
    
    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        is_valid, message_or_rut = validate_rut(rut)
        if not is_valid:
            raise forms.ValidationError(message_or_rut)
        if Usuario.objects.filter(rut=message_or_rut).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe un usuario con este RUT.")
        return message_or_rut

    def clean(self):
        cleaned_data = super().clean()
        rubro = cleaned_data.get("rubro")
        rubro_otro = cleaned_data.get("rubro_otro")
        if rubro == 'otro' and not rubro_otro:
            self.add_error('rubro_otro', 'Debes especificar el rol si seleccionas "Otro".')
        sede = cleaned_data.get("sede")
        sede_otro = cleaned_data.get("sede_otro")
        if sede == 'otro' and not sede_otro:
            self.add_error('sede_otro', 'Debes especificar la sede si seleccionas "Otra Sede".')
        carrera = cleaned_data.get("carrera")
        carrera_otro = cleaned_data.get("carrera_otro")
        if carrera == 'otro' and not carrera_otro:
            self.add_error('carrera_otro', 'Debes especificar la carrera si seleccionas "Otra Carrera / Especialidad".')

    def save(self, commit=True):
        from django.contrib.auth.hashers import make_password
        usuario = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            usuario.password = make_password(password)
        if commit:
            usuario.save()
        return usuario


class CambiarPasswordForm(forms.Form):
    password_actual = forms.CharField(label="Contraseña Actual", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    nueva_password = forms.CharField(label="Nueva Contraseña", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    confirmar_password = forms.CharField(label="Confirmar Nueva Contraseña", widget=forms.PasswordInput(attrs={'class': 'form-control'}))

    def clean_nueva_password(self):
        password = self.cleaned_data.get('nueva_password')
        if len(password) < 8:
            raise forms.ValidationError("La contraseña debe tener al menos 8 caracteres.")
        if not re.search(r'[A-Z]', password):
            raise forms.ValidationError("La contraseña debe contener al menos una letra mayúscula.")
        if not re.search(r'[a-z]', password):
            raise forms.ValidationError("La contraseña debe contener al menos una letra minúscula.")
        if not re.search(r'[0-9]', password):
            raise forms.ValidationError("La contraseña debe contener al menos un número.")
        return password

    def clean(self):
        cleaned_data = super().clean()
        nueva_password = cleaned_data.get("nueva_password")
        confirmar_password = cleaned_data.get("confirmar_password")

        if nueva_password and confirmar_password and nueva_password != confirmar_password:
            self.add_error('confirmar_password', "Las nuevas contraseñas no coinciden.")
        return cleaned_data

class RespuestaEncuestaForm(forms.ModelForm):
    class Meta:
        model = RespuestaEncuesta
        fields = ['puntuacion', 'comentarios']
        widgets = {
            'puntuacion': forms.RadioSelect(attrs={'class': 'btn-check'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Tus comentarios son valiosos...'}),
        }
        labels = {
            'comentarios': 'Comentarios (opcional)'
        }
