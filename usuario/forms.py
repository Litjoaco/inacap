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
        ('inacap', 'Soy de INACAP'),
        ('externo', 'Soy Externo')
    ]
    SUBTIPO_EXTERNO_CHOICES = [
        ('natural', 'Persona Natural'),
        ('empresa', 'Empresa u Organización')
    ]
    
    tipo_usuario = forms.ChoiceField(
        choices=TIPO_USUARIO_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        label="¿Cuál es tu Origen?",
        initial='inacap',
        required=True
    )
    subtipo_externo = forms.ChoiceField(
        choices=SUBTIPO_EXTERNO_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        label="Tipo de Invitado Externo",
        initial='natural',
        required=False
    )

    class Meta:
        model = Usuario
        fields = ['tipo_usuario', 'subtipo_externo', 'rut', 'nombre', 'apellido', 'email',
            'rubro', 'telefono', 'institucion_empresa', 'acepta_terminos']
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control form-control-lg text-center form-control-rut', 'placeholder': '12.345.678-9'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Juan'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pérez'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@correo.cl'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56 9 1234 5678'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'institucion_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la empresa'}),
        }
        labels = {
            'rut': 'RUT',
            'nombre': 'Nombre',
            'apellido': 'Apellido',
            'email': 'Correo Electrónico',
            'telefono': 'Teléfono / WhatsApp',
            'rubro': 'Rol en INACAP',
            'institucion_empresa': 'Empresa'
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rubro'].required = False
        self.fields['telefono'].required = False
        self.fields['institucion_empresa'].required = False
        self.fields['rubro'].choices = [
            ('', 'Selecciona tu rol en INACAP...'),
            ('estudiante', 'Alumno / Estudiante'),
            ('docente', 'Profesor / Docente'),
            ('administrativo', 'Administrativo / Colaborador'),
            ('exalumno', 'Exalumno / Titulado'),
            ('directivo', 'Directivo'),
            ('otro', 'Otro Rol'),
        ]

    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        is_valid, message_or_rut = validate_rut(rut)
        if not is_valid:
            raise forms.ValidationError(message_or_rut)

        if Usuario.objects.filter(rut=message_or_rut).exists():
            raise forms.ValidationError("Ya existe un usuario registrado con este RUT.")

        return message_or_rut

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe un usuario con este correo electrónico.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        tipo_usuario = cleaned_data.get('tipo_usuario')
        subtipo_externo = cleaned_data.get('subtipo_externo')

        if tipo_usuario == 'inacap':
            rubro = cleaned_data.get('rubro')
            if not rubro:
                self.add_error('rubro', 'Por favor selecciona tu rol en INACAP.')
        elif tipo_usuario == 'externo':
            if subtipo_externo == 'empresa':
                empresa = cleaned_data.get('institucion_empresa')
                if not empresa or not empresa.strip():
                    self.add_error('institucion_empresa', 'Por favor ingresa el nombre de la Empresa u Organización.')

        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        rut_limpio = self.cleaned_data.get('rut', '')
        tipo = self.cleaned_data.get('tipo_usuario')
        subtipo = self.cleaned_data.get('subtipo_externo')

        # Asignar contraseña segura por defecto (RUT sin DV)
        if not usuario.password and rut_limpio:
            password_por_defecto = rut_limpio[:-1]
            usuario.password = make_password(password_por_defecto)

        if tipo == 'externo':
            usuario.sede = None
            usuario.carrera = None
            usuario.rubro = 'externo'
            if subtipo == 'natural':
                if not usuario.institucion_empresa:
                    usuario.institucion_empresa = 'Particular'
        else:
            usuario.sede = None
            usuario.carrera = None
            if not usuario.institucion_empresa:
                usuario.institucion_empresa = 'INACAP'

        if commit:
            usuario.save()
        return usuario

class EditarUsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            'nombre', 'apellido', 'rut', 'email', 'telefono',
            'rubro', 'rubro_otro', 'institucion_empresa',
            'foto'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'rubro_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu rol aquí'}),
            'institucion_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la empresa u organización'}),
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
        return cleaned_data

class AyudanteUsuarioForm(EditarUsuarioForm):
    """Formulario para que los ayudantes editen usuarios, sin campos sensibles."""
    class Meta(EditarUsuarioForm.Meta):
        # Se redefine el widget para que sea un campo de número estándar.
        fields = EditarUsuarioForm.Meta.fields + ['cantidad_asistencias']
        widgets = EditarUsuarioForm.Meta.widgets.copy()
        widgets['cantidad_asistencias'] = forms.NumberInput(attrs={'class': 'form-control'})

