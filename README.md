# Precio Agro Hoy

Página de precio del café en Colombia que se actualiza sola todos los días con el PDF de la Federación Nacional de Cafeteros.

## Cómo funciona

1. GitHub Actions ejecuta `scripts/cafe_colombia.py` de lunes a viernes a las 5:30 p. m. (hora Colombia) y repite a las 7:30 a. m. por si la Federación publicó tarde.
2. El script busca el PDF vigente en la página de publicaciones, lo lee y guarda `data/cafe-colombia.json` y `data/cafe-colombia-historico.json`.
3. La página de Blogger lee esos dos archivos y muestra el precio, la calculadora, la tabla por ciudad, la tabla por factor de rendimiento y el histórico.
4. Si el PDF cambia de formato o no se puede descargar, el proceso falla y GitHub te envía un correo.

## Instalación (unos 30 minutos)

### 1. GitHub

1. Crea una cuenta en github.com si no tienes.
2. Crea un repositorio **público** llamado `precio-agro-hoy`. Tiene que ser público para que la página pueda leer los datos sin contraseña.
3. Sube todo el contenido de esta carpeta (arrastra los archivos y carpetas a la página del repositorio, incluida la carpeta `.github`).
4. Ve a **Settings → Actions → General → Workflow permissions**, marca **Read and write permissions** y guarda.
5. Ve a la pestaña **Actions**, abre **Actualizar precios** y pulsa **Run workflow**. En un par de minutos debe quedar en verde y el archivo `data/cafe-colombia.json` debe mostrar la fecha de hoy.
6. Revisa en **Settings (de tu cuenta) → Notifications → Actions** que esté activado el aviso por correo de flujos fallidos.

### 2. Blogger

1. Entra a blogger.com con tu cuenta de Google y crea un blog. Nombre sugerido: **Precio Agro Hoy**.
2. Ve a **Páginas → Nueva página**. Título: **Precio del café hoy en Colombia**.
3. Cambia el editor a **Vista HTML** (ícono `< >`).
4. Abre `blogger/cafe-colombia.html`, copia todo y pégalo.
5. En las dos primeras líneas del bloque `PAH_CONFIG`, cambia `TU_USUARIO` por tu usuario de GitHub.
6. Publica y abre la página para comprobar que aparece el precio.

Si Blogger quita el código al guardar, pega el mismo contenido en un gadget **HTML/JavaScript** desde **Diseño** y deja la página solo con un texto introductorio.

### 3. Google

1. Agrega el blog en Google Search Console (Blogger ofrece la verificación automática).
2. Envía el mapa del sitio: `https://TU-BLOG.blogspot.com/sitemap.xml`.
3. Solicita indexación de la página del café.

## Pruebas

```
python3 -m unittest discover -s tests -v
```

Las pruebas usan un PDF de muestra con el mismo formato del original y los valores del 17 de noviembre de 2026.

## Riesgos conocidos

- La Federación puede cambiar el formato del PDF o su dirección. El script busca el enlace en la página de publicaciones antes de usar la dirección guardada, y si falla te llega el correo.
- El sitio de la Federación podría bloquear las descargas desde los servidores de GitHub. En ese caso la alternativa es correr la descarga desde Google Apps Script.
- GitHub desactiva los flujos programados de repositorios públicos sin actividad durante 60 días. Los commits diarios del propio flujo deberían mantenerlo activo; si aun así se desactiva, GitHub avisa por correo y se reactiva desde la pestaña Actions.
- Los datos son de la Federación Nacional de Cafeteros; la página la cita como fuente.
