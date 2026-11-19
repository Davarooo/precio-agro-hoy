"""Precios de heno por estado en Estados Unidos (USDA AMS, MyMarketNews).

Lee la API oficial MARS del USDA (clave gratuita en la variable USDA_API_KEY) y escribe:
  data/usa/hay/<slug>.json          último reporte de cada estado
  data/usa/hay/history/<slug>.json  resumen semanal para la gráfica
  data/usa/hay/index.json           resumen de todos los estados

Las cifras se copian tal cual del USDA. Solo se descartan filas con
precios fuera de rango (errores de captura).
"""
import base64
import json
import os
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://mymarketnews.ams.usda.gov"
API = "https://marsapi.ams.usda.gov/services/v1.2"
AGENTE = "HayCattleBoard-bot/1.0 (+https://haycattleboard.blogspot.com)"
RAIZ = os.path.join(os.path.dirname(__file__), "..", "data", "usa", "hay")

# slug del USDA -> (estado, ruta de la página en el blog)
ESTADOS = {
    3784: ("Arizona", "arizona"),
    2904: ("California", "california"),
    2905: ("Colorado", "colorado"),
    3056: ("Idaho", "idaho"),
    2807: ("Iowa", "iowa"),
    2885: ("Kansas", "kansas"),
    3905: ("Kentucky", "kentucky"),
    2929: ("Missouri", "missouri"),
    2769: ("Montana", "montana"),
    2935: ("Nebraska", "nebraska"),
    3926: ("Nevada", "nevada"),
    2939: ("New Mexico", "new-mexico"),
    3095: ("Oklahoma", "oklahoma"),
    3057: ("Oregon", "oregon"),
    3183: ("South Dakota", "south-dakota"),
    3793: ("Tennessee", "tennessee"),
    2707: ("Texas", "texas"),
    3731: ("Utah", "utah"),
    3058: ("Washington", "washington"),
    3236: ("Wyoming", "wyoming"),
}

# Rangos razonables (US$) para descartar errores de captura.
RANGOS = {
    "Per Ton": (20, 1500),
    "Per Bale": (1, 600),
    "Per Bundle": (5, 1500),
    "Per Point/Ton": (0.5, 20),
}
NO_HENO = ("Straw", "Corn Stalk", "Stalk")  # paja y rastrojo no entran al resumen
HISTORIA_MAX = 104
DIAS_VIEJO = 45


def descargar_json(ruta, intentos=2):
    clave = os.environ.get("USDA_API_KEY", "")
    if not clave:
        raise RuntimeError("falta la variable USDA_API_KEY")
    auth = base64.b64encode(f"{clave}:".encode()).decode()
    url = API + ruta
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json",
                                                       "Authorization": f"Basic {auth}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if n == intentos - 1:
                raise
            time.sleep(5)


def fecha_iso(texto):
    """'11/09/2026' o '11/12/2026 08:24:54' -> '2026-11-09'."""
    if not texto:
        return None
    mes, dia, anio = texto.split(" ")[0].split("/")
    return f"{anio}-{int(mes):02d}-{int(dia):02d}"


def fecha_usda(iso):
    anio, mes, dia = iso.split("-")
    return f"{mes}/{dia}/{anio}"


def numero(valor):
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return v


def limpiar_fila(r):
    """Devuelve la fila normalizada o None si el precio no es creíble."""
    unidad = r.get("price_Unit") or ""
    pmin, pmax = numero(r.get("price_Min")), numero(r.get("price_Max"))
    if pmin is None or pmax is None or pmin <= 0 or pmax <= 0:
        return None
    if pmin > pmax:
        pmin, pmax = pmax, pmin
    bajo, alto = RANGOS.get(unidad, (0.5, 5000))
    if pmin < bajo or pmax > alto:
        return None
    prom = numero(r.get("wtd_Avg_Price"))
    if not prom or prom <= 0 or not (pmin <= prom <= pmax):
        prom = None
    texto = lambda k: (r.get(k) or "").strip() if isinstance(r.get(k), str) else ""
    return {
        "region": texto("region"),
        "hay": texto("class"),
        "quality": texto("quality"),
        "package": texto("package"),
        "sale": texto("sale_Type"),
        "unit": unidad,
        "low": round(pmin, 2),
        "high": round(pmax, 2),
        "avg": round(prom, 2) if prom else None,
        "freight": texto("freight"),
        "use": texto("use") if texto("use") != "null" else "",
    }


def es_alfalfa(fila):
    return "Alfalfa" in fila["hay"]


def resumen(filas):
    """Mediana del punto medio por tonelada para alfalfa y para heno de pasto."""
    def calc(grupo):
        mids = [f["avg"] or (f["low"] + f["high"]) / 2 for f in grupo]
        if not mids:
            return None
        return {
            "median": round(statistics.median(mids), 2),
            "low": min(f["low"] for f in grupo),
            "high": max(f["high"] for f in grupo),
            "rows": len(grupo),
        }
    heno = [f for f in filas if not any(x in f["hay"] for x in NO_HENO)]
    tonelada = [f for f in heno if f["unit"] == "Per Ton"]
    paca = [f for f in heno if f["unit"] == "Per Bale"]
    return {
        "alfalfa_ton": calc([f for f in tonelada if es_alfalfa(f)]),
        "grass_ton": calc([f for f in tonelada if not es_alfalfa(f)]),
        "small_bale": calc([f for f in paca if f["package"].startswith("Small Square")]),
        "round_bale": calc([f for f in paca if "Round" in f["package"]]),
    }


