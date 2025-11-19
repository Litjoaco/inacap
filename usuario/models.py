from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import qrcode
from io import BytesIO
from django.core.files import File
from django.urls import reverse
from django.conf import settings

RUBRO_CHOICES = [
    ('estudiante', 'Estudiante'),
    ('docente', 'Docente'),
    ('administrativo', 'Administrativo'),
    ('externo', 'Externo'), # Rol para los externos
]

SEDE_CHOICES = [
    ('Zona Norte', (
        ('Arica', 'Arica'),
        ('Iquique', 'Iquique'),
        ('Calama', 'Calama'),
        ('Antofagasta', 'Antofagasta'),
        ('Copiapó', 'Copiapó'),
        ('La Serena', 'La Serena'),
        ('Valparaíso', 'Valparaíso'),
    )),
    ('Región Metropolitana', (
        ('Apoquindo', 'Apoquindo'),
        ('Maipú', 'Maipú'),
        ('Renca', 'Renca'),
        ('Ñuñoa', 'Ñuñoa'),
        ('Santiago Centro', 'Santiago Centro'),
        ('Santiago Sur', 'Santiago Sur'),
        ('La Granja', 'La Granja'),
        ('Puente Alto', 'Puente Alto'),
    )),
    ('Zona Sur', (
        ('Rancagua', 'Rancagua'),
        ('Curicó', 'Curicó'),
        ('Talca', 'Talca'),
        ('Chillán', 'Chillán'),
        ('Concepción-Talcahuano', 'Concepción-Talcahuano'),
        ('San Pedro de la Paz', 'San Pedro de la Paz'),
        ('Los Ángeles', 'Los Ángeles'),
        ('Temuco', 'Temuco'),
        ('Valdivia', 'Valdivia'),
        ('Osorno', 'Osorno'),
        ('Puerto Montt', 'Puerto Montt'),
        ('Coyhaique', 'Coyhaique'),
        ('Punta Arenas', 'Punta Arenas'),
    )),
    ('otro', 'Otra Sede'),
]

CARRERA_CHOICES = [
    ('Tecnologías de la Información y Ciberseguridad', (
        ('ing_informatica', 'Ingeniería en Informática'),
        ('analista_programador', 'Analista Programador'),
        ('ciberseguridad', 'Ingeniería en Ciberseguridad'),
    )),
    ('Administración y Negocios', (
        ('ing_adm_empresas', 'Ingeniería en Administración de Empresas'),
        ('contador_auditor', 'Contador Auditor'),
        ('comercio_exterior', 'Comercio Exterior'),
    )),
    ('Mecánica y Mantenimiento', (
        ('ing_mecanica_electromovilidad', 'Ingeniería en Mecánica y Electromovilidad Automotriz'),
        ('tec_mantenimiento_industrial', 'Técnico en Mantenimiento Industrial'),
        ('ing_maquinaria_pesada', 'Ingeniería en Maquinaria Pesada'),
    )),
    ('Electricidad y Electrónica', (
        ('ing_electronica_sistemas', 'Ingeniería en Electrónica y Sistemas Inteligentes'),
        ('tec_electricidad_industrial', 'Técnico en Electricidad Industrial'),
        ('ing_telecomunicaciones', 'Ingeniería en Telecomunicaciones, Conectividad y Redes'),
    )),
    ('Diseño y Comunicación', (
        ('diseno_digital', 'Diseño Digital Profesional'),
        ('diseno_moda', 'Diseño y Producción de Moda'),
    )),
    ('Salud', (
        ('tec_enfermeria', 'Técnico en Enfermería'),
        ('laboratorista_clinico', 'Laboratorista Clínico y Banco de Sangre'),
    )),
    ('Otras Áreas', (
        ('gastronomia', 'Gastronomía'),
        ('construccion_civil', 'Construcción Civil'),
        ('ing_agricola', 'Ingeniería Agrícola'),
    )),
    ('otro', 'Otra Carrera / Especialidad'),
]

class UsuarioManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El campo Email es obligatorio.')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('es_admin', True) # Aseguramos que el superuser sea admin

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser debe tener is_superuser=True.')

        return self.create_user(email, password=password, **extra_fields)

