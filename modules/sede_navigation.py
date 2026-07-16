from flask import url_for


OPERATIVA_MODULES = [
    {"key": "personal", "label": "Personal", "tone": "tone-personal"},
    {"key": "depositos", "label": "Depositos", "tone": "tone-dep"},
    {"key": "planos", "label": "Planos", "tone": "tone-planos"},
    {"key": "aires", "label": "Aires", "tone": "tone-aires"},
    {"key": "luminarias", "label": "Luminarias", "tone": "tone-lum"},
    {"key": "mobiliario", "label": "Inventario operativo", "tone": "tone-mob"},
    {"key": "matafuegos", "label": "Matafuegos", "tone": "tone-mata"},
    {"key": "evacuacion", "label": "Evacuacion", "tone": "tone-eva"},
    {"key": "sst_carteleria", "label": "SG-SST Carteleria", "tone": "tone-planos"},
    {"key": "sst_luces", "label": "SG-SST Luces", "tone": "tone-lum"},
]

CALENDAR_TYPE_TO_MODULE = {
    "carteleria": "sst_carteleria",
    "desinfeccion": "sst_desinfecciones",
    "luces": "sst_luces",
    "matafuegos": "matafuegos",
    "visita": "sst_visitas",
}

MODULE_ROUTE_MAP = {
    "sede": {"endpoint": "sede_ficha", "kind": "sede_ficha"},
    "personal": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "personal"},
    "depositos": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "depositos"},
    "planos": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "planos", "anchor": "#planos"},
    "aires": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "aires"},
    "luminarias": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "luminarias"},
    "mobiliario": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "mobiliario"},
    "matafuegos": {
        "endpoint": "matafuegos_home",
        "kind": "external",
        "sede_param": "sede",
        "open_param": "open_sede",
        "preserve": ("estado", "lote", "year", "month", "q"),
    },
    "evacuacion": {"endpoint": "sede_ficha", "kind": "sede_ficha", "tab": "evacuacion"},
    "sst_carteleria": {
        "endpoint": "sst_carteleria_home",
        "kind": "external",
        "sede_param": "sede",
        "open_param": "open_sede",
        "preserve": ("estado", "month", "q"),
    },
    "sst_luces": {
        "endpoint": "sst_luces_home",
        "kind": "external",
        "sede_param": "sede",
        "open_param": "open_sede",
        "preserve": ("estado", "month", "q"),
    },
    "sst_calendario": {
        "endpoint": "sst_calendario_operativo",
        "kind": "external",
        "sede_param": "sede",
        "preserve": ("vista", "year", "month", "region", "tipo", "estado", "responsable"),
    },
    "sst_desinfecciones": {
        "endpoint": "sst_desinfecciones_home",
        "kind": "external",
        "sede_param": "sede",
        "open_param": "open_sede",
        "preserve": ("estado", "modalidad", "year", "month", "q"),
    },
    "sst_visitas": {
        "endpoint": "sst_visitas",
        "kind": "external",
        "sede_param": "sede",
        "open_param": "open_sede",
        "preserve": ("estado", "month", "q"),
    },
}

SEDE_ACCENT_BY_CODE = {
    "S08": "#f58a5e",
    "S11": "#F14B94",
    "S12": "#f58a5e",
    "S13": "#65BFF4",
    "S14": "#F14B94",
    "S15": "#F14B94",
    "S16": "#F14B94",
    "S17": "#F14B94",
    "S18": "#F14B94",
    "S19": "#F14B94",
    "S20": "#F14B94",
}


def _clean_str(value):
    return str(value or "").strip()


def _clean_upper(value):
    return _clean_str(value).upper()


def _get_value(item, key):
    if item is None:
        return ""
    if isinstance(item, dict):
        return item.get(key, "")
    try:
        return item[key]
    except Exception:
        return getattr(item, key, "")


def normalize_module_key(module_key):
    key = _clean_str(module_key).lower()
    aliases = {
        "carteleria": "sst_carteleria",
        "desinfeccion": "sst_desinfecciones",
        "desinfecciones": "sst_desinfecciones",
        "inventario": "mobiliario",
        "inventario_operativo": "mobiliario",
        "luces": "sst_luces",
    }
    return aliases.get(key, key)


