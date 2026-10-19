"""
文字游戏引擎 MVP —— Flask 多会话隔离版本
架构：SessionManager 管理每个玩家浏览器会话的独立引擎实例
      GAME_DATA 全局只读共享，game_state 按 session_id 完全隔离
"""
from flask import Flask, request, jsonify, session, redirect
import json
import os
import uuid
import random

# ---------- 导入引擎模块 ----------
from engine import (
    SessionManager,
    SaveManager,
    AuthManager,
    AppRegistry,
    ApplicationSaveManager,
    ApplicationSessionManager,
    FormFlowRuntime,
    RevisionConflictError,
    InteractiveStoryRuntime,
    RuntimeDefinition,
    TaskFlowRuntime,
    OrganizationManager,
    ProcessInstanceManager,
    RoleManager,
    beat_combat,
    VALID_ROLES,
)
from engine.editor_manager import EditorManager
# ---------- Flask 初始化 ----------
app = Flask(__name__, static_folder='static', static_url_path='/static')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
# 【安全】secret_key 生产环境从环境变量读，没有才用开发默认值
app.secret_key = os.environ.get('SECRET_KEY') or 'text-game-engine-dev-secret-key-change-in-production'
# 【安全】生产环境强制 debug=False，只有显式设 FLASK_DEBUG=true 才开
DEBUG = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

# ---------- 通用互动故事预览运行时（与旧游戏会话完全隔离） ----------
STORY_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "interactive_story")
STORY_SESSIONS = {}
STORY_SAVE = SaveManager(db_path="game_data/story_saves.db", defaults={})

# ---------- 任务流程模板（独立于游戏和故事会话） ----------
TASK_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "task_flow")
TASK_SESSIONS = {}

# ---------- 表单流程模板（字段 + FlowRuntime） ----------
FORM_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates", "form_flow")
FORM_SESSIONS = {}

# ---------- 应用注册中心：自动发现 templates/*/app.json ----------
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
APP_REGISTRY = AppRegistry(TEMPLATES_DIR)
APP_SESSION_MANAGER = ApplicationSessionManager(APP_REGISTRY)
APP_SAVE_MANAGER = ApplicationSaveManager(APP_REGISTRY, APP_SESSION_MANAGER)
APP_SESSION_MANAGER.set_save_manager(APP_SAVE_MANAGER)
ROLE_MANAGER = RoleManager()
ORGANIZATION_MANAGER = OrganizationManager()
PROCESS_MANAGER = ProcessInstanceManager()


