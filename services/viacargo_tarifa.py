# -*- coding: utf-8 -*-
"""
Tarifa fija Vía Cargo (retiro en agencia): precio por unidad según tipo de producto y zona.
No depende del peso, solo de la medida. Fuente: "BAUSING TARIFA.xlsx", hoja "21,04" (tarifa 01/07/26).

- 1 plaza incluye 1½ plaza; 2 plazas incluye queen y extra queen; 2x2 = king (200x200).
- Conjunto = colchón + base.
- Provincias fuera de las zonas (San Luis, Tierra del Fuego): sin envío.
- El tipo de tarifa sale de las subcategorías del producto (Colchones / Sommier y colchón > medida,
  Grandes electros > Heladeras / Lavarropas). Bases solas: precio de colchón 1 plaza.
  Sin match (cuna, TV, aires): se cotiza en Busplus.
- Los precios se editan desde el admin (system_settings "viacargo.tarifas"); VIACARGO_TARIFAS es el default.
- Desde el admin se pueden agregar tarifas extra asociadas a una categoría/subcategoría (y opcionalmente
  una opción, p. ej. Grandes electros > Smart TV) y/o a productos puntuales.
  Prioridad: producto puntual > tipo fijo > categoría.
"""
import unicodedata
from typing import Any, Dict, Optional, Sequence

from models.settings import SystemSettings

SETTINGS_KEY = "viacargo.tarifas"

ZONA_1 = "zona_1"
ZONA_2 = "zona_2"
ZONA_3 = "zona_3"
ZONA_4 = "zona_4"
ZONA_5 = "zona_5"
ZONA_SUR_ESPECIAL = "sur_especial"

ZONAS = (ZONA_1, ZONA_2, ZONA_3, ZONA_4, ZONA_5, ZONA_SUR_ESPECIAL)

ZONA_LABELS = {
    ZONA_1: "Zona 1",
    ZONA_2: "Zona 2",
    ZONA_3: "Zona 3",
    ZONA_4: "Zona 4",
    ZONA_5: "Zona 5",
    ZONA_SUR_ESPECIAL: "Bariloche / Comodoro",
}

TIPO_LABELS = {
    "colchon_1p": "Colchón 1 plaza (y 1½) · Bases",
    "conjunto_1p": "Conjunto 1 plaza (y 1½)",
    "colchon_2p": "Colchón 2 plazas (queen, extra queen)",
    "conjunto_2p": "Conjunto 2 plazas (queen, extra queen)",
    "colchon_2x2": "Colchón 2x2 / king",
    "conjunto_2x2": "Conjunto 2x2 / king",
    "heladera": "Heladera",
    "lavarropas": "Lavarropas",
}

# Precio por unidad (ARS) en el orden de ZONAS
VIACARGO_TARIFAS = {
    "colchon_1p": (87000, 62000, 57000, 76000, 105000, 138000),
    "conjunto_1p": (134000, 106000, 97000, 131000, 184000, 214000),
    "colchon_2p": (118000, 103000, 94000, 128000, 179000, 188000),
    "conjunto_2p": (189000, 160000, 145000, 199000, 279000, 304000),
    "colchon_2x2": (174000, 122000, 111000, 151000, 211000, 280000),
    "conjunto_2x2": (266000, 185000, 168000, 230000, 323000, 429000),
    "heladera": (146000, 134000, 122000, 166000, 233000, 233000),
    "lavarropas": (88000, 81000, 74000, 100000, 138000, 138000),
}

# Clave: nombre de provincia normalizado (sin tildes, minúsculas)
_PROVINCIA_ZONA = {
    "caba": ZONA_1,
    "capital federal": ZONA_1,
    "ciudad autonoma de buenos aires": ZONA_1,
    "ciudad de buenos aires": ZONA_1,
    "buenos aires": ZONA_1,
    "provincia de buenos aires": ZONA_1,
    "cordoba": ZONA_2,
    "entre rios": ZONA_2,
    "la pampa": ZONA_2,
    "santa fe": ZONA_2,
    "la rioja": ZONA_2,
    "chaco": ZONA_3,
    "corrientes": ZONA_3,
    "mendoza": ZONA_3,
    "misiones": ZONA_3,
    "san juan": ZONA_3,
    "santiago del estero": ZONA_3,
    "catamarca": ZONA_4,
    "jujuy": ZONA_4,
    "neuquen": ZONA_4,
    "salta": ZONA_4,
    "tucuman": ZONA_4,
    "formosa": ZONA_4,
    "chubut": ZONA_5,
    "rio negro": ZONA_5,
    "santa cruz": ZONA_5,
}

# CP clásico (4 dígitos) → zona especial: Bariloche y Comodoro Rivadavia
_CP_SUR_ESPECIAL = {"8400", "9000"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace(".", " ").split())


# Subcategoría padre → prefijo de tarifa
_PADRE_TIPO = {
    "colchones": "colchon",
    "sommier y colchon": "conjunto",
}

# Opción de "Grandes electros" → tarifa
_ELECTRO_TARIFA = {
    "heladeras": "heladera",
    "lavarropas": "lavarropas",
}

_BASES_SOMMIER = "bases de sommier"


def _medida_desde_subcategoria(nombre: str) -> Optional[str]:
    n = _norm(nombre)
    if "king" in n or "200x200" in n:
        return "2x2"
    if "queen" in n or "dos plazas" in n or "2 plazas" in n:
        return "2p"
    if "plaza" in n:  # una plaza / 1 plaza / plaza y media
        return "1p"
    return None


