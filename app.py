import os
import io
from datetime import datetime, date

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text


@st.cache_resource
def get_engine():
    return create_engine(
        st.secrets["db"]["url"],
        pool_pre_ping=True,
        pool_recycle=280,
    )


def qdf(sql: str, params: dict | None = None) -> pd.DataFrame:
    with get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or {})


def exec_(sql: str, params: dict | None = None):
    with get_engine().begin() as conn:
        conn.execute(text(sql), params or {})


def init_schema():
    exec_("""
        CREATE TABLE IF NOT EXISTS productos (
            id bigserial PRIMARY KEY,
            nombre text NOT NULL UNIQUE,
            categoria text,
            unidad text,
            proveedor text,
            activo boolean NOT NULL DEFAULT true,
            creado_en timestamptz NOT NULL DEFAULT now(),
            actualizado_en timestamptz NOT NULL DEFAULT now()
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS faltantes (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            producto text NOT NULL,
            categoria text,
            cantidad double precision,
            unidad text,
            prioridad text,
            sector text,
            proveedor text,
            estado text NOT NULL,
            notas text
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            fecha date NOT NULL DEFAULT current_date,
            estados_incluidos text,
            texto_wp text
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS pedido_items (
            id bigserial PRIMARY KEY,
            pedido_id bigint NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            faltante_id bigint,
            producto text,
            categoria text,
            cantidad double precision,
            unidad text,
            sector text,
            proveedor text,
            estado text,
            prioridad text,
            creado_en timestamptz NOT NULL DEFAULT now()
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            usuario text,
            rol text,
            faltante_id bigint NOT NULL,
            accion text NOT NULL,
            estado_anterior text,
            estado_nuevo text,
            nota text
        );
    """)


@st.cache_resource
def ensure_schema():
    init_schema()
    return True


# --- IMPORTANTE: esto va DESPUÉS de definir get_engine/exec_/init_schema ---
ensure_schema()