def _form_runtime():
    sid = session.get("form_sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["form_sid"] = sid
    return APP_SESSION_MANAGER.get_or_create("request_form_demo", sid)


def _form_payload(runtime):
    return {
        "title": runtime.definition.title,
        "description": runtime.definition.config.get("description", ""),
        "node_id": runtime.state.get("current_node"),
        "node": runtime.current_node(),
        "fields": runtime.fields,
        "form": runtime.state.get("variables.form", {}),
        "state": runtime.state.export(),
    }


def _task_runtime():
    sid = session.get("task_sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["task_sid"] = sid
    return APP_SESSION_MANAGER.get_or_create("task_flow_demo", sid)


def _task_payload(runtime):
    return {
        "title": runtime.definition.title,
        "description": runtime.definition.config.get("description", ""),
        "node_id": runtime.state.get("current_node"),
        "node": runtime.current_task(),
        "state": runtime.state.export(),
    }


def _story_runtime():
    """按浏览器 session 创建独立互动故事状态。"""
    sid = session.get("story_sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["story_sid"] = sid
    return APP_SESSION_MANAGER.get_or_create("first_branch", sid)


def _story_payload(runtime):
    page = runtime.current_page()
    return {
        "title": runtime.definition.title,
        "description": runtime.definition.config.get("description", ""),
        "page_id": runtime.state.get("current_page"),
        "page": page,
        "state": runtime.state.export(),
    }


def _read_story_editor_data():
    """读取互动故事编辑器需要的配置和页面数据。"""
    with open(os.path.join(STORY_TEMPLATE_DIR, "app.json"), encoding="utf-8") as handle:
        config = json.load(handle)
    with open(os.path.join(STORY_TEMPLATE_DIR, "pages.json"), encoding="utf-8") as handle:
        pages = json.load(handle)
    return config, pages


def _validate_story_editor_data(config, pages):
    """使用运行时校验编辑器提交的数据，并检查基本编辑字段。"""
    if not isinstance(config, dict) or not isinstance(pages, dict):
        raise ValueError("config 和 pages 必须是对象")
    if not str(config.get("title", "")).strip():
        raise ValueError("故事标题不能为空")
    for page_id, page in pages.items():
        if not isinstance(page_id, str) or not page_id.strip():
            raise ValueError("页面 ID 不能为空")
        if not isinstance(page, dict) or not str(page.get("title", "")).strip():
            raise ValueError(f"页面 {page_id} 的标题不能为空")
        for choice in page.get("choices", []):
            if not isinstance(choice, dict) or not str(choice.get("text", "")).strip():
                raise ValueError(f"页面 {page_id} 存在空选项")
            condition = choice.get("if")
            if condition:
                if not isinstance(condition, dict) or not condition.get("path"):
                    raise ValueError(f"页面 {page_id} 的条件格式无效")
                if condition.get("operator", "equals") not in {
                    "equals", "not_equals", "greater_than", "greater_or_equal",
                    "less_than", "less_or_equal", "truthy", "falsy",
                }:
                    raise ValueError(f"页面 {page_id} 的条件运算符无效")
            for action in choice.get("actions", []):
                if action.get("type") not in {"set_variable", "modify_variable"}:
                    raise ValueError(f"页面 {page_id} 的动作类型不支持")
                if not action.get("path"):
                    raise ValueError(f"页面 {page_id} 的动作路径不能为空")
                if action.get("type") == "modify_variable" and not isinstance(action.get("amount"), (int, float)):
                    raise ValueError(f"页面 {page_id} 的修改量必须是数字")
    definition = InteractiveStoryRuntime.from_directory(STORY_TEMPLATE_DIR).definition
    definition.config.update(config)
    InteractiveStoryRuntime(definition, pages).validate()


def _atomic_story_write(filename, payload):
    """先写临时文件，再替换模板文件，避免留下半截 JSON。"""
    target = os.path.join(STORY_TEMPLATE_DIR, filename)
    temp = target + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, target)

# ---------- 加载游戏数据（全局只读，所有玩家共享） ----------
def _derive_character_views(data: dict) -> None:
    """从 characters.json 派生 enemies / npcs 两个只读视图（原地替换内容）。

    角色（characters）是权威数据，引擎核心只认 enemies / npcs 两个键：
      tags 含 enemy    → 出现在 enemies 视图（可战斗、可掉落）
      tags 含 talkable → 出现在 npcs 视图（可对话）
    原地 clear+update（而非整体替换）保证已持有同一 dict 引用的子模块立刻看到新数据。
    """
    chars = data.get("characters") or {}
    enemies = {cid: c for cid, c in chars.items() if "enemy" in (c.get("tags") or [])}
    npcs = {cid: c for cid, c in chars.items() if "talkable" in (c.get("tags") or [])}
    data.setdefault("enemies", {}).clear()
    data["enemies"].update(enemies)
    data.setdefault("npcs", {}).clear()
    data["npcs"].update(npcs)


def load_game_data() -> dict:
    """从 JSON 文件加载游戏数据 —— 只读，所有 session 共用"""
    base = os.path.join(os.path.dirname(__file__), "game_data")
    result = {"scenes": {}, "items": {}, "tags": {}, "characters": {},
              "enemies": {}, "npcs": {}, "events": {}, "config": {}}
    for fname, key in [("scenes.json", "scenes"), ("items.json", "items"),
                       ("tags.json", "tags"), ("characters.json", "characters"),
                       ("events.json", "events"), ("game_config.json", "config")]:
        path = os.path.join(base, fname)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                result[key] = json.load(f)
    _derive_character_views(result)
    return result

GAME_DATA = load_game_data()


def rebuild_character_views() -> None:
    """角色数据变动后重建派生视图（enemies / npcs）"""
    _derive_character_views(GAME_DATA)

# 全局唯一的 SessionManager —— 管理所有玩家的会话
SM = SessionManager(GAME_DATA)
# 全局唯一的 SaveManager —— SQLite 多槽存档（默认值由 game_config 派生，兼容老存档）
SM_SAVE = SaveManager(defaults=SM.initial_state_defaults())
# 全局唯一的 AuthManager —— SQLite 用户账号（在线模式用，独立 auth.db）
SM_AUTH = AuthManager()
# 可视化编辑器数据管理（地点/物品 JSON 的校验与写盘）
EDITOR = EditorManager(data_dir=os.path.join(os.path.dirname(__file__), "game_data"))


def _editor_guard():
    """线上环境（ONLINE_MODE=online）关闭所有编辑器写接口，避免匿名改游戏数据"""
    if os.environ.get('ONLINE_MODE', '').lower() == 'online':
        return jsonify({"success": False, "message": "线上环境已关闭编辑器接口"}), 403
    return None


def _action_time(name: str, default: int = 0) -> int:
    """从 game_config 读每种操作推进的游戏时间（秒）"""
    return (GAME_DATA.get("config") or {}).get("action_time", {}).get(name, default)

# ---------- 请求计数：每 N 次请求清理一次过期 session ----------
_request_counter = 0
CLEANUP_INTERVAL = 100  # 每 100 个请求清一次


def _get_engines():
    """
    每个路由的入口：从 Flask session 拿 sid → 从 SessionManager 拿该玩家的引擎实例
    返回 dict：{game_state, scene_manager, item_system, npc_system, combat_system, console_handler}
    额外附带：_sid（存档隔离键）、_mode（offline/online）、_user_id（在线模式才有）
    
    隔离键优先级：
      在线模式  → user_id（数据库主键，稳定不变）
      离线模式  → client_id（localStorage，稳定不变） → fallback Flask session sid
    """
    global _request_counter
    _request_counter += 1

    # 每 CLEANUP_INTERVAL 次请求触发过期 session 清理
    if _request_counter % CLEANUP_INTERVAL == 0:
        cleaned = SM.cleanup_stale(max_age_minutes=30)
        if cleaned > 0:
            print(f"🧹 SessionManager 清理了 {cleaned} 个过期会话，当前活跃 {SM.session_count()} 个")

    # 模式：query param 优先，否则 session 里已存的，否则默认 offline
    mode = request.args.get('mode') or session.get('mode') or 'offline'
    session['mode'] = mode  # 持久化到 cookie

    # ---------- 核心隔离键逻辑 ----------
    user_id = session.get('user_id')  # 在线模式登录后存进 session 的

    if mode == 'online':
        # 在线模式：必须登录，用 user_id 当存档隔离键
        if not user_id:
            # 没登录 —— 返回 None，调用方检查
            return None
        sid = f"user_{user_id}"  # 加前缀和离线 client_id 区分开
    else:
        # 离线模式：用 localStorage client_id（前端 fetch 自动带上）
        client_id = request.args.get('client_id')
        if client_id:
            sid = client_id
        else:
            sid = session.get('sid')
            if not sid:
                sid = uuid.uuid4().hex[:16]
                session['sid'] = sid

    # 从 SessionManager 获取/创建该玩家的独立引擎实例
    engines = SM.get_or_create(sid)
    engines['_sid'] = sid        # 存档隔离键
    engines['_mode'] = mode      # 模式
    engines['_user_id'] = user_id  # 在线模式才可能有值
    return engines


def _maybe_autosave(e: dict) -> None:
    """
    自动存档：
      - 离线模式 → slot_name="auto"（30 秒防抖，覆盖自己）
      - 在线模式 → slot_name="online_auto"（每次操作都写，服务器实时存档）
    三路隔离：auto(离线) / quick(离线快速) / slot_1~5(离线槽位) / online_auto(在线)
    """
    sid = e['_sid']
    mode = e.get('_mode')

    if mode == 'online':
        # 在线模式：每次操作都自动写（服务器实时存档）
        SM_SAVE.save_slot(sid, "online_auto", e["game_state"], is_auto=True)
    else:
        # 离线模式：30 秒防抖
        import time
        now = time.time()
        last = session.get('_last_autosave', 0)
        if now - last >= 30:
            SM_SAVE.save_slot(sid, "auto", e["game_state"], is_auto=True)
            session['_last_autosave'] = now


# ============================================================
# Flask 路由层 —— 每个路由都先拿 engines dict 再分发
# ============================================================
@app.route('/form')
def serve_form():
    return redirect('/static/form.html')


@app.route('/api/form/state', methods=['GET'])
def form_state():
    return jsonify({"success": True, **_form_payload(_form_runtime())})


@app.route('/api/form/submit', methods=['POST'])
def form_submit():
    denied = _require_capability("submit_form")
    if denied:
        return denied
    runtime = _form_runtime()
    errors = runtime.submit_form(request.get_json(silent=True) or {})
    if errors:
        return jsonify({"success": False, "errors": errors}), 400
    return jsonify({"success": True, **_form_payload(runtime)})


@app.route('/api/form/advance', methods=['POST'])
def form_advance():
    denied = _require_capability("approve")
    if denied:
        return denied
    runtime = _form_runtime()
    index = (request.get_json(silent=True) or {}).get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        return jsonify({"success": False, "message": "index 必须是整数"}), 400
    if runtime.state.get("current_node") == "draft" and not runtime.has_submitted_form():
        return jsonify({"success": False, "message": "请先完整提交表单"}), 400
    try:
        runtime.advance(index)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, **_form_payload(runtime)})


@app.route('/api/form/reset', methods=['POST'])
def form_reset():
    sid = session.get("form_sid")
    if sid:
        APP_SESSION_MANAGER.reset("request_form_demo", sid)
    return jsonify({"success": True, **_form_payload(_form_runtime())})


@app.route('/apps')
def app_hub():
    return redirect('/static/apps.html')


@app.route('/api/apps', methods=['GET'])
def app_catalog():
    return jsonify({"success": True, "apps": APP_REGISTRY.catalog()})


@app.route('/apps/<app_id>')
def generic_app_entry(app_id):
    app_info = APP_REGISTRY.get(app_id)
    if not app_info:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    page_by_type = {
        "interactive_story": "/story",
        "task_flow": "/task",
        "form_flow": "/form",
    }
    target = page_by_type.get(app_info["app_type"])
    if not target:
        return jsonify({"success": False, "message": "应用类型没有运行页面"}), 400
    return redirect(target)


