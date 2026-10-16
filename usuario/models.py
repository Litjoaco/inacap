import re
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from django.urls import reverse
import qrcode
from io import BytesIO
from django.core.files import File

# OPCIONES PARA FORMULARIOS Y MODELOS
RUBRO_CHOICES = [
    ('estudiante', 'Estudiante INACAP'),
    ('docente', 'Docente / Académico'),
    ('exalumno', 'Exalumno / Titulado'),
    ('administrativo', 'Colaborador / Administrativo'),
    ('directivo', 'Directivo'),
    ('externo', 'Invitado Externo / Empresa'),
    ('otro', 'Otro'),
]

SEDE_CHOICES = [
    ('Zona Norte', (
        ('Arica', 'Arica'),
        ('Iquique', 'Iquique'),
        ('Calama', 'Calama'),
        ('Antofagasta', 'Antofagasta'),
        ('Copiapó', 'Copiapó'),
        ('La Serena', 'La Serena'),
    )),
    ('Región Metropolitana', (
        ('Santiago Centro', 'Santiago Centro'),
        ('Santiago Sur', 'Santiago Sur (San Joaquín)'),
        ('Apoquindo', 'Apoquindo'),
        ('Maipú', 'Maipú'),
        ('Renca', 'Renca'),
        ('Puente Alto', 'Puente Alto'),
        ('Pérez Rosales', 'Pérez Rosales'),
        ('Los Dominicos', 'Los Dominicos'),
        ('La Granja', 'La Granja'),
        ('Ñuñoa', 'Ñuñoa'),
    )),
    ('Zona Centro Sur', (
        ('Valparaíso', 'Valparaíso'),
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
        extra_fields.setdefault('es_admin', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser debe tener is_superuser=True.')

        return self.create_user(email, password=password, **extra_fields)

class Usuario(AbstractBaseUser, PermissionsMixin):
    nombre = models.CharField(max_length=100, db_index=True)
    apellido = models.CharField(max_length=100, db_index=True)
    rut = models.CharField(max_length=12, unique=True)
    email = models.EmailField(unique=True, verbose_name='Email')
    
    is_staff = models.BooleanField(default=False, help_text='Designa si el usuario puede iniciar sesión en el sitio de administración.')
    is_active = models.BooleanField(default=True, help_text='Designa si este usuario debe ser tratado como activo.')
    last_login = models.DateTimeField(null=True, blank=True, verbose_name='Último inicio de sesión')

    telefono = models.CharField(max_length=15, blank=True, null=True)
    rubro = models.CharField(max_length=100, choices=RUBRO_CHOICES, blank=True, null=True, verbose_name="Rol")
    rubro_otro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Especificar otro rol")
    sede = models.CharField(max_length=100, choices=SEDE_CHOICES, blank=True, null=True, verbose_name="Sede")
    sede_otro = models.CharField(max_length=100, blank=True, null=True, verbose_name="Especificar otra sede")
    carrera = models.CharField(max_length=150, choices=CARRERA_CHOICES, blank=True, null=True, verbose_name="Carrera o Especialidad")
    carrera_otro = models.CharField(max_length=150, blank=True, null=True, verbose_name="Especificar otra carrera")
    institucion_empresa = models.CharField(max_length=150, blank=True, null=True, verbose_name="Institución o Empresa")
    foto = models.ImageField(upload_to='usuarios/', null=True, blank=True)
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True, null=True)
    etiqueta_emojis = models.CharField(max_length=10, blank=True)
    
    es_admin = models.BooleanField(default=False, db_index=True)
    es_ayudante = models.BooleanField(default=False, db_index=True)
    es_totem = models.BooleanField(default=False, db_index=True)
    cantidad_asistencias = models.IntegerField(default=0, db_index=True, verbose_name="Cantidad de Asistencias")
    perfil_publico = models.BooleanField(default=True)
    destacado = models.BooleanField(default=False)
    acepta_terminos = models.BooleanField(default=True, verbose_name="Acepta Términos y Protección de Datos")
    fecha_aceptacion_terminos = models.DateTimeField(auto_now_add=True, null=True, blank=True, verbose_name="Fecha de Aceptación de Términos")

    
    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"
        indexes = [
            models.Index(fields=['apellido', 'nombre']),
            models.Index(fields=['rut', 'is_active']),
            models.Index(fields=['sede', 'carrera']),
        ]

    objects = UsuarioManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['nombre', 'apellido', 'rut']

    def __str__(self):
        return f"{self.nombre} {self.apellido}"

    def get_email_field_name(self):
        return 'email'

    def rut_formateado(self):
        if not self.rut:
            return ""
        clean = re.sub(r'[^0-9kK]', '', str(self.rut).upper())
        if len(clean) < 2:
            return clean
        cuerpo = clean[:-1]
        dv = clean[-1]
        try:
            cuerpo_fmt = "{:,}".format(int(cuerpo)).replace(",", ".")
            return f"{cuerpo_fmt}-{dv}"
        except:
            return clean

    def get_rubro_real_display(self):
        if self.rubro == 'otro':
            return self.rubro_otro or 'Otro'
        return self.get_rubro_display()

    def get_sede_real_display(self):
        if self.sede == 'otro':
            return self.sede_otro or 'Otra Sede'
        return self.get_sede_display()

    def get_carrera_real_display(self):
        if self.carrera == 'otro':
            return self.carrera_otro or 'Otra Carrera'
        return self.get_carrera_display()

    def save(self, *args, **kwargs):
        if self.nombre:
            partes = str(self.nombre).strip().split()
            self.nombre = ' '.join('-'.join(sub.capitalize() for sub in p.split('-')) for p in partes)
        if self.apellido:
            partes = str(self.apellido).strip().split()
            self.apellido = ' '.join('-'.join(sub.capitalize() for sub in p.split('-')) for p in partes)
        super().save(*args, **kwargs)

@receiver(post_save, sender=Usuario)
def extras_post_creacion(sender, instance, created, **kwargs):
    import random
    if created:
        update_fields = []
        if not instance.etiqueta_emojis:
            emojis_disponibles = ['🎓', '⚡', '💻', '🚀', '⭐', '🔥', '📚', '🎯', '✨', '🏢', '🛠️', '💡', '🎉', '🏆', '🔧', '📊']
            instance.etiqueta_emojis = "".join(random.sample(emojis_disponibles, 3))
            update_fields.append('etiqueta_emojis')
        if not instance.qr_code:
            base_url = getattr(settings, 'BASE_URL', 'http://127.0.0.1:8000')
            try:
                qr_url = base_url + reverse('imprimir_etiqueta', args=[instance.id])
            except:
                qr_url = f"{base_url}/etiqueta/{instance.id}/"
            buffer = BytesIO()
            qrcode.make(qr_url).save(buffer, format='PNG')
            instance.qr_code.save(f'qr_usuario_{instance.id}.png', File(buffer), save=False)
            update_fields.append('qr_code')

        if update_fields:
            instance.save(update_fields=update_fields)
