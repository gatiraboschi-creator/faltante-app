import os
import io
import sqlite3
from datetime import datetime, date

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Faltantes",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)
DB_PATH = "faltantes.db"


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
# DB helpers
# ============================================================
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(conn: sqlite3.Connection):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS faltantes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creado_en TEXT NOT NULL,
        producto TEXT NOT NULL,
        categoria TEXT,
        cantidad REAL,
        unidad TEXT,
        prioridad TEXT,
        sector TEXT,
        proveedor TEXT,
        estado TEXT NOT NULL,
        notas TEXT
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL UNIQUE,
        categoria TEXT,
        unidad TEXT,
        proveedor TEXT,
        activo INTEGER NOT NULL DEFAULT 1,
        creado_en TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creado_en TEXT NOT NULL,
        fecha TEXT NOT NULL,
        estados_incluidos TEXT NOT NULL,
        texto_wp TEXT NOT NULL
    );
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS pedido_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        faltante_id INTEGER,
        producto TEXT NOT NULL,
        categoria TEXT,
        cantidad REAL,
        unidad TEXT,
        sector TEXT,
        proveedor TEXT,
        estado TEXT,
        prioridad TEXT,
        creado_en TEXT NOT NULL,
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
    );
    """)
     
    conn.execute("""
    CREATE TABLE IF NOT EXISTS movimientos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        creado_en TEXT NOT NULL,
        usuario TEXT NOT NULL,
        rol TEXT NOT NULL,
        faltante_id INTEGER NOT NULL,
        accion TEXT NOT NULL,
        estado_anterior TEXT,
        estado_nuevo TEXT,
        nota TEXT,
        FOREIGN KEY (faltante_id) REFERENCES faltantes(id) ON DELETE CASCADE
    );
    """)

    conn.commit()



def qdf(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def exec_(conn, sql, params=()):
    conn.execute(sql, params)
    conn.commit()



def log_mov(conn, faltante_id: int, accion: str, estado_anterior: str | None, estado_nuevo: str | None, nota: str = ""):
    ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    usuario = st.session_state.auth.get("user", "desconocido")
    rol = st.session_state.auth.get("role", "desconocido")

    exec_(conn, """
        INSERT INTO movimientos (creado_en, usuario, rol, faltante_id, accion, estado_anterior, estado_nuevo, nota)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (ahora, usuario, rol, int(faltante_id), accion, estado_anterior, estado_nuevo, (nota or "").strip()))