@app.route('/api/apps/<app_id>', methods=['GET'])
def app_info(app_id):
    app_info = APP_REGISTRY.get(app_id)
    if not app_info:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    return jsonify({"success": True, "app": {
        key: value for key, value in app_info.items()
        if key not in {"directory", "config"}
    }})


def _current_user_context():
    user_id = session.get("user_id")
    if not user_id:
        return {"user_id": None, "username": "演示用户",
                "roles": ["applicant", "handler", "approver"], "demo": True}
    user = SM_AUTH.get_user(user_id)
    if not user:
        session.pop("user_id", None)
        return {"user_id": None, "username": "演示用户",
                "roles": ["applicant", "handler", "approver"], "demo": True}
    roles = set(ROLE_MANAGER.roles_for(user_id))
    admin_username = os.environ.get("ADMIN_USERNAME", "").strip()
    if admin_username and user["username"] == admin_username:
        ROLE_MANAGER.assign(user_id, "admin")
        roles.add("admin")
    if not roles:
        ROLE_MANAGER.assign(user_id, "applicant")
        roles.add("applicant")
    organizations = ORGANIZATION_MANAGER.list_for_user(user_id)
    active_id = session.get("organization_id")
    active = next((org for org in organizations if org["id"] == active_id), None)
    effective_roles = set(active["labels"]) if active else roles
    return {"user_id": user_id, "username": user["username"],
            "roles": sorted(effective_roles), "global_roles": sorted(roles),
            "organizations": organizations, "active_organization": active, "demo": False}


def _require_capability(capability: str):
    context = _current_user_context()
    if context["demo"]:
        return None
    if not ROLE_MANAGER.allowed(context["roles"], capability):
        return jsonify({"success": False, "message": "当前账号没有执行此操作的权限"}), 403
    return None


def _process_instance(app_id: str, create: bool = True):
    instance_id = session.get(f"{app_id}_instance_id")
    instance = PROCESS_MANAGER.get(instance_id) if instance_id else None
    if instance is None and create:
        user_id = session.get("user_id")
        instance = PROCESS_MANAGER.create(app_id, user_id)
        session[f"{app_id}_instance_id"] = instance["instance_id"]
    return instance


def _process_payload(app_id: str):
    return _process_instance(app_id, create=False)


def _unified_app_session_id():
    sid = session.get("app_sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["app_sid"] = sid
    return sid


def _auto_save_app(app_id: str, sid: str) -> None:
    APP_SAVE_MANAGER.save(app_id, sid, "auto")
    APP_SAVE_MANAGER.save_current(app_id, sid)


@app.route('/api/apps/<app_id>/process', methods=['GET'])
def process_instance_state(app_id):
    instance = _process_payload(app_id)
    return jsonify({"success": True, "process": instance})


@app.route('/api/apps/<app_id>/process', methods=['POST'])
def process_instance_create(app_id):
    context = _current_user_context()
    instance = PROCESS_MANAGER.create(app_id, context["user_id"])
    session[f"{app_id}_instance_id"] = instance["instance_id"]
    return jsonify({"success": True, "process": instance})


@app.route('/api/apps/<app_id>/process/assign', methods=['POST'])
def process_instance_assign(app_id):
    denied = _require_capability("edit_template")
    if denied:
        return denied
    instance = _process_payload(app_id)
    if not instance:
        return jsonify({"success": False, "message": "没有当前流程实例"}), 404
    values = request.get_json(silent=True) or {}
    try:
        updated = PROCESS_MANAGER.assign(
            instance["instance_id"],
            applicant_id=values.get("applicant_id"),
            handler_id=values.get("handler_id"),
            approver_id=values.get("approver_id"),
        )
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "process": updated})


@app.route('/workbench')
def workbench_page():
    return redirect('/static/workbench.html')


@app.route('/api/workbench', methods=['GET'])
def workbench_data():
    context = _current_user_context()
    user_id = context["user_id"]
    if context["demo"]:
        current = []
        for app_id in ("request_form_demo", "task_flow_demo"):
            instance = _process_payload(app_id)
            if instance:
                current.append(instance)
        return jsonify({"success": True, "demo": True, "submitted": current, "tasks": current, "approvals": current, "completed": []})
    return jsonify({"success": True, "demo": False,
        "submitted": PROCESS_MANAGER.query(user_id=user_id, role="applicant"),
        "tasks": PROCESS_MANAGER.query(user_id=user_id, role="handler"),
        "approvals": PROCESS_MANAGER.query(user_id=user_id, role="approver"),
        "completed": PROCESS_MANAGER.query(user_id=user_id, role="applicant", status="approved")})


@app.route('/api/apps/<app_id>/state', methods=['GET'])
def unified_app_state(app_id):
    sid = session.get("app_sid")
    if not sid:
        sid = uuid.uuid4().hex
        session["app_sid"] = sid
    try:
        payload = APP_SESSION_MANAGER.payload(app_id, sid)
        payload.update(APP_SAVE_MANAGER.current_metadata(app_id, sid))
        payload["process"] = _process_payload(app_id)
        return jsonify({"success": True, **payload})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404


@app.route('/api/apps/<app_id>/reset', methods=['POST'])
def unified_app_reset(app_id):
    sid = session.get("app_sid") or uuid.uuid4().hex
    session["app_sid"] = sid
    try:
        APP_SESSION_MANAGER.reset(app_id, sid)
        payload = APP_SESSION_MANAGER.payload(app_id, sid)
        payload.update(APP_SAVE_MANAGER.current_metadata(app_id, sid))
        payload["process"] = _process_payload(app_id)
        return jsonify({"success": True, **payload})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404


@app.route('/api/apps/<app_id>/transition', methods=['POST'])
def unified_app_transition(app_id):
    capability = "approve" if app_id == "request_form_demo" else "take_task"
    denied = _require_capability(capability)
    if denied:
        return denied
    sid = session.get("app_sid") or uuid.uuid4().hex
    session["app_sid"] = sid
    index = (request.get_json(silent=True) or {}).get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        return jsonify({"success": False, "message": "index 必须是整数"}), 400
    try:
        instance = _process_instance(app_id)
        context = _current_user_context()
        if context["user_id"] is not None:
            field = "approver_id" if app_id == "request_form_demo" else "handler_id"
            current_id = instance.get(field)
            if current_id not in (None, context["user_id"]) and "admin" not in context["roles"]:
                return jsonify({"success": False, "message": "当前流程已分配给其他用户"}), 403
            if current_id is None:
                instance = PROCESS_MANAGER.assign(instance["instance_id"], **{field: context["user_id"]})
        APP_SESSION_MANAGER.transition(app_id, sid, index)
        if app_id == "request_form_demo":
            PROCESS_MANAGER.set_status(instance["instance_id"], "approved" if index == 0 else "rejected")
        else:
            PROCESS_MANAGER.set_status(instance["instance_id"], "in_progress")
        _auto_save_app(app_id, sid)
        payload = APP_SESSION_MANAGER.payload(app_id, sid)
        payload.update(APP_SAVE_MANAGER.current_metadata(app_id, sid))
        payload["process"] = _process_payload(app_id)
        return jsonify({"success": True, **payload})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    except (IndexError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@app.route('/api/apps/<app_id>/saves', methods=['GET'])
def unified_app_saves(app_id):
    sid = _unified_app_session_id()
    try:
        return jsonify({"success": True, "saves": APP_SAVE_MANAGER.list_slots(app_id, sid)})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404


@app.route('/api/apps/<app_id>/save', methods=['POST'])
def unified_app_save(app_id):
    sid = _unified_app_session_id()
    payload = request.get_json(silent=True) or {}
    slot = payload.get("slot", "auto")
    expected_revision = payload.get("expected_revision")
    if expected_revision is not None and (isinstance(expected_revision, bool) or not isinstance(expected_revision, int)):
        return jsonify({"success": False, "message": "expected_revision 必须是整数"}), 400
    try:
        result = APP_SAVE_MANAGER.save(app_id, sid, slot, expected_revision)
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    except RevisionConflictError as exc:
        return jsonify({"success": False, "message": str(exc), "conflict": True}), 409
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "save": result})


