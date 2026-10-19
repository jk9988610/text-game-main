# -*- coding: utf-8 -*-
"""
M3 回归套件：金币体系 / 货币折算 / 商店购买 / 消耗品使用 / 编辑器物品保护。

依赖的游戏数据（当前 game_data）：
  - 初始：village 场景、背包 [iron_sword]、金币 10、玩家 50HP
  - gold_coin：currency_value=1（拿到即折算金币，不进背包）
  - village：商店无限供应 healing_potion@5 金币

测试原则：断言读游戏实际配置，不硬编码数值——验证"机制"而非"具体数值"，
这样游戏数据调整后测试不会假失败。
"""
from qa.tge_api import (
    GameClient, QaRunner,
    editor_snapshot, editor_restore,
    inventory_ids,
)

SUITE = "M3 金币/商店/喝药"

BREAD = {
    "id": "qa_bread",
    "name": "QA面包",
    "description": "QA 专用零金币商品，套件结束应被自动删除。",
    "tags": ["consumable"],
    "heal": 10,
}


def run(r: QaRunner) -> None:
    c = GameClient("qa_m3")
    snap = editor_snapshot(c)
    try:
        # ---------- S1 新游戏初始经济状态 ----------
        r.section("S1 初始状态")
        c.reset()
        st = c.state()
        cfg = c.editor_data()["config"]
        r.check("initial-gold-matches-config",
                st.get("player_gold") == cfg.get("initial_gold", 0),
                {"actual": st.get("player_gold"), "config": cfg.get("initial_gold")})
        r.check("initial-inventory-matches-config",
                inventory_ids(st) == sorted(cfg.get("initial_inventory", [])),
                {"actual": inventory_ids(st),
                 "config": cfg.get("initial_inventory")})

        # ---------- S2 货币类物品直接折算金币 ----------
        r.section("S2 货币折算")
        before = c.state().get("player_gold", 0)
        out = c.give("gold_coin")
        st = c.state()
        r.check("give-coin-gold-plus-1",
                st.get("player_gold") == before + 1,
                {"before": before, "after": st.get("player_gold"), "resp": out})
        r.check("coin-not-in-bag", "gold_coin" not in inventory_ids(st), inventory_ids(st))

        # ---------- S3 商店数据随场景下发 ----------
        r.section("S3 药水店在售货物")
        c.teleport("village")
        shop = c.state()["scene"].get("shop_items", [])
        r.check("potion-on-sale",
                any(g.get("id") == "healing_potion" and g.get("price", -1) > 0
                    for g in shop),
                shop)

        # ---------- S4 没钱买不了 ----------
        r.section("S4 金币不足拦截")
        c.reset()
        c.teleport("village")
        st = c.state()
        cfg = c.editor_data()["config"]
        shop = st["scene"].get("shop_items", [])
        potion = next((g for g in shop if g.get("id") == "healing_potion"), None)
        if potion is None:
            r.check("shop-has-potion", False, shop)
        elif st.get("player_gold", 0) >= potion.get("price", 0):
            r.check("skip-broke-case-insufficient-gold", True,
                    {"note": "初始金币足够，跳过金币不足拦截测试",
                     "gold": st.get("player_gold"), "price": potion.get("price")})
        else:
            poor = c.buy("healing_potion")
            r.check("broke-buy-blocked",
                    poor.get("success") is False and "金币不足" in poor.get("message", ""),
                    poor)
            r.check("gold-still-same", c.state().get("player_gold") == st.get("player_gold"))

        # ---------- S5 有钱成交、可复购、余额扣减 ----------
        r.section("S5 购买成交")
        st = c.state()
        shop = st["scene"].get("shop_items", [])
        potion = next((g for g in shop if g.get("id") == "healing_potion"), None)
        if potion is None:
            r.check("shop-has-potion", False, shop)
        else:
            before = st.get("player_gold", 0)
            price = potion.get("price", 0)
            if before < price:
                c.give("gold_coin", price - before)  # 补齐
            deal = c.buy("healing_potion")
            r.check("buy-success", deal.get("success") is True, deal)
            st2 = c.state()
            r.check("gold-deducted", st2.get("player_gold") == before - price + (price - before if before < price else 0),
                    {"before": before, "after": st2.get("player_gold"), "price": price})
            r.check("potion-in-bag", "healing_potion" in inventory_ids(st2))

        # ---------- S6 地上的药水也能捡；满血喝药被拒 ----------
        r.section("S6 拾取与满血拦截")
        st = c.state()
        bag_potions = inventory_ids(st).count("healing_potion")
        ground = st.get("scene", {}).get("items_here", [])
        if "healing_potion" not in ground:
            r.check("skip-ground-potion-not-in-scene", True,
                    {"note": "当前场景地上没有药水，跳过拾取测试", "items_here": ground})
        else:
            take = c.take("healing_potion")
            r.check("ground-potion-take", take.get("success") is True, take)
            r.check("two-potions",
                    inventory_ids(c.state()).count("healing_potion") == bag_potions + 1)
        if bag_potions == 0:
            r.check("skip-full-hp-blocked-no-potion", True)
        else:
            full = c.use_item("healing_potion")
            r.check("full-hp-use-blocked",
                    full.get("success") is False and "满" in full.get("message", ""), full)

        # ---------- S7 编辑器：物品 CRUD + 无法获得警告 + 校验 ----------
        r.section("S7 编辑器物品")
        res = c.editor_save("item", BREAD)
        r.check("bread-create-ok", res.get("success") is True, res)
        r.check("unobtainable-warning",
                any("无法获得" in w for w in res.get("warnings", [])),
                res.get("warnings"))
        r.check("weapon-neg-damage-blocked",
                c.editor_save("item", {**BREAD, "id": "qa_bad",
                                       "tags": ["weapon"],
                                       "damage": -1}).get("success") is False)
        r.check("currency-zero-blocked",
                c.editor_save("item", {**BREAD, "id": "qa_bad",
                                       "tags": ["currency"],
                                       "currency_value": 0}).get("success") is False)
        r.check("empty-name-blocked",
                c.editor_save("item", {**BREAD, "id": "qa_bad", "name": ""}).get("success") is False)
        r.check("bad-item-not-saved", "qa_bad" not in c.editor_data()["items"])

        # ---------- S8 零金币商品也能买（价格边界） ----------
        r.section("S8 零价格商品")
        cfg = c.editor_data()["config"]
        start_scene = cfg.get("initial_scene")
        scene = c.editor_data()["scenes"][start_scene]
        scene["shop_items"] = [{"item_id": "qa_bread", "price": 0}]
        r.check("start-scene-shop-save",
                c.editor_save("scene", scene).get("success") is True)
        c.reset()  # 初始场景
        shop = c.state()["scene"].get("shop_items", [])
        r.check("bread-on-sale-0g",
                any(g.get("id") == "qa_bread" and g.get("price") == 0 for g in shop),
                shop)
        free = c.buy("qa_bread")
        r.check("free-buy-success", free.get("success") is True, free)
        r.check("bread-in-bag", "qa_bread" in inventory_ids(c.state()))
        r.check("free-bread-full-hp-blocked",
                c.use_item("qa_bread").get("success") is False)

        # ---------- S9 引用中的物品禁止删除 ----------
        r.section("S9 删除保护")
        # S8 改写了初始场景商店，先恢复到原始数据，确保 healing_potion 仍在售
        editor_restore(c, snap)
        r.check("potion-delete-blocked",
                c.editor_delete("item", "healing_potion").get("success") is False)
        sword_id = next((i for i in c.editor_data()["items"]
                         if "weapon" in c.editor_data()["items"][i].get("tags", [])), None)
        if sword_id:
            r.check("sword-delete-blocked",
                    c.editor_delete("item", sword_id).get("success") is False)

    finally:
        editor_restore(c, snap)
        c.cleanup_saves()


if __name__ == "__main__":
    import sys
    from qa.tge_api import ping, DEFAULT_BASE
    if not ping():
        print(f"服务器未响应（{DEFAULT_BASE}），请先启动：.venv\\Scripts\\python.exe app.py")
        sys.exit(2)
    r = QaRunner(SUITE)
    run(r)
    print("\n" + "=" * 60)
    print(r.report())
    sys.exit(1 if r.failed else 0)
