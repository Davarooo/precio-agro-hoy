import json
import os
import re
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import heno_usa  # noqa: E402

# Filas reales del Missouri Direct Hay Report (USDA, semana del 9 nov 2026),
# más dos filas dañadas a propósito.
DETALLE_MO = {"results": [
    {"region": None, "class": "Alfalfa", "quality": "Fair", "package": "Large Round", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": 125.0, "price_Max": 150.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    {"region": None, "class": "Alfalfa", "quality": "Good", "package": "Small Square", "sale_Type": "Ask",
     "price_Unit": "Per Bale", "price_Min": 6.0, "price_Max": 10.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    {"region": None, "class": "Alfalfa", "quality": "Good", "package": "Large Round", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": 150.0, "price_Max": 200.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    {"region": None, "class": "Alfalfa", "quality": "Premium", "package": "Medium Square 3x3", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": 200.0, "price_Max": 275.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    {"region": None, "class": "Mixed Grass", "quality": "Good", "package": "Large Round", "sale_Type": "Trade",
     "price_Unit": "Per Ton", "price_Min": 90.0, "price_Max": 130.0, "wtd_Avg_Price": 110.0, "freight": "F.O.B.", "use": "Farm/Ranch"},
    {"region": None, "class": "Wheat", "quality": "", "package": "Large Square 3x4", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": 80.0, "price_Max": 80.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    # dañadas: precio absurdo y precio vacío
    {"region": None, "class": "Alfalfa", "quality": "Good", "package": "Large Round", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": 15000.0, "price_Max": 16000.0, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
    {"region": None, "class": "Alfalfa", "quality": "Good", "package": "Large Round", "sale_Type": "Ask",
     "price_Unit": "Per Ton", "price_Min": None, "price_Max": None, "wtd_Avg_Price": 0, "freight": "F.O.B.", "use": None},
]}
CABECERA_MO = {"results": [{
    "report_title": "Missouri Direct Hay Report", "report_begin_date": "11/09/2026",
    "report_end_date": "11/13/2026", "published_date": "11/12/2026 08:24:54",
    "report_narrative": "Hay feeding is occurring.",
}]}
# Cabeceras de las últimas semanas publicadas (consulta por rango de fechas).
FECHAS = {"results": [{"report_begin_date": "10/12/2026"}, {"report_begin_date": "11/09/2026"},
                      {"report_begin_date": "10/26/2026"}, {"report_begin_date": "11/09/2026"}]}


def obtener_falso(ruta):
    assert ruta.startswith("/reports/"), ruta
    if "Report%20Details" in ruta:
        return DETALLE_MO
    if re.search(r"\d{4}:\d\d/", ruta):  # rango de fechas
        return FECHAS
    return CABECERA_MO


def test_descarta_filas_danadas():
    filas = [heno_usa.limpiar_fila(r) for r in DETALLE_MO["results"]]
    validas = [f for f in filas if f]
    assert len(validas) == 6
    assert all(f["high"] < 1500 for f in validas if f["unit"] == "Per Ton")


def test_promedio_cero_queda_vacio_y_el_real_se_conserva():
    f0 = heno_usa.limpiar_fila(DETALLE_MO["results"][0])
    f4 = heno_usa.limpiar_fila(DETALLE_MO["results"][4])
    assert f0["avg"] is None
    assert f4["avg"] == 110.0


def test_resumen_por_tonelada_sin_paja():
    filas = [f for f in (heno_usa.limpiar_fila(r) for r in DETALLE_MO["results"]) if f]
    r = heno_usa.resumen(filas)
    # alfalfa por tonelada: puntos medios 137.5, 175, 237.5 -> mediana 175
    assert r["alfalfa_ton"]["median"] == 175.0
    assert r["alfalfa_ton"]["low"] == 125.0 and r["alfalfa_ton"]["high"] == 275.0
    # pasto: mixed grass (promedio 110) y wheat (80) -> mediana 95
    assert r["grass_ton"]["median"] == 95.0


def test_procesar_estado_escribe_reporte_e_historia():
    with tempfile.TemporaryDirectory() as raiz:
        rep = heno_usa.procesar_estado(2929, obtener_falso, raiz, hoy=date(2026, 11, 18), pausa=0)
        assert rep["state"] == "Missouri"
        assert rep["week_start"] == "2026-11-09"
        assert rep["published"] == "2026-11-12"
        assert rep["stale"] is False
        assert rep["source_url"].endswith("/viewReport/2929")
        with open(os.path.join(raiz, "history", "2929.json")) as f:
            hist = json.load(f)
        assert [w["week_start"] for w in hist["weeks"]] == ["2026-10-12", "2026-10-26", "2026-11-09"]
        # segunda corrida sin reporte nuevo: no duplica semanas
        heno_usa.procesar_estado(2929, obtener_falso, raiz, hoy=date(2026, 11, 18), pausa=0)
        with open(os.path.join(raiz, "history", "2929.json")) as f:
            assert len(json.load(f)["weeks"]) == 3


def test_reporte_viejo_queda_marcado():
    with tempfile.TemporaryDirectory() as raiz:
        rep = heno_usa.procesar_estado(2929, obtener_falso, raiz, hoy=date(2027, 1, 30), pausa=0)
        assert rep["stale"] is True


def test_un_estado_caido_no_tumba_el_indice():
    def obtener_con_falla(ruta):
        if "/2707" in ruta:
            raise OSError("caído")
        return obtener_falso(ruta)
    with tempfile.TemporaryDirectory() as raiz:
        heno_usa.main(obtener_con_falla, raiz, pausa=0)
        with open(os.path.join(raiz, "index.json")) as f:
            idx = json.load(f)
        nombres = [s["state"] for s in idx["states"]]
        assert "Texas" not in nombres and len(nombres) == len(heno_usa.ESTADOS) - 1


def test_fechas_publicadas_sin_repetir_y_ordenadas():
    assert heno_usa.fechas_publicadas(2929, obtener_falso, date(2026, 11, 18)) == ["2026-11-09", "2026-10-26", "2026-10-12"]


def test_sin_clave_avisa_claro():
    viejo = os.environ.pop("USDA_API_KEY", None)
    try:
        heno_usa.descargar_json("/reports/2707")
    except RuntimeError as e:
        assert "USDA_API_KEY" in str(e)
    else:
        raise AssertionError("debió fallar sin clave")
    finally:
        if viejo is not None:
            os.environ["USDA_API_KEY"] = viejo


def test_fechas():
    assert heno_usa.fecha_iso("11/12/2026 08:24:54") == "2026-11-12"
    assert heno_usa.fecha_usda("2026-11-09") == "11/09/2026"


# El robot corre las pruebas con unittest: cada función de arriba entra como un caso.
import unittest  # noqa: E402


class PruebasHenoUSA(unittest.TestCase):
    pass


for _nombre, _f in list(globals().items()):
    if _nombre.startswith("test_") and callable(_f):
        setattr(PruebasHenoUSA, _nombre, (lambda f: lambda self: f())(_f))