@app.route('/api/apps/<app_id>/load', methods=['POST'])
def unified_app_load(app_id):
    sid = _unified_app_session_id()
    slot = (request.get_json(silent=True) or {}).get("slot", "auto")
    try:
        APP_SAVE_MANAGER.load(app_id, sid, slot)
        payload = APP_SESSION_MANAGER.payload(app_id, sid)
        payload.update(APP_SAVE_MANAGER.current_metadata(app_id, sid))
        payload["process"] = _process_payload(app_id)
        return jsonify({"success": True, **payload})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    except FileNotFoundError:
        return jsonify({"success": False, "message": "没有找到存档"}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400


@app.route('/api/apps/<app_id>/delete-save', methods=['POST'])
def unified_app_delete_save(app_id):
    sid = _unified_app_session_id()
    slot = (request.get_json(silent=True) or {}).get("slot", "auto")
    try:
        deleted = APP_SAVE_MANAGER.delete(app_id, sid, slot)
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "deleted": deleted})


@app.route('/api/apps/<app_id>/submit', methods=['POST'])
def unified_app_submit(app_id):
    denied = _require_capability("submit_form")
    if denied:
        return denied
    sid = session.get("app_sid") or uuid.uuid4().hex
    session["app_sid"] = sid
    try:
        errors = APP_SESSION_MANAGER.submit_form(app_id, sid, request.get_json(silent=True) or {})
    except KeyError:
        return jsonify({"success": False, "message": "应用不存在"}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    if errors:
        return jsonify({"success": False, "errors": errors}), 400
    context = _current_user_context()
    instance = _process_instance(app_id)
    if context["user_id"] is not None:
        instance = PROCESS_MANAGER.assign(instance["instance_id"], applicant_id=context["user_id"])
    PROCESS_MANAGER.set_status(instance["instance_id"], "submitted")
    _auto_save_app(app_id, sid)
    payload = APP_SESSION_MANAGER.payload(app_id, sid)
    payload.update(APP_SAVE_MANAGER.current_metadata(app_id, sid))
    payload["process"] = _process_payload(app_id)
    return jsonify({"success": True, **payload})


@app.route('/task')
def serve_task():
    return redirect('/static/task.html')


@app.route('/task/editor')
def serve_task_editor():
    return redirect('/static/task-editor.html')


@app.route('/api/task/state', methods=['GET'])
def task_state():
    return jsonify({"success": True, **_task_payload(_task_runtime())})


@app.route('/api/task/advance', methods=['POST'])
def task_advance():
    denied = _require_capability("take_task")
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    index = payload.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        return jsonify({"success": False, "message": "index 必须是整数"}), 400
    try:
        runtime = _task_runtime()
        runtime.advance(index)
    except (IndexError, KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, **_task_payload(runtime)})


@app.route('/api/task/reset', methods=['POST'])
def task_reset():
    sid = session.get("task_sid")
    if sid:
        APP_SESSION_MANAGER.reset("task_flow_demo", sid)
    return jsonify({"success": True, **_task_payload(_task_runtime())})


@app.route('/api/task/editor/data', methods=['GET'])
def task_editor_data():
    try:
        with open(os.path.join(TASK_TEMPLATE_DIR, "app.json"), encoding="utf-8") as handle:
            config = json.load(handle)
        with open(os.path.join(TASK_TEMPLATE_DIR, "nodes.json"), encoding="utf-8") as handle:
            nodes = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 500
    return jsonify({"success": True, "config": config, "nodes": nodes})


@app.route('/api/task/editor/save', methods=['POST'])
def task_editor_save():
    denied = _require_capability("edit_template")
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    config, nodes = payload.get("config"), payload.get("nodes")
    try:
        if not isinstance(config, dict) or not isinstance(nodes, dict):
            raise ValueError("config 和 nodes 必须是对象")
        if not str(config.get("title", "")).strip():
            raise ValueError("任务流程标题不能为空")
        TaskFlowRuntime(RuntimeDefinition(config, {"nodes": nodes}), nodes)
        for node_id, node in nodes.items():
            if not str(node.get("title", "")).strip():
                raise ValueError(f"节点 {node_id} 标题不能为空")
            for transition in node.get("transitions", []):
                if not str(transition.get("label", "")).strip():
                    raise ValueError(f"节点 {node_id} 存在空转移名称")
        for filename, data in (("app.json", config), ("nodes.json", nodes)):
            target = os.path.join(TASK_TEMPLATE_DIR, filename)
            temp = target + ".tmp"
            with open(temp, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temp, target)
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    TASK_SESSIONS.clear()
    return jsonify({"success": True, "message": "任务流程已保存"})


@app.route('/story')
def serve_story():
    return redirect('/static/story.html')


@app.route('/story/editor')
def serve_story_editor():
    return redirect('/static/story-editor.html')


@app.route('/api/story/editor/data', methods=['GET'])
def story_editor_data():
    try:
        config, pages = _read_story_editor_data()
    except (OSError, json.JSONDecodeError) as exc:
        return jsonify({"success": False, "message": f"读取故事模板失败：{exc}"}), 500
    return jsonify({"success": True, "config": config, "pages": pages})


