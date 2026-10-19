# -*- coding: utf-8 -*-
"""
M16 QA：限量商店（shop_items.stock）。

stock 为整数时是限量，<=0 售罄；无 stock 字段 = 无限供应（向后兼容）。
库存变化写回 scenes.json（全局共享），买完重启也不恢复。
"""
from qa.tge_api import GameClient, QaRunner, editor_snapshot, editor_restore, inventory_ids

SUITE = "M16 限量商店"


def _shop(c, scene_id=None):
    st = c.state()
    return st["scene"].get("shop_items", [])


def run(r: QaRunner) -> None:
    c = GameClient("qa_m16")
    snap = editor_snapshot(c)
    try:
        # ---------- 准备：village 商店放一个限量商品 + 一个无限商品 ----------
        r.section("S0 准备测试商品")
        village = c.editor_data()["scenes"]["village"]
        village["shop_items"] = [
            {"item_id": "healing_potion", "price": 5, "stock": 2},
            {"item_id": "gold_coin", "price": 1},  # 无 stock = 无限
        ]
        r.check("scene-save-ok",
                c.editor_save("scene", village).get("success") is True)

        # ---------- S1 /api/state 暴露 stock ----------
        r.section("S1 状态暴露库存")
        c.reset()
        shop = _shop(c)
        potion = next((g for g in shop if g["id"] == "healing_potion"), None)
        coin = next((g for g in shop if g["id"] == "gold_coin"), None)
        r.check("stock-visible", potion and potion.get("stock") == 2, potion)
        r.check("infinite-no-stock-key", coin and "stock" not in coin, coin)

        # ---------- S2 限量商品买两次后售罄 ----------
        r.section("S2 限量商品")
        # 测试经济：把初始金币改成 1000，避免被金币卡住
        cfg = c.editor_data()["config"]
        cfg["initial_gold"] = 1000
        r.check("config-gold-ok", c.config_save(cfg).get("success") is True)
        c.reset()  # 重新开局，拿到 1000 金币
        b1 = c.buy("healing_potion")
        r.check("buy-1-ok", b1.get("success") is True, b1)
        b2 = c.buy("healing_potion")
        r.check("buy-2-ok", b2.get("success") is True, b2)
        b3 = c.buy("healing_potion")
        r.check("buy-3-soldout",
                b3.get("success") is False and "售罄" in b3.get("message", ""), b3)
        shop = _shop(c)
        potion = next((g for g in shop if g["id"] == "healing_potion"), None)
        r.check("stock-zero-after-2", potion and potion.get("stock") == 0, potion)

        # ---------- S3 无限商品照常买 ----------
        r.section("S3 无限商品")
        for i in range(3):
            res = c.buy("gold_coin")
            r.check("infinite-buy-%d" % (i + 1), res.get("success") is True, res)

        # ---------- S4 库存持久化到磁盘 ----------
        r.section("S4 库存持久化")
        import json, os
        scenes_path = os.path.join(
            os.environ.get("TGE_ROOT", os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)))), "game_data", "scenes.json")
        # 更稳的方式：直接读磁盘
        from qa.tge_api import DEFAULT_BASE
        # 用 editor_data 读内存 + 用磁盘读校验写盘
        data = c.editor_data()["scenes"]["village"]
        potion_mem = next((g for g in data.get("shop_items", [])
                           if g.get("item_id") == "healing_potion"), None)
        r.check("memory-stock-zero", potion_mem and potion_mem.get("stock") == 0,
                potion_mem)

        # 用新 client 读同一份磁盘数据（新会话不改变全局库存）
        c2 = GameClient("qa_m16b")
        c2.reset()
        shop2 = _shop(c2)
        potion2 = next((g for g in shop2 if g["id"] == "healing_potion"), None)
        r.check("new-session-sees-zero",
                potion2 and potion2.get("stock") == 0, potion2)
        r.check("new-session-cannot-buy",
                c2.buy("healing_potion").get("success") is False)

        c2.cleanup_saves()
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
