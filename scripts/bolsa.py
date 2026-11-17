#!/usr/bin/env python3
"""Precios de bolsa del cacao y del café para Ecuador, Perú, República
Dominicana y Colombia.

Lee el último cierre de los futuros en la Bolsa de Nueva York (ICE) y las tasas
de cambio del día (primero desde CNBC, que responde en una sola consulta; si
falla, desde Yahoo Finanzas), y escribe:
  data/cacao.json, data/cacao-historico.json
  data/cafe-peru.json, data/cafe-peru-historico.json

No es el precio que paga un comprador: es el precio internacional convertido a
la moneda y a las unidades de cada país. Las páginas lo explican y traen una
calculadora de descuento.

Solo usa la librería estándar. Si algo no cuadra, termina con código 1 para que
GitHub Actions marque el fallo y envíe el correo de alerta.
"""
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATOS = RAIZ / "data"
MAX_HISTORICO = 800
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
# símbolo de CNBC -> símbolo interno (el de Yahoo)
CNBC = {"@CC.1": "CC=F", "@KC.1": "KC=F", "COP=": "COP=X", "PEN=": "PEN=X", "DOP=": "DOP=X"}
CNBC_URL = ("https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
            "?symbols={}&requestMethod=itv&noform=1&partnerId=2&fund=1&exthrs=1&output=json")

# símbolo de Yahoo -> (mínimo, máximo) aceptables
SIMBOLOS = {
    "CC=F": (500, 30000),   # cacao, US$ por tonelada métrica
    "KC=F": (50, 900),      # café arábica contrato C, centavos de US$ por libra
    "COP=X": (2500, 7000),  # pesos colombianos por dólar
    "PEN=X": (2, 6),        # soles por dólar
    "DOP=X": (30, 120),     # pesos dominicanos por dólar
}

LB_POR_KG = 2.2046226218
KG_QUINTAL_100LB = 45.359237   # quintal de 100 libras (Ecuador, Rep. Dominicana)
KG_QUINTAL_CAFE_PERU = 46.0    # quintal de café en Perú


def descargar_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def numero(texto) -> float:
    return float(str(texto).replace(",", ""))


def cotizaciones_cnbc(obtener=descargar_json) -> dict:
    """Los cinco precios en una consulta. Para los futuros usa el precio de
    liquidación del día (settlePrice) y su fecha."""
    url = CNBC_URL.format("|".join(CNBC))
    citas = obtener(url)["FormattedQuoteResult"]["FormattedQuote"]
    salida = {}
    for q in citas:
        simbolo = CNBC.get(q.get("symbol"))
        if not simbolo:
            continue
        if q.get("settlePrice") and q.get("settleDate"):
            valor, fecha = numero(q["settlePrice"]), q["settleDate"][:10]
        else:
            valor, fecha = numero(q["last"]), q["last_time"][:10]
        minimo, maximo = SIMBOLOS[simbolo]
        if not (minimo <= valor <= maximo):
            raise ValueError(f"{simbolo}: valor fuera de rango {valor}")
        salida[simbolo] = {"valor": valor, "fecha": fecha, "anterior": None, "contrato": q.get("name", "")}
    faltan = [s for s in SIMBOLOS if s not in salida]
    if faltan:
        raise ValueError(f"CNBC no trajo {faltan}")
    return salida


def todas_las_cotizaciones(obtener=descargar_json):
    """Devuelve (cotizaciones, nombre de la fuente)."""
    try:
        return cotizaciones_cnbc(obtener), "CNBC"
    except Exception as exc:
        print(f"Aviso: CNBC no respondió bien ({exc}); pruebo Yahoo Finanzas")
    return {s: cotizacion(s, obtener) for s in SIMBOLOS}, "Yahoo Finanzas"


def anterior_del_historico(nombre: str, campo: str, fecha: str):
    ruta = DATOS / f"{nombre}-historico.json"
    if not ruta.exists():
        return None
    filas = [h for h in json.loads(ruta.read_text(encoding="utf-8")) if h.get("fecha", "") < fecha and h.get(campo)]
    return float(filas[-1][campo]) if filas else None


def cotizacion(simbolo: str, obtener=descargar_json) -> dict:
    """Último cierre diario y el anterior, con la fecha de Nueva York."""
    ultimo_error = None
    for intento in range(3):
        for host in HOSTS:
            url = f"https://{host}/v8/finance/chart/{simbolo}?range=10d&interval=1d"
            try:
                return extraer_cierre(obtener(url), simbolo)
            except Exception as exc:  # se reintenta con el otro servidor
                ultimo_error = exc
        time.sleep(5 * (intento + 1))
    raise RuntimeError(f"No se pudo leer {simbolo}: {ultimo_error}")


def extraer_cierre(datos: dict, simbolo: str) -> dict:
    res = datos["chart"]["result"][0]
    meta = res["meta"]
    tiempos = res.get("timestamp") or []
    cierres = res["indicators"]["quote"][0]["close"]
    pares = [(t, c) for t, c in zip(tiempos, cierres) if c is not None]
    if not pares:
        raise ValueError(f"{simbolo}: sin cierres")
    gmt = meta.get("gmtoffset", -18000)
    fechas = [datetime.fromtimestamp(t + gmt, tz=timezone.utc).date().isoformat() for t, _ in pares]
    minimo, maximo = SIMBOLOS[simbolo]
    valor = float(pares[-1][1])
    if not (minimo <= valor <= maximo):
        raise ValueError(f"{simbolo}: valor fuera de rango {valor}")
    anterior = float(pares[-2][1]) if len(pares) > 1 else None
    return {"valor": valor, "fecha": fechas[-1], "anterior": anterior, "contrato": meta.get("shortName", "")}


