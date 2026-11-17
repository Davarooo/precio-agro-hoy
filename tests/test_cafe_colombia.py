import sys
import unittest
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))
sys.path.insert(0, str(RAIZ / "tests"))

import cafe_colombia as cc  # noqa: E402
import crear_pdf_prueba as muestra  # noqa: E402


class PruebasParser(unittest.TestCase):
    def setUp(self):
        self.pdf = muestra.construir()

    def test_valores_principales(self):
        d = cc.parsear(self.pdf)
        cc.validar(d)
        self.assertEqual(d["fecha"], "2026-11-17")
        self.assertEqual(d["precio_carga"], 2_115_000)
        self.assertEqual(d["factor_referencia"], 94)
        self.assertEqual(d["bolsa_ny_usc_lb"], 286.60)
        self.assertEqual(d["pasilla_cop_kg"], 12_000)
        self.assertEqual(len(d["factores"]), 13)
        self.assertEqual(len(d["ciudades"]), 16)
        medellin = next(c for c in d["ciudades"] if c["ciudad"] == "Medellín")
        self.assertEqual(medellin["carga"], 2_114_625)

    def test_flujo_comprimido(self):
        """Si la Federacion empieza a comprimir el contenido, debe seguir leyendo."""
        comprimido = self.pdf
        for pagina in (muestra.PAGINA1, muestra.PAGINA2):
            plano = muestra.flujo(pagina)
            comprimido = comprimido.replace(plano, zlib.compress(plano))
        d = cc.parsear(comprimido)
        self.assertEqual(d["precio_carga"], 2_115_000)

    def test_pdf_sin_texto_falla(self):
        with self.assertRaises(ValueError):
            cc.parsear(b"%PDF-1.3\n%%EOF")

    def test_precio_absurdo_falla(self):
        d = cc.parsear(self.pdf)
        d["precio_carga"] = 50
        with self.assertRaises(ValueError):
            cc.validar(d)


if __name__ == "__main__":
    unittest.main()
