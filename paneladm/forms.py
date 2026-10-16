from django import forms
from .models import Reunion, Encuesta, SoporteTicket, TicketRespuesta, EtiquetaPlantilla

class ReunionForm(forms.ModelForm):
    class Meta:
        model = Reunion
        fields = [
            'detalle', 
            'descripcion', 
            'fecha', 
            'ubicacion', 
            'direccion', 
            'imagen', 
            'imprimir_etiqueta_al_asistir',
            'plantilla_etiqueta',
            'aforo_maximo',
        ]
        widgets = {
            'detalle': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Seminario de Innovación Tecnológica'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Descripción del evento...'}),
            'fecha': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'ubicacion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Auditorio Sede Santiago Sur'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Av. Vicuña Mackenna 3864'}),
            'imagen': forms.FileInput(attrs={'class': 'form-control'}),
            'imprimir_etiqueta_al_asistir': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'plantilla_etiqueta': forms.Select(attrs={'class': 'form-select'}),
            'aforo_maximo': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 150 (opcional, sin límite si está vacío)', 'min': '1'}),
        }
        help_texts = {
            'imprimir_etiqueta_al_asistir': None,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['plantilla_etiqueta'].empty_label = "-- Usar diseño por defecto INACAP --"

class EtiquetaPlantillaForm(forms.ModelForm):
    ELEMENTOS_CHOICES = [
        ('nombre_completo', 'Nombre Completo del Participante'),
        ('carrera', 'Carrera / Especialidad'),
        ('sede', 'Sede INACAP'),
        ('rubro', 'Rol / Rubro'),
        ('nombre_reunion', 'Nombre del Evento / Reunión'),
        ('asistencias', 'Cantidad de Asistencias'),
        ('emojis', 'Emojis de Identificación'),
        ('texto_extra', 'Texto Personalizado'),
    ]
    
    orden_elementos = forms.MultipleChoiceField(
        choices=ELEMENTOS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input me-2'}),
        label="Elementos a mostrar en la etiqueta",
        help_text="Selecciona los elementos que aparecerán en la credencial.",
        required=True
    )
    class Meta:
        model = EtiquetaPlantilla
        fields = ['nombre', 'logo', 'nombre_reunion_ejemplo', 'texto_extra']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Credencial Alumnos 2026'}),
            'logo': forms.ClearableFileInput(attrs={'class': 'form-control'}),
            'nombre_reunion_ejemplo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Feria de Empleabilidad'}),
            'texto_extra': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: ¡Asistente Confirmado!'}),
        }
        labels = {
            'texto_extra': 'Texto Personalizado (Opcional)',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.orden_elementos:
            self.initial['orden_elementos'] = self.instance.orden_elementos
        elif not self.instance.pk:
            self.initial['orden_elementos'] = ['nombre_completo', 'carrera', 'sede', 'asistencias']

    def clean_orden_elementos(self):
        elementos = self.cleaned_data.get('orden_elementos')
        if not elementos:
            raise forms.ValidationError("Debes seleccionar al menos un elemento para la etiqueta.")
        return list(elementos)

class EncuestaForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            reuniones_con_encuesta = Encuesta.objects.values_list('reunion_id', flat=True)
            self.fields['reunion'].queryset = Reunion.objects.exclude(id__in=reuniones_con_encuesta).order_by('-fecha')
        else:
            self.fields['reunion'].queryset = Reunion.objects.filter(id=self.instance.reunion_id)

    class Meta:
        model = Encuesta
        fields = ['reunion', 'titulo', 'tipo_encuesta', 'archivo_encuesta', 'url_externa', 'modalidad_entrega', 'pregunta_estrellas', 'pregunta_opinion', 'permitir_anonimo', 'activa']
        widgets = {
            'reunion': forms.Select(attrs={'class': 'form-select'}),
            'titulo': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Encuesta de Satisfacción'}),
            'tipo_encuesta': forms.Select(attrs={'class': 'form-select', 'id': 'id_tipo_encuesta'}),
            'archivo_encuesta': forms.FileInput(attrs={'class': 'form-control', 'accept': '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg'}),
            'url_externa': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://forms.google.com/... o enlace provisto por la entidad'}),
            'modalidad_entrega': forms.RadioSelect(attrs={'class': 'btn-check'}),
            'pregunta_estrellas': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '¿Cómo calificarías tu experiencia general en este evento?'}),
            'pregunta_opinion': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '¿Qué fue lo más destacado o qué sugerencias tienes para mejorar?'}),
            'permitir_anonimo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'activa': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class SoporteTicketForm(forms.ModelForm):
    class Meta:
        model = SoporteTicket
        fields = ['asunto', 'mensaje']
        widgets = {
            'asunto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Problema al editar mi perfil'}),
            'mensaje': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Describe tu problema o consulta con el mayor detalle posible.'}),
        }

class SoporteTicketAdminForm(forms.ModelForm):
    class Meta:
        model = SoporteTicket
        fields = ['estado']
        widgets = {
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }

class TicketRespuestaForm(forms.ModelForm):
    class Meta:
        model = TicketRespuesta
        fields = ['mensaje', 'imagen']
        widgets = {
            'mensaje': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Escribe tu respuesta...'}),
            'imagen': forms.FileInput(attrs={'class': 'd-none'}),
        }
        labels = {
            'mensaje': ''
        }