@app.route('/api/story/editor/save', methods=['POST'])
def story_editor_save():
    denied = _require_capability("edit_template")
    if denied:
        return denied
    payload = request.get_json(silent=True) or {}
    config = payload.get("config")
    pages = payload.get("pages")
    try:
        _validate_story_editor_data(config, pages)
        _atomic_story_write("app.json", config)
        _atomic_story_write("pages.json", pages)
    except (OSError, TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    STORY_SESSIONS.clear()
    return jsonify({"success": True, "message": "互动故事已保存"})


@app.route('/api/story/state', methods=['GET'])
def story_state():
    return jsonify({"success": True, **_story_payload(_story_runtime())})


@app.route('/api/story/reset', methods=['POST'])
def story_reset():
    sid = session.get("story_sid")
    if sid:
        APP_SESSION_MANAGER.reset("first_branch", sid)
    runtime = _story_runtime()
    return jsonify({"success": True, **_story_payload(runtime)})


@app.route('/api/story/save', methods=['POST'])
def story_save():
    runtime = _story_runtime()
    sid = session.get("story_sid")
    slot = (request.get_json(silent=True) or {}).get("slot", "auto")
    if not isinstance(slot, str) or not slot or len(slot) > 32:
        return jsonify({"success": False, "message": "存档槽位无效"}), 400
    data = {"runtime_type": "interactive_story", "app_id": runtime.definition.app_id,
            "state": runtime.state.export()}
    result = STORY_SAVE.save_slot(sid, f"story_{slot}", data)
    return jsonify({"success": True, "slot": slot, "result": result})


@app.route('/api/story/load', methods=['POST'])
def story_load():
    sid = session.get("story_sid")
    payload = request.get_json(silent=True) or {}
    slot = payload.get("slot", "auto")
    if not isinstance(slot, str) or not slot or len(slot) > 32:
        return jsonify({"success": False, "message": "存档槽位无效"}), 400
    saved = STORY_SAVE.load_slot(sid, f"story_{slot}")
    if not saved or saved.get("runtime_type") != "interactive_story":
        return jsonify({"success": False, "message": "没有找到故事存档"}), 404
    runtime = _story_runtime()
    saved_state = saved.get("state") or {}
    current = saved_state.get("current_node", saved_state.get("current_page"))
    if current not in runtime.pages and current is not None:
        return jsonify({"success": False, "message": "存档页面已不存在"}), 400
    runtime.state.replace(saved_state)
    runtime.state.set("current_node", current)
    runtime.state.set("current_page", current)
    return jsonify({"success": True, "slot": slot, **_story_payload(runtime)})


@app.route('/api/story/choose', methods=['POST'])
def story_choose():
    payload = request.get_json(silent=True) or {}
    index = payload.get("index")
    if isinstance(index, bool) or not isinstance(index, int):
        return jsonify({"success": False, "message": "index 必须是整数"}), 400
    try:
        runtime = _story_runtime()
        runtime.choose(index)
    except IndexError:
        return jsonify({"success": False, "message": "无效的故事选项"}), 400
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, **_story_payload(runtime)})


@app.route('/')
def serve_index():
    # 前端已拆分为 index.html + styles.css + js/*，静态资源统一挂在 /static/ 下。
    # 根路径重定向到 /static/index.html，保证页面里的相对路径（styles.css、js/*.js）
    # 能正确解析；GitHub Pages 直接访问 /static/index.html 也与之一致。
    return redirect('/static/index.html')


@app.route('/api/game-info', methods=['GET'])
def game_info():
    """游戏标题/简介（无需会话，模式选择层和页面顶栏启动时拉取）"""
    cfg = GAME_DATA.get("config") or {}
    return jsonify({
        "title": cfg.get("game_title", "文字游戏引擎"),
        "intro": cfg.get("game_intro", ""),
    })


@app.route('/api/state', methods=['GET'])
def get_state():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    scene_id = e["game_state"].get("current_scene", "")
    return jsonify({
        "scene": e["scene_manager"].get_current_scene(),
        "player_inventory": e["item_system"].get_player_inventory(),
        "player_gold": e["game_state"].get("player_gold", 0),
        "flags": e["game_state"].get("flags", {}),
        "game_time": e["game_state"].get("game_time", 0),
        "npcs_here": e["npc_system"].list_npcs_in_scene(scene_id),      # 场景里的 NPC
        "enemies_here": e["combat_system"].list_enemies_in_scene(scene_id),  # 场景里的敌人
    })


# ---------- 主动触发对话/战斗的路由 ----------
@app.route('/api/dialogue/start', methods=['POST'])
def start_dialogue():
    """玩家点"和 XX 说话" → 手动启动对话"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    result = e["npc_system"].start_dialogue(data.get("npc_id", ""))
    return jsonify(result)


@app.route('/api/combat/start', methods=['POST'])
def start_combat():
    """玩家点"挑战 XX" → 手动开始/继续战斗（保留敌人残血）"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    result = e["combat_system"].start_battle(data.get("enemy_id", ""))
    if result.get("success"):
        # 玩家主动接战（含休整中重新挑战）→ 取消恢复计时 + 重置 AP/拍序号
        # （两个调用在未启用 Beat 战斗的工程里都是无害空操作）
        beat_combat.cancel_detach(e["game_state"])
        beat_combat.init_engagement(e["game_state"], GAME_DATA)
    return jsonify(result)


@app.route('/api/action', methods=['POST'])
def handle_action():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    action_type = data.get("type")
    action_target = data.get("target")

    result = {"success": False, "message": ""}
    if action_type == "take_item":
        result = e["item_system"].take_item(action_target)
    elif action_type == "move_scene":
        result = e["scene_manager"].move_to(action_target)
    elif action_type == "buy_item":
        result = e["shop_system"].buy_item(action_target)
    elif action_type == "use_item":
        result = e["item_system"].use_item(action_target, data.get("target_id"))
    else:
        result = {"success": False, "message": f"未知操作类型：{action_type}"}

    # 玩家做了操作 → 推进游戏时间（每种操作的秒数由 game_config 配置）
    if result.get("success"):
        time_delta = _action_time(action_type, 0)
        e["game_state"]["game_time"] = e["game_state"].get("game_time", 0) + time_delta
        # 行动时间推进后静默结算脱离休整恢复（未脱离/未启用 Beat 时空操作）
        beat_combat.tick_recover(e["combat_system"], e["game_state"], GAME_DATA)

    #  玩家做了操作 → 尝试自动存档（离线模式 + 30秒防抖）
    if result.get("success"):
        _maybe_autosave(e)
    return jsonify(result)


@app.route('/api/console', methods=['POST'])
def handle_console():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    return jsonify({"output": e["console_handler"].handle(data.get("command", ""))})


@app.route('/api/dialogue', methods=['GET'])
def get_dialogue():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    return jsonify(e["npc_system"].get_dialogue_for_api())


@app.route('/api/dialogue', methods=['POST'])
def handle_dialogue():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    result = e["npc_system"].select_choice(data.get("choice_index", 0))

    # 执行选项挂的效果（给物品/置标志/回血/传送/开战等跨系统动作统一在此编排）
    effects = result.pop("effects", None)
    if result.get("success") and effects:
        eff_res = e["effects"].apply(effects)
        result["effect_messages"] = eff_res.get("messages", [])
        # 开战/传送类效果会让对话无法继续：确保对话已结束
        if eff_res.get("combat_started"):
            e["npc_system"].end_dialogue()
    return jsonify(result)


@app.route('/api/combat', methods=['GET'])
def get_combat():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    result = e["combat_system"].get_battle_for_api()
    # 战斗中：附带背包里可使用的消耗品（给战斗面板渲染"喝药"按钮）
    if result.get("active"):
        result["usable_items"] = [
            it for it in e["item_system"].get_player_inventory()
            if it.get("usable")
        ]
        # Beat 制战斗：下发拍面（意图/AP/费用）；脱离/未开拍时隐藏战斗面板
        if beat_combat.beat_config(GAME_DATA):
            result["beat"] = beat_combat.describe(e["game_state"], GAME_DATA)
            if result["beat"] and not result["beat"].get("in_battle"):
                result["active"] = False
        # 已脱离（休整中）：底层 current_battle 保留残血，但对外隐藏战斗面板
        if result.get("active") and beat_combat.is_detached(e["game_state"]):
            result["active"] = False
    return jsonify(result)


