# AppDynamics - Calculadora de Licencias

Calculadora de licencias AppDynamics basada en CPUs, cubriendo:

- **APM** (Application Performance Monitoring): 1 CPU core = 1 licencia
- **Database**: 1 CPU core = 1 licencia (AppDynamics SaaS)
- **Server Visibility**: Por instancia de sistema operativo (incluido en APM o separado)
- **RUM Browser**: Sesiones y/o usuarios conectados al mes → Pageviews → RUM Tokens (10M pageviews/año por unidad)
- **RUM Mobile**: Apps activas por mes → Active Agents (5000 por unidad, 160 tokens/agente/mes)

## Uso

### 1. Interfaz web (recomendado)

```bash
# Crear entorno virtual e instalar dependencias
python3 -m venv venv
source venv/bin/activate   # En Windows: venv\Scripts\activate
pip install -r requirements.txt

# Ejecutar servidor
python app.py
```

Abre http://localhost:5000 en el navegador.

- **Cargar Excel**: Sube un archivo con la hoja "Anexo Aplicaciones" para extraer aplicaciones, bases de datos, SAP, microservicios y apps móviles.
- **Ingreso manual**: Completa o edita las tablas y haz clic en "Calcular licencias".

### 2. Línea de comandos

```bash
source venv/bin/activate
python license_calculator.py
```

### 3. Desde Python

```python
from license_calculator import (
    calculate_licenses,
    parse_excel_anexo_aplicaciones,
    Application,
    Database,
    SAPApplication,
    Microservice,
    MobileApp,
)

# Opción A: desde Excel
parsed = parse_excel_anexo_aplicaciones("MiFel_sizing-Architecture.xlsx")
result = calculate_licenses(**parsed)

# Opción B: datos manuales
apps = [
    Application("MiApp", "Jboss 7", "Java", nodes=4, cores_per_node=8,
                is_web_app=True, sessions_users_per_month=2000),
]
dbs = [Database("Oracle", "11G", 12, 2, "RHEL 7", "MiApp")]
result = calculate_licenses(applications=apps, databases=dbs)

print("APM cores:", result.apm_cores)
print("Database cores:", result.database_cores)
print("Total infrastructure cores:", result.total_infrastructure_cores)
print("RUM Browser units:", result.rum_browser_units)
print("RUM Mobile units:", result.rum_mobile_units)
```

## Estructura del Excel (Anexo Aplicaciones)

El archivo debe tener una hoja llamada **"Anexo Aplicaciones"** con:

1. **Tabla de aplicaciones**: Aplicación, servidor, tipo, nodos, cores/nodo, ¿es web?, sesiones/usuarios al mes.
2. **Tabla de base de datos**: DB, versión, cores/nodo, nodos, SO, aplicación relacionada.
3. **Tabla SAP** (si aplica): Aplicación, nodos, cores (ej. "ASCS 2 VCPU, APP 16 VCPU").
4. **Microservicios** (K8s/OpenShift): Microservicio, contenedores, sesiones/usuarios al mes.
5. **Aplicaciones móviles**: APP, tipo, plataforma, IDE, Active Agents/mes.

## Modelo de licenciamiento (AppDynamics)

- **Infrastructure-based**: 1 licencia = 1 CPU core (APM, Database, SAP).
- **RUM Browser**: 10 millones de pageviews por 12 meses por unidad.
- **RUM Mobile**: 5.000 Active Agents por mes por unidad (1 Active Agent = app instalada y lanzada en un mes).
- **RUM Tokens**: 1 Pageview = 1 token; 1 Active Agent = 160 tokens/mes.

Para RUM Browser se usa un promedio de 20 pageviews por usuario al mes. Puedes ajustar `PAGEVIEWS_PER_USER_PER_MONTH` en `license_calculator.py` según tu caso de uso.

## ThousandEyes - Calculadora de unidades

La pestaña **ThousandeyesV1** del Excel y la sección ThousandEyes en la interfaz permiten calcular unidades de consumo para pruebas Cloud/Enterprise.

### Columnas y su importancia

| Columna | Descripción |
|--------|-------------|
| **Tipo de prueba** | Define el alcance: Red (Network), HTTP Server, Page Load, DNS Trace, BGP, Transaction, SIP, RTP Stream. Cada tipo tiene un milli-unit cost distinto. |
| **Intervalo (min)** | Cada cuántos minutos se ejecuta la prueba. Intervalos más cortos (1-2 min) detectan fallos antes pero consumen más. Típico: 1-5 min. |
| **# Agentes** | Número de agentes que ejecutan la misma prueba. Más agentes = más cobertura geográfica = más unidades. |
| **Tipo agente** | **Cloud**: gestionado por ThousandEyes, costo 2×. **Enterprise**: en tu infraestructura, 50% del costo de Cloud. |
| **Timeout (seg)** | Solo para pruebas Web/Voice (HTTP, Page Load, Transaction, SIP, RTP). Tiempo máximo para considerar la prueba exitosa (5-180 seg). Multiplica el milli-unit cost. |

### Alcance de tipos de prueba

- **Red (Network Agent-to-Server/Agent-to-Agent)**: Conectividad, pérdida de paquetes, latencia, jitter. Incluye BGP del objetivo.
- **HTTP Server / Page Load / Transaction**: Disponibilidad y tiempo de respuesta web. Usa timeout.
- **DNS Server / Trace / DNSSEC**: Resolución DNS, traza hasta autoritativo, validación DNSSEC.
- **BGP**: Propagación de prefijos, hijacks, route flaps. Usa BGP monitors (no agentes).
- **Voice (SIP / RTP Stream)**: VoIP, MOS, latencia. Usa timeout/duración.