def _categorias_producto(product) -> list:
    """(categoría, opción) del producto: la principal (a veces es directamente la medida) y las subcategorías."""
    categorias = [(product.category, product.category_option)] if getattr(product, "category", None) else []
    categorias += [(a.subcategory, a.category_option) for a in product.subcategory_associations or []]
    return categorias


def tipo_tarifa_producto(product) -> Optional[str]:
    """Tipo de tarifa (clave de VIACARGO_TARIFAS) según las subcategorías del producto, o None."""
    tipos = set()
    es_base = False
    for sub, option in _categorias_producto(product):
        if not sub:
            continue
        sub_n = _norm(sub.name)
        padre_n = _norm(sub.parent.name) if sub.parent else ""
        if sub_n == _BASES_SOMMIER:
            es_base = True
            continue
        if sub_n == "grandes electros" and option:
            t = _ELECTRO_TARIFA.get(_norm(option.value))
            if t:
                tipos.add(t)
            continue
        prefijo = _PADRE_TIPO.get(padre_n)
        medida = _medida_desde_subcategoria(sub.name) if prefijo else None
        if medida:
            tipos.add(f"{prefijo}_{medida}")
    if es_base:  # base sola (sin colchón): mismo precio que colchón 1 plaza, cualquier medida
        return "colchon_1p"
    if len(tipos) > 1:
        # Varias medidas/tipos cargados: la más cara en zona 1 para no cobrar de menos
        return max(tipos, key=lambda t: VIACARGO_TARIFAS[t][0])
    return next(iter(tipos), None)


def zona_viacargo(provincia: Optional[str], cp4: Optional[str]) -> Optional[str]:
    """Zona de tarifa para la provincia/CP destino, o None si no hay envío."""
    if cp4 and cp4 in _CP_SUR_ESPECIAL:
        return ZONA_SUR_ESPECIAL
    return _PROVINCIA_ZONA.get(_norm(provincia or ""))


def provincias_por_zona() -> Dict[str, list]:
    """Para mostrar en el admin (debe coincidir con _PROVINCIA_ZONA y _CP_SUR_ESPECIAL)."""
    return {
        ZONA_1: ["CABA", "Buenos Aires"],
        ZONA_2: ["Córdoba", "Entre Ríos", "La Pampa", "Santa Fe", "La Rioja"],
        ZONA_3: ["Chaco", "Corrientes", "Mendoza", "Misiones", "San Juan", "Santiago del Estero"],
        ZONA_4: ["Catamarca", "Jujuy", "Neuquén", "Salta", "Tucumán", "Formosa"],
        ZONA_5: ["Chubut", "Río Negro", "Santa Cruz"],
        ZONA_SUR_ESPECIAL: [],
    }


def _fila_valida(fila) -> bool:
    """Un precio por zona; None = esa zona se cotiza en Busplus."""
    return isinstance(fila, list) and len(fila) == len(ZONAS)


def tarifas_vigentes() -> Dict[str, Any]:
    """
    {"precios": {tipo: [precio por zona]},
     "extras": [{id, label, category_id, category_option_id, product_ids, precios}]}
    Precios de tipos fijos faltantes o mal guardados caen al default.
    """
    guardadas = SystemSettings.get_value(SETTINGS_KEY, default=None) or {}
    if not isinstance(guardadas, dict):
        guardadas = {}
    # Formato anterior: {tipo: [...]} directamente
    precios_guardados = guardadas.get("precios") if "precios" in guardadas else guardadas
    if not isinstance(precios_guardados, dict):
        precios_guardados = {}
    precios = {}
    for tipo, default in VIACARGO_TARIFAS.items():
        fila = precios_guardados.get(tipo)
        precios[tipo] = fila if _fila_valida(fila) else list(default)
    extras = [
        e for e in (guardadas.get("extras") or [])
        if isinstance(e, dict) and (e.get("category_id") or e.get("product_ids")) and _fila_valida(e.get("precios"))
    ]
    return {"precios": precios, "extras": extras}


def _ids_con_ancestros(cat) -> set:
    ids = set()
    pasos = 0
    while cat is not None and pasos < 10:
        ids.add(str(cat.id))
        cat = cat.parent
        pasos += 1
    return ids


def _extra_por_producto(product, extras: list) -> Optional[dict]:
    """Primera tarifa extra que eligió este producto puntualmente."""
    pid = str(product.id)
    return next((e for e in extras if pid in (e.get("product_ids") or [])), None)


def _extra_para_producto(product, extras: list) -> Optional[dict]:
    """Primera tarifa extra cuya categoría (o un ancestro de la del producto) y opción coinciden."""
    categorias = [(_ids_con_ancestros(c), str(o.id) if o else None) for c, o in _categorias_producto(product) if c]
    for extra in extras:
        if not extra.get("category_id"):
            continue
        cat_id = str(extra["category_id"])
        opt_id = extra.get("category_option_id")
        for ids, producto_opt in categorias:
            if cat_id in ids and (not opt_id or str(opt_id) == producto_opt):
                return extra
    return None


def precios_producto(product, tarifas: Dict[str, Any]) -> Optional[Sequence[int]]:
    """Fila de precios por zona que aplica al producto (tipo fijo o tarifa extra), o None → Busplus.
    Un precio None en la fila también significa Busplus para esa zona."""
    extra = _extra_por_producto(product, tarifas["extras"])
    if extra:
        return extra["precios"]
    tipo = tipo_tarifa_producto(product)
    if tipo:
        return tarifas["precios"][tipo]
    extra = _extra_para_producto(product, tarifas["extras"])
    return extra["precios"] if extra else None
