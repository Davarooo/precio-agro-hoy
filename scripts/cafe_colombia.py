#!/usr/bin/env python3
"""Descarga el PDF diario de precios de la Federacion Nacional de Cafeteros,
extrae los datos y actualiza data/cafe-colombia.json y su historico.

Solo usa la libreria estandar de Python. Si algo no cuadra, termina con
codigo 1 para que GitHub Actions marque el fallo y envie el correo de alerta.
"""
import json
import re
import sys
import time
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path

PUBLICACIONES_URL = "https://federaciondecafeteros.org/publicaciones/"
PDF_URL_RESPALDO = "https://federaciondecafeteros.org/wp-content/uploads/2026/03/precio_cafe.pdf"
RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "data" / "cafe-colombia.json"
HISTORICO = RAIZ / "data" / "cafe-colombia-historico.json"
MAX_HISTORICO = 800

MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
UA = "Mozilla/5.0 (compatible; PrecioAgroHoy/1.0; +https://github.com)"


def descargar(url: str, intentos: int = 3) -> bytes:
    """El servidor de la Federacion a veces corta la conexion: se reintenta."""
    for n in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception as exc:
            if n == intentos - 1:
                raise
            print(f"Aviso: intento {n + 1} fallo ({exc}); reintento")
            time.sleep(20 * (n + 1))


def url_del_pdf() -> str:
    """Busca el enlace vigente al PDF en la pagina de publicaciones."""
    try:
        html = descargar(PUBLICACIONES_URL).decode("utf-8", "ignore")
        m = re.search(r'href="([^"]*precio_cafe\.pdf)"', html)
        if m:
            return m.group(1)
    except Exception as exc:  # la pagina puede fallar; se usa el respaldo
        print(f"Aviso: no se pudo leer publicaciones ({exc}); uso URL de respaldo")
    return PDF_URL_RESPALDO


def flujos_de_contenido(pdf: bytes):
    """Devuelve el texto de cada stream, descomprimiendo los que se puedan."""
    for m in re.finditer(rb"(?<!end)stream\r?\n", pdf):
        ini = m.end()
        fin = pdf.find(b"endstream", ini)
        if fin < 0:
            continue
        crudo = pdf[ini:fin].rstrip(b"\r\n")
        if b"Td" in crudo and b"Tj" in crudo:
            yield crudo.decode("latin-1")
            continue
        try:
            plano = zlib.decompress(crudo)
            if b"Td" in plano and b"Tj" in plano:
                yield plano.decode("latin-1")
        except zlib.error:
            pass


def tokens(pdf: bytes):
    """Lista de (x, y, texto) para cada 'x y Td <hex> Tj' o 'x y Td (txt) Tj'."""
    patron = re.compile(r"([\d.]+)\s+([\d.]+)\s+Td\s*(?:<([0-9A-Fa-f]+)>|\(((?:\\.|[^\\)])*)\))\s*Tj")
    salida = []
    for pagina, flujo in enumerate(flujos_de_contenido(pdf)):
        for m in patron.finditer(flujo):
            x, y = float(m.group(1)), float(m.group(2))
            if m.group(3):
                texto = bytes.fromhex(m.group(3)).decode("latin-1")
            else:
                texto = m.group(4)
            texto = texto.strip()
            if texto:
                salida.append((pagina, round(x), round(y), texto))
    return salida


def numero(txt: str) -> float:
    return float(txt.replace(",", ""))


def es_numero(txt: str) -> bool:
    return re.fullmatch(r"[\d,]+(\.\d+)?", txt) is not None


def agrupar_por_linea(toks):
    """Agrupa tokens por pagina y coordenada y, conservando el orden."""
    lineas = {}
    orden = []
    for pagina, x, y, t in toks:
        clave = (pagina, y)
        if clave not in lineas:
            lineas[clave] = []
            orden.append(clave)
        lineas[clave].append((x, t))
    return [(y, sorted(lineas[y])) for y in orden]


