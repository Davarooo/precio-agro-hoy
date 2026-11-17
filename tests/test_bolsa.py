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

    def test_ignora_cierres_vacios(self):
        d = respuesta("CC=F", [5066.0, 5119.0, 5042.0, None])
        c = bolsa.extraer_cierre(d, "CC=F")
        self.assertEqual(c["valor"], 5042.0)
        self.assertEqual(c["fecha"], "2026-11-16")


if __name__ == "__main__":
    unittest.main()
