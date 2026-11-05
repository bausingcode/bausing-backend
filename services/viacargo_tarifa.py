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
"""
import unicodedata
from typing import Optional

ZONA_1 = "zona_1"
ZONA_2 = "zona_2"
ZONA_3 = "zona_3"
ZONA_4 = "zona_4"
ZONA_5 = "zona_5"
ZONA_SUR_ESPECIAL = "sur_especial"

ZONAS = (ZONA_1, ZONA_2, ZONA_3, ZONA_4, ZONA_5, ZONA_SUR_ESPECIAL)

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


def tipo_tarifa_producto(product) -> Optional[str]:
    """Tipo de tarifa (clave de VIACARGO_TARIFAS) según las subcategorías del producto, o None."""
    tipos = set()
    es_base = False
    # La categoría principal a veces es directamente la medida (p. ej. "Colchones > Queen Size")
    categorias = [(product.category, product.category_option)] if getattr(product, "category", None) else []
    categorias += [(a.subcategory, a.category_option) for a in product.subcategory_associations or []]
    for sub, option in categorias:
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


def precio_tarifa(tariff_type: str, zona: str) -> Optional[int]:
    precios = VIACARGO_TARIFAS.get(tariff_type)
    if not precios or zona not in ZONAS:
        return None
    return precios[ZONAS.index(zona)]