def parsear(pdf: bytes) -> dict:
    toks = tokens(pdf)
    if not toks:
        raise ValueError("El PDF no tiene texto legible con el formato esperado")
    textos = [t for _, _, _, t in toks]
    unido = " ".join(textos)

    # Fecha: "Noviembre 17 / 2026"
    mf = re.search(r"([A-Za-z]+)\s+(\d{1,2})\s*/\s*(\d{4})", unido)
    if not mf or mf.group(1).lower() not in MESES:
        raise ValueError("No se encontro la fecha del boletin")
    fecha = datetime(int(mf.group(3)), MESES[mf.group(1).lower()], int(mf.group(2))).date().isoformat()

    mb = re.search(r"([\d.]+)\s*USCent/Lb", unido)
    bolsa = float(mb.group(1)) if mb else None

    mc = re.search(r"Precio total por carga.*?FR\s*(\d+)\s+([\d,]+)\s+COP", unido)
    if not mc:
        raise ValueError("No se encontro el precio total por carga")
    factor_ref = int(mc.group(1))
    precio_carga = numero(mc.group(2))

    mp = re.search(r"pasilla\s+contenida en el pergamino\s+([\d,]+)\s+COP/Kg", unido)
    pasilla = numero(mp.group(1)) if mp else None

    factores, ciudades = [], []
    for _, celdas in agrupar_por_linea(toks):
        valores = [t for _, t in celdas]
        if len(valores) == 6 and all(es_numero(v) for v in valores):
            f = numero(valores[0])
            if 70 <= f <= 120:
                factores.append({
                    "factor": int(f),
                    "kg_excelso": numero(valores[1]),
                    "kg_pasilla": numero(valores[2]),
                    "valor_excelso": numero(valores[3]),
                    "valor_pasilla": numero(valores[4]),
                    "total": numero(valores[5]),
                })
        elif (len(valores) == 4 and re.fullmatch(r"[A-ZÁÉÍÓÚÑ .]+", valores[0])
              and all(es_numero(v) for v in valores[1:])
              and abs(numero(valores[1]) / 125 - numero(valores[2])) <= numero(valores[2]) * 0.01):
            ciudades.append({
                "ciudad": valores[0].title(),
                "carga": numero(valores[1]),
                "kilo": numero(valores[2]),
                "arroba": numero(valores[3]),
            })

    factores = list({r["factor"]: r for r in factores}.values())
    ciudades = list({c["ciudad"]: c for c in ciudades}.values())
    factores.sort(key=lambda r: r["factor"])
    ciudades.sort(key=lambda c: c["ciudad"])
    return {
        "producto": "cafe",
        "pais": "colombia",
        "moneda": "COP",
        "fecha": fecha,
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fuente": "Federación Nacional de Cafeteros de Colombia",
        "bolsa_ny_usc_lb": bolsa,
        "factor_referencia": factor_ref,
        "precio_carga": precio_carga,
        "precio_kilo": round(precio_carga / 125, 2),
        "pasilla_cop_kg": pasilla,
        "factores": factores,
        "ciudades": ciudades,
    }


def validar(d: dict) -> None:
    errores = []
    if not 500_000 <= d["precio_carga"] <= 8_000_000:
        errores.append(f"precio_carga fuera de rango: {d['precio_carga']}")
    if len(d["factores"]) < 8:
        errores.append(f"muy pocas filas de factor de rendimiento: {len(d['factores'])}")
    if len(d["ciudades"]) < 8:
        errores.append(f"muy pocas ciudades: {len(d['ciudades'])}")
    ref = next((f for f in d["factores"] if f["factor"] == d["factor_referencia"]), None)
    if ref and abs(ref["total"] - d["precio_carga"]) > 1:
        errores.append("el total de la tabla no coincide con el precio de referencia")
    if errores:
        raise ValueError("; ".join(errores))


def actualizar_historico(d: dict) -> list:
    historico = []
    if HISTORICO.exists():
        historico = json.loads(HISTORICO.read_text(encoding="utf-8"))
    historico = [h for h in historico if h["fecha"] != d["fecha"]]
    historico.append({"fecha": d["fecha"], "carga": d["precio_carga"], "bolsa_ny_usc_lb": d["bolsa_ny_usc_lb"]})
    historico.sort(key=lambda h: h["fecha"])
    return historico[-MAX_HISTORICO:]


def main(argv) -> int:
    if len(argv) > 1:  # modo prueba: python cafe_colombia.py archivo.pdf
        pdf = Path(argv[1]).read_bytes()
    else:
        url = url_del_pdf()
        print(f"Descargando {url}")
        pdf = descargar(url)
    datos = parsear(pdf)
    validar(datos)
    historico = actualizar_historico(datos)
    if len(historico) >= 2:
        anterior = historico[-2]["carga"]
        datos["variacion_carga"] = datos["precio_carga"] - anterior
        datos["variacion_pct"] = round((datos["precio_carga"] - anterior) / anterior * 100, 2)
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    HISTORICO.write_text(json.dumps(historico, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"OK {datos['fecha']}: carga {datos['precio_carga']:,.0f} COP, "
          f"{len(datos['factores'])} factores, {len(datos['ciudades'])} ciudades")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv))
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