# ============================================================
# UI config
# ============================================================
st.set_page_config(
    page_title="Faltantes",
    page_icon="🧾",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Defaults
CATEGORIAS = ["Almacén", "Verdulería", "Fiambre", "Carnicería", "Limpieza", "Descartables", "Bebidas",  "Panaderia", "Otros"]
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

# Conn
conn = get_conn()
init_db(conn)

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
    df_prod = qdf(conn, "SELECT nombre, categoria, unidad, proveedor FROM productos WHERE activo=1 ORDER BY nombre")
    productos = df_prod["nombre"].dropna().tolist()
    prod_map = {r["nombre"]: r for _, r in df_prod.iterrows()}
    return productos, prod_map


def upsert_producto(conn, nombre: str, categoria: str, unidad: str, proveedor: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    df_check = qdf(conn, "SELECT categoria FROM productos WHERE nombre = ?", (nombre,))
    if df_check.empty:
        exec_(conn, """
        INSERT INTO productos (nombre, categoria, unidad, proveedor, activo, creado_en, actualizado_en)
        VALUES (?, ?, ?, ?, 1, ?, ?)
        """, (nombre, categoria, unidad, proveedor.strip(), now, now))
        return categoria

    categoria_guardada = df_check.iloc[0]["categoria"]
    if categoria_guardada and categoria_guardada != categoria:
        categoria = categoria_guardada

    exec_(conn, """
    UPDATE productos
    SET unidad = ?, proveedor = ?, actualizado_en = ?
    WHERE nombre = ?
    """, (unidad, proveedor.strip(), now, nombre))

    return categoria


# ============================================================
# TAB 1: Cargar
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

        es_nuevo = bool(producto_nuevo.strip())
        producto = producto_nuevo.strip() if es_nuevo else producto_sel.strip()

        default_categoria = CATEGORIAS[0]
        default_unidad = UNIDADES[0]
        default_proveedor = ""

        if producto and producto in prod_map:
            default_categoria = prod_map[producto]["categoria"] or default_categoria
            default_unidad = prod_map[producto]["unidad"] or default_unidad
            default_proveedor = prod_map[producto]["proveedor"] or default_proveedor

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
        if not producto:
            st.error("El campo Producto es obligatorio.")
        else:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")

            categoria = upsert_producto(conn, producto, categoria, unidad, proveedor)

            df_exist = qdf(conn, """
                SELECT id, cantidad
                FROM faltantes
                WHERE producto = ?
                AND categoria = ?
                AND unidad = ?
                AND sector = ?
                AND estado IN ('Pendiente','Pedido')
                ORDER BY id DESC
                LIMIT 1
            """, (producto, categoria, unidad, sector))

            if not df_exist.empty:
                fid = int(df_exist.iloc[0]["id"])
                cant_old = float(df_exist.iloc[0]["cantidad"] or 0)
                cant_new = cant_old + float(cantidad)

                exec_(conn, "UPDATE faltantes SET cantidad=? WHERE id=?", (cant_new, fid))
                st.success(f"✅ Ya existía → sumé cantidad: {cant_new:g} {unidad}")
                st.rerun()

            exec_(conn, """
                INSERT INTO faltantes
                (creado_en, producto, categoria, cantidad, unidad, prioridad, sector, proveedor, estado, notas)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                now, producto, categoria, float(cantidad), unidad, prioridad, sector,
                proveedor.strip(), "Pendiente", notas.strip()
            ))

            st.success("✅ Cargado correctamente")
            st.rerun()


# ============================================================
# TAB 2: Lista + WhatsApp + Recibir Todo
# ============================================================
with tab2:
    sub1, sub2 = st.tabs(["📋 Lista", "🧾 Pedido WhatsApp"])

    # ---------- SUBTAB LISTA ----------
    with sub1:
        st.subheader("Lista")

        with st.expander("🔎 Filtros", expanded=False):
            # Por rol: si no es admin, ocultamos filtro sector (ya viene fijo)
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

        df = qdf(conn, "SELECT * FROM faltantes ORDER BY id DESC")

        # Filtro por rol automático
        role = st.session_state.auth["role"]
        if role in ["Cocina", "Barra", "Salón"]:
            df = df[df["sector"] == role]

        # Apply filters
        if f_estado:
            df = df[df["estado"].isin(f_estado)]
        if f_sector:
            df = df[df["sector"].isin(f_sector)]
        if f_categoria:
            df = df[df["categoria"].isin(f_categoria)]
        if f_prioridad:
            df = df[df["prioridad"].isin(f_prioridad)]
        if f_proveedor.strip():
            df = df[df["proveedor"].fillna("").str.contains(f_proveedor.strip(), case=False, na=False)]
        if buscar.strip():
            df = df[df["producto"].str.contains(buscar.strip(), case=False, na=False)]

        cA, cB, cC = st.columns(3)
        cA.metric("Pendientes", int((df["estado"] == "Pendiente").sum()) if not df.empty else 0)
        cB.metric("Pedido", int((df["estado"] == "Pedido").sum()) if not df.empty else 0)
        cC.metric("Total", int(len(df)))

        # Recibir todo lo que está en Pedido (sobre DF filtrado)
        df_pedido = df[df["estado"] == "Pedido"] if not df.empty else pd.DataFrame()
        if not df_pedido.empty:
            if st.button("📦 Recibir TODO el pedido", use_container_width=True, key="btn_recibir_todo"):
                ids = df_pedido["id"].astype(int).tolist()
                placeholders = ",".join(["?"] * len(ids))
                exec_(conn, f"UPDATE faltantes SET estado='Recibido' WHERE id IN ({placeholders})", tuple(ids))

                for fid_ in ids:
                    log_mov(conn, fid_, "RECIBIR_TODO", "Pedido", "Recibido")

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
                creado = row["creado_en"]
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
                        estado_old = estado
                        estado_new = "Pedido"
                        exec_(conn, "UPDATE faltantes SET estado=? WHERE id=?", (estado_new, fid))
                        log_mov(conn, fid, "CAMBIO_ESTADO", estado_old, estado_new)
                        st.rerun()

                with b2:
                    if st.button("📦 Recibido", key=f"card_rec_{fid}", use_container_width=True,
                                 disabled=(estado in ["Recibido", "Anulado"])):
                        estado_old = estado
                        estado_new = "Recibido"
                        exec_(conn, "UPDATE faltantes SET estado=? WHERE id=?", (estado_new, fid))
                        log_mov(conn, fid, "CAMBIO_ESTADO", estado_old, estado_new)
                        st.rerun()

                with b3:
                    if is_admin:
                        if st.button("🗑️ Anular", key=f"card_anu_{fid}", use_container_width=True,
                                      disabled=(estado == "Anulado")):
                            estado_old = estado
                            estado_new = "Anulado"
                            exec_(conn, "UPDATE faltantes SET estado=? WHERE id=?", (estado_new, fid))
                            log_mov(conn, fid, "CAMBIO_ESTADO", estado_old, estado_new)
                            st.rerun()
                    else:
                        st.button(
                            "🗑️ Anular",
                            use_container_width=True,
                            disabled=True,
                            key=f"card_anu_disabled_{fid}"
                        )

                
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

        # Siempre traemos sólo Pendiente/Pedido (limpio), luego aplicamos el multiselect
        df_ped = qdf(conn, """
            SELECT * FROM faltantes
            WHERE estado IN ('Pendiente','Pedido')
            ORDER BY categoria, producto
        """)

        # Filtro por rol
        role = st.session_state.auth["role"]
        if role in ["Cocina", "Barra", "Salón"]:
            df_ped = df_ped[df_ped["sector"] == role]

        if estados_incluir:
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
                    lineas.append(f"- {r['producto']} x{r['cantidad']:g} {r['unidad']}")
                lineas.append("")

            texto = "\n".join(lineas).strip()

            # Forzar actualización del texto aunque tenga key
            st.session_state["wp_texto_comercial"] = texto

            st.text_area(
                "Texto listo para WhatsApp",
                value=st.session_state["wp_texto_comercial"],
                height=280,
                key="wp_texto_comercial"
            )

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
                    ahora = datetime.now()
                    creado_en = ahora.strftime("%Y-%m-%d %H:%M")
                    fecha_ = ahora.strftime("%Y-%m-%d")
                    estados_str = ",".join(estados_incluir)

                    exec_(conn, """
                    INSERT INTO pedidos (creado_en, fecha, estados_incluidos, texto_wp)
                    VALUES (?, ?, ?, ?)
                    """, (creado_en, fecha_, estados_str, texto))

                    pedido_id = int(qdf(conn, "SELECT last_insert_rowid() AS id").iloc[0]["id"])

                    for _, r in df_ped.iterrows():
                        exec_(conn, """
                        INSERT INTO pedido_items (
                            pedido_id, faltante_id, producto, categoria, cantidad, unidad,
                            sector, proveedor, estado, prioridad, creado_en
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            pedido_id,
                            int(r["id"]) if pd.notna(r["id"]) else None,
                            r.get("producto"),
                            r.get("categoria"),
                            float(r.get("cantidad") or 0),
                            r.get("unidad"),
                            r.get("sector"),
                            r.get("proveedor"),
                            r.get("estado"),
                            r.get("prioridad"),
                            creado_en
                        ))

                    st.success(f"✅ Pedido guardado (#{pedido_id})")
                    st.rerun()
            with col3:
                if st.button("✅ Pend→Pedido", use_container_width=True, key="wp_btn_marcar"):
                    ids = df_ped[df_ped["estado"] == "Pendiente"]["id"].astype(int).tolist()
                    if ids:
                        placeholders = ",".join(["?"] * len(ids))
                        exec_(conn, f"UPDATE faltantes SET estado='Pedido' WHERE id IN ({placeholders})", tuple(ids))
                        st.success(f"✅ {len(ids)} ítems pasaron a 'Pedido'.")
                        st.rerun()
                    else:
                        st.info("No había Pendientes para marcar.")


# ============================================================
# TAB 3: Pedidos por fecha + Backup/Restore DB
# ============================================================
with tab3:
    st.subheader("📅 Pedidos por fecha")

    hoy = date.today()
    c1, c2 = st.columns(2)
    with c1:
        desde = st.date_input("Desde", value=hoy, key="p_desde")
    with c2:
        hasta = st.date_input("Hasta", value=hoy, key="p_hasta")

    df_p = qdf(conn, """
    SELECT id, creado_en, fecha, estados_incluidos
    FROM pedidos
    WHERE fecha BETWEEN ? AND ?
    ORDER BY id DESC
    """, (desde.strftime("%Y-%m-%d"), hasta.strftime("%Y-%m-%d")))

    if df_p.empty:
        st.info("No hay pedidos guardados en ese rango.")
    else:
        pid = st.selectbox(
            "Seleccioná un pedido",
            options=df_p["id"].tolist(),
            format_func=lambda x: f"Pedido #{x} — {df_p.loc[df_p['id']==x,'creado_en'].iloc[0]}",
            key="p_sel"
        )

        cab = qdf(conn, "SELECT * FROM pedidos WHERE id=?", (int(pid),)).iloc[0]
        st.write(f"**Creado:** {cab['creado_en']}  |  **Estados incluidos:** {cab['estados_incluidos']}")

        st.text_area("Texto WhatsApp guardado", value=cab["texto_wp"], height=260, key="p_texto")

        df_items = qdf(conn, """
        SELECT producto, categoria, cantidad, unidad, sector, proveedor
        FROM pedido_items
        WHERE pedido_id = ?
        ORDER BY categoria, producto
        """, (int(pid),))
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
    df_hist = qdf(conn, f"""
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

    if hist_buscar.strip():
        bb = hist_buscar.strip().lower()
        df_hist = df_hist[df_hist["producto"].fillna("").str.lower().str.contains(bb, na=False)]

    st.dataframe(df_hist, use_container_width=True)

    st.markdown("### 🔎 Historial de un ítem")
    fid_lookup = st.number_input("Faltante ID", min_value=1, step=1, value=1, key="hist_fid")

    df_one = qdf(conn, """
        SELECT creado_en, usuario, rol, accion, estado_anterior, estado_nuevo, nota
        FROM movimientos
        WHERE faltante_id = ?
        ORDER BY id DESC
        LIMIT 200
    """, (int(fid_lookup),))

    if df_one.empty:
        st.info("Sin movimientos para ese ID.")
    else:
        st.dataframe(df_one, use_container_width=True)        
    
  
# ============================================================
# TAB 4: Maestro de Productos (listar / editar / eliminar)
# ============================================================
with tab4:
    st.subheader("🛠 Maestro de Productos")

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
        cat_filter = st.selectbox(
            "Filtrar categoría",
            ["Todas"] + CATEGORIAS,
            key="prod_cat_filter"
        )

    solo_activos = st.checkbox("Solo activos", value=True, key="prod_solo_activos")

    df_prod = qdf(conn, """
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
        df_prod = df_prod[df_prod["activo"] == 1]

    if cat_filter != "Todas":
        df_prod = df_prod[df_prod["categoria"] == cat_filter]

    if q.strip():
        qq = q.strip().lower()
        df_prod = df_prod[
            df_prod["nombre"].str.lower().str.contains(qq, na=False) |
            df_prod["proveedor"].str.lower().str.contains(qq, na=False)
        ]

    st.dataframe(
        df_prod[["nombre", "categoria", "unidad", "proveedor", "activo"]],
        use_container_width=True
    )

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
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Si el nombre cambia y ya existe otro igual -> unificar
        df_check = qdf(conn, "SELECT id FROM productos WHERE nombre=?", (nombre.strip(),))
        if not df_check.empty and int(df_check.iloc[0]["id"]) != prod_id:
            st.error("Ya existe un producto con ese nombre. No se puede duplicar.")
            st.stop()

        # Actualizar maestro
        exec_(conn, """
            UPDATE productos
            SET nombre=?, categoria=?, unidad=?, proveedor=?, activo=?, actualizado_en=?
            WHERE id=?
        """, (
            nombre.strip(),
            categoria,
            unidad,
            proveedor.strip(),
            1 if activo else 0,
            now,
            prod_id
        ))

        # Actualizar faltantes
        exec_(conn, """
            UPDATE faltantes
            SET producto=?, categoria=?, unidad=?, proveedor=?
            WHERE producto=?
        """, (
            nombre.strip(),
            categoria,
            unidad,
            proveedor.strip(),
            prod["nombre"]
        ))

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
        # flag propio (NO es key de widget)
        if "confirm_delete_prod_flag" not in st.session_state:
            st.session_state["confirm_delete_prod_flag"] = False

        if st.button("❌ Eliminar producto seleccionado", use_container_width=True, key="btn_delete_prod"):
            st.session_state["confirm_delete_prod_flag"] = True

        if st.session_state["confirm_delete_prod_flag"]:
            st.warning("⚠ Esto eliminará el producto del maestro (solo si NO tiene faltantes asociados).")

            c1, c2 = st.columns(2)

            with c1:
                if st.button("✅ Confirmar eliminación", use_container_width=True, key="btn_confirm_delete_prod"):
                    # Ver si tiene faltantes asociados
                    df_rel = qdf(conn, "SELECT COUNT(*) as total FROM faltantes WHERE producto=?", (prod["nombre"],))
                    total_rel = int(df_rel.iloc[0]["total"])

                    if total_rel > 0:
                        st.error(f"No se puede eliminar. Tiene {total_rel} faltantes asociados.")
                        st.session_state["confirm_delete_prod_flag"] = False
                        st.stop()

                    exec_(conn, "DELETE FROM productos WHERE id=?", (prod_id,))
                    st.success("🗑 Producto eliminado.")
                    st.session_state["confirm_delete_prod_flag"] = False
                    st.rerun()

            with c2:
                if st.button("Cancelar", use_container_width=True, key="btn_cancel_delete_prod"):
                    st.session_state["confirm_delete_prod_flag"] = False
                    st.rerun()  
    st.divider()
    st.subheader("💾 Backup / Restaurar base de datos")

    # Descargar backup
    if os.path.exists(DB_PATH):
        with open(DB_PATH, "rb") as f:
            st.download_button(
                "⬇️ Descargar backup faltantes.db",
                data=f,
                file_name="faltantes_backup.db",
                mime="application/octet-stream",
                use_container_width=True,
                key="backup_db"
            )

    # Restaurar backup
    st.markdown("### 🔄 Restaurar backup")
    uploaded_file = st.file_uploader("Subir archivo .db", type=["db"], key="db_uploader")

    if uploaded_file is not None:
        confirmar = st.checkbox("Confirmo restaurar (se reemplaza la base actual)", key="db_confirm")
        if st.button("Restaurar base", use_container_width=True, key="db_restore", disabled=not confirmar):
            with open(DB_PATH, "wb") as f:
                f.write(uploaded_file.getbuffer())
            st.success("✅ Base restaurada. Reiniciando...")
            st.rerun()