def sede_accent_color(sede_codigo):
    code = _clean_upper(sede_codigo)
    if not code:
        return "#6666cc"
    if code in SEDE_ACCENT_BY_CODE:
        return SEDE_ACCENT_BY_CODE[code]
    if code in {"S01", "S02", "S03", "S04", "S05", "S06", "S07", "S09", "S10"}:
        return "#6666cc"
    return "#6666cc"


def resolve_sede_module_key(module_key, calendar_type=""):
    key = normalize_module_key(module_key)
    if key == "sst_calendario":
        calendar_key = CALENDAR_TYPE_TO_MODULE.get(_clean_str(calendar_type).lower())
        return calendar_key or key
    return key or "sede"


def _clean_params(values):
    clean = {}
    for key, value in (values or {}).items():
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            clean[key] = text
            continue
        if value in (False, 0):
            continue
        clean[key] = value
    return clean


def _pick_filters(filters, keys):
    out = {}
    for key in keys or ():
        value = (filters or {}).get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if value == 0:
            continue
        out[key] = value
    return out


def build_context_url(
    module_key,
    target_sede,
    *,
    piso="",
    local="",
    view="",
    home=False,
    filters=None,
    calendar_type="",
):
    resolved_key = resolve_sede_module_key(module_key, calendar_type=calendar_type)
    config = MODULE_ROUTE_MAP.get(resolved_key) or MODULE_ROUTE_MAP["sede"]
    target_code = _clean_upper(target_sede)

    if config["kind"] == "sede_ficha":
        params = {"codigo": target_code}
        tab_key = config.get("tab")
        if tab_key:
            params["tab"] = tab_key
        if piso:
            params["piso"] = piso
        if local:
            params["local"] = local
        if view:
            params["view"] = view
        if home:
            params["home"] = 1
        url = url_for(config["endpoint"], **_clean_params(params))
        anchor = config.get("anchor") or ""
        return f"{url}{anchor}"

    params = _pick_filters(filters, config.get("preserve"))
    if target_code:
        params[config.get("sede_param", "sede")] = target_code
        open_param = config.get("open_param")
        if open_param:
            params[open_param] = target_code
    url = url_for(config["endpoint"], **_clean_params(params))
    anchor = config.get("anchor") or ""
    return f"{url}{anchor}"


def build_operativa_nav_context(
    sedes,
    current_sede,
    active_module,
    *,
    piso="",
    local="",
    view="",
    home=False,
    filters=None,
    dynamic_sede_token="",
):
    active_code = _clean_upper(current_sede)
    calendar_type = _clean_str((filters or {}).get("tipo")).lower()
    current_module_key = normalize_module_key(active_module)
    highlight_module_key = resolve_sede_module_key(current_module_key, calendar_type=calendar_type)

    nav_sedes = []
    for item in sedes or []:
        sede_code = _clean_upper(_get_value(item, "codigo"))
        if not sede_code:
            continue
        sede_name = _clean_str(_get_value(item, "nombre"))
        nav_sedes.append({
            "codigo": sede_code,
            "nombre": sede_name,
            "href": build_context_url(
                "sede",
                sede_code,
                piso=piso,
                local=local,
                view=view,
                home=home,
                filters=filters,
                calendar_type=calendar_type,
            ),
            "active": sede_code == active_code,
        })

    module_sede = active_code or _clean_upper(dynamic_sede_token)
    nav_modules = []
    for item in OPERATIVA_MODULES:
        module_key = item["key"]
        href = build_context_url(
            module_key,
            module_sede,
            piso=piso,
            local=local,
            view=view,
            home=home,
            filters=filters,
        )
        href_template = ""
        if dynamic_sede_token:
            href_template = build_context_url(
                module_key,
                dynamic_sede_token,
                piso=piso,
                local=local,
                view=view,
                home=home,
                filters=filters,
            )
        nav_modules.append({
            "key": module_key,
            "label": item["label"],
            "tone": item["tone"],
            "href": href,
            "href_template": href_template,
            "active": highlight_module_key == module_key,
        })

    return {
        "accent_color": sede_accent_color(active_code),
        "sedes": nav_sedes,
        "modules": nav_modules,
    }