@app.route('/api/combat/attack', methods=['POST'])
def handle_attack():
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json
    # 前端无需指定武器：不传时自动使用背包中第一把武器（引擎不绑定具体物品 ID）
    weapon_id = data.get("weapon_id") or e["item_system"].first_weapon_id()
    # 一出手即视为重新接战，取消休整计时（未脱离时空操作）
    beat_combat.cancel_detach(e["game_state"])
    result = e["combat_system"].player_attack(weapon_id)
    # 战斗推进游戏时间（每回合秒数由 game_config 配置）
    e["game_state"]["game_time"] = e["game_state"].get("game_time", 0) + _action_time("combat_turn", 60)
    # 战斗后也自动存档
    if result.get("success") or result.get("player_dead"):
        beat_combat.tick_recover(e["combat_system"], e["game_state"], GAME_DATA)
        _maybe_autosave(e)
    return jsonify(result)


@app.route('/api/combat/use-item', methods=['POST'])
def handle_combat_use_item():
    """战斗中使用消耗品（喝药算一回合，敌人会趁机反击）"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    data = request.json or {}
    # 战斗中喝药即视为继续接战，取消休整计时（未脱离时空操作）
    beat_combat.cancel_detach(e["game_state"])
    item_id = data.get("item_id", "")
    result = e["combat_system"].use_item_in_battle(item_id)
    # 与攻击回合同等耗时
    e["game_state"]["game_time"] = e["game_state"].get("game_time", 0) + _action_time("combat_turn", 60)
    if result.get("success") or result.get("player_dead"):
        beat_combat.tick_recover(e["combat_system"], e["game_state"], GAME_DATA)
        _maybe_autosave(e)
    return jsonify(result)


@app.route('/api/combat/beat', methods=['POST'])
def handle_combat_beat():
    """Beat 制：提交本拍主动作 attack/block/dodge/charge/disengage，同拍揭晓结算"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401
    if not beat_combat.beat_config(GAME_DATA):
        return jsonify({"success": False, "message": "当前工程未启用 Beat 战斗"}), 409
    data = request.json or {}
    # 重新接战统一走 /api/combat/start（「挑战」按钮：残血复用 + 重置 AP/拍序号）；
    # 休整态直接提交动作会被拒答（"你已经脱离战斗了"）
    weapon_id = data.get("weapon_id") or e["item_system"].first_weapon_id()
    result = beat_combat.resolve(e["combat_system"], e["game_state"], GAME_DATA,
                                 data.get("action", ""), weapon_id)
    # 每个 beat 与一次战斗回合同等耗时（脱离拍也计入）
    if result.get("success") or result.get("player_dead"):
        e["game_state"]["game_time"] = e["game_state"].get("game_time", 0) + _action_time("combat_turn", 60)
        beat_combat.tick_recover(e["combat_system"], e["game_state"], GAME_DATA)
        _maybe_autosave(e)
    return jsonify(result)


# ============================================================
# 3.5 用户认证路由（在线模式专属，全部返回 JSON）
# ============================================================
@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    """注册新用户"""
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    ok, msg, user_id = SM_AUTH.register(username, password)
    if ok:
        # 注册成功 → 自动登录（session 绑定 user_id）
        session['user_id'] = user_id
        session['username'] = username
        session['mode'] = 'online'
        ROLE_MANAGER.assign(user_id, "applicant")
        if os.environ.get("ADMIN_USERNAME", "").strip() == username:
            ROLE_MANAGER.assign(user_id, "admin")
        return jsonify({"success": True, "message": msg, "user_id": user_id, "username": username})
    return jsonify({"success": False, "message": msg})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    """用户登录"""
    data = request.json or {}
    username = data.get('username', '').strip()
    password = data.get('password', '')
    ok, msg, user_info = SM_AUTH.login(username, password)
    if ok:
        # 登录成功 → session 绑定 user_id
        session['user_id'] = user_info['user_id']
        session['username'] = user_info['username']
        session['mode'] = 'online'
        return jsonify({"success": True, "message": msg, "user": user_info})
    return jsonify({"success": False, "message": msg})


@app.route('/api/auth/logout', methods=['POST', 'GET'])
def auth_logout():
    """
    退出登录 —— 只清在线登录态，保留离线隔离键 sid
    sid 是离线模式用的存档隔离键，和在线登录态完全独立，不能清！
    """
    session.pop('user_id', None)
    session.pop('username', None)
    session.pop('_last_autosave', None)
    session.pop('mode', None)       # 清掉 mode，让前端重新选
    # session.pop('sid', None)      # 不要清！sid 是离线模式隔离键
    return jsonify({"success": True, "message": "已退出登录"})


@app.route('/api/organizations', methods=['GET'])
def organization_list():
    context = _current_user_context()
    if context["demo"]:
        return jsonify({"success": True, "organizations": [], "active": None})
    return jsonify({"success": True, "organizations": context["organizations"], "active": context["active_organization"]})


@app.route('/api/organizations', methods=['POST'])
def organization_create():
    context = _current_user_context()
    if context["demo"]:
        return jsonify({"success": False, "message": "请先登录后创建组织"}), 401
    try:
        organization = ORGANIZATION_MANAGER.create(
            (request.get_json(silent=True) or {}).get("name", ""), context["user_id"]
        )
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    session["organization_id"] = organization["id"]
    return jsonify({"success": True, "organization": organization})


@app.route('/api/organizations/join', methods=['POST'])
def organization_join():
    context = _current_user_context()
    if context["demo"]:
        return jsonify({"success": False, "message": "请先登录后加入组织"}), 401
    try:
        organization = ORGANIZATION_MANAGER.join(
            (request.get_json(silent=True) or {}).get("join_code", ""), context["user_id"]
        )
    except KeyError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    session["organization_id"] = organization["id"]
    return jsonify({"success": True, "organization": organization})


@app.route('/api/organizations/select', methods=['POST'])
def organization_select():
    context = _current_user_context()
    if context["demo"]:
        return jsonify({"success": False, "message": "请先登录"}), 401
    organization_id = (request.get_json(silent=True) or {}).get("organization_id")
    if not any(org["id"] == organization_id for org in context["organizations"]):
        return jsonify({"success": False, "message": "不是该组织成员"}), 403
    session["organization_id"] = organization_id
    return jsonify({"success": True, "user": _current_user_context()})


@app.route('/api/organizations/<int:organization_id>/members', methods=['GET'])
def organization_members(organization_id):
    context = _current_user_context()
    if not context["active_organization"] or context["active_organization"]["id"] != organization_id:
        return jsonify({"success": False, "message": "请先选择组织"}), 403
    return jsonify({"success": True, "members": ORGANIZATION_MANAGER.members(organization_id)})


@app.route('/api/organizations/<int:organization_id>/members/<int:user_id>/labels', methods=['POST'])
def organization_labels(organization_id, user_id):
    context = _current_user_context()
    active = context["active_organization"]
    if not active or active["id"] != organization_id or "admin" not in active["labels"]:
        return jsonify({"success": False, "message": "只有组织管理员可以修改成员标签"}), 403
    try:
        ORGANIZATION_MANAGER.set_labels(
            organization_id, user_id, (request.get_json(silent=True) or {}).get("labels", [])
        )
    except (KeyError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "members": ORGANIZATION_MANAGER.members(organization_id)})


@app.route('/api/auth/roles', methods=['GET'])
def auth_roles():
    return jsonify({"success": True, "user": _current_user_context()})


