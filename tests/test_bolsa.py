import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bolsa  # noqa: E402

# Cierres reales del 13 al 17 de noviembre de 2026 (cacao y café), tasas aproximadas
CIERRES = {
    "CC=F": ([5066.0, 5119.0, 5042.0, 5184.0], "Cocoa Dec 26"),
    "KC=F": ([284.1, 285.9, 283.2, 286.6], "Coffee Mar 27"),
    "COP=X": ([3812.0, 3809.5, 3820.1, 3815.4], "USD/COP"),
    "PEN=X": ([3.74, 3.75, 3.75, 3.76], "USD/PEN"),
    "DOP=X": ([63.1, 63.2, 63.3, 63.4], "USD/DOP"),
}
TIEMPOS = [1794459600, 1794546000, 1794805200, 1794891600]


def respuesta(simbolo, cierres=None):
    valores, nombre = CIERRES[simbolo]
    return {"chart": {"result": [{
        "meta": {"shortName": nombre, "gmtoffset": -18000},
        "timestamp": TIEMPOS,
        "indicators": {"quote": [{"close": cierres or valores}]},
    }], "error": None}}


def obtener_falso(url):
    simbolo = url.split("/chart/")[1].split("?")[0]
    return respuesta(simbolo)


# Respuesta real de CNBC del 17 de noviembre de 2026 (recortada)
CNBC_RESPUESTA = {"FormattedQuoteResult": {"FormattedQuote": [
    {"symbol": "@CC.1", "name": "Cocoa (Mar'27)", "last": "5,177.00", "last_time": "2026-11-17T00:00:00.000-0500",
     "settlePrice": "5177.00", "settleDate": "2026-11-17"},
    {"symbol": "@KC.1", "name": "Coffee (Mar'27)", "last": "281.40", "last_time": "2026-11-17T00:00:00.000-0500",
     "settlePrice": "281.40", "settleDate": "2026-11-17"},
    {"symbol": "COP=", "last": "3,304.81", "last_time": "2026-11-17T18:14:00.000-0500"},
    {"symbol": "PEN=", "last": "3.4103", "last_time": "2026-11-17T18:48:00.000-0500"},
    {"symbol": "DOP=", "last": "60.27", "last_time": "2026-11-17T18:22:00.000-0500"},
]}}


def obtener_cnbc(url):
    if "cnbc.com" in url:
        return CNBC_RESPUESTA
    raise AssertionError("no debería llegar a Yahoo")


class PruebasBolsa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        bolsa.DATOS = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_calcula_cacao_y_cafe(self):
        self.assertEqual(bolsa.main([], obtener=obtener_falso), 0)
        cacao = json.loads((bolsa.DATOS / "cacao.json").read_text())
        self.assertEqual(cacao["fecha"], "2026-11-17")
        self.assertEqual(cacao["usd_tonelada"], 5184.0)
        self.assertEqual(cacao["variacion_usd_tonelada"], 142.0)
        ec = cacao["paises"]["ecuador"]
        self.assertAlmostEqual(ec["precio_unidad"], 5184 / 1000 * 45.359237, places=1)  # US$ por quintal
        co = cacao["paises"]["colombia"]
        self.assertAlmostEqual(co["precio_kilo"], 5.184 * 3815.4, places=0)
        cafe = json.loads((bolsa.DATOS / "cafe-peru.json").read_text())
        self.assertAlmostEqual(cafe["precio_quintal"], 2.866 * 2.2046226218 * 46 * 3.76, places=0)
        hist = json.loads((bolsa.DATOS / "cacao-historico.json").read_text())
        self.assertEqual(len(hist), 1)

    def test_historico_no_duplica_fecha(self):
        bolsa.main([], obtener=obtener_falso)
        bolsa.main([], obtener=obtener_falso)
        hist = json.loads((bolsa.DATOS / "cafe-peru-historico.json").read_text())
        self.assertEqual(len(hist), 1)

    def test_valor_absurdo_falla(self):
        def malo(url):
            simbolo = url.split("/chart/")[1].split("?")[0]
            if simbolo == "CC=F":
                return respuesta(simbolo, [5066.0, 5119.0, 5042.0, 51.84])
            return respuesta(simbolo)
        bolsa.time.sleep = lambda s: None
        self.assertEqual(bolsa.main([], obtener=malo), 1)
        self.assertFalse((bolsa.DATOS / "cacao.json").exists())

    def test_cnbc_primero_y_variacion_desde_historico(self):
        (bolsa.DATOS / "cacao-historico.json").write_text(json.dumps(
            [{"fecha": "2026-11-16", "usd_tonelada": 5100.0}]))
        self.assertEqual(bolsa.main([], obtener=obtener_cnbc), 0)
        cacao = json.loads((bolsa.DATOS / "cacao.json").read_text())
        self.assertEqual(cacao["usd_tonelada"], 5177.0)
        self.assertEqual(cacao["fecha"], "2026-11-17")
        self.assertEqual(cacao["variacion_usd_tonelada"], 77.0)
        self.assertIn("CNBC", cacao["fuente"])
        self.assertEqual(cacao["paises"]["colombia"]["tasa"], 3304.81)
        cafe = json.loads((bolsa.DATOS / "cafe-peru.json").read_text())
        self.assertEqual(cafe["usc_libra"], 281.4)
        self.assertNotIn("variacion_pct", cafe)  # sin histórico previo no inventa variación

    def test_si_cnbc_falla_usa_yahoo(self):
        def mixto(url):
            if "cnbc.com" in url:
                raise OSError("HTTP Error 403")
            return obtener_falso(url)
        self.assertEqual(bolsa.main([], obtener=mixto), 0)
        cacao = json.loads((bolsa.DATOS / "cacao.json").read_text())
        self.assertIn("Yahoo", cacao["fuente"])
        self.assertEqual(cacao["usd_tonelada"], 5184.0)

    def test_ignora_cierres_vacios(self):
        d = respuesta("CC=F", [5066.0, 5119.0, 5042.0, None])
        c = bolsa.extraer_cierre(d, "CC=F")
        self.assertEqual(c["valor"], 5042.0)
        self.assertEqual(c["fecha"], "2026-11-16")


if __name__ == "__main__":
    unittest.main()
