"""Genera tests/precio_cafe_muestra.pdf imitando el formato del PDF de la
Federacion (texto en hexadecimal con 'x y Td <hex> Tj'), con los valores
publicados el 17 de noviembre de 2026."""
from pathlib import Path

PAGINA1 = [
    (9, 692, "Noviembre 17 / 2026"),
    (9, 675, "La Federación Nacional de"),
    (236, 601, "PRECIO EXTERNO"),
    (177, 590, "Cierre contrato C Nueva York"),
    (311, 590, "286.60 USCent/Lb"),
    (192, 559, "PRECIO INTERNO DE REFERENCIA"),
    (80, 547, "Precio total por carga de 125"),
    (233, 547, "Kg de pergamino seco FR 94"),
    (384, 547, "2,115,000"),
    (463, 547, "COP"),
    (80, 536, "Precio total  de pasilla"),
    (181, 536, "contenida en el pergamino"),
    (390, 536, "12,000"),
    (440, 536, "COP/Kg"),
    (75, 450, "Factor de"),
    (69, 442, "rendimiento"),
]
FILAS = """100 87.50 12.81 1,896,030 153,720 2,049,750
99 88.38 12.16 1,915,080 145,920 2,061,000
98 89.29 11.25 1,934,750 135,000 2,069,750
97 90.21 10.52 1,954,635 126,240 2,080,875
96 91.15 9.60 1,974,925 115,200 2,090,125
95 92.11 8.93 1,995,840 107,160 2,103,000
94 93.09 8.16 2,017,080 97,920 2,115,000
93 94.09 7.19 2,038,720 86,280 2,125,000
92 95.11 6.45 2,060,975 77,400 2,138,375
91 96.15 5.55 2,083,525 66,600 2,150,125
90 97.22 4.94 2,106,720 59,280 2,166,000
89 98.31 4.20 2,130,350 50,400 2,180,750
88 99.43 2.13 2,154,565 25,560 2,180,125"""
y = 290
for fila in FILAS.splitlines():
    for x, v in zip([125, 190, 271, 325, 414, 453], fila.split()):
        PAGINA1.append((x, y, v))
    y += 11

CIUDADES = """ARMENIA 2,115,500 16,924 211,550
BOGOTÁ 2,114,250 16,914 211,425
BUCARAMANGA 2,113,875 16,911 211,388
BUGA 2,116,250 16,930 211,625
CHINCHINÁ 2,115,375 16,923 211,538
CÚCUTA 2,113,375 16,907 211,338
IBAGUÉ 2,114,625 16,917 211,463
MANIZALES 2,115,375 16,923 211,538
MEDELLÍN 2,114,625 16,917 211,463
NEIVA 2,113,750 16,910 211,375
PAMPLONA 2,113,500 16,908 211,350
PASTO 2,113,500 16,908 211,350
PEREIRA 2,115,375 16,923 211,538
POPAYÁN 2,115,625 16,925 211,563
SANTA MARTA 2,117,125 16,937 211,713
VALLEDUPAR 2,114,750 16,918 211,475"""
PAGINA2 = [(50, 673, "Noviembre 17 / 2026"), (61, 628, "SUCURSAL ALMACAFÉ"), (240, 628, "Carga"),
           (349, 628, "Kilo"), (449, 628, "Arroba")]
y = 617
for linea in CIUDADES.splitlines():
    partes = linea.rsplit(" ", 3)
    for x, v in zip([61, 242, 349, 447], partes):
        PAGINA2.append((x, y, v))
    y -= 11
PAGINA2 += [(221, 424, "DESCUENTOS POR TAZA"), (61, 411, "1"), (242, 411, "2"), (349, 411, "3"), (447, 411, "4")]


def flujo(tokens):
    partes = ["q", "/F001 10.00 Tf"]
    for x, y, t in tokens:
        partes.append(f"BT {x}.00 {y}.00 Td <{t.encode('latin-1').hex().upper()}> Tj ET")
    partes.append("Q")
    return "\n".join(partes).encode("latin-1")


def construir():
    objetos = []
    for pagina in (PAGINA1, PAGINA2):
        datos = flujo(pagina)
        objetos.append(b"<< /Length %d >>\nstream\n" % len(datos) + datos + b"\nendstream")
    cuerpo = b"%PDF-1.3\n"
    for i, obj in enumerate(objetos, start=1):
        cuerpo += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    cuerpo += b"%%EOF\n"
    return cuerpo


if __name__ == "__main__":
    destino = Path(__file__).parent / "precio_cafe_muestra.pdf"
    destino.write_bytes(construir())
    print(f"Creado {destino}")