@app.route('/api/auth/roles/<int:user_id>', methods=['POST'])
def assign_role(user_id):
    denied = _require_capability("edit_template")
    if denied:
        return denied
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in VALID_ROLES:
        return jsonify({"success": False, "message": "无效角色"}), 400
    try:
        ROLE_MANAGER.assign(user_id, role)
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    return jsonify({"success": True, "user_id": user_id, "roles": ROLE_MANAGER.roles_for(user_id)})


@app.route('/api/auth/roles/<int:user_id>', methods=['DELETE'])
def revoke_role(user_id):
    denied = _require_capability("edit_template")
    if denied:
        return denied
    role = (request.get_json(silent=True) or {}).get("role")
    if role not in VALID_ROLES:
        return jsonify({"success": False, "message": "无效角色"}), 400
    return jsonify({"success": True, "deleted": ROLE_MANAGER.revoke(user_id, role), "roles": ROLE_MANAGER.roles_for(user_id)})


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    """查询当前登录用户信息（前端用来判断登录态）"""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({"logged_in": False})
    user = SM_AUTH.get_user(user_id)
    if not user:
        # user_id 在 session 里但数据库里没了（极端情况）→ 清 session
        session.pop('user_id', None)
        session.pop('username', None)
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user": user})


# ============================================================
# 4. 存档路由
#    在线模式：自动存档（online_auto），禁手动
#    离线模式：auto（自动）/ quick（快速保存）/ slot_1~5（手动槽位）
# ============================================================
@app.route('/api/saves', methods=['GET'])
def list_saves():
    """
    列出当前隔离键的所有存档槽位（带完整状态视图）
    返回格式：{auto, quick, slots: [{slot_name, has_data, updated_at}]}
    """
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401

    # 从 DB 拉已有的存档记录
    existing = {s["slot_name"]: s for s in SM_SAVE.list_slots(e['_sid'])}

    if e['_mode'] == 'online':
        # 在线模式只有 online_auto
        online = existing.get("online_auto")
        return jsonify({
            "mode": "online",
            "can_manual_save": False,
            "online_auto": bool(online),
            "online_auto_updated_at": online["updated_at"] if online else None,
        })

    # 离线模式：完整三路
    auto = existing.get("auto")
    quick = existing.get("quick")
    slots = []
    for i in range(1, 6):
        sname = f"slot_{i}"
        s = existing.get(sname)
        slots.append({
            "slot_name": sname,
            "has_data": bool(s),
            "updated_at": s["updated_at"] if s else None,
        })
    return jsonify({
        "mode": "offline",
        "can_manual_save": True,
        "auto_has_data": bool(auto),
        "auto_updated_at": auto["updated_at"] if auto else None,
        "quick_has_data": bool(quick),
        "quick_updated_at": quick["updated_at"] if quick else None,
        "slots": slots,
    })


@app.route('/api/save', methods=['POST'])
def manual_save():
    """
    手动存档到指定槽位 —— 离线模式专属
    在线模式返回 403（自动存档，不允许手动）
    """
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401

    if e['_mode'] == 'online':
        return jsonify({"success": False, "message": "在线模式自动存档，无需手动保存"}), 403

    data = request.json or {}
    slot_name = (data.get("slot_name") or "slot_1").strip()
    # 安全校验：只允许 slot_1 ~ slot_5
    if slot_name not in [f"slot_{i}" for i in range(1, 6)]:
        return jsonify({"success": False, "message": "槽位名无效，可用：slot_1~slot_5"})

    result = SM_SAVE.save_slot(e['_sid'], slot_name, e["game_state"], is_auto=False)
    session['_last_autosave'] = 0
    return jsonify(result)


@app.route('/api/save/quick', methods=['POST'])
def quick_save():
    """
    快速保存 —— 快捷键一键存，覆盖 quick 槽位
    离线模式专属
    """
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401

    if e['_mode'] == 'online':
        return jsonify({"success": False, "message": "在线模式自动存档，无需手动保存"}), 403

    result = SM_SAVE.save_slot(e['_sid'], "quick", e["game_state"], is_auto=False)
    session['_last_autosave'] = 0
    return jsonify(result)


