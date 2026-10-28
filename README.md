# ComfyUI-AutoDownload2Client-Metadata

Descarga automáticamente los PNG de ComfyUI a tu PC mediante el navegador, con los metadatos completos `prompt` y `workflow` que guarda **Save Image**. Pensado para ComfyUI en Google Colab y Firefox en Windows, con la interfaz dentro del iframe del notebook.

Basado en [ComfyUI-AutoDownload2Client de iwindy910](https://github.com/iwindy910/ComfyUI-AutoDownload2Client). Conserva el identificador `AutoDownloadNode` y el nombre visible **AutoDownload2Client**, para reutilizar los workflows existentes.

## Qué cambia

- El PNG incorpora `prompt` y todos los campos de `extra_pnginfo`, incluido `workflow`, mediante `PngInfo` y `json.dumps`, igual que [Save Image](https://github.com/comfyanonymous/ComfyUI/blob/e1df394db644987bfbdd05c887a78b9115d49261/nodes.py#L1670).
- Se mantiene el transporte original: PNG en memoria → Base64 por WebSocket → Blob → descarga de Firefox. Se descargan los bytes originales, sin recodificar en un canvas. El nodo no guarda imágenes en Colab ni en Google Drive.
- Fecha configurable con `America/Mexico_City` por defecto, independientemente del reloj del servidor o navegador.
- Nombres con UUID completo por ejecución e índice de imagen para distinguir batches y ejecuciones simultáneas.
- Eventos dirigidos al cliente que ejecutó el workflow; vista previa asociada al ID del nodo, con batches y prefijos con guiones bajos.

## Instalación en Colab

Usa el Python del entorno donde corre ComfyUI. Las instrucciones asumen `/content/ComfyUI`; ajusta la ruta si es distinta.

1. Detén ComfyUI y guarda una copia del nodo original fuera de `custom_nodes` o con el sufijo `.disabled`. **Debe quedar una sola versión activa**, porque ambas usan la misma clase y extensión web.
2. Instala esta versión en la ubicación del nodo original:

```bash
cd /content/ComfyUI/custom_nodes
git clone https://github.com/daneelolivaw2020/ComfyUI-AutoDownload2Client-Metadata.git ComfyUI-AutoDownload2Client
python -m pip install -r ComfyUI-AutoDownload2Client/requirements.txt
```

3. Inicia ComfyUI y carga la interfaz una vez para recibir la nueva extensión JavaScript. Después no hace falta recargar el iframe durante el uso normal ni cambiar el notebook.
4. Conserva la configuración de Firefox que ya funciona: carpeta de descargas predeterminada y guardado automático, sin preguntar por cada archivo.

Para volver al original: detén ComfyUI, mueve esta versión fuera de `custom_nodes`, restaura tu copia e inicia ComfyUI otra vez. No se modifican otros nodos.

## Uso y nombres

Conecta una salida `IMAGE` a `image` y configura:

| Campo | Valor inicial | Uso |
|---|---|---|
| `filename_prefix` | `ComfyUI2Client` | Prefijo; admite `%batch_num%` con índice desde cero, como Save Image. |
| `timestamp_format` | `%Y-%m-%d_%H-%M-%S` | Comodines Python `strftime`. Vacío: omite la fecha, conservando la unicidad. |
| `timezone` | `America/Mexico_City` | Zona IANA; también `UTC` o `local` para la zona del servidor. |

Comodines: `%Y` año de cuatro cifras, `%y` año de dos, `%m` mes, `%d` día, `%H` hora de 24 horas, `%M` minuto, `%S` segundo, `%f` microsegundos y `%z` desplazamiento UTC. El formato de fecha del nodo original era `%y_%m%d_%H%M_%S`.

Ejemplo con prefijo `Luis`:

```text
Luis_2026-10-27_21-04-05_6434e8bfb8954b9fa46bdc97c2e78ef3_00001.png
Luis_2026-10-27_21-04-05_6434e8bfb8954b9fa46bdc97c2e78ef3_00002.png
```

Los caracteres incompatibles con Windows se sustituyen por `_`; se limita la longitud. El prefijo no selecciona una carpeta: la carpeta la controla Firefox.

Para recuperar el workflow, arrastra el **PNG descargado original** al lienzo de ComfyUI. Se conservan nodos, enlaces, widgets y todos los demás datos del workflow que ComfyUI entregó al ejecutar la imagen.

Como Save Image, el nodo respeta `--disable-metadata`: esa opción debe estar desactivada para recuperar workflows. Si ejecutas con una API propia, envía `extra_data.extra_pnginfo.workflow` junto al prompt; el nodo solo puede guardar los datos que recibe. La interfaz normal de ComfyUI envía ese campo.

## Prueba rápida en tu Colab

Abre [examples/smoke-test-workflow.json](examples/smoke-test-workflow.json). Usa solo Empty Image y AutoDownload2Client: produce cuatro PNG de 64 × 64 sin modelos ni GPU.

1. Ejecuta con `batch_size=1` y confirma una descarga automática.
2. Arrastra el PNG al lienzo: deben reaparecer ambos nodos y sus valores.
3. Cambia `batch_size` a `4`, ejecuta y confirma cuatro nombres distintos. Arrastra cualquiera y comprueba que conserva el batch de cuatro.
4. Cambia a **View output fullscreen**, ejecuta y regresa al iframe normal. Repite sin recargarlo.

Si repites sin cambiar ningún input, ComfyUI puede reutilizar la caché y no ejecutar el nodo. Cambia un input para esta prueba. Se conserva este comportamiento del nodo original.

## Pruebas locales y alcance

Validado el 28 de octubre de 2026:

- 14 pruebas Python: JSON completo y Unicode, píxeles RGB/RGBA, batches, ausencia de escrituras de imágenes en servidor, nombres únicos, formato de fecha, zona de Ciudad de México y nombres válidos para Windows.
- Comparación con la clase real Save Image de ComfyUI: seis PNG tienen los mismos metadatos y píxeles, con metadatos activados y desactivados.
- Firefox 153.0 en Windows mediante Playwright: nueve descargas reales en un iframe de otro origen, incluyendo pantalla completa y vuelta al modo normal, sin recargar el iframe. Los ocho PNG principales coinciden byte por byte con los enviados por Python. También se prueba registrar la extensión dos veces, seleccionar la vista previa correcta y descargar después de retirar el nodo del grafo.

**Pendiente:** validación completa en tu sesión real de ComfyUI/Colab y tu perfil habitual de Firefox. El ensayo local usa una API y un grafo de prueba; no equivale a haber probado el notebook ni el arrastre dentro de tu instalación real.

Repetir las pruebas:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python tests/compare_native.py /ruta/a/ComfyUI/nodes.py
```

Transporte en Firefox (Node.js y Playwright solo son dependencias de desarrollo):

```bash
npm install --no-save playwright@1.62.1
npx playwright install firefox
python tests/export_fixture.py fixture.json
node tests/browser_download.cjs fixture.json downloads
```

El CI ejecuta las pruebas Python en Windows/Linux y Firefox en Windows. Consulta su estado en Actions; las pruebas locales no implican que el CI ya haya terminado.

Base original: [`6fad00f`](https://github.com/iwindy910/ComfyUI-AutoDownload2Client/commit/6fad00fa4361d2386a1fdb5679f2bbd24eec8342). Referencia nativa: [ComfyUI `e1df394`](https://github.com/comfyanonymous/ComfyUI/commit/e1df394db644987bfbdd05c887a78b9115d49261). Se conserva la licencia Apache 2.0 y la atribución en `NOTICE`.