st.set_page_config(
    page_title="Faltantes",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ============================================================
# AUTH (Login + Roles) - usa .streamlit/secrets.toml
# ============================================================
def require_login():
    if "auth" not in st.session_state:
        st.session_state.auth = {"logged": False, "user": None, "role": None}

    if st.session_state.auth["logged"]:
        return

    st.markdown("## 🔐 Iniciar sesión")
    st.caption("Ingresá usuario y clave para acceder.")

    u = st.text_input("Usuario", key="login_user")
    p = st.text_input("Clave", type="password", key="login_pass")

    if st.button("Entrar", use_container_width=True, key="login_btn"):
        try:
            users = st.secrets["auth"]["users"]
        except Exception:
            st.error("Falta configurar .streamlit/secrets.toml (sección [auth]).")
            st.stop()

        ok = None
        for item in users:
            if item.get("user") == u and item.get("pass") == p:
                ok = item
                break

        if ok:
            st.session_state.auth = {
                "logged": True,
                "user": ok["user"],
                "role": ok.get("role", "Admin"),
            }
            st.rerun()
        else:
            st.error("Usuario o clave incorrectos.")

    st.stop()


require_login()



# ============================================================
# UI config
# ============================================================


# Defaults
CATEGORIAS = ["Almacén", "Verdulería", "Fiambre", "Carnicería", "Pescaderia", "Limpieza", "Descartables", "Bebidas",  "Panaderia", "Otros"]
PRIORIDAD = ["Alta", "Media", "Baja"]
ESTADOS = ["Pendiente", "Pedido", "Recibido", "Anulado"]
SECTORES = ["Cocina", "Barra", "Salón"]
UNIDADES = ["und", "caja", "kg", "atado", "lt", "pack", "bolsa"]

# Premium Dark CSS (sin img global para no cortar logos)
st.markdown("""
<style>
body { background-color: #0f172a; }

.block-container { padding-top: 3rem !important; padding-bottom: 2rem !important; }
h1 { margin-top: 0.5rem !important; padding-top: 0.25rem !important; }

/* Card premium */
.card {
    background: linear-gradient(145deg, #111827, #0f172a);
    border: 1px solid #1f2937;
    border-radius: 16px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: 0px 6px 20px rgba(0,0,0,0.45);
    transition: 0.2s ease-in-out;
}
.card:hover { transform: translateY(-2px); box-shadow: 0px 8px 25px rgba(0,0,0,0.6); }

/* Badges */
.badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 999px;
    font-size: 0.75rem;
    margin-right: 6px;
    font-weight: 700;
    background-color: #111827;
    border: 1px solid #334155;
    color: #f1f5f9;
}
.badge-pendiente { background-color: #f59e0b; color: #000; border: 0; }
.badge-pedido    { background-color: #3b82f6; color: #fff; border: 0; }
.badge-recibido  { background-color: #10b981; color: #000; border: 0; }
.badge-anulado   { background-color: #ef4444; color: #fff; border: 0; }

.small { font-size: 0.85rem; color: #cbd5e1; }

/* Buttons */
.stButton > button {
    border-radius: 10px;
    font-weight: 700;
    background-color: #1f2937;
    border: 1px solid #374151;
    color: #f1f5f9;
    transition: 0.2s ease-in-out;
}
.stButton > button:hover { background-color: #2563eb; border-color: #2563eb; }

/* Tabs */
button[role="tab"] { font-weight: 700; color: #94a3b8; }
button[aria-selected="true"] { color: #00bcd4 !important; }

/* Inputs / Labels ULTRA legibles */
label, .stMarkdown, .stTextInput label, .stSelectbox label, .stNumberInput label, .stTextArea label {
    color: #e2e8f0 !important;
    font-weight: 700 !important;
}
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea textarea {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    padding: 10px 12px !important;
}
.stTextInput input::placeholder,
.stTextArea textarea::placeholder {
    color: #94a3b8 !important;
    opacity: 1 !important;
}
.stSelectbox > div > div {
    background-color: #1e293b !important;
    border: 1px solid #334155 !important;
    border-radius: 10px !important;
    color: #ffffff !important;
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border: 1px solid #00bcd4 !important;
    box-shadow: 0 0 0 2px rgba(0,188,212,0.35) !important;
    outline: none !important;
}
</style>
""", unsafe_allow_html=True)

try:
    with get_engine().connect() as c:
        c.execute(text("select 1"))
    st.success("✅ Conectado a Supabase OK")
except Exception as e:
    st.error(f"❌ No conecta: {e}")
    st.stop()

def init_schema():
    # OJO: en Supabase puede requerir permisos. Ideal hacerlo en SQL Editor.
    exec_("""
        CREATE TABLE IF NOT EXISTS productos (
            id bigserial PRIMARY KEY,
            nombre text NOT NULL UNIQUE,
            categoria text,
            unidad text,
            proveedor text,
            activo boolean NOT NULL DEFAULT true,
            creado_en timestamptz NOT NULL DEFAULT now(),
            actualizado_en timestamptz NOT NULL DEFAULT now()
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS faltantes (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            producto text NOT NULL,
            categoria text,
            cantidad double precision,
            unidad text,
            prioridad text,
            sector text,
            proveedor text,
            estado text NOT NULL,
            notas text
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            fecha date NOT NULL DEFAULT current_date,
            estados_incluidos text,
            texto_wp text
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS pedido_items (
            id bigserial PRIMARY KEY,
            pedido_id bigint NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
            faltante_id bigint,
            producto text,
            categoria text,
            cantidad double precision,
            unidad text,
            sector text,
            proveedor text,
            estado text,
            prioridad text,
            creado_en timestamptz NOT NULL DEFAULT now()
        );
    """)

    exec_("""
        CREATE TABLE IF NOT EXISTS movimientos (
            id bigserial PRIMARY KEY,
            creado_en timestamptz NOT NULL DEFAULT now(),
            usuario text,
            rol text,
            faltante_id bigint NOT NULL,
            accion text NOT NULL,
            estado_anterior text,
            estado_nuevo text,
            nota text
        );
    """)


def log_mov(faltante_id: int, accion: str, estado_anterior: str = "", estado_nuevo: str = "", nota: str = ""):
    auth = st.session_state.get("auth", {})
    exec_("""
        INSERT INTO movimientos (usuario, rol, faltante_id, accion, estado_anterior, estado_nuevo, nota)
        VALUES (:usuario, :rol, :fid, :accion, :ea, :en, :nota)
    """, {
        "usuario": auth.get("user"),
        "rol": auth.get("role"),
        "fid": int(faltante_id),
        "accion": accion,
        "ea": estado_anterior or "",
        "en": estado_nuevo or "",
        "nota": nota or "",
    })





# ============================================================
# Roles
# ============================================================
def sectores_permitidos():
    role = st.session_state.auth["role"]
    if role == "Admin":
        return SECTORES
    if role == "Cocina":
        return ["Cocina"]
    if role == "Barra":
        return ["Barra"]
    if role == "Salón":
        return ["Salón"]
    return SECTORES


# ============================================================
# Header (Logo opcional)
# ============================================================
c_logo, c_title, c_out = st.columns([1, 5, 1])

with c_logo:
    # Si no existe el logo, no rompe
    if os.path.exists("assets/logo_pad.png"):
        st.image("assets/logo_pad.png", width=70)
    elif os.path.exists("assets/logo.png"):
        st.image("assets/logo.png", width=70)

with c_title:
    st.markdown(
        """
        <h1 style="margin:0; font-size:40px;">Faltantes</h1>
        <p style="margin:0; color:#94a3b8; font-size:16px;">Sistema interno de control</p>
        """,
        unsafe_allow_html=True
    )
    st.caption(f"👤 {st.session_state.auth['user']}  |  Rol: {st.session_state.auth['role']}")

with c_out:
    if st.button("Salir", use_container_width=True, key="logout"):
        st.session_state.auth = {"logged": False, "user": None, "role": None}
        st.rerun()

tab1, tab2, tab3, tab4 = st.tabs(
    ["➕ Cargar", "📋 Pendientes", "📅 Pedidos ", "🛠 Productos / Backup "]
)


# ============================================================
# Maestro productos
# ============================================================
def load_product_master():
    df_prod = qdf("""
        SELECT nombre, categoria, unidad, proveedor
        FROM productos
        WHERE activo = true
        ORDER BY nombre
    """)
    productos = df_prod["nombre"].dropna().tolist() if not df_prod.empty else []
    prod_map = {r["nombre"]: r for _, r in df_prod.iterrows()} if not df_prod.empty else {}
    return productos, prod_map


def upsert_producto(nombre: str, categoria: str, unidad: str, proveedor: str) -> str:
    nombre = (nombre or "").strip()
    proveedor = (proveedor or "").strip()

    if not nombre:
        return categoria  # safety

    # Si existe, respetamos categoria guardada (bloqueo real)
    df_check = qdf(
        "SELECT categoria FROM productos WHERE nombre = :nombre LIMIT 1",
        {"nombre": nombre},
    )

    if df_check.empty:
        exec_("""
            INSERT INTO productos (nombre, categoria, unidad, proveedor, activo, creado_en, actualizado_en)
            VALUES (:nombre, :categoria, :unidad, :proveedor, true, now(), now())
        """, {
            "nombre": nombre,
            "categoria": categoria,
            "unidad": unidad,
            "proveedor": proveedor,
        })
        return categoria

    # Ya existe:
    categoria_guardada = (df_check.iloc[0]["categoria"] or "").strip()
    if categoria_guardada:
        categoria = categoria_guardada  # bloquea categoria

    # Actualizamos unidad/proveedor y timestamp (sin tocar categoria guardada)
    exec_("""
        UPDATE productos
        SET unidad = :unidad,
            proveedor = :proveedor,
            actualizado_en = now()
        WHERE nombre = :nombre
    """, {
        "unidad": unidad,
        "proveedor": proveedor,
        "nombre": nombre,
    })

    return categoria
# ============================================================
# TAB 1: Cargar (Supabase)
# ============================================================
with tab1:
    st.subheader("Nuevo faltante")

    productos_existentes, prod_map = load_product_master()

    with st.form("form_faltante", clear_on_submit=True):

        producto_sel = st.selectbox(
            "Producto (buscar y elegir)",
            options=[""] + productos_existentes,
            index=0,
            key="c_prod_sel"
        )

        producto_nuevo = st.text_input(
            "O escribir producto nuevo",
            placeholder="Ej: Coca 2.25L / Peceto / Servilletas",
            key="c_prod_new"
        )

        es_nuevo = bool((producto_nuevo or "").strip())
        producto = (producto_nuevo or "").strip() if es_nuevo else (producto_sel or "").strip()

        default_categoria = CATEGORIAS[0]
        default_unidad = UNIDADES[0]
        default_proveedor = ""

        if producto and producto in prod_map:
            default_categoria = prod_map[producto].get("categoria") or default_categoria
            default_unidad = prod_map[producto].get("unidad") or default_unidad
            default_proveedor = prod_map[producto].get("proveedor") or default_proveedor

        producto_en_maestro = (not es_nuevo) and (producto in prod_map)

        categoria = st.selectbox(
            "Categoría",
            CATEGORIAS,
            index=(CATEGORIAS.index(default_categoria) if default_categoria in CATEGORIAS else 0),
            key="c_categoria",
            disabled=producto_en_maestro
        )

        c1, c2 = st.columns(2)
        with c1:
            cantidad = st.number_input(
                "Cantidad (permite media caja)",
                min_value=0.0,
                value=1.0,
                step=0.5,
                format="%.2f",
                key="c_cantidad"
            )
        with c2:
            unidad = st.selectbox(
                "Unidad",
                UNIDADES,
                index=(UNIDADES.index(default_unidad) if default_unidad in UNIDADES else 0),
                key="c_unidad"
            )

        sectores = sectores_permitidos()
        sector = st.selectbox("Sector", sectores, index=0, key="c_sector")

        prioridad = st.selectbox("Prioridad", PRIORIDAD, index=0, key="c_prioridad")

        proveedor = st.text_input("Proveedor", value=default_proveedor, key="c_proveedor")
        notas = st.text_area("Notas", placeholder="Marca, presentación, alternativa aceptable, etc.", key="c_notas")

        st.text_input("Estado", value="Pendiente", disabled=True)

        guardar = st.form_submit_button("💾 Guardar", use_container_width=True)

    if guardar:
        if not (producto or "").strip():
            st.error("El campo Producto es obligatorio.")
        else:
            producto = producto.strip()
            proveedor = (proveedor or "").strip()
            notas = (notas or "").strip()

            # 1) Upsert en maestro (NO usa conn)
            categoria = upsert_producto(producto, categoria, unidad, proveedor)

            # 2) Si ya existe faltante abierto (Pendiente/Pedido) -> sumar cantidad
            df_exist = qdf("""
                SELECT id, cantidad
                FROM faltantes
                WHERE producto = :producto
                  AND categoria = :categoria
                  AND unidad = :unidad
                  AND sector = :sector
                  AND estado IN ('Pendiente','Pedido')
                ORDER BY id DESC
                LIMIT 1
            """, {
                "producto": producto,
                "categoria": categoria,
                "unidad": unidad,
                "sector": sector
            })

            if not df_exist.empty:
                fid = int(df_exist.iloc[0]["id"])
                cant_old = float(df_exist.iloc[0]["cantidad"] or 0)
                cant_new = cant_old + float(cantidad)

                exec_(
                    "UPDATE faltantes SET cantidad=:cantidad WHERE id=:id",
                    {"cantidad": cant_new, "id": fid}
                )

                # (opcional) log movimiento si tenés tabla movimientos
                # exec_("INSERT INTO movimientos (...) VALUES (...)", {...})

                st.success(f"✅ Ya existía → sumé cantidad: {cant_new:g} {unidad}")
                st.rerun()

            # 3) Insert nuevo faltante
            exec_("""
                INSERT INTO faltantes
                (creado_en, producto, categoria, cantidad, unidad, prioridad, sector, proveedor, estado, notas)
                VALUES
                (now(), :producto, :categoria, :cantidad, :unidad, :prioridad, :sector, :proveedor, 'Pendiente', :notas)
            """, {
                "producto": producto,
                "categoria": categoria,
                "cantidad": float(cantidad),
                "unidad": unidad,
                "prioridad": prioridad,
                "sector": sector,
                "proveedor": proveedor,
                "notas": notas
            })

            st.success("✅ Cargado correctamente")
            st.rerun()      


# ============================================================
# TAB 2: Lista + WhatsApp + Recibir Todo (Supabase)
# ============================================================
with tab2:
    sub1, sub2 = st.tabs(["📋 Lista", "🧾 Pedido WhatsApp"])

    # ---------- SUBTAB LISTA ----------
    with sub1:
        st.subheader("Lista")

        with st.expander("🔎 Filtros", expanded=False):
            role = st.session_state.auth["role"]
            is_admin = role == "Admin"

            f_estado = st.multiselect("Estado", ESTADOS, default=["Pendiente", "Pedido"], key="f_estado")

            if is_admin:
                f_sector = st.multiselect("Sector", SECTORES, default=[], key="f_sector")
            else:
                f_sector = []  # se filtra automático por rol

            f_categoria = st.multiselect("Categoría", CATEGORIAS, default=[], key="f_categoria")
            f_prioridad = st.multiselect("Prioridad", PRIORIDAD, default=[], key="f_prioridad")
            f_proveedor = st.text_input("Proveedor contiene", value="", key="f_proveedor")
            buscar = st.text_input("Buscar producto", value="", key="f_buscar")

        # Traer todo desde Supabase
        df = qdf("SELECT * FROM faltantes ORDER BY id DESC")

        # Filtro por rol automático
        role = st.session_state.auth["role"]
        if role in ["Cocina", "Barra", "Salón"] and not df.empty:
            df = df[df["sector"] == role]

        # Apply filters
        if f_estado and not df.empty:
            df = df[df["estado"].isin(f_estado)]
        if f_sector and not df.empty:
            df = df[df["sector"].isin(f_sector)]
        if f_categoria and not df.empty:
            df = df[df["categoria"].isin(f_categoria)]
        if f_prioridad and not df.empty:
            df = df[df["prioridad"].isin(f_prioridad)]
        if f_proveedor.strip() and not df.empty:
            df = df[df["proveedor"].fillna("").str.contains(f_proveedor.strip(), case=False, na=False)]
        if buscar.strip() and not df.empty:
            df = df[df["producto"].fillna("").str.contains(buscar.strip(), case=False, na=False)]

        cA, cB, cC = st.columns(3)
        cA.metric("Pendientes", int((df["estado"] == "Pendiente").sum()) if not df.empty else 0)
        cB.metric("Pedido", int((df["estado"] == "Pedido").sum()) if not df.empty else 0)
        cC.metric("Total", int(len(df)))

        # Recibir todo lo que está en Pedido (sobre DF filtrado)
        df_pedido = df[df["estado"] == "Pedido"] if not df.empty else pd.DataFrame()
        if not df_pedido.empty:
            if st.button("📦 Recibir TODO el pedido", use_container_width=True, key="btn_recibir_todo"):
                ids = df_pedido["id"].astype(int).tolist()

                exec_("UPDATE faltantes SET estado='Recibido' WHERE id = ANY(:ids::bigint[])", {"ids": ids})

                for fid_ in ids:
                    log_mov(int(fid_), "RECIBIR_TODO", "Pedido", "Recibido")

                st.success(f"✅ {len(ids)} ítems marcados como Recibido.")
                st.rerun()

        st.divider()

        if df.empty:
            st.info("No hay faltantes con esos filtros.")
        else:
            is_admin = st.session_state.auth["role"] == "Admin"

            for _, row in df.iterrows():
                fid = int(row["id"])
                producto = row["producto"]
                sector = row["sector"]
                cantidad = row["cantidad"]
                unidad = row["unidad"]
                proveedor = row["proveedor"] if row["proveedor"] else "-"
                estado = str(row["estado"]).strip()
                prioridad = row["prioridad"] if row["prioridad"] else "-"
                categoria = row["categoria"] if row["categoria"] else "-"
                from zoneinfo import ZoneInfo

                creado = row["creado_en"]

                if creado:
                    creado = pd.to_datetime(creado)

                    # Si viene sin zona horaria, asumimos UTC
                    if creado.tzinfo is None:
                        creado = creado.tz_localize("UTC")

                    creado = creado.tz_convert("America/Argentina/Buenos_Aires")
                    creado = creado.strftime("%d/%m/%Y %H:%M hs")

                notas = row["notas"] if row["notas"] else ""

                estado_class = {
                    "Pendiente": "badge-pendiente",
                    "Pedido": "badge-pedido",
                    "Recibido": "badge-recibido",
                    "Anulado": "badge-anulado",
                }.get(estado, "")

                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown(f"### {producto}")

                st.markdown(
                    f'<span class="badge">🏷️ {categoria}</span> '
                    f'<span class="badge">📍 {sector}</span> '
                    f'<span class="badge">⚡ {prioridad}</span> '
                    f'<span class="badge {estado_class}">{estado}</span>',
                    unsafe_allow_html=True
                )

                st.markdown(
                    f"<div class='small'>🕒 {creado} | 📦 {float(cantidad or 0):g} {unidad} | 🚚 {proveedor}</div>",
                    unsafe_allow_html=True
                )
                if notas:
                    st.markdown(f"**Notas:** {notas}")

                role = st.session_state.auth["role"]
                is_admin = role == "Admin"

                b1, b2, b3 = st.columns(3)

                with b1:
                    if st.button("✅ Pedido", key=f"card_ped_{fid}", use_container_width=True,
                                disabled=(estado in ["Recibido", "Anulado"])):

                        exec_(
                            "UPDATE faltantes SET estado='Pedido' WHERE id=:id",
                            {"id": fid}
                        )

                        log_mov(fid, "CAMBIO_ESTADO", estado, "Pedido")
                        st.rerun()

                with b2:
                    if st.button("📦 Recibido", key=f"card_rec_{fid}", use_container_width=True,
                                disabled=(estado in ["Recibido", "Anulado"])):

                        exec_(
                            "UPDATE faltantes SET estado='Recibido' WHERE id=:id",
                            {"id": fid}
                        )

                        log_mov(fid, "CAMBIO_ESTADO", estado, "Recibido")
                        st.rerun()                
                with b3:
                    if is_admin:
                        if st.button("🗑️ Anular", key=f"card_anu_{fid}", use_container_width=True,
                                    disabled=(estado == "Anulado")):

                           exec_(
                               "UPDATE faltantes SET estado='Anulado' WHERE id=:id",
                                {"id": fid}
                            )

                           log_mov(fid, "CAMBIO_ESTADO", estado, "Anulado")
                           st.rerun()
                
                    else:
                        st.button("🗑️ Anular", use_container_width=True, disabled=True, key=f"card_anu_disabled_{fid}")

                st.markdown("</div>", unsafe_allow_html=True)

    # ---------- SUBTAB WHATSAPP ----------
    with sub2:
        st.subheader("Pedido WhatsApp (por rubro)")

        estados_incluir = st.multiselect(
            "Incluir estados",
            ["Pendiente", "Pedido"],
            default=["Pendiente", "Pedido"],
            key="wp_estados"
        )

        # Traemos Pendiente/Pedido desde DB
        df_ped = qdf("""
            SELECT *
            FROM faltantes
            WHERE estado IN ('Pendiente','Pedido')
            ORDER BY categoria, producto
        """)

        # Filtro por rol
        role = st.session_state.auth["role"]
        if role in ["Cocina", "Barra", "Salón"] and not df_ped.empty:
            df_ped = df_ped[df_ped["sector"] == role]

        # Estados a incluir
        if estados_incluir and not df_ped.empty:
            df_ped = df_ped[df_ped["estado"].isin(estados_incluir)]

        if df_ped.empty:
            st.info("No hay ítems para generar pedido con esos estados.")
        else:
            hoy = datetime.now().strftime("%d/%m")

            df_ped["categoria"] = df_ped["categoria"].fillna("").astype(str).str.strip()
            df_ped.loc[df_ped["categoria"] == "", "categoria"] = "OTROS"
            df_ped = df_ped.sort_values(["categoria", "producto"])

            lineas = [f"🧾 PEDIDO {hoy}", ""]
            for rubro, grub in df_ped.groupby("categoria", sort=False):
                lineas.append(str(rubro).upper())
                for _, r in grub.iterrows():
                    lineas.append(f"- {r['producto']} x{float(r['cantidad'] or 0):g} {r['unidad']}")
                lineas.append("")

            texto = "\n".join(lineas).strip()

            # SIN key para que se actualice siempre al cambiar filtros
            st.text_area("Texto listo para WhatsApp", value=texto, height=280)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.download_button(
                    "⬇️ pedido.txt",
                    data=texto.encode("utf-8"),
                    file_name="pedido.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key="wp_download"
                )

            with col2:
                if st.button("💾 Guardar pedido", use_container_width=True, key="wp_guardar"):
                    estados_str = ",".join(estados_incluir)

                    # Insert pedido y obtener ID (Postgres: RETURNING)
                    with get_engine().begin() as c:
                        res = c.execute(
                            text("""
                                INSERT INTO pedidos (fecha, estados_incluidos, texto_wp)
                                VALUES (current_date, :estados, :texto)
                                RETURNING id
                            """),
                            {"estados": estados_str, "texto": texto}
                        )
                        pedido_id = int(res.scalar_one())

                    # Insert items
                    creado_en = datetime.now()
                    for _, r in df_ped.iterrows():
                        exec_("""
                            INSERT INTO pedido_items (
                                pedido_id, faltante_id, producto, categoria, cantidad, unidad,
                                sector, proveedor, estado, prioridad, creado_en
                            ) VALUES (
                                :pedido_id, :faltante_id, :producto, :categoria, :cantidad, :unidad,
                                :sector, :proveedor, :estado, :prioridad, :creado_en
                            )
                        """, {
                            "pedido_id": pedido_id,
                            "faltante_id": int(r["id"]) if pd.notna(r["id"]) else None,
                            "producto": r.get("producto"),
                            "categoria": r.get("categoria"),
                            "cantidad": float(r.get("cantidad") or 0),
                            "unidad": r.get("unidad"),
                            "sector": r.get("sector"),
                            "proveedor": r.get("proveedor"),
                            "estado": r.get("estado"),
                            "prioridad": r.get("prioridad"),
                            "creado_en": creado_en
                        })

                    st.success(f"✅ Pedido guardado (#{pedido_id})")
                    st.rerun()

            with col3:
                if st.button("✅ Pend→Pedido", use_container_width=True, key="wp_btn_marcar"):
                    ids = df_ped[df_ped["estado"] == "Pendiente"]["id"].astype(int).tolist()
                    if ids:
                        exec_(
                            "UPDATE faltantes SET estado='Pedido' WHERE id = ANY(:ids::bigint[])",
                            {"ids": ids}
                        )
                        st.success(f"✅ {len(ids)} ítems pasaron a 'Pedido'.")
                        st.rerun()
                    else:
                        st.info("No había Pendientes para marcar.")



 # ============================================================
# TAB 3: Pedidos por fecha + Historial (Supabase)
# ============================================================
with tab3:
    st.subheader("📅 Pedidos por fecha")

    hoy = date.today()
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input("Desde", value=hoy, key="p_desde")
    with c2:
        hasta = st.date_input("Hasta", value=hoy, key="p_hasta")

    df_p = qdf("""
        SELECT id, creado_en, fecha, estados_incluidos
        FROM pedidos
        WHERE fecha BETWEEN :desde AND :hasta
        ORDER BY id DESC
    """, {
        "desde": desde,
        "hasta": hasta
    })

    if df_p.empty:
        st.info("No hay pedidos guardados en ese rango.")
    else:
        pid = st.selectbox(
            "Seleccioná un pedido",
            options=df_p["id"].tolist(),
            format_func=lambda x: f"Pedido #{x} — {df_p.loc[df_p['id']==x,'creado_en'].iloc[0]}",
            key="p_sel"
        )

        cab = qdf("SELECT * FROM pedidos WHERE id=:id", {"id": int(pid)}).iloc[0]
        st.write(f"**Creado:** {cab['creado_en']}  |  **Estados incluidos:** {cab.get('estados_incluidos', '')}")

        st.text_area("Texto WhatsApp guardado", value=str(cab["texto_wp"]), height=260, key="p_texto")

        df_items = qdf("""
            SELECT producto, categoria, cantidad, unidad, sector, proveedor
            FROM pedido_items
            WHERE pedido_id = :pid
            ORDER BY categoria, producto
        """, {"pid": int(pid)})

        st.dataframe(df_items, use_container_width=True)

        st.download_button(
            "⬇️ Descargar pedido seleccionado (.txt)",
            data=str(cab["texto_wp"]).encode("utf-8"),
            file_name=f"pedido_{pid}.txt",
            mime="text/plain",
            use_container_width=True,
            key="p_dl"
        )

    st.divider()
    st.subheader("📜 Historial de movimientos")

    c1, c2 = st.columns([2, 1])
    with c1:
        hist_buscar = st.text_input("Buscar por producto (opcional)", key="hist_buscar")
    with c2:
        hist_limite = st.selectbox("Mostrar", [50, 100, 200, 500], index=1, key="hist_limite")

    # Traemos movimientos + nombre del producto
    df_hist = qdf(f"""
        SELECT
            m.creado_en,
            m.usuario,
            m.rol,
            m.faltante_id,
            f.producto,
            m.accion,
            m.estado_anterior,
            m.estado_nuevo,
            m.nota
        FROM movimientos m
        JOIN faltantes f ON f.id = m.faltante_id
        ORDER BY m.id DESC
        LIMIT {int(hist_limite)}
    """)

    if hist_buscar.strip() and not df_hist.empty:
        bb = hist_buscar.strip().lower()
        df_hist = df_hist[df_hist["producto"].fillna("").str.lower().str.contains(bb, na=False)]

    st.dataframe(df_hist, use_container_width=True)

    st.markdown("### 🔎 Historial de un ítem")
    fid_lookup = st.number_input("Faltante ID", min_value=1, step=1, value=1, key="hist_fid")

    df_one = qdf("""
        SELECT creado_en, usuario, rol, accion, estado_anterior, estado_nuevo, nota
        FROM movimientos
        WHERE faltante_id = :fid
        ORDER BY id DESC
        LIMIT 200
    """, {"fid": int(fid_lookup)})

    if df_one.empty:
        st.info("Sin movimientos para ese ID.")
    else:
        st.dataframe(df_one, use_container_width=True)  
    
    from zoneinfo import ZoneInfo

    if not df_hist.empty:
        df_hist["creado_en"] = (
        pd.to_datetime(df_hist["creado_en"])
        .dt.tz_convert("America/Argentina/Buenos_Aires")
        .dt.strftime("%d/%m/%Y %H:%M hs")
    )
  
import zipfile

# ============================================================
# TAB 4: Maestro de Productos + Backup (Supabase)
# ============================================================
with tab4:
    st.subheader("🛠 Productos / Backup")

    role = st.session_state.auth["role"]
    is_admin = role == "Admin"

    # ==========================
    # LISTADO
    # ==========================
    st.markdown("### 📋 Productos cargados")

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        q = st.text_input("Buscar producto / proveedor", key="prod_q")
    with col_f2:
        cat_filter = st.selectbox("Filtrar categoría", ["Todas"] + CATEGORIAS, key="prod_cat_filter")

    solo_activos = st.checkbox("Solo activos", value=True, key="prod_solo_activos")

    df_prod = qdf("""
        SELECT id, nombre, categoria, unidad, proveedor, activo
        FROM productos
        ORDER BY nombre
    """)

    if df_prod.empty:
        st.info("No hay productos cargados todavía.")
        st.stop()

    # Normalizar
    df_prod["nombre"] = df_prod["nombre"].fillna("").astype(str)
    df_prod["categoria"] = df_prod["categoria"].fillna("").astype(str)
    df_prod["proveedor"] = df_prod["proveedor"].fillna("").astype(str)

    # Filtros
    if solo_activos:
        df_prod = df_prod[df_prod["activo"] == True]

    if cat_filter != "Todas":
        df_prod = df_prod[df_prod["categoria"] == cat_filter]

    if q.strip():
        qq = q.strip().lower()
        df_prod = df_prod[
            df_prod["nombre"].str.lower().str.contains(qq, na=False) |
            df_prod["proveedor"].str.lower().str.contains(qq, na=False)
        ]

    st.dataframe(df_prod[["nombre", "categoria", "unidad", "proveedor", "activo"]], use_container_width=True)

    st.divider()

    # ==========================
    # EDITAR PRODUCTO
    # ==========================
    st.markdown("### ✏ Editar producto")

    prod_id = st.selectbox(
        "Seleccionar producto",
        options=df_prod["id"].tolist(),
        format_func=lambda x: df_prod.loc[df_prod["id"] == x, "nombre"].iloc[0],
        key="prod_select_edit"
    )

    prod = df_prod[df_prod["id"] == prod_id].iloc[0]

    with st.form("form_edit_producto"):
        nombre = st.text_input("Nombre", value=prod["nombre"])
        categoria = st.selectbox(
            "Categoría",
            CATEGORIAS,
            index=CATEGORIAS.index(prod["categoria"]) if prod["categoria"] in CATEGORIAS else 0
        )
        unidad = st.selectbox(
            "Unidad",
            UNIDADES,
            index=UNIDADES.index(prod["unidad"]) if prod["unidad"] in UNIDADES else 0
        )
        proveedor = st.text_input("Proveedor", value=prod["proveedor"] or "")
        activo = st.checkbox("Activo", value=bool(prod["activo"]))

        guardar = st.form_submit_button("💾 Guardar cambios", use_container_width=True)

    if guardar:
        nuevo_nombre = (nombre or "").strip()
        if not nuevo_nombre:
            st.error("El nombre no puede estar vacío.")
            st.stop()

        # Si el nombre cambia y ya existe otro igual -> bloquear
        df_check = qdf(
            "SELECT id FROM productos WHERE lower(nombre)=lower(:n) LIMIT 1",
            {"n": nuevo_nombre}
        )
        if not df_check.empty and int(df_check.iloc[0]["id"]) != int(prod_id):
            st.error("Ya existe un producto con ese nombre. No se puede duplicar.")
            st.stop()

        old_name = prod["nombre"]

        # Actualizar maestro
        exec_("""
            UPDATE productos
            SET nombre=:nombre,
                categoria=:categoria,
                unidad=:unidad,
                proveedor=:proveedor,
                activo=:activo,
                actualizado_en=now()
            WHERE id=:id
        """, {
            "nombre": nuevo_nombre,
            "categoria": categoria,
            "unidad": unidad,
            "proveedor": (proveedor or "").strip(),
            "activo": bool(activo),
            "id": int(prod_id)
        })

        # Propagar a faltantes existentes por nombre viejo (si cambió)
        exec_("""
            UPDATE faltantes
            SET producto=:nuevo,
                categoria=:categoria,
                unidad=:unidad,
                proveedor=:proveedor
            WHERE producto=:viejo
        """, {
            "nuevo": nuevo_nombre,
            "viejo": old_name,
            "categoria": categoria,
            "unidad": unidad,
            "proveedor": (proveedor or "").strip()
        })

        st.success("✅ Producto actualizado en maestro y faltantes.")
        st.rerun()

    st.divider()

    # ==========================
    # ELIMINAR PRODUCTO
    # ==========================
    st.markdown("### 🗑 Eliminar producto")

    if not is_admin:
        st.info("Solo el Admin puede eliminar productos.")
    else:
        if "confirm_delete_prod_flag" not in st.session_state:
            st.session_state["confirm_delete_prod_flag"] = False

        if st.button("❌ Eliminar producto seleccionado", use_container_width=True, key="btn_delete_prod"):
            st.session_state["confirm_delete_prod_flag"] = True

        if st.session_state["confirm_delete_prod_flag"]:
            st.warning("⚠ Elimina el producto del maestro SOLO si NO tiene faltantes asociados.")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("✅ Confirmar eliminación", use_container_width=True, key="btn_confirm_delete_prod"):
                    df_rel = qdf(
                        "SELECT COUNT(*) AS total FROM faltantes WHERE producto=:p",
                        {"p": prod["nombre"]}
                    )
                    total_rel = int(df_rel.iloc[0]["total"]) if not df_rel.empty else 0

                    if total_rel > 0:
                        st.error(f"No se puede eliminar. Tiene {total_rel} faltantes asociados.")
                        st.session_state["confirm_delete_prod_flag"] = False
                        st.stop()

                    exec_("DELETE FROM productos WHERE id=:id", {"id": int(prod_id)})
                    st.success("🗑 Producto eliminado.")
                    st.session_state["confirm_delete_prod_flag"] = False
                    st.rerun()

            with c2:
                if st.button("Cancelar", use_container_width=True, key="btn_cancel_delete_prod"):
                    st.session_state["confirm_delete_prod_flag"] = False
                    st.rerun()

    st.divider()

    # ==========================
    # BACKUP / RESTORE (CSV ZIP) - SOLO ADMIN
    # ==========================
    st.subheader("💾 Backup / Restaurar (ZIP CSV)")

    if not is_admin:
        st.info("Solo el Admin puede ver y ejecutar backups/restores.")
        st.stop()

    # -------- BACKUP ZIP --------
    st.markdown("### ⬇️ Descargar backup (ZIP)")

    if st.button("📦 Generar ZIP de backup", use_container_width=True, key="btn_make_zip"):
        tables = ["productos", "faltantes", "pedidos", "pedido_items", "movimientos"]
        bio = io.BytesIO()

        with zipfile.ZipFile(bio, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for t in tables:
                try:
                    df_t = qdf(f"SELECT * FROM {t} ORDER BY 1")
                except Exception:
                    df_t = pd.DataFrame()
                z.writestr(f"{t}.csv", df_t.to_csv(index=False))

        bio.seek(0)
        st.download_button(
            "⬇️ Descargar backup_faltantes.zip",
            data=bio.getvalue(),
            file_name="backup_faltantes.zip",
            mime="application/zip",
            use_container_width=True,
            key="dl_zip"
        )

    st.divider()

    # -------- RESTORE ZIP --------
    st.markdown("### 🔄 Restaurar desde ZIP (CSV)")
    up_zip = st.file_uploader("Subí backup_faltantes.zip", type=["zip"], key="up_zip")

    modo = st.radio(
        "Modo de restauración",
        ["Reemplazar todo (BORRA y carga de cero)", "Agregar (append)"],
        index=0,
        key="restore_mode"
    )
    confirmar = st.checkbox("Confirmo restaurar (acción delicada)", key="restore_confirm")

    if up_zip is not None and st.button("Restaurar ahora", use_container_width=True, key="btn_restore_zip", disabled=not confirmar):
        # Leer ZIP
        zbytes = io.BytesIO(up_zip.getvalue())
        with zipfile.ZipFile(zbytes, "r") as z:
            def read_csv(name):
                try:
                    with z.open(name) as f:
                        return pd.read_csv(f)
                except Exception:
                    return pd.DataFrame()

            df_productos = read_csv("productos.csv")
            df_faltantes = read_csv("faltantes.csv")
            df_pedidos = read_csv("pedidos.csv")
            df_pedido_items = read_csv("pedido_items.csv")
            df_mov = read_csv("movimientos.csv")

        eng = get_engine()

        # Reemplazar = TRUNCATE
        if modo.startswith("Reemplazar"):
            exec_("TRUNCATE TABLE pedido_items, pedidos, movimientos, faltantes, productos RESTART IDENTITY CASCADE")

        # Cargar (to_sql)
        # Nota: to_sql usa el engine directo
        with eng.begin() as c:
            if not df_productos.empty:
                df_productos.to_sql("productos", c, if_exists="append", index=False, method="multi")
            if not df_faltantes.empty:
                df_faltantes.to_sql("faltantes", c, if_exists="append", index=False, method="multi")
            if not df_pedidos.empty:
                df_pedidos.to_sql("pedidos", c, if_exists="append", index=False, method="multi")
            if not df_pedido_items.empty:
                df_pedido_items.to_sql("pedido_items", c, if_exists="append", index=False, method="multi")
            if not df_mov.empty:
                df_mov.to_sql("movimientos", c, if_exists="append", index=False, method="multi")

        st.success("✅ Restore completado.")
        st.rerun()