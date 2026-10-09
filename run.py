import os
import math
import secrets
from functools import wraps
from uuid import uuid4
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from supabase import create_client
from werkzeug.utils import secure_filename


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

supabase = None

if SUPABASE_URL and SUPABASE_KEY:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


EXTENSIONES_PERMITIDAS = {"jpg", "jpeg", "png", "webp"}

TIPOS_IMAGEN = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}


def exigir_supabase():
    if supabase is None:
        raise RuntimeError(
            "Falta configurar la conexión con Supabase."
        )


def interpretar_disponibilidad(valor):
    if valor is None:
        return True

    if isinstance(valor, str):
        return valor.strip().lower() not in {
            "false", "0", "no", "off"
        }

    return bool(valor)


def interpretar_destacado(valor):
    if isinstance(valor, str):
        return valor.strip().lower() in {
            "true", "1", "sí", "si", "on", "yes"
        }

    return bool(valor)


def generar_csrf():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = generar_csrf


def validar_csrf():
    token_sesion = session.get("csrf_token", "")
    token_formulario = request.form.get("csrf_token", "")

    if (
        not token_sesion
        or not token_formulario
        or not secrets.compare_digest(
            token_sesion,
            token_formulario,
        )
    ):
        abort(400, description="Formulario de seguridad inválido.")


def administrador_requerido(funcion):
    @wraps(funcion)
    def envoltura(*args, **kwargs):
        if not session.get("administrador"):
            return redirect(url_for("admin_login"))

        return funcion(*args, **kwargs)

    return envoltura


def normalizar_producto(producto):
    producto["disponible"] = interpretar_disponibilidad(
        producto.get("disponible")
    )
    producto["destacado"] = interpretar_destacado(
        producto.get("destacado", False)
    )

    emojis = {
        "Hamburguesas": "🍔",
        "Perros calientes": "🌭",
        "Salchipapas": "🍟",
        "Acompañamientos": "🍟",
        "Bebidas": "🥤",
        "Combos": "🍟",
    }

    producto["emoji"] = emojis.get(
        producto.get("categoria"),
        "🍽️",
    )

    return producto


def obtener_productos():
    exigir_supabase()

    respuesta = (
        supabase.table("productos")
        .select("*")
        .order("id")
        .execute()
    )

    return [
        normalizar_producto(producto)
        for producto in (respuesta.data or [])
    ]


def obtener_producto(producto_id):
    exigir_supabase()

    respuesta = (
        supabase.table("productos")
        .select("*")
        .eq("id", producto_id)
        .limit(1)
        .execute()
    )

    if not respuesta.data:
        abort(404)

    return normalizar_producto(respuesta.data[0])


def subir_fotografia(archivo):
    if not archivo or not archivo.filename:
        return None

    nombre_seguro = secure_filename(archivo.filename)

    if "." not in nombre_seguro:
        raise ValueError(
            "El archivo no tiene una extensión válida."
        )

    extension = nombre_seguro.rsplit(".", 1)[1].lower()

    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValueError(
            "Usa una imagen JPG, JPEG, PNG o WEBP."
        )

    contenido = archivo.read()

    if not contenido:
        raise ValueError("La imagen está vacía.")

    firmas = {
        "jpg": (b"\xff\xd8\xff",),
        "jpeg": (b"\xff\xd8\xff",),
        "png": (b"\x89PNG\r\n\x1a\n",),
        "webp": (b"RIFF",),
    }

    if not any(
        contenido.startswith(firma)
        for firma in firmas[extension]
    ):
        raise ValueError(
            "El contenido no coincide con la imagen."
        )

    if extension == "webp" and contenido[8:12] != b"WEBP":
        raise ValueError("El archivo WEBP no es válido.")

    nombre_archivo = f"{uuid4().hex}.{extension}"
    ruta = f"productos/{nombre_archivo}"

    exigir_supabase()

    supabase.storage.from_("productos").upload(
        ruta,
        contenido,
        file_options={
            "content-type": TIPOS_IMAGEN[extension],
            "upsert": "false",
        },
    )

    return supabase.storage.from_(
        "productos"
    ).get_public_url(ruta)


def eliminar_fotografia_si_es_de_aloha(url_foto):
    if not url_foto or not SUPABASE_URL or supabase is None:
        return

    try:
        ruta_url = urlparse(url_foto).path
        prefijo = "/storage/v1/object/public/productos/"

        if prefijo not in ruta_url:
            return

        ruta_archivo = unquote(
            ruta_url.split(prefijo, 1)[1]
        )

        if ruta_archivo:
            supabase.storage.from_("productos").remove(
                [ruta_archivo]
            )

    except Exception:
        app.logger.exception(
            "No se pudo eliminar una imagen de Storage."
        )


# ==================================================
# TIENDA PÚBLICA
# ==================================================

