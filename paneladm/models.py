from django.db import models
from django.utils import timezone

class Reunion(models.Model):
    detalle = models.CharField(max_length=200, db_index=True, verbose_name="Título o Detalle")
    descripcion = models.TextField(verbose_name="Descripción")
    fecha = models.DateTimeField(db_index=True, verbose_name="Fecha y Hora")
    ubicacion = models.CharField(max_length=255, verbose_name="Ubicación")
    direccion = models.CharField(max_length=255, verbose_name="Dirección (Opcional)", blank=True, null=True)
    imagen = models.ImageField(upload_to='reuniones/', null=True, blank=True, verbose_name="Imagen (Opcional)")
    asistentes = models.ManyToManyField('usuario.Usuario', related_name='reuniones_asistidas', blank=True)
    interesados = models.ManyToManyField('usuario.Usuario', related_name='reuniones_interesado', blank=True)
    imprimir_etiqueta_al_asistir = models.BooleanField(
        default=True,
        verbose_name="¿Imprimir etiqueta al escanear QR?",
        help_text="Si se marca, se abrirá la ventana para imprimir la etiqueta del asistente al escanear su QR."
    )
    plantilla_etiqueta = models.ForeignKey(
        'EtiquetaPlantilla',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Plantilla de Etiqueta",
        help_text="Selecciona una plantilla para las etiquetas de esta reunión. Si no se selecciona, se usará el diseño por defecto."
    )
    aforo_maximo = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name="Aforo Máximo (Capacidad)",
        help_text="Número máximo de asistentes permitidos en el evento. Dejar en blanco si no tiene límite."
    )

    def tiene_aforo_limitado(self):
        return self.aforo_maximo is not None and self.aforo_maximo > 0

    def porcentaje_aforo(self):
        if not self.tiene_aforo_limitado():
            return 0
        total = self.asistentes.count()
        return min(100, int((total / self.aforo_maximo) * 100))

    def aforo_completo(self):
        if not self.tiene_aforo_limitado():
            return False
        return self.asistentes.count() >= self.aforo_maximo

    def cupos_disponibles(self):
        if not self.tiene_aforo_limitado():
            return None
        return max(0, self.aforo_maximo - self.asistentes.count())

    def __str__(self):
        return self.detalle

    class Meta:
        verbose_name = "Reunión"
        verbose_name_plural = "Reuniones"

class EtiquetaPlantilla(models.Model):
    """
    Modelo para almacenar plantillas de diseño para las etiquetas de los asistentes.
    """
    nombre = models.CharField(max_length=100, unique=True, verbose_name="Nombre de la Plantilla")
    logo = models.ImageField(upload_to='logos_etiquetas/', blank=True, null=True, verbose_name="Logo Personalizado", help_text="Opcional. Si se deja en blanco, se usará el logo principal del sistema.")
    nombre_reunion_ejemplo = models.CharField(max_length=100, blank=True, null=True, verbose_name="Nombre de reunión (ejemplo)", help_text="Texto de ejemplo para la previsualización de la etiqueta.")
    texto_extra = models.CharField(max_length=100, blank=True, verbose_name="Texto Personalizado (Opcional)", help_text="Este texto aparecerá en la etiqueta si el elemento 'Texto Personalizado' está seleccionado.")
    orden_elementos = models.JSONField(default=list, verbose_name="Orden de los Elementos", help_text="Define el orden en que aparecerán los campos en la etiqueta.")

    class Meta:
        verbose_name = "Plantilla de Etiqueta"
        verbose_name_plural = "Plantillas de Etiquetas"
        db_table = 'paneladm_plantillaetiqueta'

    def __str__(self):
        return self.nombre

