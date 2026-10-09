import os
from datetime import datetime, timezone

from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)


def generar_hash(contrasena):
    """Genera un hash seguro de una contraseña."""
    return generate_password_hash(
        contrasena,
        method="scrypt",
    )


def verificar_hash(contrasena, hash_guardado):
    """Verifica una contraseña sin almacenarla en texto plano."""
    if not contrasena or not hash_guardado:
        return False

    try:
        return check_password_hash(
            hash_guardado,
            contrasena,
        )
    except (ValueError, TypeError):
        return False


def credenciales_iniciales():
    """Lee las credenciales iniciales de las variables de entorno."""
    return {
        "usuario": os.getenv("ADMIN_USERNAME", "").strip(),
        "contrasena": os.getenv("ADMIN_PASSWORD", ""),
    }


def obtener_configuracion(supabase):
    """
    Obtiene la configuración administrativa.

    Si todavía no existe, la crea con las credenciales iniciales
    del entorno. Nunca reemplaza una configuración existente.
    """
    respuesta = (
        supabase.table("configuracion_admin")
        .select("id, usuario, password_hash")
        .limit(1)
        .execute()
    )

    if respuesta.data:
        return respuesta.data[0]

    iniciales = credenciales_iniciales()
    usuario = iniciales["usuario"]
    contrasena = iniciales["contrasena"]

    if not usuario or not contrasena:
        raise RuntimeError(
            "Faltan las credenciales iniciales del administrador."
        )

    datos = {
        "usuario": usuario,
        "password_hash": generar_hash(contrasena),
    }

    try:
        (
            supabase.table("configuracion_admin")
            .insert(datos)
            .execute()
        )

    except Exception:
        # Puede que otra petición haya creado el registro
        # al mismo tiempo. Comprobamos antes de informar del error.
        respuesta = (
            supabase.table("configuracion_admin")
            .select("id, usuario, password_hash")
            .limit(1)
            .execute()
        )

        if respuesta.data:
            return respuesta.data[0]

        raise

    respuesta = (
        supabase.table("configuracion_admin")
        .select("id, usuario, password_hash")
        .limit(1)
        .execute()
    )

    if not respuesta.data:
        raise RuntimeError(
            "No se pudo inicializar la cuenta administrativa."
        )

    return respuesta.data[0]


def autenticar_administrador(supabase, usuario, contrasena):
    """Comprueba las credenciales almacenadas en Supabase."""
    configuracion = obtener_configuracion(supabase)

    usuario_correcto = (
        isinstance(usuario, str)
        and usuario == configuracion["usuario"]
    )

    contrasena_correcta = verificar_hash(
        contrasena,
        configuracion["password_hash"],
    )

    return usuario_correcto and contrasena_correcta


def actualizar_credenciales(
    supabase,
    configuracion_id,
    nuevo_usuario,
    nueva_contrasena=None,
):
    """Actualiza el usuario y, si se indica, el hash de contraseña."""
    datos = {
        "usuario": nuevo_usuario,
        "actualizado_en": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    if nueva_contrasena is not None:
        datos["password_hash"] = generar_hash(
            nueva_contrasena
        )

    respuesta = (
        supabase.table("configuracion_admin")
        .update(datos)
        .eq("id", configuracion_id)
        .execute()
    )

    if not respuesta.data:
        # Verifica que el registro siga existiendo y que
        # la actualización no haya fallado silenciosamente.
        comprobacion = (
            supabase.table("configuracion_admin")
            .select("id, usuario, password_hash")
            .eq("id", configuracion_id)
            .limit(1)
            .execute()
        )

        if not comprobacion.data:
            raise RuntimeError(
                "No se encontró la configuración administrativa."
            )

    return True