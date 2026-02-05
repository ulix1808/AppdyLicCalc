"""
AppDynamics License Calculator

Calcula licencias basadas en el modelo de AppDynamics SaaS:
- APM: 1 CPU core = 1 licencia (aplicaciones, SAP)
- Database: 1 CPU core = 1 licencia (igual que aplicaciones)
- Server Visibility: Por instancia OS (incluido en APM o separado)
- RUM Browser: Sesiones/usuarios conectados al mes → Pageviews → RUM Tokens
- RUM Mobile: Apps activas → Active Agents (5000 por unidad, 160 tokens/agente/mes)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# === Definiciones de licenciamiento AppDynamics ===
# Basado en documentación oficial: Infrastructure-based Licensing Model

# RUM Tokens: 1 Pageview = 1 token, 1 Active Agent (mobile) = 160 tokens/mes
RUM_TOKENS_PER_PAGEVIEW = 1
RUM_TOKENS_PER_ACTIVE_AGENT_MONTH = 160

# RUM Pro Edition: 10M pageviews/12 meses, o 10M tokens
RUM_BROWSER_PAGEVIEWS_PER_UNIT_ANNUAL = 10_000_000

# RUM Mobile: 5000 Active Agents por unidad/mes
RUM_MOBILE_ACTIVE_AGENTS_PER_UNIT = 5_000

# Microservices: 5 contenedores = 1 unidad APM Microservices
MICROSERVICES_CORES_EQUIVALENT = 5  # 5 contenedores cuentan como 5 CPU cores (o 1 unidad)


@dataclass
class Application:
    """Aplicación tradicional (Tabla de aplicaciones)"""
    name: str
    server: str
    app_type: str
    nodes: int
    cores_per_node: int
    is_web_app: bool
    has_secure_app: bool = False  # Cisco Secure Application (1 CPU core = 1 licencia)
    sessions_users_per_month: Optional[int] = None
    notes: str = ""

    @property
    def total_cores(self) -> int:
        return self.nodes * self.cores_per_node


@dataclass
class Database:
    """Base de datos (Tabla de base de datos)"""
    name: str
    version: str
    cores_per_node: int
    nodes: int
    os: str
    related_app: str

    @property
    def total_cores(self) -> int:
        # AppDynamics SaaS: 1 CPU core = 1 licencia (igual que aplicaciones)
        return self.nodes * self.cores_per_node


@dataclass
class SAPApplication:
    """Aplicación SAP (Tabla SAP)"""
    name: str
    server: str
    app_type: str
    nodes: int
    cores_str: str  # e.g. "ASCS 2 VCPU, Primario APP Server 16 VCPU"

    @property
    def total_cores(self) -> int:
        """Extrae VCPUs/cores de cadenas como 'ASCS 2 VCPU, Primario APP Server 16 VCPU'"""
        numbers = re.findall(r'(\d+)\s*(?:VCPU|vCPU|CPU|core)', self.cores_str, re.IGNORECASE)
        return sum(int(n) for n in numbers) * self.nodes if numbers else self.nodes * 4


@dataclass
class Microservice:
    """Microservicio (Kubernetes/OpenShift/containers) - APM basado en nodos × cores del cluster"""
    name: str
    server: str
    app_type: str
    nodes: int  # nodos del cluster (EC2, on-prem, etc.)
    cores_per_node: int  # CPUs por nodo
    is_web_app: bool
    sessions_users_per_month: Optional[int] = None
    containers: Optional[int] = None  # referencia opcional

    @property
    def total_cores(self) -> int:
        # APM Infrastructure: licencias = nodos × cores por nodo (igual que aplicaciones)
        return self.nodes * self.cores_per_node


@dataclass
class ServerVisibilityOnly:
    """Servidor solo con Server Visibility (sin APM ni Database monitoring)"""
    name: str
    nodes: int
    cores_per_node: int
    os: str = ""

    @property
    def total_cores(self) -> int:
        return self.nodes * self.cores_per_node


@dataclass
class MobileApp:
    """Aplicación móvil"""
    name: str
    app_type: str
    platform: str
    ide: str
    # Active Agent = app instalada y lanzada en un mes
    active_agents_per_month: Optional[int] = None

    @property
    def rum_tokens_per_month(self) -> int:
        if self.active_agents_per_month:
            return self.active_agents_per_month * RUM_TOKENS_PER_ACTIVE_AGENT_MONTH
        return 0


@dataclass
class LicenseResult:
    """Resultado del cálculo de licencias"""
    apm_cores: int = 0
    database_cores: int = 0
    sap_cores: int = 0
    microservices_containers: int = 0
    server_visibility_instances: int = 0
    server_visibility_only_cores: int = 0  # CPUs solo Server Visibility (sin APM/DB)
    secure_app_cores: int = 0  # Cisco Secure Application (1 CPU core = 1 licencia)

    rum_browser_pageviews_monthly: int = 0
    rum_browser_pageviews_annual: int = 0
    rum_browser_units: float = 0
    rum_browser_tokens_annual: int = 0
    
    rum_mobile_active_agents: int = 0
    rum_mobile_units: float = 0
    rum_mobile_tokens_monthly: int = 0
    
    details: dict = field(default_factory=dict)

    @property
    def total_apm_cores(self) -> int:
        """Cores totales para APM (aplicaciones + microservicios)"""
        return self.apm_cores + self.microservices_containers

    @property
    def total_infrastructure_cores(self) -> int:
        """Cores totales para licenciamiento Infrastructure (APM + DB + SAP + Server Visibility Only + Secure App)"""
        return self.apm_cores + self.database_cores + self.sap_cores + self.microservices_containers + self.server_visibility_only_cores + self.secure_app_cores


def parse_sessions_or_users(value) -> Optional[int]:
    """Extrae número de sesiones/usuarios de cadenas como '2000 usuarios', '50000', etc."""
    if value is None or (isinstance(value, float) and (value != value or value == 0)):
        return None
    if isinstance(value, (int, float)) and value > 0:
        return int(value)
    if isinstance(value, str):
        numbers = re.findall(r'(\d+(?:[\.,]\d+)*(?:\s*k|\s*m)?)', value, re.IGNORECASE)
        if numbers:
            n = numbers[0].strip().lower().replace(',', '.')
            multiplier = 1
            if 'k' in n:
                multiplier = 1000
                n = n.replace('k', '').strip()
            elif 'm' in n:
                multiplier = 1_000_000
                n = n.replace('m', '').strip()
            try:
                return int(float(n) * multiplier)
            except ValueError:
                pass
    return None


def calculate_licenses(
    applications: list[Application] = None,
    databases: list[Database] = None,
    sap_apps: list[SAPApplication] = None,
    microservices: list[Microservice] = None,
    server_visibility_only: list[ServerVisibilityOnly] = None,
    mobile_apps: list[MobileApp] = None,
) -> LicenseResult:
    """
    Calcula todas las licencias AppDynamics a partir de los inventarios.
    """
    applications = applications or []
    databases = databases or []
    sap_apps = sap_apps or []
    microservices = microservices or []
    server_visibility_only = server_visibility_only or []
    mobile_apps = mobile_apps or []

    result = LicenseResult()

    # === Server Visibility Only ===
    # Servidores que solo requieren Server Visibility (sin APM ni DB monitoring)
    result.server_visibility_only_cores = sum(s.total_cores for s in server_visibility_only)

    # === APM (Application Performance Monitoring) ===
    # 1 CPU core = 1 licencia
    result.apm_cores = sum(a.total_cores for a in applications)

    # === Cisco Secure Application ===
    # 1 CPU core = 1 licencia (solo para apps con flag has_secure_app)
    result.secure_app_cores = sum(a.total_cores for a in applications if a.has_secure_app)
    result.database_cores = sum(d.total_cores for d in databases)
    result.sap_cores = sum(s.total_cores for s in sap_apps)
    result.microservices_containers = sum(m.total_cores for m in microservices)

    # Server Visibility: 1 por instancia OS (asumimos 1 por nodo de app + DB + SAP + microservicios)
    app_nodes = sum(a.nodes for a in applications)
    db_nodes = sum(d.nodes for d in databases)
    sap_nodes = sum(s.nodes for s in sap_apps)
    micro_nodes = sum(m.nodes for m in microservices)
    result.server_visibility_instances = app_nodes + db_nodes + sap_nodes + micro_nodes

    # === RUM Browser ===
    # Sesiones/usuarios conectados al mes → asumimos 1 usuario ≈ 10-50 pageviews/mes (promedio 20)
    # Ajustable según el caso de uso
    PAGEVIEWS_PER_USER_PER_MONTH = 20  # Promedio conservador

    rum_pageviews = 0
    for a in applications:
        if a.is_web_app and a.sessions_users_per_month:
            rum_pageviews += a.sessions_users_per_month * PAGEVIEWS_PER_USER_PER_MONTH
    for m in microservices:
        if m.is_web_app and m.sessions_users_per_month:
            rum_pageviews += m.sessions_users_per_month * PAGEVIEWS_PER_USER_PER_MONTH

    result.rum_browser_pageviews_monthly = rum_pageviews
    result.rum_browser_pageviews_annual = rum_pageviews * 12
    result.rum_browser_tokens_annual = result.rum_browser_pageviews_annual * RUM_TOKENS_PER_PAGEVIEW
    result.rum_browser_units = (
        result.rum_browser_tokens_annual / RUM_BROWSER_PAGEVIEWS_PER_UNIT_ANNUAL
        if RUM_BROWSER_PAGEVIEWS_PER_UNIT_ANNUAL > 0
        else 0
    )

    # === RUM Mobile ===
    # Active Agents = apps móviles activas por mes
    # 1 unidad = 5000 Active Agents, 1 Active Agent = 160 tokens/mes
    result.rum_mobile_active_agents = sum(
        ma.active_agents_per_month or 0 for ma in mobile_apps
    )
    result.rum_mobile_tokens_monthly = sum(
        ma.rum_tokens_per_month for ma in mobile_apps
    )
    result.rum_mobile_units = (
        result.rum_mobile_active_agents / RUM_MOBILE_ACTIVE_AGENTS_PER_UNIT
        if RUM_MOBILE_ACTIVE_AGENTS_PER_UNIT > 0
        else 0
    )

    # Detalles para reporte
    result.details = {
        "applications": [{"name": a.name, "cores": a.total_cores, "secure_app": a.has_secure_app} for a in applications],
        "databases": [{"name": d.name, "cores": d.total_cores} for d in databases],
        "sap": [{"name": s.name, "cores": s.total_cores} for s in sap_apps],
        "microservices": [{"name": m.name, "nodes": m.nodes, "cores": m.total_cores} for m in microservices],
        "server_visibility_only": [{"name": s.name, "nodes": s.nodes, "cores": s.total_cores} for s in server_visibility_only],
        "mobile_apps": [{"name": ma.name, "active_agents": ma.active_agents_per_month} for ma in mobile_apps],
    }

    return result


def parse_excel_anexo_aplicaciones(filepath: str) -> dict:
    """
    Parsea el archivo Excel 'MiFel_sizing-Architecture.xlsx' hoja 'Anexo Aplicaciones'
    y extrae aplicaciones, bases de datos, SAP, microservicios y apps móviles.

    Retorna un diccionario con listas de objetos para pasar a calculate_licenses().
    """
    import pandas as pd

    xl = pd.ExcelFile(filepath)
    if "Anexo Aplicaciones" not in xl.sheet_names:
        raise ValueError("No se encontró la hoja 'Anexo Aplicaciones'")

    df = pd.read_excel(xl, sheet_name="Anexo Aplicaciones", header=None)

    applications = []
    databases = []
    sap_apps = []
    microservices = []
    mobile_apps = []

    # Tabla de aplicaciones: filas 3-5 (0-indexed: 3, 4)
    for idx in range(3, min(6, len(df))):
        row = df.iloc[idx]
        vals = [str(x).strip() if pd.notna(x) and str(x) != "nan" else None for x in row]
        name = vals[1] if len(vals) > 1 else None
        if not name or name.lower() in ("nan", ""):
            continue
        try:
            nodes = int(float(vals[5])) if vals[5] and str(vals[5]).replace(".", "").isdigit() else 1
            cores = int(float(vals[6])) if vals[6] and str(vals[6]).replace(".", "").replace("-", "").isdigit() else 4
        except (ValueError, TypeError):
            nodes, cores = 1, 4
        is_web = str(vals[7]).lower() in ("si", "sí", "yes", "true", "1") if vals[7] else False
        sessions = parse_sessions_or_users(vals[8]) if len(vals) > 8 else None

        applications.append(Application(
            name=name or f"App-{idx}",
            server=vals[2] or "",
            app_type=vals[3] or "",
            nodes=nodes,
            cores_per_node=cores,
            is_web_app=is_web,
            sessions_users_per_month=sessions,
        ))

    # Tabla DB: filas 9-11 (fila 8 es header)
    for idx in range(9, min(12, len(df))):
        row = df.iloc[idx]
        vals = [str(x).strip() if pd.notna(x) and str(x) != "nan" else None for x in row]
        name = vals[1] if len(vals) > 1 else None
        if not name or name.lower() in ("db", "nan", ""):
            continue
        if name:
            try:
                cores = int(float(vals[3])) if vals[3] and str(vals[3]).replace(".", "").isdigit() else 4
                nodes = int(float(vals[4])) if vals[4] and str(vals[4]).replace(".", "").isdigit() else 1
            except (ValueError, TypeError):
                cores, nodes = 4, 1
            databases.append(Database(
                name=name,
                version=vals[2] or "",
                cores_per_node=cores,
                nodes=nodes,
                os=vals[5] or "",
                related_app=vals[6] or "",
            ))

    # Tabla SAP: filas 17-18
    for idx in range(17, min(19, len(df))):
        row = df.iloc[idx]
        vals = [str(x).strip() if pd.notna(x) and str(x) != "nan" else None for x in row]
        name = vals[1] if len(vals) > 1 else None
        if not name or name.lower() in ("nan", ""):
            continue
        cores_str = (vals[6] if len(vals) > 6 else None) or (vals[5] if len(vals) > 5 else None) or "4"
        try:
            nodes = int(float(vals[4])) if vals[4] and str(vals[4]).replace(".", "").isdigit() else 1
        except (ValueError, TypeError):
            nodes = 1
        sap_apps.append(SAPApplication(
            name=name,
            server=vals[2] or "",
            app_type=vals[3] or "",
            nodes=nodes,
            cores_str=str(cores_str),
        ))

    # Microservicios: filas 22 - APM basado en nodos × cores del cluster
    # Nota: Excel tiene "contenedores" y SO; nodes/cores se ingresan en UI. Default: 1 nodo, 4 cores.
    for idx in range(22, min(24, len(df))):
        row = df.iloc[idx]
        vals = [str(x).strip() if pd.notna(x) and str(x) != "nan" else None for x in row]
        name = vals[1] if len(vals) > 1 else None
        if name and name.lower() not in ("no aplica", "nan", ""):
            nodes, cores_per_node = 1, 4  # Default; Excel no tiene nodos/cores, editar en UI
            is_web = str(vals[8]).lower() in ("si", "sí", "yes") if len(vals) > 8 and vals[8] else False
            sessions = parse_sessions_or_users(vals[9]) if len(vals) > 9 else None
            microservices.append(Microservice(
                name=name,
                server=vals[2] or "",
                app_type=vals[3] or "",
                nodes=nodes,
                cores_per_node=cores_per_node,
                is_web_app=is_web,
                sessions_users_per_month=sessions,
            ))

    # Apps móviles: filas 31
    for idx in range(31, min(33, len(df))):
        row = df.iloc[idx]
        vals = [str(x).strip() if pd.notna(x) and str(x) != "nan" else None for x in row]
        name = vals[1] if len(vals) > 1 else None
        if name and name.lower() not in ("no aplica", "app", "nan", ""):
            mobile_apps.append(MobileApp(
                name=name,
                app_type=vals[2] or "",
                platform=vals[3] or "",
                ide=vals[4] or "",
                active_agents_per_month=None,  # No hay columna en el Excel, se ingresa manualmente
            ))

    return {
        "applications": applications,
        "databases": databases,
        "sap_apps": sap_apps,
        "microservices": microservices,
        "mobile_apps": mobile_apps,
    }


if __name__ == "__main__":
    # Demo con datos del ejemplo del Excel
    apps = [
        Application("Ejemplo 1", "Jboss 7", "Java", nodes=4, cores_per_node=8, is_web_app=True, sessions_users_per_month=2000),
        Application("Ejemplo 2", "", ".NET", nodes=1, cores_per_node=4, is_web_app=True, sessions_users_per_month=None),
    ]
    dbs = [
        Database("Oracle", "11G", 12, 2, "RHEL 7", "Ejemplo-1"),
        Database("SQL Server", "2016", 8, 1, "Windows server 2016", "Ejemplo 2"),
    ]
    sap = [
        SAPApplication("Ejemplo", "", "", 1, "ASCS 2 VCPU, Primario APP Server 16 VCPU"),
    ]

    result = calculate_licenses(applications=apps, databases=dbs, sap_apps=sap)
    print("=== Resumen de licencias AppDynamics ===\n")
    print(f"APM (aplicaciones):     {result.apm_cores} CPU cores")
    print(f"Database:               {result.database_cores} CPU cores")
    print(f"SAP:                    {result.sap_cores} CPU cores")
    print(f"Server Visibility:      {result.server_visibility_instances} instancias")
    print(f"\nRUM Browser:")
    print(f"  Pageviews/mes:        {result.rum_browser_pageviews_monthly:,}")
    print(f"  Pageviews/año:        {result.rum_browser_pageviews_annual:,}")
    print(f"  Unidades (10M/año):   {result.rum_browser_units:.2f}")
    print(f"\nRUM Mobile:")
    print(f"  Active Agents/mes:    {result.rum_mobile_active_agents}")
    print(f"  Unidades (5K/ unidad): {result.rum_mobile_units:.2f}")
    print(f"\n--- Total Infrastructure Cores: {result.total_infrastructure_cores} ---")