@app.route("/")
def inicio():
    error_productos = False

    try:
        todos = obtener_productos()

        productos = [
            producto
            for producto in todos
            if producto["disponible"]
        ]

        categorias = list(
            dict.fromkeys(
                producto["categoria"]
                for producto in productos
                if producto.get("categoria")
                and producto["categoria"].strip().lower()
                != "combos"
            )
        )

    except Exception:
        app.logger.exception(
            "No se pudieron cargar los productos de la tienda."
        )

        productos = []
        categorias = []
        error_productos = True

    return render_template(
        "index.html",
        productos=productos,
        categorias=categorias,
        error_productos=error_productos,
    )


# ==================================================
# INICIO DE SESIÓN
# ==================================================

@app.route("/admin/login", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
def admin_login():
    if (
        not app.secret_key
        or not ADMIN_USERNAME
        or not ADMIN_PASSWORD
    ):
        return (
            "Falta configurar FLASK_SECRET_KEY, "
            "ADMIN_USERNAME y ADMIN_PASSWORD en .env.",
            500,
        )

    if request.method == "GET":
        session.clear()
        generar_csrf()

    if request.method == "POST":
        validar_csrf()

        usuario = request.form.get("usuario", "")
        contrasena = request.form.get("contrasena", "")

        usuario_correcto = secrets.compare_digest(
            usuario, ADMIN_USERNAME
        )
        contrasena_correcta = secrets.compare_digest(
            contrasena, ADMIN_PASSWORD
        )

        if usuario_correcto and contrasena_correcta:
            session.clear()
            session["administrador"] = True
            session["csrf_token"] = secrets.token_urlsafe(32)

            return redirect(url_for("admin_dashboard"))

        flash("Usuario o contraseña incorrectos.", "error")

    return render_template("admin_login.html")


# ==================================================
# CERRAR SESIÓN
# ==================================================

@app.route("/admin/logout", methods=["POST"])
@administrador_requerido
def admin_logout():
    validar_csrf()
    session.clear()
    return redirect(url_for("admin_login"))


# ==================================================
# /admin SIEMPRE DEVUELVE 404
# ==================================================

@app.route("/admin")
def admin_ruta_no_encontrada():
    abort(404)


# ==================================================
# PANEL PROTEGIDO
# ==================================================

@app.route("/panel")
@administrador_requerido
def admin_dashboard():
    try:
        productos = obtener_productos()
        error_carga = False

    except Exception:
        app.logger.exception(
            "No se pudieron cargar los productos del administrador."
        )
        flash("No se pudieron cargar los productos.", "error")
        productos = []
        error_carga = True

    return render_template(
        "admin_dashboard.html",
        productos=productos,
        error_carga=error_carga,
    )


# ==================================================
# CREAR PRODUCTO
# ==================================================

@app.route("/admin/productos/nuevo", methods=["GET", "POST"])
@administrador_requerido
def admin_producto_nuevo():
    if request.method == "POST":
        validar_csrf()

        referencia = request.form.get(
            "referencia", ""
        ).strip().upper()
        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get(
            "descripcion", ""
        ).strip()
        categoria = request.form.get("categoria", "").strip()
        precio_texto = request.form.get("precio", "").strip()

        # CORREGIDO: el formulario usa value="true".
        # Si la casilla está desmarcada, el valor será False.
        destacado = interpretar_destacado(
            request.form.get("destacado", False)
        )

        if not referencia or not nombre or not categoria:
            flash(
                "Referencia, nombre y categoría son obligatorios.",
                "error",
            )
            return render_template(
                "admin_form.html",
                modo="nuevo",
                producto={
                    **request.form,
                    "destacado": destacado,
                },
            )

        try:
            precio = float(precio_texto)

            if not math.isfinite(precio) or precio < 0:
                raise ValueError

        except (ValueError, TypeError):
            flash("Introduce un precio válido.", "error")
            return render_template(
                "admin_form.html",
                modo="nuevo",
                producto={
                    **request.form,
                    "destacado": destacado,
                },
            )

        try:
            exigir_supabase()

            fotografia = subir_fotografia(
                request.files.get("foto")
            )

            datos = {
                "referencia": referencia,
                "nombre": nombre,
                "descripcion": descripcion,
                "precio": precio,
                "categoria": categoria,
                "foto": fotografia,
                "disponible": True,
                "destacado": destacado,
            }

            supabase.table("productos").insert(datos).execute()

            flash("Producto creado correctamente.", "success")
            return redirect(url_for("admin_dashboard"))

        except Exception:
            app.logger.exception("Error creando producto.")
            flash(
                "No se pudo crear el producto. Comprueba que "
                "la referencia no exista y revisa Supabase.",
                "error",
            )
            return render_template(
                "admin_form.html",
                modo="nuevo",
                producto={
                    **request.form,
                    "destacado": destacado,
                },
            )

    return render_template(
        "admin_form.html",
        modo="nuevo",
        producto={},
    )


# ==================================================
# EDITAR PRODUCTO
# ==================================================

@app.route(
    "/admin/productos/<int:producto_id>/editar",
    methods=["GET", "POST"],
)
@administrador_requerido
def admin_producto_editar(producto_id):
    producto = obtener_producto(producto_id)

    if request.method == "POST":
        validar_csrf()

        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get(
            "descripcion", ""
        ).strip()
        categoria = request.form.get("categoria", "").strip()
        precio_texto = request.form.get("precio", "").strip()

        # CORREGIDO: interpreta true/on/1 y guarda False
        # cuando la casilla está desmarcada.
        destacado = interpretar_destacado(
            request.form.get("destacado", False)
        )

        if not nombre or not categoria:
            flash(
                "Nombre y categoría son obligatorios.",
                "error",
            )
            return render_template(
                "admin_form.html",
                modo="editar",
                producto={
                    **producto,
                    **request.form,
                    "destacado": destacado,
                },
            )

        try:
            precio = float(precio_texto)

            if not math.isfinite(precio) or precio < 0:
                raise ValueError

        except (ValueError, TypeError):
            flash("Introduce un precio válido.", "error")
            return render_template(
                "admin_form.html",
                modo="editar",
                producto={
                    **producto,
                    **request.form,
                    "destacado": destacado,
                },
            )

        try:
            fotografia = subir_fotografia(
                request.files.get("foto")
            )

            datos = {
                "nombre": nombre,
                "descripcion": descripcion,
                "precio": precio,
                "categoria": categoria,
                "destacado": destacado,
            }

            if fotografia:
                datos["foto"] = fotografia

            exigir_supabase()

            (
                supabase.table("productos")
                .update(datos)
                .eq("id", producto_id)
                .execute()
            )

            if fotografia:
                eliminar_fotografia_si_es_de_aloha(
                    producto.get("foto")
                )

            flash("Producto actualizado correctamente.", "success")
            return redirect(url_for("admin_dashboard"))

        except Exception:
            app.logger.exception("Error editando producto.")
            flash(
                "No se pudo actualizar el producto. "
                "Revisa Supabase y Storage.",
                "error",
            )
            return render_template(
                "admin_form.html",
                modo="editar",
                producto={
                    **producto,
                    **request.form,
                    "destacado": destacado,
                },
            )

    return render_template(
        "admin_form.html",
        modo="editar",
        producto=producto,
    )


# ==================================================
# CAMBIAR DISPONIBILIDAD
# ==================================================

@app.route(
    "/admin/productos/<int:producto_id>/disponibilidad",
    methods=["POST"],
)
@administrador_requerido
def admin_producto_disponibilidad(producto_id):
    validar_csrf()

    try:
        producto = obtener_producto(producto_id)
        nueva_disponibilidad = not producto["disponible"]

        (
            supabase.table("productos")
            .update({"disponible": nueva_disponibilidad})
            .eq("id", producto_id)
            .execute()
        )

        flash("Disponibilidad actualizada.", "success")

    except Exception:
        app.logger.exception(
            "Error cambiando disponibilidad."
        )
        flash(
            "No se pudo cambiar la disponibilidad.",
            "error",
        )

    return redirect(url_for("admin_dashboard"))


# ==================================================
# ELIMINAR PRODUCTO
# ==================================================

@app.route(
    "/admin/productos/<int:producto_id>/eliminar",
    methods=["POST"],
)
@administrador_requerido
def admin_producto_eliminar(producto_id):
    validar_csrf()

    try:
        producto = obtener_producto(producto_id)

        (
            supabase.table("productos")
            .delete()
            .eq("id", producto_id)
            .execute()
        )

        eliminar_fotografia_si_es_de_aloha(
            producto.get("foto")
        )

        flash(
            f"Producto «{producto.get('nombre', '')}» eliminado.",
            "success",
        )

    except Exception:
        app.logger.exception("Error eliminando producto.")
        flash(
            "No se pudo eliminar el producto. "
            "Comprueba los permisos de Supabase.",
            "error",
        )

    return redirect(url_for("admin_dashboard"))


# ==================================================
# ARCHIVO DEMASIADO GRANDE
# ==================================================

@app.errorhandler(413)
def archivo_demasiado_grande(_error):
    return (
        "La imagen supera el límite permitido de 5 MB. "
        "Reduce su tamaño e inténtalo de nuevo.",
        413,
    )


if __name__ == "__main__":
    if not app.secret_key:
        raise RuntimeError(
            "Debes configurar FLASK_SECRET_KEY en el archivo .env."
        )

    app.run(debug=True)