class AdminUsuarioForm(forms.ModelForm):
    # Hacemos el campo de contraseña no requerido y añadimos un placeholder
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Dejar en blanco para no cambiar'}), required=False)

    class Meta:
        model = Usuario
        fields = ['nombre', 'apellido', 'rut', 'email', 'telefono',
                  'rubro', 'rubro_otro', 'institucion_empresa',
                  'password', 'foto', 'es_admin', 'es_ayudante', 'es_totem', 'cantidad_asistencias']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'rubro_otro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escribe tu rol aquí'}),
            'institucion_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de la empresa u organización'}),
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
        return cleaned_data

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
        fields = ['puntuacion', 'comentarios', 'es_anonimo']
        widgets = {
            'puntuacion': forms.RadioSelect(attrs={'class': 'btn-check'}),
            'comentarios': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Escribe aquí tu opinión, comentarios o sugerencias...'}),
            'es_anonimo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'puntuacion': 'Calificación de Experiencia',
            'comentarios': 'Opinión y Sugerencias',
            'es_anonimo': 'Responder de forma anónima'
        }

password_help_text = (
    "<ul>"
    "<li>Tu contraseña no puede ser muy similar a tu otra información personal.</li>"
    "<li>Tu contraseña debe contener al menos 8 caracteres.</li>"
    "<li>Tu contraseña no puede ser una contraseña de uso común.</li>"
    "<li>Tu contraseña no puede ser completamente numérica.</li>"
    "</ul>"
)

class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Correo Electrónico", 
        max_length=254, 
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@inacap.cl', 'autocomplete': 'email'})
    )

class SetNewPasswordForm(forms.Form):
    new_password1 = forms.CharField(
        label="Nueva Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        strip=False,
        help_text=password_help_text
    )
    new_password2 = forms.CharField(
        label="Confirmar Nueva Contraseña",
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        strip=False,
    )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

    def clean_new_password1(self):
        password = self.cleaned_data.get('new_password1')
        if self.user:
            validate_password(password, self.user)
        return password

    def clean(self):
        cleaned_data = super().clean()
        new_password1 = cleaned_data.get("new_password1")
        new_password2 = cleaned_data.get("new_password2")
        if new_password1 and new_password2 and new_password1 != new_password2:
            self.add_error('new_password2', "Las contraseñas no coinciden.")
        return cleaned_data

class RegistroRapidoForm(forms.ModelForm):
    TIPO_CHOICES = [
        ('inacap', 'Comunidad INACAP (Alumno / Docente / Directivo)'),
        ('externo', 'Invitado Externo / Empresa')
    ]
    tipo_asistente = forms.ChoiceField(
        choices=TIPO_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'btn-check'}),
        initial='inacap',
        label="Tipo de Asistente"
    )

    class Meta:
        model = Usuario
        fields = [
            'nombre', 'apellido', 'email', 'telefono',
            'rubro', 'institucion_empresa'
        ]
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Juan'}),
            'apellido': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pérez'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'ejemplo@inacap.cl'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+56 9 1234 5678'}),
            'rubro': forms.Select(attrs={'class': 'form-select'}),
            'institucion_empresa': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre de tu empresa u organización'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['telefono'].required = False
        self.fields['institucion_empresa'].required = False
        if 'rubro' in self.fields:
            self.fields['rubro'].required = False

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if Usuario.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo ya se encuentra registrado. Ingresa otro o usa tu RUT.")
        return email

    def save(self, rut, commit=True):
        usuario = super().save(commit=False)
        usuario.rut = rut
        # Asignar contraseña segura automática sin molestar al usuario
        if not usuario.password:
            import secrets
            usuario.set_password(secrets.token_urlsafe(12))
        
        tipo = self.cleaned_data.get('tipo_asistente')
        if tipo == 'externo':
            usuario.rubro = 'externo'
            if not usuario.institucion_empresa:
                usuario.institucion_empresa = 'Particular'
        else:
            if not usuario.rubro or usuario.rubro == 'externo':
                usuario.rubro = 'estudiante'
            if not usuario.institucion_empresa:
                usuario.institucion_empresa = 'INACAP'

        if commit:
            usuario.save()
        return usuario
