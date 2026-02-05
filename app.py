"""
AppDynamics License Calculator - Web App
Servidor Flask para la calculadora de licencias.
"""

import json
import os
from pathlib import Path

from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename

from license_calculator import (
    calculate_licenses,
    parse_excel_anexo_aplicaciones,
    Application,
    Database,
    SAPApplication,
    Microservice,
    ServerVisibilityOnly,
    MobileApp,
    parse_sessions_or_users,
)
from thousandeyes_calculator import (
    ThousandEyesTest,
    calculate_thousandeyes,
    parse_excel_thousandeyes,
    get_test_types_for_ui,
    HELP_INTERVAL,
    HELP_AGENTS,
    HELP_AGENT_TYPE,
    HELP_TIMEOUT,
    TEST_TYPE_SCOPES,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB
UPLOAD_FOLDER = Path(__file__).parent / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ("xlsx", "xls")


@app.route("/")
def index():
    return render_template(
        "index.html",
        te_test_types=get_test_types_for_ui(),
        te_help_interval=HELP_INTERVAL,
        te_help_agents=HELP_AGENTS,
        te_help_agent_type=HELP_AGENT_TYPE,
        te_help_timeout=HELP_TIMEOUT,
    )


@app.route("/api/calculate", methods=["POST"])
def api_calculate():
    """Calcula licencias a partir de datos JSON enviados desde el formulario."""
    try:
        data = request.get_json() or {}

        applications = []
        for a in data.get("applications", []):
            sessions = a.get("sessions_users_per_month")
            if sessions is not None and sessions != "":
                sessions = parse_sessions_or_users(str(sessions))
            applications.append(
                Application(
                    name=a.get("name", ""),
                    server=a.get("server", ""),
                    app_type=a.get("type", ""),
                    nodes=int(a.get("nodes", 1) or 1),
                    cores_per_node=int(a.get("cores_per_node", 4) or 4),
                    is_web_app=str(a.get("is_web_app", "")).lower() in ("si", "sí", "yes", "true", "1"),
                    has_secure_app=str(a.get("has_secure_app", "")).lower() in ("si", "sí", "yes", "true", "1"),
                    sessions_users_per_month=sessions,
                    notes=a.get("notes", ""),
                )
            )

        databases = []
        for d in data.get("databases", []):
            databases.append(
                Database(
                    name=d.get("name", ""),
                    version=d.get("version", ""),
                    cores_per_node=int(d.get("cores_per_node", 4) or 4),
                    nodes=int(d.get("nodes", 1) or 1),
                    os=d.get("os", ""),
                    related_app=d.get("related_app", ""),
                )
            )

        sap_apps = []
        for s in data.get("sap_apps", []):
            sap_apps.append(
                SAPApplication(
                    name=s.get("name", ""),
                    server=s.get("server", ""),
                    app_type=s.get("type", ""),
                    nodes=int(s.get("nodes", 1) or 1),
                    cores_str=s.get("cores_str", "4"),
                )
            )

        microservices = []
        for m in data.get("microservices", []):
            sessions = m.get("sessions_users_per_month")
            if sessions is not None and sessions != "":
                sessions = parse_sessions_or_users(str(sessions))
            microservices.append(
                Microservice(
                    name=m.get("name", ""),
                    server=m.get("server", ""),
                    app_type=m.get("type", ""),
                    nodes=int(m.get("nodes", 1) or 1),
                    cores_per_node=int(m.get("cores_per_node", 4) or 4),
                    is_web_app=str(m.get("is_web_app", "")).lower() in ("si", "sí", "yes", "true", "1"),
                    sessions_users_per_month=sessions,
                )
            )

        server_visibility_only = []
        for s in data.get("server_visibility_only", []):
            server_visibility_only.append(
                ServerVisibilityOnly(
                    name=s.get("name", ""),
                    nodes=int(s.get("nodes", 1) or 1),
                    cores_per_node=int(s.get("cores_per_node", 4) or 4),
                    os=s.get("os", ""),
                )
            )

        mobile_apps = []
        for ma in data.get("mobile_apps", []):
            agents = ma.get("active_agents_per_month")
            if agents is not None and agents != "":
                try:
                    agents = int(agents)
                except (ValueError, TypeError):
                    agents = None
            mobile_apps.append(
                MobileApp(
                    name=ma.get("name", ""),
                    app_type=ma.get("type", ""),
                    platform=ma.get("platform", ""),
                    ide=ma.get("ide", ""),
                    active_agents_per_month=agents,
                )
            )

        result = calculate_licenses(
            applications=applications,
            databases=databases,
            sap_apps=sap_apps,
            microservices=microservices,
            server_visibility_only=server_visibility_only,
            mobile_apps=mobile_apps,
        )

        return jsonify({
            "success": True,
            "result": {
                "apm_cores": result.apm_cores,
                "database_cores": result.database_cores,
                "sap_cores": result.sap_cores,
                "microservices_containers": result.microservices_containers,
                "server_visibility_instances": result.server_visibility_instances,
                "server_visibility_only_cores": result.server_visibility_only_cores,
                "secure_app_cores": result.secure_app_cores,
                "total_infrastructure_cores": result.total_infrastructure_cores,
                "rum_browser_pageviews_monthly": result.rum_browser_pageviews_monthly,
                "rum_browser_pageviews_annual": result.rum_browser_pageviews_annual,
                "rum_browser_units": round(result.rum_browser_units, 2),
                "rum_browser_tokens_annual": result.rum_browser_tokens_annual,
                "rum_mobile_active_agents": result.rum_mobile_active_agents,
                "rum_mobile_units": round(result.rum_mobile_units, 2),
                "rum_mobile_tokens_monthly": result.rum_mobile_tokens_monthly,
            },
            "details": result.details,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/parse-excel", methods=["POST"])
def api_parse_excel():
    """Parsea un archivo Excel (Anexo Aplicaciones) y devuelve los datos extraídos."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No se envió ningún archivo"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No se seleccionó archivo"}), 400
    if not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Solo se permiten archivos .xlsx o .xls"}), 400

    try:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        parsed = parse_excel_anexo_aplicaciones(filepath)
        te_tests = parse_excel_thousandeyes(filepath)
        os.remove(filepath)

        # Convertir a estructuras serializables para el frontend
        def to_dict(obj):
            if hasattr(obj, "__dict__"):
                return {k: v for k, v in obj.__dict__.items() if not k.startswith("_")}
            return obj

        data = {
            "applications": [
                {
                    "name": a.name,
                    "server": a.server,
                    "type": a.app_type,
                    "nodes": a.nodes,
                    "cores_per_node": a.cores_per_node,
                    "is_web_app": "Si" if a.is_web_app else "No",
                    "has_secure_app": "Si" if a.has_secure_app else "No",
                    "sessions_users_per_month": a.sessions_users_per_month,
                    "notes": a.notes,
                }
                for a in parsed["applications"]
            ],
            "databases": [
                {
                    "name": d.name,
                    "version": d.version,
                    "cores_per_node": d.cores_per_node,
                    "nodes": d.nodes,
                    "os": d.os,
                    "related_app": d.related_app,
                }
                for d in parsed["databases"]
            ],
            "sap_apps": [
                {
                    "name": s.name,
                    "server": s.server,
                    "type": s.app_type,
                    "nodes": s.nodes,
                    "cores_str": s.cores_str,
                }
                for s in parsed["sap_apps"]
            ],
            "microservices": [
                {
                    "name": m.name,
                    "server": m.server,
                    "type": m.app_type,
                    "nodes": m.nodes,
                    "cores_per_node": m.cores_per_node,
                    "is_web_app": "Si" if m.is_web_app else "No",
                    "sessions_users_per_month": m.sessions_users_per_month,
                }
                for m in parsed["microservices"]
            ],
            "mobile_apps": [
                {
                    "name": ma.name,
                    "type": ma.app_type,
                    "platform": ma.platform,
                    "ide": ma.ide,
                    "active_agents_per_month": ma.active_agents_per_month,
                }
                for ma in parsed["mobile_apps"]
            ],
            "server_visibility_only": [],
            "thousandeyes_tests": [
                {
                    "test_type": t.test_type,
                    "interval_minutes": t.interval_minutes,
                    "num_agents": t.num_agents,
                    "agent_type": t.agent_type,
                    "timeout_seconds": t.timeout_seconds,
                }
                for t in te_tests
            ],
        }
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/calculate-te", methods=["POST"])
def api_calculate_te():
    """Calcula unidades ThousandEyes a partir de las pruebas configuradas."""
    try:
        data = request.get_json() or {}
        tests_raw = data.get("thousandeyes_tests", [])
        tests = []
        for t in tests_raw:
            if not t.get("test_type"):
                continue
            tests.append(ThousandEyesTest(
                test_type=t.get("test_type", "Red"),
                interval_minutes=int(t.get("interval_minutes", 5) or 5),
                num_agents=int(t.get("num_agents", 1) or 1),
                agent_type=t.get("agent_type", "ENTERPRISE"),
                timeout_seconds=int(t.get("timeout_seconds", 5) or 5) if t.get("timeout_seconds") is not None and t.get("timeout_seconds") != "" else 5,
            ))
        result = calculate_thousandeyes(tests)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@app.route("/api/te-help")
def api_te_help():
    """Devuelve las explicaciones y alcances de tipos de prueba TE."""
    return jsonify({
        "test_types": {
            k: {"name": v.get("name"), "scope": v.get("scope"), "uses_timeout": v.get("uses_timeout", False)}
            for k, v in TEST_TYPE_SCOPES.items()
            if k not in ("agent_to_agent", "agent_to_server") or k == "red"
        },
        "help_interval": HELP_INTERVAL,
        "help_agents": HELP_AGENTS,
        "help_agent_type": HELP_AGENT_TYPE,
        "help_timeout": HELP_TIMEOUT,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
