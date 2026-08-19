# Guía de instalación — RPI_Cluster

Esta guía es para instalar y correr el programa por primera vez en un computador
Windows. **No necesitas saber programar.** Vas a copiar y pegar comandos.

Si algo no funciona, ve directo a la sección **[Problemas comunes](#problemas-comunes)**
al final: están los errores típicos con su solución.

---

## ¿Qué hace este programa?

Consulta las páginas oficiales de 9 autoridades sanitarias (Colombia, Ecuador,
El Salvador, Guatemala, Honduras, República Dominicana, Costa Rica, más EMA de
Europa y FDA de Estados Unidos), busca las moléculas que le interesan al equipo,
y genera **archivos de Excel/CSV** con los registros sanitarios de la competencia.

Lo que antes tomaba horas de búsqueda manual, el programa lo hace en minutos y
con el mismo formato siempre.

---

## Antes de empezar: qué necesitas

| Necesitas | Para qué | Cómo saber si lo tienes |
|---|---|---|
| **Python 3.11** | Es el lenguaje en que está escrito el programa | Paso 1 te lo dice |
| **Google Chrome** | Tres países (Guatemala, Rep. Dominicana, Costa Rica) requieren abrir un navegador | Si lo usas normalmente, ya lo tienes |
| **La carpeta del proyecto** | El programa en sí | Te la entrega tu equipo o la descargas del repositorio |
| **Conexión a internet** | Consulta páginas web oficiales | — |

> **Nota:** el programa no instala nada raro ni modifica tu computador. Todo lo que
> descarga queda dentro de su propia carpeta.

---

## Paso 0 — Abrir la terminal

Casi todos los pasos se hacen en la **terminal** (también llamada PowerShell). Es
una ventana donde escribes comandos en vez de hacer clic.

**Cómo abrirla:**
1. Presiona la tecla `Windows`
2. Escribe `powershell`
3. Presiona `Enter`

Se abre una ventana azul o negra con texto. Ahí vas a pegar los comandos.

> **Truco:** para pegar en la terminal usa `Ctrl + V` o clic derecho. Después de
> pegar cada comando, presiona `Enter` para ejecutarlo.

---

## Paso 1 — Verificar si tienes Python

Copia y pega esto en la terminal, y presiona `Enter`:

```powershell
python --version
```

**Si responde algo como `Python 3.11.2`** → perfecto, sigue al Paso 2.

**Si responde `Python 3.9` o superior** → también sirve, sigue al Paso 2.

**Si dice "no se reconoce" o abre la Microsoft Store** → no lo tienes instalado.
Haz esto:

1. Ve a **https://www.python.org/downloads/**
2. Descarga Python 3.11 (o la versión más reciente)
3. Al ejecutar el instalador, **marca la casilla que dice
   `Add Python to PATH`** antes de darle a "Install Now"

   ⚠️ Este es el error más común. Si no marcas esa casilla, Windows no encuentra
   Python después y nada funciona.

4. Cierra la terminal, ábrela de nuevo, y repite el comando de arriba.

---

## Paso 2 — Ir a la carpeta del proyecto

Necesitas decirle a la terminal dónde está el programa. Suponiendo que la carpeta
se llama `RPI_PACA` y está en Descargas:

```powershell
cd $HOME\Downloads\RPI_PACA
```

**Para confirmar que estás en el lugar correcto**, ejecuta:

```powershell
dir rpi_cluster.py
```

Si te muestra el archivo `rpi_cluster.py`, vas bien. Si dice que no lo encuentra,
la ruta está mal — busca la carpeta en el Explorador de Windows, copia su
dirección de la barra superior, y usa `cd` con esa ruta.

---

## Paso 3 — Crear el entorno virtual

Un **entorno virtual** es una carpeta donde se instalan las herramientas que el
programa necesita, sin tocar el resto de tu computador. Es como un cajón aparte:
si algo sale mal, borras el cajón y ya.

```powershell
python -m venv .venv
```

Tarda unos segundos y no muestra nada. Es normal.

Ahora hay que **activarlo**:

```powershell
.venv\Scripts\Activate.ps1
```

**Cómo saber que funcionó:** al inicio de la línea de la terminal aparece `(.venv)`.
Se ve así:

```
(.venv) PS C:\Users\tu-usuario\Downloads\RPI_PACA>
```

> ⚠️ **Importante:** tienes que activar el entorno **cada vez** que abras una
> terminal nueva para usar el programa. Si no ves `(.venv)`, ejecuta el comando
> de activación otra vez.

**Si sale un error rojo sobre "ejecución de scripts está deshabilitada"**, ejecuta
esto una sola vez y luego repite la activación:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## Paso 4 — Instalar las herramientas

Con el entorno activado (recuerda: debes ver `(.venv)`), ejecuta:

```powershell
pip install -r requirements.txt
```

Esto descarga las 4 herramientas que el programa necesita. Tarda **1 a 3 minutos**
y muestra mucho texto — es normal.

**Terminó bien si** al final ves una línea que empieza con
`Successfully installed` seguida de varios nombres.

---

## Paso 5 — Verificar que todo quedó bien

Antes de hacer una consulta real, comprobamos que la instalación está sana. Este
comando corre 132 pruebas internas **sin salir a internet**, en unos 5 segundos:

```powershell
python -m unittest discover -s tests -t .
```

**Resultado esperado** — la última línea debe decir:

```
OK (skipped=11)
```

- `OK` significa que todo está bien instalado.
- Los `skipped` (omitidos) son normales: son pruebas que sí salen a internet y se
  saltan a propósito en esta verificación.

**Si dice `FAILED`** → algo quedó mal instalado. Ve a
[Problemas comunes](#problemas-comunes).

---

## Paso 6 — Configuración (puedes saltarlo)

**No hay nada que configurar.** El programa funciona tal cual: no pide usuario,
ni contraseña, ni token de ningún tipo.

Si más adelante alguien te pide cambiar la carpeta de salida, se hace copiando
la plantilla y editándola con el Bloc de notas:

```powershell
copy .env.example .env
```

> 🔒 **Importante — este programa NO envía datos a ningún lado.**
> Solo lee páginas web públicas y **escribe archivos en tu computador**. No manda
> correos automáticos ni sube nada a Notion, Airtable ni ningún otro servicio.
> Es intencional: la empresa no permite conectores automatizados.
>
> **La entrega de resultados es manual:** abres el Excel que genera el programa
> y copias las filas al archivo consolidado del equipo.

---

## Paso 7 — Tu primera consulta

Empecemos con algo pequeño para confirmar que funciona: buscar una sola molécula
en la FDA (Estados Unidos), que es rápido y no necesita navegador.

```powershell
python rpi_cluster.py --country FDA --molecule regorafenib
```

Deberías ver algo así:

```
→ FDA starting…
    [FDA] collected 3 rows
  FDA done: 3 approvals, 0 submissions → RPIFDA_canonical.csv
```

Los resultados quedan en la carpeta `output`. Ábrela y verás archivos `.csv` que
puedes abrir con Excel.

---

## Paso 8 — La corrida completa

Cuando ya confirmaste que funciona, esta es la consulta real de todos los países
y todas las moléculas:

```powershell
python rpi_cluster.py
```

**Qué esperar:**
- Tarda entre **15 y 30 minutos**
- Se van a **abrir ventanas de Chrome solas** — es normal, son los países que
  necesitan navegador (Guatemala, Rep. Dominicana, Costa Rica).
  **No las cierres ni toques el mouse** mientras trabajan.
- Al final muestra una tabla resumen con cada país y su estado.

---

## Cómo leer el resultado

Al terminar, el programa muestra una tabla como esta:

```
║ Country        ║ Approvals  ║ Submissions ║ Status           ║
║ FDA (US)       ║ 253        ║ 112         ║ ✅ OK            ║
║ Colombia       ║ 91         ║ 565         ║ ✅ OK            ║
║ Costa Rica     ║ 130        ║ 476         ║ ✅ OK            ║
```

**Qué significa cada símbolo** — esto es lo más importante de entender:

| Símbolo | Significa | ¿Qué haces? |
|---|---|---|
| ✅ **OK** | Funcionó y encontró registros | Nada, todo bien |
| ⚠️ **Empty** | Funcionó bien, pero **no hay registros** de esas moléculas en ese país | **Nada.** Esto NO es un error: es información válida (significa "buscamos y no hay") |
| ⚠️ **Failed** | **No se pudo consultar** la página | Reintentar más tarde; si sigue, avisar |
| ⚠️ **Partial** | Funcionó a medias: algunas moléculas sí, otras fallaron | Revisar el log y avisar |
| 🔄 **Skipped** | Se omitió a propósito | Normal si usaste alguna bandera |
| ❌ **Error** | Falla inesperada | Avisar con el archivo de log |

> 💡 **La diferencia entre `Empty` y `Failed` es clave para el trabajo regulatorio.**
> `Empty` significa "la búsqueda sí se hizo y no hay registro" — es un dato real y
> confiable. `Failed` significa "no pudimos mirar" — ahí no sabes nada. Nunca
> reportes un `Failed` como si fuera "no hay producto".

---

## Archivos que genera

Todo queda en la carpeta `output`:

| Archivo | Qué contiene |
|---|---|
| `RPICO_aprob_canonical.csv` | Aprobaciones de Colombia |
| `RPICR_canonical.csv` | Costa Rica |
| *(uno por cada país)* | … |
| **`RPI_CONSOLIDATED.csv`** | **Todo junto — este es el que subes a SharePoint.** Siempre se llama igual y se sobrescribe en cada corrida. ⚠️ **No le cambies el nombre**: el flujo de Power Automate lo busca en una ruta fija. |
| `_history\` | Copias fechadas de corridas anteriores. No se sube; solo por si hay que consultar el pasado. |
| `RPI_REPORT_DDMMAAAA.xlsx` | Reporte ejecutivo en Excel con resumen y gráficos |
| `rpi_run_DDMMAAAA.log` | Registro detallado de la corrida (útil si algo falló) |

Todos los CSV se abren directamente con Excel y tienen las mismas 19 columnas
siempre, sin importar el país.

---

## Comandos útiles

```powershell
# Un solo país (útil para probar o repetir uno que falló)
python rpi_cluster.py --country CO

# Una sola molécula, en todos los países
python rpi_cluster.py --molecule dapagliflozin

# Solo las fuentes rápidas, sin navegador (5-8 minutos)
python rpi_cluster.py --tier-a

# Sin abrir Chrome (omite Guatemala, Rep. Dominicana y Costa Rica)
python rpi_cluster.py --no-selenium

# Ver todas las opciones disponibles
python rpi_cluster.py --help
```

Códigos de país válidos: `CO` `EC` `SV` `GT` `HN` `DO` `CR` `EMA` `FDA`

> **Perú (`PE`) está desactivado** por decisión de alcance. Si lo pides, el programa
> lo indica con ⛔ y sigue sin error — no es una falla.

---

## Problemas comunes

### «python no se reconoce como un comando»
Python no está instalado, o no se marcó `Add Python to PATH` al instalarlo.
Reinstálalo desde python.org marcando esa casilla (ver Paso 1).

### «No se puede cargar el archivo Activate.ps1 … la ejecución de scripts está deshabilitada»
Windows bloquea scripts por defecto. Ejecuta una sola vez:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
Responde `S` (sí) y vuelve a activar el entorno.

### «ModuleNotFoundError: No module named 'requests'»
No se instalaron las herramientas, o el entorno no está activado.
Verifica que veas `(.venv)` al inicio de la línea; si no, actívalo (Paso 3) y
repite el Paso 4.

### Las pruebas dicen FAILED
Borra el entorno y empieza de nuevo:
```powershell
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Se abre Chrome y se queda pegado / da error de "chromedriver"
Casi siempre es que Chrome se actualizó. Ciérralo por completo (revisa que no
queden ventanas abiertas) y vuelve a correr. Si insiste, puedes trabajar sin los
países que usan navegador:
```powershell
python rpi_cluster.py --no-selenium
```

### Un país sale ⚠️ Failed pero los demás funcionan
Normalmente es que **esa página del gobierno está caída o lenta** — no es tu
computador. Espera un rato y reintenta solo ese país:
```powershell
python rpi_cluster.py --country CR
```
El programa **nunca borra los datos buenos** que ya tenías: si una corrida falla,
conserva lo de la corrida anterior.

### El programa se demora muchísimo
Es esperable: Ecuador descarga un archivo grande (~44 MB) y tarda 25-45 segundos,
y los países con navegador son lentos por naturaleza. Una corrida completa de
15-30 minutos es normal. Si tienes prisa, usa `--tier-a`.

---

## Cuándo pedir ayuda

Escribe al responsable del proyecto si:

- Varios países fallan al mismo tiempo (puede ser la red de la empresa)
- Un país falla **de forma consistente** varios días seguidos → probablemente
  la página web cambió y hay que ajustar el programa
- Ves ❌ **Error** (falla inesperada, distinta de Failed)
- Los datos se ven raros: productos de un país apareciendo en otro, fechas
  imposibles, moléculas que no pediste

**Siempre adjunta el archivo de log** (`output\rpi_run_DDMMAAAA.log`) — ahí está
el detalle técnico de qué pasó.