def redondo(x: float, n: int = 2) -> float:
    return round(x + 0.0, n)


def armar_cacao(cc: dict, fx: dict, ahora: str, via: str = "Yahoo Finanzas") -> dict:
    usd_t = cc["valor"]
    usd_kg = usd_t / 1000
    paises = {
        "ecuador": {"moneda": "USD", "tasa": 1.0, "unidad": "quintal", "kg_unidad": KG_QUINTAL_100LB},
        "peru": {"moneda": "PEN", "tasa": fx["PEN=X"]["valor"], "unidad": "kilo", "kg_unidad": 1.0},
        "republica-dominicana": {"moneda": "DOP", "tasa": fx["DOP=X"]["valor"], "unidad": "quintal", "kg_unidad": KG_QUINTAL_100LB},
        "colombia": {"moneda": "COP", "tasa": fx["COP=X"]["valor"], "unidad": "kilo", "kg_unidad": 1.0},
    }
    for p in paises.values():
        p["precio_kilo"] = redondo(usd_kg * p["tasa"], 2)
        p["precio_unidad"] = redondo(usd_kg * p["kg_unidad"] * p["tasa"], 2)
        p["tasa"] = redondo(p["tasa"], 4)
    datos = {
        "producto": "cacao",
        "fecha": cc["fecha"],
        "actualizado": ahora,
        "fuente": f"Futuros de cacao en la Bolsa de Nueva York (ICE) y tasas de cambio, vía {via}",
        "contrato": cc["contrato"],
        "usd_tonelada": redondo(usd_t, 2),
        "paises": paises,
    }
    if cc["anterior"]:
        datos["variacion_usd_tonelada"] = redondo(usd_t - cc["anterior"], 2)
        datos["variacion_pct"] = redondo((usd_t - cc["anterior"]) / cc["anterior"] * 100, 2)
    return datos


def armar_cafe_peru(kc: dict, fx: dict, ahora: str, via: str = "Yahoo Finanzas") -> dict:
    usd_lb = kc["valor"] / 100
    usd_kg = usd_lb * LB_POR_KG
    tasa = fx["PEN=X"]["valor"]
    datos = {
        "producto": "cafe",
        "pais": "peru",
        "fecha": kc["fecha"],
        "actualizado": ahora,
        "fuente": f"Futuros de café arábica (contrato C) en la Bolsa de Nueva York (ICE) y tasa de cambio, vía {via}",
        "contrato": kc["contrato"],
        "usc_libra": redondo(kc["valor"], 2),
        "tasa_pen": redondo(tasa, 4),
        "kg_quintal": KG_QUINTAL_CAFE_PERU,
        "precio_kilo": redondo(usd_kg * tasa, 2),
        "precio_quintal": redondo(usd_kg * KG_QUINTAL_CAFE_PERU * tasa, 2),
    }
    if kc["anterior"]:
        datos["variacion_usc_libra"] = redondo(kc["valor"] - kc["anterior"], 2)
        datos["variacion_pct"] = redondo((kc["valor"] - kc["anterior"]) / kc["anterior"] * 100, 2)
    return datos


def guardar_con_historico(nombre: str, datos: dict, fila: dict) -> None:
    DATOS.mkdir(parents=True, exist_ok=True)
    ruta_hist = DATOS / f"{nombre}-historico.json"
    hist = json.loads(ruta_hist.read_text(encoding="utf-8")) if ruta_hist.exists() else []
    hist = [h for h in hist if h.get("fecha") != fila["fecha"]] + [fila]
    hist.sort(key=lambda h: h["fecha"])
    hist = hist[-MAX_HISTORICO:]
    (DATOS / f"{nombre}.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    ruta_hist.write_text(json.dumps(hist, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main(argv, obtener=descargar_json) -> int:
    ahora = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    try:
        cot, via = todas_las_cotizaciones(obtener)
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    fx = {s: cot[s] for s in ("COP=X", "PEN=X", "DOP=X")}
    # CNBC no da un cierre anterior confiable: se toma del histórico propio
    if cot["CC=F"]["anterior"] is None:
        cot["CC=F"]["anterior"] = anterior_del_historico("cacao", "usd_tonelada", cot["CC=F"]["fecha"])
    if cot["KC=F"]["anterior"] is None:
        cot["KC=F"]["anterior"] = anterior_del_historico("cafe-peru", "usc_libra", cot["KC=F"]["fecha"])

    cacao = armar_cacao(cot["CC=F"], fx, ahora, via)
    guardar_con_historico("cacao", cacao, {
        "fecha": cacao["fecha"], "usd_tonelada": cacao["usd_tonelada"],
        "COP": fx["COP=X"]["valor"], "PEN": fx["PEN=X"]["valor"], "DOP": fx["DOP=X"]["valor"],
    })
    cafe = armar_cafe_peru(cot["KC=F"], fx, ahora, via)
    guardar_con_historico("cafe-peru", cafe, {
        "fecha": cafe["fecha"], "usc_libra": cafe["usc_libra"], "PEN": cafe["tasa_pen"],
        "precio_quintal": cafe["precio_quintal"],
    })
    print(f"[{via}] Cacao {cacao['fecha']}: US$ {cacao['usd_tonelada']}/t | Café {cafe['fecha']}: {cafe['usc_libra']} c/lb")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
