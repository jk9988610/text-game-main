# -*- coding: utf-8 -*-
"""
M17 QA：经验/升级系统。

击杀敌人给 exp（characters.json 的 exp 字段），阈值 = level * 20，
升级固定奖励：max_hp +5（回满），attack +1。
"""
from qa.tge_api import GameClient, QaRunner, editor_snapshot, editor_restore

SUITE = "M17 经验/升级"


def _st(c):
    return c.state()


def run(r: QaRunner) -> None:
    c = GameClient("qa_m17")
    snap = editor_snapshot(c)
    try:
        # ---------- S1 初始等级/经验 ----------
        r.section("S1 初始状态")
        c.reset()
        st = _st(c)
        r.check("level-1", st.get("player_level") == 1, st.get("player_level"))
        r.check("exp-0", st.get("player_exp") == 0, st.get("player_exp"))
        r.check("exp-next-20", st.get("exp_next") == 20, st.get("exp_next"))

        # ---------- S2 击杀给经验 ----------
        r.section("S2 击杀给经验")
        # 自建一个低血高经验的测试敌人，一次击杀够升级
        char = {
            "id": "qa_exp_dummy", "name": "QA经验包",
            "description": "M17 测试用。",
            "tags": ["enemy"], "hp": 1, "attack": 1, "defense": 0,
            "exp": 25,
        }
        r.check("dummy-create",
                c.editor_save("character", char).get("success") is True)
        forest = c.editor_data()["scenes"]["forest"]
        forest["enemies_here"] = forest.get("enemies_here", []) + ["qa_exp_dummy"]
        c.editor_save("scene", forest)

        c.reset()
        c.teleport("forest")
        r.check("battle-start",
                c.combat_start("qa_exp_dummy").get("success") is True)
        kill = c.post("/api/combat/beat", {"action": "attack", "weapon_id": "iron_sword"})[1]
        # 低血敌人一击必杀，看日志/经验
        st = _st(c)
        r.check("exp-gained", st.get("player_exp", 0) + (st.get("player_level", 1) - 1) * 20 >= 25,
                {"level": st.get("player_level"), "exp": st.get("player_exp")})
        # 25 exp >= 20 → 应该升到 Lv.2，exp 剩 5
        r.check("level-up-to-2", st.get("player_level") == 2, st.get("player_level"))
        r.check("exp-after-level", st.get("player_exp") == 5, st.get("player_exp"))
        r.check("max-hp-bonus", st.get("player_max_hp", 0) >= 55,
                st.get("player_max_hp"))
        r.check("attack-bonus", st.get("player_attack", 0) >= 6,
                st.get("player_attack"))
        r.check("level-up-log",
                any("升级" in line for line in kill.get("log", [])),
                kill.get("log"))

        # ---------- S3 未达阈值不升级（自建 exp=10 敌人）----------
        r.section("S3 未达阈值")
        char10 = {
            "id": "qa_exp10", "name": "QA经验10",
            "description": "M17 测试用。",
            "tags": ["enemy"], "hp": 1, "attack": 1, "defense": 0,
            "exp": 10,
        }
        r.check("exp10-create",
                c.editor_save("character", char10).get("success") is True)
        forest10 = c.editor_data()["scenes"]["forest"]
        forest10["enemies_here"] = forest10.get("enemies_here", []) + ["qa_exp10"]
        c.editor_save("scene", forest10)
        c.reset()
        c.teleport("forest")
        c.combat_start("qa_exp10")
        c.post("/api/combat/beat", {"action": "attack", "weapon_id": "iron_sword"})
        st = _st(c)
        r.check("still-level-1", st.get("player_level") == 1, st.get("player_level"))
        r.check("exp-10", st.get("player_exp") == 10, st.get("player_exp"))

        # ---------- S3b 存量 slime 给经验（数据回归）----------
        r.section("S3b 存量 slime 给经验")
        c.reset()
        c.teleport("forest")
        c.combat_start("slime")
        last = c.attack_until("slime")
        st = _st(c)
        r.check("slime-gives-10-exp", st.get("player_exp") == 10,
                {"exp": st.get("player_exp"), "log": last.get("log")})

        # ---------- S4 两次击杀升级（自建两个 exp=10 敌人）----------
        r.section("S4 二次击杀升级")
        char_b = {
            "id": "qa_exp10b", "name": "QA经验10b",
            "description": "M17 测试用。",
            "tags": ["enemy"], "hp": 1, "attack": 1, "defense": 0,
            "exp": 10,
        }
        c.editor_save("character", char_b)
        forest_b = c.editor_data()["scenes"]["forest"]
        forest_b["enemies_here"] = forest_b.get("enemies_here", []) + ["qa_exp10b"]
        c.editor_save("scene", forest_b)
        c.reset()
        c.teleport("forest")
        # 第一次击杀 qa_exp10（已经建过），拿 10 exp
        c.combat_start("qa_exp10")
        c.post("/api/combat/beat", {"action": "attack", "weapon_id": "iron_sword"})
        st = _st(c)
        r.check("exp-10-before-second", st.get("player_exp") == 10, st.get("player_exp"))
        # 第二次击杀 qa_exp10b，累计 20 → 升级
        c.combat_start("qa_exp10b")
        c.post("/api/combat/beat", {"action": "attack", "weapon_id": "iron_sword"})
        st = _st(c)
        r.check("level-up-after-second", st.get("player_level") == 2, st.get("player_level"))

        c.cleanup_saves()
    finally:
        editor_restore(c, snap)
        c.cleanup_saves()


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