@app.route('/api/load', methods=['POST'])
def load_save():
    """从指定槽位读档 → 覆盖当前 game_state"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401

    data = request.json or {}
    slot_name = data.get("slot_name", "").strip()
    if not slot_name:
        return jsonify({"success": False, "message": "请指定槽位名"})

    loaded = SM_SAVE.load_slot(e['_sid'], slot_name)
    if not loaded:
        return jsonify({"success": False, "message": f"槽位 {slot_name} 是空的"})

    # 覆盖当前隔离键的 game_state
    e["game_state"].clear()
    e["game_state"].update(loaded)
    # 旧版原型存档键迁移（_proto_* → 正式键，幂等）
    beat_combat.migrate_state(e["game_state"])
    # 触发 SCENE_ENTER → 让 NPC/战斗系统同步场景（对话、刷怪）
    e["bus"].publish("SCENE_ENTER", scene_id=e["game_state"]["current_scene"])
    session['_last_autosave'] = 0
    return jsonify({"success": True, "message": f"已读取槽位 {slot_name} 的存档"})


@app.route('/api/save', methods=['DELETE'])
def delete_save():
    """删除一个槽位的存档 —— 离线模式专属"""
    e = _get_engines()
    if not e:
        return jsonify({"success": False, "message": "请先登录（在线模式）"}), 401

    if e['_mode'] == 'online':
        return jsonify({"success": False, "message": "在线模式不允许删除存档"}), 403

    data = request.json or {}
    slot_name = data.get("slot_name", "").strip()
    if not slot_name:
        return jsonify({"success": False, "message": "请指定槽位名"})
    ok = SM_SAVE.delete_slot(e['_sid'], slot_name)
    if ok:
        return jsonify({"success": True, "message": f"已删除槽位 {slot_name}"})
    return jsonify({"success": False, "message": f"槽位 {slot_name} 不存在"})


# ============================================================
# 5. 可视化编辑器 API（地点 / 物品）
#    仅本地开发环境开放；线上 ONLINE_MODE=online 时全部 403
# ============================================================
@app.route('/api/editor/data', methods=['GET'])
def editor_get_data():
    """编辑器首屏数据：全部地点 + 全部物品 + 初始场景标记"""
    denied = _editor_guard()
    if denied:
        return denied
    # 事件字典是从磁盘直读的只读词汇表：编辑器每次拉数据时顺手同步进 GAME_DATA，
    # 这样手改 events.json 后不用重启服务，新开的游戏也能用上新字典。
    events = EDITOR.load_events()
    GAME_DATA.setdefault("events", {}).clear()
    GAME_DATA["events"].update(events)
    return jsonify({
        "success": True,
        "scenes": GAME_DATA["scenes"],
        "items": GAME_DATA["items"],
        "tags": GAME_DATA["tags"],
        "characters": GAME_DATA["characters"],
        "events": events,
        # enemies / npcs 是 characters 的派生物，仅供对话树/画布的条件选项使用
        "enemies": GAME_DATA["enemies"],
        "npcs": GAME_DATA["npcs"],
        "config": GAME_DATA["config"],
        "layouts": EDITOR.load_layouts(),
        "scene_layouts": EDITOR.load_scene_layouts(),
        "editor_settings": EDITOR.load_editor_settings(),
        "initial_scene": (GAME_DATA.get("config") or {}).get("initial_scene", ""),
    })


@app.route('/api/editor/scene', methods=['POST'])
def editor_upsert_scene():
    """新建/更新一个地点（按 id 区分新建与编辑）"""
    denied = _editor_guard()
    if denied:
        return denied
    payload = request.json or {}
    result = EDITOR.upsert_scene(
        GAME_DATA["scenes"], GAME_DATA["items"], GAME_DATA["enemies"], payload)
    if result.get("success"):
        SM.refresh_new_scenes()  # 让所有存活会话补齐新场景的状态键
    return jsonify(result)


@app.route('/api/editor/scene/<scene_id>', methods=['DELETE'])
def editor_delete_scene(scene_id):
    """删除一个地点（初始场景/被引用/有玩家在里面时拒绝）"""
    denied = _editor_guard()
    if denied:
        return denied
    initial_scene = (GAME_DATA.get("config") or {}).get("initial_scene", "")
    result = EDITOR.delete_scene(
        GAME_DATA["scenes"], GAME_DATA["items"], scene_id,
        initial_scene=initial_scene,
        live_scene_ids=SM.live_current_scenes())
    return jsonify(result)


@app.route('/api/editor/scene-layout/<scene_id>', methods=['POST'])
def editor_save_scene_layout(scene_id):
    """保存场景地图画布上单个地点的坐标（辅助数据，不影响游戏内容）"""
    denied = _editor_guard()
    if denied:
        return denied
    return EDITOR.save_scene_layout(scene_id, request.json or {})


@app.route('/api/editor/settings', methods=['POST'])
def editor_save_settings():
    """保存编辑器偏好（自动保存/收起键；写入 editor_settings.json，非游戏内容）"""
    denied = _editor_guard()
    if denied:
        return denied
    return EDITOR.save_editor_settings(request.json or {})


@app.route('/api/editor/item', methods=['POST'])
def editor_upsert_item():
    """新建/更新一个物品"""
    denied = _editor_guard()
    if denied:
        return denied
    payload = request.json or {}
    result = EDITOR.upsert_item(
        GAME_DATA["scenes"], GAME_DATA["items"], GAME_DATA["enemies"],
        GAME_DATA.get("config") or {}, GAME_DATA["tags"], payload)
    return jsonify(result)


@app.route('/api/editor/tag', methods=['POST'])
def editor_upsert_tag():
    """新建/更新一个标签（标签 = 目标类型 + 字段组，物品/角色按标签展开字段）"""
    denied = _editor_guard()
    if denied:
        return denied
    return jsonify(EDITOR.upsert_tag(GAME_DATA["tags"], request.json or {}))


@app.route('/api/editor/tag/<tag_id>', methods=['DELETE'])
def editor_delete_tag(tag_id):
    """删除一个标签（仍有物品或角色贴用时拒绝）"""
    denied = _editor_guard()
    if denied:
        return denied
    return jsonify(EDITOR.delete_tag(
        GAME_DATA["tags"], GAME_DATA["items"], GAME_DATA["characters"], tag_id))


@app.route('/api/editor/item/<item_id>', methods=['DELETE'])
def editor_delete_item(item_id):
    """删除一个物品（被地点放置/商店售卖/敌人掉落/初始背包引用时拒绝）"""
    denied = _editor_guard()
    if denied:
        return denied
    result = EDITOR.delete_item(
        GAME_DATA["scenes"], GAME_DATA["items"], GAME_DATA["enemies"],
        GAME_DATA.get("config") or {}, item_id)
    return jsonify(result)


@app.route('/api/editor/character', methods=['POST'])
def editor_upsert_character():
    """新建/更新一个角色（基础字段 + 标签字段组 + 可选对话树 / Beat 配置，按 id 区分）"""
    denied = _editor_guard()
    if denied:
        return denied
    payload = request.json or {}
    result = EDITOR.upsert_character(
        GAME_DATA["characters"], GAME_DATA["scenes"], GAME_DATA["items"],
        GAME_DATA["tags"], payload)
    if result.get("success"):
        rebuild_character_views()  # 标签可能变化，重建 enemies / npcs 派生物
        # 节点可能增删，顺带清理该角色的画布孤儿坐标（坐标独立保存，不影响结果）
        EDITOR.prune_layouts(GAME_DATA["npcs"])
    return jsonify(result)


@app.route('/api/editor/character/<character_id>', methods=['DELETE'])
def editor_delete_character(character_id):
    """删除一个角色（被场景引用 / 有玩家正在与之战斗或对话时拒绝）"""
    denied = _editor_guard()
    if denied:
        return denied
    result = EDITOR.delete_character(
        GAME_DATA["scenes"], GAME_DATA["characters"], character_id,
        live_battle_ids=SM.live_battle_enemies(),
        live_dialogue_ids=SM.live_dialogue_npcs())
    if result.get("success"):
        rebuild_character_views()
        EDITOR.prune_layouts(GAME_DATA["npcs"])
    return jsonify(result)


@app.route('/api/editor/npc-layout/<npc_id>', methods=['POST'])
def editor_save_npc_layout(npc_id):
    """保存单个角色对话画布的节点坐标（与游戏内容分离，仅坐标）"""
    denied = _editor_guard()
    if denied:
        return denied
    return EDITOR.save_layout(npc_id, request.json or {})


@app.route('/api/editor/config', methods=['POST'])
def editor_save_config():
    """保存游戏开局配置（标题/简介/初始场景/背包/金币/玩家属性）"""
    denied = _editor_guard()
    if denied:
        return denied
    payload = request.json or {}
    result = EDITOR.upsert_config(
        GAME_DATA["config"], GAME_DATA["scenes"], GAME_DATA["items"], payload)
    if result.get("success"):
        # 刷新老存档 normalize 用的默认值（新会话/reset 直接读 config，不受影响）
        SM_SAVE.update_defaults(SM.initial_state_defaults())
    return result


@app.route('/api/editor/event-rule', methods=['POST'])
def editor_upsert_event_rule():
    """新建/更新一条事件规则"""
    denied = _editor_guard()
    if denied:
        return denied
    payload = request.json or {}
    result = EDITOR.upsert_event_rule(
        GAME_DATA["config"], GAME_DATA["scenes"], GAME_DATA["items"],
        GAME_DATA["enemies"], GAME_DATA["npcs"], payload)
    return result


@app.route('/api/editor/event-rule/<rule_id>', methods=['DELETE'])
def editor_delete_event_rule(rule_id):
    """删除一条事件规则"""
    denied = _editor_guard()
    if denied:
        return denied
    return EDITOR.delete_event_rule(GAME_DATA["config"], rule_id)


# ============================================================
# 启动入口
# ============================================================
if __name__ == '__main__':
    print("=" * 50)
    print("文字游戏引擎 MVP")
    print("访问 http://localhost:5000")
    print(f"debug={DEBUG} | SECRET_KEY={'(env)' if os.environ.get('SECRET_KEY') else '(开发默认值)'}")
    print("=" * 50)
    # 开发模式才跑 Flask 内置服务器，生产用 gunicorn
    if os.environ.get('GUNICORN_RUNNING', '').lower() != 'true':
        app.run(host='0.0.0.0', port=5000, debug=DEBUG)


@app.errorhandler(404)
def handle_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"success": False, "message": f"API 路由不存在: {request.path}"}), 404
    return error
