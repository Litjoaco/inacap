# -*- coding: utf-8 -*-
import os
import django
from collections import defaultdict

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Inacap.settings')
django.setup()

from usuario.models import Usuario

def normalize_existing_ruts():
    """
    Recorre todos los usuarios y normaliza su campo RUT al formato limpio
    (sin puntos ni guiones), manejando de forma segura los posibles conflictos
    por duplicados.
    """
    print("Iniciando la normalización de RUTs existentes (Modo Seguro)...")
    
    usuarios_a_actualizar = []
    conflictos = defaultdict(list)
    ruts_ya_limpios = set(Usuario.objects.values_list('rut', flat=True))

    todos_los_usuarios = Usuario.objects.all().order_by('id')
    total_usuarios = todos_los_usuarios.count()

    for i, usuario in enumerate(todos_los_usuarios):
        rut_original = usuario.rut
        if not rut_original:
            continue

        rut_limpio = str(rut_original).upper().replace(".", "").replace("-", "")

        if rut_limpio == rut_original:
            continue

        print(f"[{i+1}/{total_usuarios}] Analizando Usuario ID {usuario.id} ({usuario.email}): RUT '{rut_original}' -> '{rut_limpio}'")

        if rut_limpio in ruts_ya_limpios:
            print(f"  -> ¡CONFLICTO! El RUT normalizado '{rut_limpio}' ya existe en otro usuario. Omitiendo actualización.")
            conflictos[rut_limpio].append({'id': usuario.id, 'email': usuario.email, 'rut_original': rut_original})
            if not any(u.get('id') == usuario.id for u in conflictos[rut_limpio]):
                 usuarios_existentes = Usuario.objects.filter(rut=rut_limpio)
                 for u_existente in usuarios_existentes:
                     conflictos[rut_limpio].append({'id': u_existente.id, 'email': u_existente.email, 'rut_original': u_existente.rut})
            continue

        usuario.rut = rut_limpio
        usuarios_a_actualizar.append(usuario)
        ruts_ya_limpios.add(rut_limpio)

    if usuarios_a_actualizar:
        print(f"\nActualizando {len(usuarios_a_actualizar)} usuarios en la base de datos...")
        Usuario.objects.bulk_update(usuarios_a_actualizar, ['rut'])
        print("¡Actualización masiva completada!")
    else:
        print("\nNo se encontraron RUTs que necesitaran normalización.")

    if conflictos:
        print("\n" + "="*50)
        print("¡ATENCIÓN! SE ENCONTRARON CONFLICTOS DE RUT DUPLICADOS:")
        for rut, users in conflictos.items():
            print(f"\n--- RUT en conflicto: {rut} ---")
            usuarios_mostrados = set()
            for u in users:
                if u['id'] not in usuarios_mostrados:
                    print(f"  - Usuario ID: {u['id']}, Email: {u['email']}, RUT: '{u['rut_original']}'")
                    usuarios_mostrados.add(u['id'])
        print("="*50)
    else:
        print("\n¡Excelente! No se encontraron conflictos.")

if __name__ == '__main__':
    normalize_existing_ruts()
