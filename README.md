# 🏛️ Portal Oficial de Eventos y Asistencia - INACAP

Plataforma web institucional desarrollada en **Django** para la gestión ágil de eventos, inscripción de participantes en 1 solo clic con **RUT chileno**, generación automática de credenciales con **Código QR**, control de asistencia en tiempo real, ruleta de sorteos en vivo y carga masiva de nóminas vía **Excel**.

---

## ✨ Características Principales

1. **🔴 Identidad Visual Institucional INACAP:**
   - Paleta de colores oficial (`#B70420` / `#8B0014`), tipografía moderna (*Inter* y *Poppins*) y diseño responsivo.
   - Portal de inicio (`/`) con Hero a pantalla completa y cartelera de actividades.

2. **⚡ Inscripción Ágil y Sin Contraseñas para Asistentes:**
   - Inscripción con **RUT chileno** (validación matemática Módulo 11 y formateo en tiempo real con puntos y guion: `12.345.678-9`).
   - Generación instantánea del **Código QR** en pantalla con descarga en formato PNG.

3. **📊 Asistente de Carga Masiva Excel en 3 Pasos:**
   - **Paso 1:** Selección/arrastre de archivo `.xlsx` con plantilla oficial descargable.
   - **Paso 2:** Previsualización y tabla editable en vivo con métricas de validación (*Válidos*, *Alertas*, *Errores*).
   - **Paso 3:** Importación por lotes con barra de progreso animada en tiempo real.

4. **📱 Control de Asistencia y Modo Tótem:**
   - Escaneo de Códigos QR mediante cámara web o lector físico de códigos de barra.
   - Modo Tótem autoservicio para acreditación en accesos y entradas de recintos.

5. **📥 Exportación de Reportes a Excel:**
   - Descarga de nóminas completas de usuarios y listas de asistentes por evento con encabezados y diseño INACAP.

6. **🎁 Ruleta de Sorteos en Vivo:**
   - Realización de sorteos interactivos y dinámicos entre los asistentes presentes.

---

## 🛠️ Instalación y Puesta en Marcha

### 1. Clonar el repositorio
```bash
git clone https://github.com/Litjoaco/inacap.git
cd inacap
```

### 2. Crear y activar entorno virtual
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / Mac
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Aplicar migraciones
```bash
python manage.py migrate
```

### 5. Iniciar el servidor local
```bash
python manage.py runserver
```

El proyecto estará disponible en: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## 🔑 Credenciales de Administrador (Demo)

* **URL de Acceso:** [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/)
* **Email:** `admin@inacap.cl`
* **Contraseña:** `Admin1234!`
* **RUT:** `11.111.111-1`

---

## 📂 Estructura del Proyecto

```text
inacap_proyecto/
├── Inacap/              # Configuración principal del proyecto Django (settings, urls)
├── login/               # Aplicación y vistas de autenticación
├── paneladm/            # Panel de control administrativo, eventos, QR y carga masiva
├── usuario/             # Modelo de usuario personalizado, formularios y utilidades de RUT
├── static/              # Archivos estáticos (CSS, JS, logos institucionales)
├── templates/           # Plantillas HTML optimizadas
├── media/               # Códigos QR y archivos cargados
├── requirements.txt     # Dependencias de Python
└── manage.py
```

---

© 2026 INACAP. Todos los derechos reservados.
