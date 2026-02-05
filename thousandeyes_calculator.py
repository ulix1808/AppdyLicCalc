"""
ThousandEyes License Calculator

Calcula unidades de consumo según el modelo de ThousandEyes (Cisco):
- Tipo de prueba: afecta el milli-unit cost
- Intervalo: frecuencia de ejecución (más frecuente = más unidades)
- Número de agentes: cada agente ejecuta la prueba
- Tipo de agente: Cloud vs Enterprise (Enterprise = 50% del costo)
- Timeout: para pruebas Web/Voice, multiplica el costo

Fórmula base: milli-units × (rounds_per_hour × 24 × 31) × agents
"""

from dataclasses import dataclass
from typing import Optional

# === Documentación de alcance de tipos de prueba ===
TEST_TYPE_SCOPES = {
    "red": {
        "name": "Red (Network Agent-to-Server / Agent-to-Agent)",
        "scope": "Monitoriza conectividad de red entre agentes y servidores. Mide pérdida de paquetes, latencia, jitter. Agent-to-Agent permite métricas unidireccionales y opción de throughput.",
        "uses_timeout": False,
        "milli_cloud": 5,
        "milli_enterprise": 2.5,
    },
    "agent_to_agent": {
        "name": "Network Agent-to-Agent",
        "scope": "Pruebas entre dos agentes ThousandEyes (Enterprise→Cloud, Enterprise→Enterprise o Cloud→Cloud). Métricas unidireccionales, throughput, visualización de ruta.",
        "uses_timeout": False,
        "milli_cloud": 5,
        "milli_enterprise": 2.5,
    },
    "agent_to_server": {
        "name": "Network Agent-to-Server",
        "scope": "Prueba de conectividad desde un agente hacia un servidor/endpoint. Incluye monitoreo BGP del prefijo del objetivo.",
        "uses_timeout": False,
        "milli_cloud": 5,
        "milli_enterprise": 2.5,
    },
    "dns_server": {
        "name": "DNS Server",
        "scope": "Consulta resoluciones DNS contra uno o más servidores DNS. Consumo = milli-units × número de servidores testeados.",
        "uses_timeout": False,
        "milli_cloud": 5,  # por servidor
        "milli_enterprise": 2.5,  # por servidor
        "per_server": True,
    },
    "dns_trace": {
        "name": "DNS Trace",
        "scope": "Traza la cadena de resolución DNS desde la raíz hasta el servidor autoritativo.",
        "uses_timeout": False,
        "milli_cloud": 5,
        "milli_enterprise": 2.5,
    },
    "dnssec": {
        "name": "DNSSEC",
        "scope": "Valida firmas DNSSEC en la resolución DNS.",
        "uses_timeout": False,
        "milli_cloud": 5,
        "milli_enterprise": 2.5,
    },
    "bgp": {
        "name": "BGP",
        "scope": "Monitorea propagación de prefijos BGP (hijacks, route flaps, route leaks). Usa BGP monitors, no agentes. Siempre 8 milli-units por 1000 rondas.",
        "uses_timeout": False,
        "milli_cloud": 8,
        "milli_enterprise": 8,
        "no_agents": True,
    },
    "http_server": {
        "name": "Web - HTTP Server",
        "scope": "Verifica disponibilidad y tiempo de respuesta de servidores HTTP/HTTPS.",
        "uses_timeout": True,
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
    "ftp_server": {
        "name": "Web - FTP Server",
        "scope": "Prueba de disponibilidad de servidores FTP.",
        "uses_timeout": True,
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
    "page_load": {
        "name": "Web - Page Load",
        "scope": "Mide tiempo de carga completo de una página web en navegador real.",
        "uses_timeout": True,
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
    "transaction": {
        "name": "Web - Transaction",
        "scope": "Simula flujos multi-paso (login, checkout) con script de transacción.",
        "uses_timeout": True,
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
    "sip_server": {
        "name": "Voice - SIP Server",
        "scope": "Prueba disponibilidad de servidores SIP para VoIP.",
        "uses_timeout": True,
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
    "rtp_stream": {
        "name": "Voice - RTP Stream",
        "scope": "Emula llamada VoIP entre agentes. Mide pérdida, latencia, MOS. Usa duración del stream (segundos) en lugar de timeout.",
        "uses_timeout": True,  # usa "duration" como timeout
        "milli_cloud_per_sec": 1,
        "milli_enterprise_per_sec": 0.5,
    },
}

# Mapeo de valores del Excel / UI a claves internas
TEST_TYPE_ALIASES = {
    "red": "red",
    "network": "red",
    "agent-to-agent": "agent_to_agent",
    "agent_to_agent": "agent_to_agent",
    "agent-to-server": "agent_to_server",
    "agent_to_server": "agent_to_server",
    "dns server": "dns_server",
    "dns_server": "dns_server",
    "dns trace": "dns_trace",
    "dns_trace": "dns_trace",
    "dnssec": "dnssec",
    "bgp": "bgp",
    "http": "http_server",
    "http server": "http_server",
    "http_server": "http_server",
    "ftp": "ftp_server",
    "ftp server": "ftp_server",
    "page load": "page_load",
    "page_load": "page_load",
    "transaction": "transaction",
    "sip": "sip_server",
    "sip server": "sip_server",
    "rtp": "rtp_stream",
    "rtp stream": "rtp_stream",
    "rtp_stream": "rtp_stream",
    "web": "page_load",
}

AGENT_TYPE_ALIASES = {
    "cloud": "cloud",
    "enterprise": "enterprise",
    "clou": "cloud",
    "enterpris": "enterprise",
}

# Intervalo mínimo 1 min, máximo 60 min típico
MIN_INTERVAL = 1
MAX_INTERVAL = 60
MIN_TIMEOUT = 5
MAX_TIMEOUT = 180
DAYS_PROJECTION = 31


@dataclass
class ThousandEyesTest:
    """Configuración de una prueba ThousandEyes"""
    test_type: str  # clave interna: red, http_server, dns_trace, etc.
    interval_minutes: int
    num_agents: int
    agent_type: str  # "cloud" | "enterprise"
    timeout_seconds: Optional[int] = None  # para Web/Voice, 5-180
    dns_servers: Optional[int] = None  # solo para dns_server
    rtp_duration_seconds: Optional[int] = None  # solo para rtp_stream

    def resolve_test_type(self) -> str:
        key = self.test_type.lower().strip().replace(" ", "_").replace("-", "_")
        return TEST_TYPE_ALIASES.get(key, "red")

    def resolve_agent_type(self) -> str:
        a = self.agent_type.lower().strip()
        return AGENT_TYPE_ALIASES.get(a, "enterprise")


def get_milli_units(test: ThousandEyesTest) -> float:
    """Obtiene el milli-unit cost por 1000 rondas para esta prueba."""
    key = test.resolve_test_type()
    agent = test.resolve_agent_type()
    cfg = TEST_TYPE_SCOPES.get(key, TEST_TYPE_SCOPES["red"])

    if cfg.get("no_agents"):
        return cfg["milli_cloud"]  # BGP no depende de agentes

    if cfg.get("uses_timeout"):
        timeout = test.timeout_seconds or test.rtp_duration_seconds or MIN_TIMEOUT
        timeout = max(MIN_TIMEOUT, min(MAX_TIMEOUT, timeout))
        m_cloud = cfg.get("milli_cloud_per_sec", 1) * timeout
        m_ent = cfg.get("milli_enterprise_per_sec", 0.5) * timeout
        return m_ent if agent == "enterprise" else m_cloud

    if cfg.get("per_server"):
        servers = max(1, test.dns_servers or 1)
        base = cfg["milli_enterprise"] if agent == "enterprise" else cfg["milli_cloud"]
        return base * servers

    base = cfg["milli_enterprise"] if agent == "enterprise" else cfg["milli_cloud"]
    return base


def calculate_units_per_test(test: ThousandEyesTest) -> float:
    """
    Calcula unidades por prueba para un período de 31 días.
    Fórmula: milli-units × (60/interval × 24 × 31) × agents / 1000
    """
    milli = get_milli_units(test)
    interval = max(MIN_INTERVAL, min(MAX_INTERVAL, test.interval_minutes))
    rounds_per_hour = 60 / interval
    rounds_31_days = rounds_per_hour * 24 * DAYS_PROJECTION

    if TEST_TYPE_SCOPES.get(
        TEST_TYPE_ALIASES.get(test.test_type.lower(), "red"),
        TEST_TYPE_SCOPES["red"],
    ).get("no_agents"):
        agents = 1  # BGP no usa agentes
    else:
        agents = max(1, test.num_agents)

    milli_total = milli * rounds_31_days * agents
    units = round(milli_total / 1000)
    return max(1, units)


def calculate_thousandeyes(tests: list[ThousandEyesTest]) -> dict:
    """Calcula unidades totales y por prueba."""
    results = []
    total = 0
    for t in tests:
        u = calculate_units_per_test(t)
        key = t.resolve_test_type()
        cfg = TEST_TYPE_SCOPES.get(key, TEST_TYPE_SCOPES["red"])
        results.append({
            "test_type": t.test_type,
            "resolved_type": key,
            "scope": cfg.get("scope", ""),
            "interval_minutes": t.interval_minutes,
            "num_agents": t.num_agents,
            "agent_type": t.agent_type,
            "timeout_seconds": t.timeout_seconds,
            "units": u,
        })
        total += u

    return {
        "total_units": total,
        "projection_days": DAYS_PROJECTION,
        "tests": results,
    }


# === Explicaciones para la UI ===
HELP_INTERVAL = (
    "El intervalo define cada cuántos minutos se ejecuta la prueba. "
    "Intervalos más cortos (1–2 min) detectan fallos más rápido pero consumen más unidades. "
    "Recomendado: 1–5 min según criticidad. "
    "Un intervalo de 5 min ejecuta 12 rondas/hora; 1 min ejecuta 60 rondas/hora."
)

HELP_AGENTS = (
    "Número de agentes que ejecutan la misma prueba. Cada agente aporta su perspectiva geográfica. "
    "Más agentes = más cobertura pero más unidades (el costo se multiplica por el número de agentes)."
)

HELP_AGENT_TYPE = (
    "Cloud: agentes gestionados por ThousandEyes en Internet. Costo 2× Enterprise. "
    "Enterprise: agentes desplegados en tu infraestructura (on‑prem, datacenter). "
    "Enterprise reduce el consumo a la mitad respecto a Cloud."
)

HELP_TIMEOUT = (
    "Tiempo máximo en segundos para considerar la prueba exitosa. Solo aplica a pruebas Web y Voice "
    "(HTTP, Page Load, Transaction, SIP, RTP). "
    "Intervalo típico: 5–180 seg. "
    "Un timeout mayor multiplica el milli-unit cost (p. ej. timeout 30 → 30× el factor base)."
)


def parse_excel_thousandeyes(filepath: str) -> list[ThousandEyesTest]:
    """Parsea la hoja ThousandeyesV1 del Excel."""
    import pandas as pd

    xl = pd.ExcelFile(filepath)
    if "ThousandeyesV1" not in xl.sheet_names:
        return []

    df = pd.read_excel(xl, sheet_name="ThousandeyesV1", header=None)
    tests = []

    for idx in range(3, len(df)):  # fila 3 en adelante (0-indexed)
        row = df.iloc[idx]
        vals = [row[i] if i < len(row) else None for i in range(8)]

        def v(i, default=None):
            x = vals[i] if i < len(vals) else None
            if x is None or (isinstance(x, float) and (x != x or x == 0)):
                return default
            return x

        test_type = str(v(2, "")).strip() if v(2) else None
        if not test_type or str(test_type).lower() in ("nan", ""):
            continue

        try:
            interval = int(float(v(3) or 5))
        except (ValueError, TypeError):
            interval = 5
        try:
            agents = int(float(v(4) or 1))
        except (ValueError, TypeError):
            agents = 1
        agent_type = str(v(5, "ENTERPRISE")).strip().upper() or "ENTERPRISE"
        try:
            timeout = int(float(v(6) or 5))
        except (ValueError, TypeError):
            timeout = 5

        tests.append(ThousandEyesTest(
            test_type=test_type,
            interval_minutes=interval,
            num_agents=agents,
            agent_type=agent_type,
            timeout_seconds=timeout,
        ))

    return tests


def get_test_types_for_ui() -> list[dict]:
    """Lista de tipos de prueba para el dropdown con alcance."""
    items = []
    seen = set()
    for key, cfg in TEST_TYPE_SCOPES.items():
        if key in seen:
            continue
        seen.add(key)
        items.append({
            "value": key.replace("_", " ").title(),
            "key": key,
            "name": cfg.get("name", key),
            "scope": cfg.get("scope", ""),
            "uses_timeout": cfg.get("uses_timeout", False),
        })
    return sorted(items, key=lambda x: x["name"])