class Usuario(AbstractBaseUser, PermissionsMixin):
    # Campos de Usuario
    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    rut = models.CharField(max_length=12, unique=True)
    email = models.EmailField(unique=True, verbose_name='Email')
    # 'password' es manejado por AbstractBaseUser
    
    # Campos requeridos por Django para el modelo de usuario personalizado
    is_staff = models.BooleanField(default=False, help_text='Designa si el usuario puede iniciar sesión en el sitio de administración.')
    is_active = models.BooleanField(default=True, help_text='Designa si este usuario debe ser tratado como activo. Desmarque esto en lugar de eliminar cuentas.')
    last_login = models.DateTimeField(null=True, blank=True, verbose_name='último inicio de sesión')

    telefono = models.CharField(max_length=15, blank=True, null=True)
    rubro = models.CharField(max_length=100, choices=RUBRO_CHOICES, blank=True, null=True, help_text="Tu rol dentro de la comunidad.", verbose_name="Rol")
    rubro_otro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Especificar otro rol")
    sede = models.CharField(max_length=100, choices=SEDE_CHOICES, blank=True, null=True, verbose_name="Sede")
    sede_otro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Especificar otra sede")
    carrera = models.CharField(max_length=150, choices=CARRERA_CHOICES, blank=True, null=True, verbose_name="Carrera o Especialidad")
    carrera_otro = models.CharField(max_length=150, blank=True, null=True, verbose_name="Especificar otra carrera")
    institucion_empresa = models.CharField(max_length=150, blank=True, null=True, verbose_name="Institución o Empresa")
    foto = models.ImageField(upload_to='usuarios/', null=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    etiqueta_emojis = models.CharField(max_length=10, blank=True)
    # Campos de Sistema
    es_admin = models.BooleanField(default=False)
    es_ayudante = models.BooleanField(default=False)
    es_totem = models.BooleanField(default=False, help_text="Designa a este usuario como una cuenta para un quiosco/tótem de check-in.")
    cantidad_asistencias = models.IntegerField(default=0, verbose_name="Cantidad de Asistencias")
    perfil_publico = models.BooleanField(default=True, help_text="Permite que otros miembros vean tu perfil en el directorio.")
    destacado = models.BooleanField(default=False)

    # Manager personalizado
    objects = UsuarioManager()

    # Campo para el login
    USERNAME_FIELD = 'email'
    # Campos requeridos al crear un superusuario
    REQUIRED_FIELDS = ['nombre', 'apellido', 'rut']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"
    

    @property
    def get_rubro_real_display(self):
        if self.rubro == 'otro':
            return self.rubro_otro or 'Otro'
        return self.get_rubro_display()

    @property
    def get_sede_real_display(self):
        if self.sede == 'otro':
            return self.sede_otro or 'Otra Sede'
        return self.get_sede_display()

    @property
    def get_carrera_real_display(self):
        if self.carrera == 'otro':
            return self.carrera_otro or 'Otra Carrera'
        return self.get_carrera_display()

@receiver(post_save, sender=Usuario)
def extras_post_creacion(sender, instance, created, **kwargs):
    import random
    if created:
        update_fields = []
        if not instance.etiqueta_emojis:
            emojis_disponibles = ['💡', '🚀', '📈', '💼', '🤝', '🌐', '💻', '📱', '🎯', '🌟', '🌱', '🔗', '🛠️', '📊', '🧠', '⚡️', '🏆', '🔑']
            instance.etiqueta_emojis = "".join(random.sample(emojis_disponibles, 3))
            update_fields.append('etiqueta_emojis')
        if not instance.qr_code:
            base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
            qr_url = base_url + reverse('perfil_publico', args=[instance.id])
            buffer = BytesIO()
            qrcode.make(qr_url).save(buffer, format='PNG')
            instance.qr_code.save(f'qr_usuario_{instance.id}.png', File(buffer), save=False)
            update_fields.append('qr_code')

        if update_fields:
            instance.save(update_fields=update_fields)
