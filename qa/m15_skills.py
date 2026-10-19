# -*- coding: utf-8 -*-
"""
M15 QA：技能系统（beat_combat 动态动作 + player.skills 过滤）。

技能 = beat_combat.actions 里标 skill=true 的动作；玩家 state.player_skills
从 game_config.player.skills 初始化，只有学过的技能出现在动作列表里。
"""
from qa.tge_api import GameClient, QaRunner, editor_snapshot, editor_restore

SUITE = "M15 技能系统"


def _actions(cb):
    return cb.get("beat", {}).get("actions", {})


def run(r: QaRunner) -> None:
    c = GameClient("qa_m15")
    snap = editor_snapshot(c)
    try:
        # ---------- S1 默认玩家无技能 ----------
        r.section("S1 未学技能")
        c.reset()
        c.teleport("forest")
        c.combat_start("slime")
        acts = _actions(c.combat())
        r.check("no-fireball-default", "fireball" not in acts, list(acts.keys()))
        r.check("base-actions-present",
                {"attack", "block", "dodge", "charge", "disengage"} <= set(acts),
                list(acts.keys()))
        res = c.post("/api/combat/beat", {"action": "fireball", "weapon_id": ""})[1]
        r.check("unknown-skill-rejected",
                res.get("success") is False and "未知动作" in res.get("message", ""),
                res)

        # ---------- S2 学技能后出现在动作列表 ----------
        r.section("S2 学技能后可见")
        cfg = c.editor_data()["config"]
        cfg.setdefault("player", {})["skills"] = ["fireball"]
        r.check("config-save-ok", c.config_save(cfg).get("success") is True)
        c2 = GameClient("qa_m15b")
        c2.reset()
        c2.teleport("forest")
        c2.combat_start("slime")
        acts = _actions(c2.combat())
        r.check("fireball-visible", "fireball" in acts, list(acts.keys()))
        r.check("fireball-meta",
                acts.get("fireball", {}).get("label") == "火球术"
                and acts["fireball"].get("cost") == 2,
                acts.get("fireball"))

        # ---------- S3 技能造成伤害 ----------
        r.section("S3 技能伤害")
        c2.post("/api/combat/beat", {"action": "block", "weapon_id": ""})  # 攒 AP
        hp_before = c2.combat()["enemy"]["hp"]
        res = c2.post("/api/combat/beat", {"action": "fireball", "weapon_id": ""})[1]
        r.check("fireball-success", res.get("success") is True, res)
        r.check("fireball-log",
                any("火球" in line for line in res.get("log", [])),
                res.get("log"))
        hp_after = c2.combat()["enemy"]["hp"]
        r.check("fireball-damage-15", hp_before - hp_after == 15,
                {"before": hp_before, "after": hp_after})

        # ---------- S4 AP 不足拒绝 ----------
        r.section("S4 AP 不足")
        c3 = GameClient("qa_m15c")
        c3.reset()
        c3.teleport("forest")
        c3.combat_start("slime")  # 初始 AP=1，技能 cost=2
        res = c3.post("/api/combat/beat", {"action": "fireball", "weapon_id": ""})[1]
        r.check("ap-blocked",
                res.get("success") is False and "行动力不足" in res.get("message", ""),
                res)

        # ---------- S5 技能完整结算（HP 扣减 + beat 推进）----------
        r.section("S5 技能完整结算")
        c4 = GameClient("qa_m15d")
        c4.reset()
        c4.teleport("forest")
        c4.combat_start("slime")
        beat_before = c4.combat()["beat"]["beat"]
        c4.post("/api/combat/beat", {"action": "block", "weapon_id": ""})
        res = c4.post("/api/combat/beat", {"action": "fireball", "weapon_id": ""})[1]
        r.check("skill-settlement-ok", res.get("success") is True, res)
        r.check("skill-hp-reduced",
                c4.combat()["enemy"]["hp"] == 26 - 15,
                c4.combat()["enemy"]["hp"])
        r.check("skill-beat-advanced",
                c4.combat()["beat"]["beat"] == beat_before + 2,
                {"before": beat_before, "after": c4.combat()["beat"]["beat"]})

        for x in (c, c2, c3, c4):
            x.cleanup_saves()
    finally:
        editor_restore(c, snap)


if __name__ == "__main__":
    import sys
    from qa.tge_api import ping, DEFAULT_BASE
    if not ping():
        print(f"服务器未响应（{DEFAULT_BASE}），请先启动")
        sys.exit(2)
    r = QaRunner(SUITE)
    run(r)
    print("\n" + "=" * 60)
    print(r.report())
    sys.exit(1 if r.failed else 0)