class Encuesta(models.Model):
    MODALIDAD_CHOICES = [
        ('al_finalizar', 'Al terminar la reunión (En pantalla / Tótem)'),
        ('correo', 'Enviar al correo electrónico'),
    ]
    TIPO_CHOICES = [
        ('interna', 'Encuesta INACAP (Estrellas y Opinión)'),
        ('externa', 'Encuesta de Otra Entidad (Archivo subido o Enlace)'),
    ]
    reunion = models.OneToOneField(Reunion, on_delete=models.CASCADE, related_name="encuesta")
    titulo = models.CharField(max_length=200, default="Encuesta de Satisfacción")
    tipo_encuesta = models.CharField(max_length=20, choices=TIPO_CHOICES, default='interna')
    archivo_encuesta = models.FileField(upload_to='encuestas_archivos/', null=True, blank=True, help_text="Archivo de encuesta entregado por la entidad externa (PDF, Word, Excel, etc.)")
    url_externa = models.URLField(max_length=500, blank=True, null=True, help_text="Enlace provisto por la entidad externa (Google Forms, MS Forms, etc.)")
    modalidad_entrega = models.CharField(max_length=20, choices=MODALIDAD_CHOICES, default='al_finalizar')
    pregunta_estrellas = models.CharField(max_length=250, default="¿Cómo calificarías tu experiencia general en este evento?")
    pregunta_opinion = models.CharField(max_length=250, default="¿Qué fue lo más destacado o qué sugerencias tienes para mejorar?")
    permitir_anonimo = models.BooleanField(default=True, help_text="Permite al participante enviar su opinión de forma anónima.")
    activa = models.BooleanField(default=True, help_text="Los usuarios solo pueden ver y responder encuestas activas.")
    enviada_por_correo = models.BooleanField(default=False)
    fecha_envio_correo = models.DateTimeField(null=True, blank=True)
    creada_en = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Encuesta: {self.titulo} ({self.reunion.detalle})"

    @property
    def total_respuestas(self):
        return self.respuestas.count()

    @property
    def promedio_puntuacion(self):
        from django.db.models import Avg
        avg = self.respuestas.aggregate(avg=Avg('puntuacion'))['avg']
        return round(avg, 1) if avg else 0

class RespuestaEncuesta(models.Model):
    PUNTUACION_CHOICES = [
        (1, '1 - Muy Malo'),
        (2, '2 - Malo'),
        (3, '3 - Regular'),
        (4, '4 - Bueno'),
        (5, '5 - Excelente'),
    ]
    encuesta = models.ForeignKey(Encuesta, on_delete=models.CASCADE, related_name="respuestas")
    usuario = models.ForeignKey('usuario.Usuario', on_delete=models.CASCADE, related_name="respuestas_encuesta")
    puntuacion = models.IntegerField(choices=PUNTUACION_CHOICES)
    comentarios = models.TextField(blank=True, null=True)
    es_anonimo = models.BooleanField(default=False, help_text="Si es anónimo, el nombre no se mostrará.")
    fecha_respuesta = models.DateTimeField(default=timezone.now)
    destacado = models.BooleanField(default=False, help_text="Marcar para mostrar como testimonio en la página de inicio.")

    class Meta:
        unique_together = ('encuesta', 'usuario')

class SoporteTicket(models.Model):
    ESTADO_CHOICES = [
        ('abierto', 'Abierto'),
        ('en_progreso', 'En Progreso'),
        ('cerrado', 'Cerrado'),
    ]

    usuario = models.ForeignKey('usuario.Usuario', on_delete=models.CASCADE, related_name='tickets_soporte')
    asunto = models.CharField(max_length=200)
    mensaje = models.TextField()
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='abierto', db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Ticket de {self.usuario.nombre}: {self.asunto}"

class TicketRespuesta(models.Model):
    ticket = models.ForeignKey(SoporteTicket, on_delete=models.CASCADE, related_name='respuestas')
    usuario = models.ForeignKey('usuario.Usuario', on_delete=models.CASCADE)
    mensaje = models.TextField()
    imagen = models.ImageField(upload_to='soporte_respuestas/', null=True, blank=True, verbose_name="Imagen Adjunta")
    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['fecha_creacion']

    def __str__(self):
        return f"Respuesta de {self.usuario.nombre} en ticket #{self.ticket.id}"

class GanadorSorteo(models.Model):
    ganador = models.ForeignKey('usuario.Usuario', on_delete=models.CASCADE, related_name='sorteos_ganados')
    fuente_participantes = models.CharField(max_length=255, help_text="Describe el grupo del que se seleccionó el ganador (Ej: 'Todos los Usuarios', 'Asistentes a Evento X')")
    fecha_sorteo = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Ganador de Sorteo"
        verbose_name_plural = "Ganadores de Sorteos"
        ordering = ['-fecha_sorteo']

    def __str__(self):
        return f"{self.ganador.nombre} {self.ganador.apellido} - {self.fecha_sorteo.strftime('%d/%m/%Y')}"
