# Runbook operativo — RPI_Cluster

Guía del día a día: cada cuánto correr, qué revisar antes de reportar datos, qué
hacer cuando algo falla y cuándo escalar.

> ¿Primera vez? Instala primero con **[INSTALACION.md](INSTALACION.md)**.

---

## Índice

1. [Rutina recomendada](#1-rutina-recomendada)
2. [Antes de reportar: 5 verificaciones](#2-antes-de-reportar-5-verificaciones)
3. [Qué significa cada estado](#3-qué-significa-cada-estado)
4. [Qué hacer cuando un país falla](#4-qué-hacer-cuando-un-país-falla)
5. [Límites de cada fuente](#5-límites-de-cada-fuente-importante)
6. [Señales de alarma en los datos](#6-señales-de-alarma-en-los-datos)
7. [Cuándo y cómo escalar](#7-cuándo-y-cómo-escalar)

---

## 1 · Rutina recomendada

| Cada cuánto | Comando | Dura | Para qué |
|---|---|---|---|
| **Semanal** (lunes) | `python rpi_cluster.py` | 15-30 min | La corrida completa. Es la principal. |
| **Diario** (si se necesita) | `python rpi_cluster.py --tier-a` | 5-8 min | Solo fuentes rápidas: EMA, FDA, Colombia, El Salvador, Honduras |
| **Puntual** | `python rpi_cluster.py --country XX` | 1-10 min | Reintentar un país que falló, o consultar uno específico |

**Recuerda:** activa el entorno antes de cada sesión (debes ver `(.venv)`):

```powershell
cd $HOME\Downloads\RPI_PACA
.venv\Scripts\Activate.ps1
```

### Durante la corrida completa
- Se abren ventanas de **Chrome solas** (Guatemala, Rep. Dominicana, Costa Rica).
  **No las cierres ni muevas el mouse sobre ellas.**
- Puedes seguir trabajando en otras aplicaciones, pero no apagues el computador.

---

## 2 · Antes de reportar: 5 verificaciones

Nunca envíes datos sin pasar por esta lista. Toma 3 minutos y evita reportar
información equivocada.

### ✅ 1. ¿Todos los países dicen OK?
Mira la tabla resumen al final. Si alguno dice **Failed** o **Error**, esos datos
están incompletos → ve a la [sección 4](#4-qué-hacer-cuando-un-país-falla).

### ✅ 2. ¿Los números son razonables?
Compara contra la corrida anterior. Valores de referencia normales:

| País | Filas esperadas (aprox.) |
|---|---|
| Colombia | 650 – 700 |
| Costa Rica | 550 – 650 |
| FDA (US) | 350 – 400 |
| Rep. Dominicana | 300 – 330 |
| El Salvador | 160 – 190 |
| Ecuador | 150 – 175 |
| Honduras | 100 – 115 |
| EMA (EU) | 55 – 70 |
| Guatemala | 25 – 35 |

> Una caída brusca (ej. Colombia de 650 a 0) casi siempre significa que la página
> del gobierno está caída o cambió — **no** que desaparecieron los registros.

### ✅ 3. ¿El consolidado se regeneró?
El archivo se llama **siempre igual**: `output\RPI_CONSOLIDATED.csv`. Verifica que su
**fecha de modificación sea de hoy** (clic derecho → Propiedades, o la columna
"Fecha de modificación" en el Explorador).

> Ese nombre fijo es a propósito: es el archivo que subes a SharePoint, y el flujo de
> Power Automate / Fabric lo lee desde una ruta fija. **No le cambies el nombre ni le
> agregues la fecha** — si lo haces, el flujo deja de encontrarlo.
>
> Cada corrida guarda además una copia fechada en `output\_history\` por si hace falta
> consultar qué se reportó en una fecha pasada. Esa carpeta no se toca ni se sube.

### ✅ 4. ¿Los países coinciden con sus registros?
Abre el consolidado y revisa que la columna `country_code` cuadre con el formato
del `registration_number`:

| País | Formato típico del registro |
|---|---|
| Colombia | `INVIMA 2025M-0012345` |
| Costa Rica | `M-IN-26-20788`, `M-DE-15-00214` |
| Honduras | `HN-M-0723-0046` |
| Ecuador | `10011-MEE-0525` |
| FDA | `NDA210951-001`, `ANDA209728` |
| EMA | `EMEA/H/C/005647` |

> ⚠️ Si ves un registro `HN-...` marcado como `CR`, o cualquier mezcla parecida,
> **detente y escala**. Eso pasó una vez (ver [sección 6](#6-señales-de-alarma-en-los-datos)).

### ✅ 5. ¿Las fechas tienen sentido?
No debe haber fechas de aprobación **en el futuro**. Si las ves, hay un problema
de interpretación de formato → escalar.

---

## 3 · Qué significa cada estado

| Estado | Significa | ¿Los datos sirven? |
|---|---|---|
| ✅ **OK** | Consultó bien y encontró registros | Sí |
| ⚠️ **Empty** | Consultó bien, **no hay registros** de esas moléculas ahí | **Sí** — es un dato válido |
| ⚠️ **Failed** | **No se pudo consultar** la página | **No** — no sabes nada de ese país |
| ⚠️ **Partial** | Algunas moléculas sí, otras fallaron | Parcialmente — revisar el log |
| 🔄 **Skipped** | Omitido a propósito (por una bandera) | No aplica |
| ❌ **Error** | Falla inesperada del programa | No — escalar |
| ⛔ **Disabled** | Extractor desactivado a propósito | No aplica — hay un problema conocido |

### 🔑 La distinción más importante de todo el runbook

**`Empty` y `Failed` NO son lo mismo, aunque los dos muestren 0 registros.**

- **`Empty`** = *"Buscamos en el registro sanitario de ese país y confirmamos que no
  hay producto de la competencia con esa molécula."* → Es una **conclusión válida**
  que puedes reportar.

- **`Failed`** = *"No pudimos entrar a la página."* → **No sabes nada.** Puede haber
  10 productos nuevos y no te enteraste.

Reportar un `Failed` como si fuera "no hay competencia" es el error más costoso que
se puede cometer con esta herramienta. Si un país dice `Failed`, repórtalo como
*"pendiente de verificar"*, nunca como *"sin registros"*.

---

## 4 · Qué hacer cuando un país falla

### Regla general
1. **Reintenta solo ese país** (los demás datos ya están guardados):
   ```powershell
   python rpi_cluster.py --country CO
   ```
2. Si falla otra vez, espera **unas horas** e intenta de nuevo. Las páginas de
   gobierno se caen con frecuencia.
3. Si falla **3 días seguidos**, escala (ver [sección 7](#7-cuándo-y-cómo-escalar)).

> 💡 El programa **nunca borra los datos buenos**. Si una corrida sale vacía o
> falla, conserva los de la corrida anterior. Por eso reintentar es seguro.

### Por país

| País | Falla típica | Qué hacer |
|---|---|---|
| **Colombia** | ⚠️ Failed con mensaje *"el dataset CUM está vacío"* | **No es tu culpa ni un error del programa.** INVIMA publicó los datos abiertos vacíos (pasó el 16/08/2026: los 4 datasets CUM quedaron en 0 filas). El programa lo detecta y lo marca como **Failed**, no como Empty, justamente para que **nunca reportes "no hay competencia en Colombia"** cuando en realidad nadie puede ver los datos. Reintentar en unos días; si dura más de una semana, escalar. Mientras tanto el consolidado conserva los datos de la última corrida buena. |
| **Costa Rica** | Error de reCAPTCHA / navegador | Cierra todo Chrome y reintenta. Necesita conexión estable. |
| **Guatemala / Rep. Dominicana** | Error de navegador o tabla no encontrada | Cierra Chrome, verifica que esté actualizado, reintenta. |
| **Ecuador** | Muy lento o se corta | Descarga un archivo de ~44 MB. Con red lenta puede fallar. Reintentar; si urge, saltarlo con `--no-ec`. |
| **Honduras / El Salvador** | Error de descarga | Suele ser la página. Reintentar. |
| **EMA** | Error 404 | Significa que EMA **cambió la dirección** de su reporte. Esto ya pasó una vez. **Escalar** — requiere ajuste del programa. |
| **FDA** | Error de límite de peticiones | Muy raro. Esperar unos minutos. |
| **Perú** | — | **Desactivado** a propósito. Sale ⛔ Disabled, no es un fallo. |

### Si fallan varios países a la vez
Probablemente sea **tu conexión o la red de la empresa**, no las páginas. Verifica
que puedas navegar normalmente y reintenta.

---

## 5 · Límites de cada fuente (IMPORTANTE)

Cada autoridad publica cosas distintas. Estos límites **no son errores** — son
características de la fuente. Conocerlos evita malinterpretar los datos.

| Fuente | Qué debes saber |
|---|---|
| **Colombia — trámites** | ⛔ **Desactivado a propósito.** Los trámites de Colombia los lleva el equipo de Regulatory en su propio documento de transparencia de INVIMA, que sí trae las novedades recientes. La fuente automática solo llegaba hasta julio de 2024, así que nunca servía para alertas. Verás ⛔ Disabled en el resumen: **no es un fallo**. |
| **Colombia — aprobaciones** | Sí se extraen normalmente y están al día. |
| **Costa Rica** | No publica **concentración** ni **forma farmacéutica** → esas columnas van vacías. Los **trámites no tienen fecha** → `submission_date` vacío. |
| **Ecuador** | Descarga **dos** reportes completos: *Registros Sanitarios Vigentes* (aprobaciones, ~15k filas) y *Total de Solicitudes Ingresadas* (solicitudes, ~2.9k filas). Tarda 30-60 s porque baja todo y filtra en memoria. Es la única fuente que aporta solicitudes con fechas recientes. |
| **EMA** | Solo medicamentos de **uso humano** (excluye veterinarios a propósito). |
| **FDA** | Genera **una fila por presentación**, no por trámite. Un mismo producto con 3 concentraciones = 3 filas. Es correcto. |
| **Honduras, El Salvador, Guatemala, Rep. Dominicana** | Solo **aprobaciones**; sus portales no publican trámites en curso. Por eso su columna de solicitudes dice `N/A`. |
| **Guatemala — fecha calculada** | MSPAS no publica fecha de emisión. Se **calcula** como *fecha de vencimiento − 5 años* (el registro sanitario dura 5 años). Tiene precisión de día y las 29 filas la traen. |
| **Honduras — fecha calculada** | ARSA tampoco publica fecha. Se **deduce del número de registro**: `HN-M-MMAA-NNNN` → mes y año (ej. `HN-M-0723-…` = julio 2023). ⚠️ **Solo se conoce mes y año**, así que el día siempre aparece como **01** — no es el día real de aprobación. Los 30 registros con formato antiguo de 5 dígitos (`45992`) **no traen fecha**, y eso es correcto: no hay de dónde deducirla. |
| **Perú** | **Desactivado** (⛔) por decisión de alcance del 16/08/2026, pendiente de compliance. Si lo pides con `--country PE`, el programa lo informa y sigue — no es un fallo. Sus datos históricos quedaron guardados en `output\_quarantine\`. |

### Filtros que aplica el programa
Dos moléculas se filtran por indicación después de extraer, porque el registro
sanitario no distingue el uso:

- **Bevacizumab** → solo se conservan los de **uso oftálmico** (se descartan los
  oncológicos sistémicos)
- **Ranibizumab** → solo **biosimilares** (se descarta el originador, Lucentis)

Verás en pantalla líneas como `post-filter dropped 13 row(s)`. **Es correcto**, no
es pérdida de datos.

### Moléculas "vigiladas aunque no existan"
Tres terapias nuevas (**Marstacimab**, **Valoctocogene roxaparvovec**,
**Efanesoctocog alfa**) generan una fila especial `NO_DATA` en los países donde se
buscó y no había nada. Sirve para demostrar que **sí se revisaron**. No las cuentes
como productos registrados.

---

## 6 · Señales de alarma en los datos

Revisa esto si algo "se ve raro". Estos patrones indican un problema serio:

| Señal | Qué puede significar |
|---|---|
| Registros de un país aparecen bajo otro (ej. `HN-M-...` marcado como `CR`) | **Contaminación cruzada.** Escalar de inmediato. |
| Un país sube o baja drásticamente sin explicación | La página cambió o está devolviendo datos parciales |
| Fechas de aprobación **en el futuro** | Error de interpretación de formato de fecha |
| Una molécula que no está en el panel | Filtro demasiado amplio |
| Un país dice ✅ OK pero con muy pocas filas | Puede estar leyendo la fuente equivocada |

> **Contexto real:** en agosto de 2026 se detectó que Costa Rica llevaba tiempo
> entregando **datos de Honduras** etiquetados como costarricenses, y el programa
> reportaba ✅ OK. Se detectó porque los números eran sospechosamente bajos y los
> formatos de registro no cuadraban. Ya está corregido, pero **por eso existe la
> verificación 4 de la [sección 2](#2-antes-de-reportar-5-verificaciones)**: un ✅ OK
> no garantiza que los datos sean del país correcto. Revisa siempre los formatos.

---

## 7 · Cuándo y cómo escalar

### Escala de inmediato si:
- Ves **contaminación cruzada** entre países
- Un país falla **3 días seguidos**
- Aparece ❌ **Error** (distinto de Failed)
- Los datos contradicen algo que sabes por otra vía
- EMA da error 404 (significa que cambió su publicación)

### Qué incluir al escalar

1. **Qué comando ejecutaste** (ej. `python rpi_cluster.py --country CR`)
2. **Qué esperabas y qué pasó**
3. **El archivo de log**: `output\rpi_run_DDMMAAAA.log` ← siempre adjúntalo
4. **Captura de la tabla resumen** final
5. Si es problema de datos: el CSV y **qué filas específicas** se ven mal

### Diagnóstico rápido antes de escalar

```powershell
# ¿La instalación está sana? (5 segundos, sin internet)
python -m unittest discover -s tests -t .
```

Si dice `OK` → la instalación está bien, el problema es la página web o la red.
Si dice `FAILED` → problema de instalación, reinstala (ver INSTALACION.md).

---

## Referencia rápida

```powershell
# Corrida completa (semanal)
python rpi_cluster.py

# Solo fuentes rápidas
python rpi_cluster.py --tier-a

# Un país
python rpi_cluster.py --country CO

# Una molécula en todos los países
python rpi_cluster.py --molecule dapagliflozin

# Sin navegador (omite GT, DO, CR)
python rpi_cluster.py --no-selenium

# Sin Ecuador (ahorra 45 s)
python rpi_cluster.py --no-ec

# Verificar instalación
python -m unittest discover -s tests -t .
```

**Códigos de país:** `CO` `CR` `EC` `SV` `GT` `HN` `DO` `EMA` `FDA`