def consulta(rango):
    return urllib.parse.quote(f"report_begin_date={rango}", safe="=/:")


def detalles(slug, fecha, obtener):
    datos = obtener(f"/reports/{slug}/Report%20Details?q={consulta(fecha_usda(fecha))}")
    return [f for f in (limpiar_fila(r) for r in datos.get("results", [])) if f]


def cabecera(slug, fecha, obtener):
    datos = obtener(f"/reports/{slug}?q={consulta(fecha_usda(fecha))}")
    res = datos.get("results") or [{}]
    return res[0]


def fechas_publicadas(slug, obtener, hoy=None, dias=200):
    """Semanas publicadas en los últimos `dias`, de la más nueva a la más vieja."""
    hoy = hoy or date.today()
    rango = f"{fecha_usda((hoy - timedelta(days=dias)).isoformat())}:{fecha_usda(hoy.isoformat())}"
    datos = obtener(f"/reports/{slug}?q={consulta(rango)}")
    fechas = {fecha_iso(r.get("report_begin_date")) for r in datos.get("results", [])}
    return sorted((f for f in fechas if f), reverse=True)


def leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def escribir(ruta, datos):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
        f.write("\n")


def procesar_estado(slug, obtener=descargar_json, raiz=RAIZ, hoy=None, pausa=0.5, historia_inicial=8):
    estado, ruta = ESTADOS[slug]
    hoy = hoy or date.today()
    fechas = fechas_publicadas(slug, obtener, hoy)
    if not fechas:
        raise RuntimeError(f"{estado}: el USDA no devolvió fechas")
    ultima = fechas[0]
    filas = detalles(slug, ultima, obtener)
    if not filas:
        raise RuntimeError(f"{estado}: reporte {ultima} sin precios válidos")
    cab = cabecera(slug, ultima, obtener)
    dias = (hoy - date.fromisoformat(ultima)).days
    reporte = {
        "state": estado,
        "path": ruta,
        "slug": slug,
        "report_title": cab.get("report_title") or f"{estado} Direct Hay Report",
        "week_start": ultima,
        "week_end": fecha_iso(cab.get("report_end_date")),
        "published": fecha_iso(cab.get("published_date")),
        "stale": dias > DIAS_VIEJO,
        "narrative": (cab.get("report_narrative") or "").strip(),
        "source": "USDA AMS Market News",
        "source_url": f"{BASE}/viewReport/{slug}",
        "summary": resumen(filas),
        "rows": filas,
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    escribir(os.path.join(raiz, f"{slug}.json"), reporte)

    # Historia semanal (para la gráfica). La primera vez se rellenan semanas anteriores.
    ruta_h = os.path.join(raiz, "history", f"{slug}.json")
    hist = leer(ruta_h, {"state": estado, "slug": slug, "weeks": []})
    conocidas = {w["week_start"] for w in hist["weeks"]}
    pendientes = [ultima] if ultima not in conocidas else []
    if not hist["weeks"]:
        pendientes = fechas[:historia_inicial]
    for f in pendientes:
        fs = filas if f == ultima else detalles(slug, f, obtener)
        if f != ultima:
            time.sleep(pausa)
        r = resumen(fs)
        hist["weeks"].append({
            "week_start": f,
            "alfalfa_ton": r["alfalfa_ton"]["median"] if r["alfalfa_ton"] else None,
            "grass_ton": r["grass_ton"]["median"] if r["grass_ton"] else None,
        })
    hist["weeks"] = sorted({w["week_start"]: w for w in hist["weeks"]}.values(),
                           key=lambda w: w["week_start"])[-HISTORIA_MAX:]
    escribir(ruta_h, hist)
    return reporte


def main(obtener=descargar_json, raiz=RAIZ, pausa=0.5):
    indice = leer(os.path.join(raiz, "index.json"), {"states": []})
    previos = {s["slug"]: s for s in indice.get("states", [])}
    estados, fallas = [], []
    inicio = time.time()
    for n, slug in enumerate(ESTADOS):
        try:
            rep = procesar_estado(slug, obtener, raiz, pausa=pausa)
            estados.append({k: rep[k] for k in ("state", "path", "slug", "week_start", "published", "stale", "summary")})
            print(f"{ESTADOS[slug][0]}: semana {rep['week_start']}, {len(rep['rows'])} precios ({time.time() - inicio:.0f} s)", flush=True)
        except Exception as e:  # un estado caído no tumba a los demás
            fallas.append(f"{ESTADOS[slug][0]}: {e}")
            print(f"{ESTADOS[slug][0]}: FALLA {e}", flush=True)
            if slug in previos:
                estados.append(previos[slug])
            if n == 1 and len(fallas) == 2:  # los dos primeros fallaron: el USDA no responde, no insistir
                print("::warning::El USDA no responde; se reintenta en la siguiente ventana", flush=True)
                sys.exit(1)
        time.sleep(pausa)
    estados.sort(key=lambda s: s["state"])
    escribir(os.path.join(raiz, "index.json"), {
        "source": "USDA AMS Market News",
        "states": estados,
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    })
    for f in fallas:
        print("::warning::" + f)
    print(f"Heno USA: {len(estados) - len(fallas)} estados al día, {len(fallas)} fallas")
    if len(fallas) > len(ESTADOS) // 2:
        sys.exit(1)


if __name__ == "__main__":
    main()
