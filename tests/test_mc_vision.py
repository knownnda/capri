"""Offline tests for the Minecraft vision autopilot (no Minecraft needed):  python -m pytest tests  (or: python tests/test_mc_vision.py)"""
import os, sys, threading
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import numpy as np
import mc_vision as MV
import autoplay as AP

def test_parse_commands():
    cases = {"chop some wood": "skill:chop_wood:8", "get me 20 logs": "skill:chop_wood:20", "chop down a stack of trees": "skill:chop_wood:64",
             "find diamonds": "skill:find_ore:diamond", "get me some iron": "skill:find_ore:iron", "look for ores": "skill:find_ore:any",
             "mine down": "skill:mine:12", "go mining": "skill:mine:12", "get some cobblestone": "skill:mine:12",
             "explore": "skill:explore:60", "explore for 3 minutes": "skill:explore:180", "fight": "skill:fight:60", "protect me": "skill:fight:60",
             "eat": "skill:eat:", "i'm hungry": "skill:eat:", "build a shelter": "skill:shelter:", "build me a house": "skill:shelter:",
             "build a 6 block tower": "skill:pillar:6", "pillar up": "skill:pillar:5", "what do you see": "skill:describe:",
             "play for me": "skill:play:30", "beat the game for me": "skill:play:30", "hey capri, take over": "skill:play:30",
             "my pickaxe is in slot 3": "config:slot_tool:3", "food is in slot 8": "config:slot_food:8", "put blocks in slot 2": "config:slot_blocks:2"}
    for text, want in cases.items():
        p = AP.parse(text); assert p and p[0][0] == want, (text, p)

def test_stop_and_not_hijacked():
    for s in ("stop", "my turn", "hey capri stop", "take back control", "F8 stop now"): assert AP.stop_phrase(s) or s.startswith("F8"), s
    for s in ("describe the french revolution", "i'm hungry", "status of my order"):
        assert not AP.wants_autoplay(s, "music"), s                     # outside gaming mode these stay normal chat
    assert not AP.wants_autoplay("play minecraft", "off")               # that one LAUNCHES the game

F3_LEFT = ["Minecraft 1.21.1 (1.21.1/vanilla)", "60 fps T: 120 vsync fancy fancy-clouds B: 2", "XYZ: -12.345 / 64.00000 / 7.891", "Block: -13 64 7 [3 0 7]",
           "Chunk: -1 4 0 [3 0 7] in r.-1.0.mca", "Facing: north (Towards negative Z) (-179.9 / 12.3)", "Biome: minecraft:plains"]
F3_RIGHT = ["Java: 21.0.3 64bit", "Mem: 35% 1400/4096MB", "Targeted Block: -13, 63, 6", "minecraft:oak_log", "#minecraft:logs", "Targeted Fluid: -13, 63, 6",
            "minecraft:empty", "Targeted Entity", "minecraft:zombie"]

def test_parse_debug_clean_and_noisy():
    d = MV.parse_debug(F3_LEFT, F3_RIGHT)
    assert d["pos"] == (-12.345, 64.0, 7.891) and d["yaw"] == -179.9 and d["pitch"] == 12.3, d
    assert d["block"] == "oak_log" and d["fluid"] == "empty" and d["entity"] == "zombie", d
    noisy_l = ["XY2: -12,345 / 64,00000 / 7,891", "Facing: north (Towards negative Z) (-179.9 l 12.3)"]
    noisy_r = ["Targeted Block: -13, 63, 6", "minecraft; deepslate_diamond_ore"]
    d = MV.parse_debug(noisy_l, noisy_r)
    assert d["pos"] == (-12.345, 64.0, 7.891) and d["pitch"] == 12.3 and d["block"] == "deepslate_diamond_ore", d
    assert MV.parse_debug([], []) == {}

def frame(tree_x=None, ore=None, lava=False, water=False, w=480, h=270):
    f = np.zeros((h, w, 3), np.uint8); f[:] = (120, 165, 255)                       # sky
    f[int(h * 0.6):] = (95, 150, 60)                                                 # grass
    if tree_x is not None:
        x = int(w * tree_x); f[int(h * 0.15):int(h * 0.7), x - 8:x + 8] = (110, 85, 50)        # oak bark
        f[int(h * 0.02):int(h * 0.3), x - 45:x + 45] = (45, 105, 30)                           # leaves
        f[int(h * 0.15):int(h * 0.7), x - 8:x + 8] = (110, 85, 50)
    if ore:
        f[:] = (125, 125, 125)                                                       # stone wall
        cx, cy = int(w * ore[0]), int(h * ore[1]); f[cy - 6:cy + 6, cx - 6:cx + 6] = (90, 230, 220)   # diamond specks
    if lava: f[int(h * 0.45):int(h * 0.8), int(w * 0.35):int(w * 0.65)] = (255, 120, 15)
    if water: f[int(h * 0.55):int(h * 0.86), :] = (40, 70, 200)
    return f

def test_colour_finders():
    t = MV.find_tree(frame(tree_x=0.7)); assert t and abs(t[0] - 0.7) < 0.05, t
    assert MV.find_tree(frame()) is None
    o = MV.find_color(frame(ore=(0.3, 0.4)), "diamond"); assert o and abs(o[0] - 0.3) < 0.05 and abs(o[1] - 0.4) < 0.08, o
    assert MV.danger(frame(lava=True)) and not MV.danger(frame())
    assert MV.water_ahead(frame(water=True)) and not MV.water_ahead(frame())

def test_camera_math():
    assert abs(MV.deg_per_pixel({"mouseSensitivity": "0.5"}) - 0.15) < 1e-6
    assert MV.vertical_fov({"fov": "0.0"}) == 70 and MV.vertical_fov({"fov": "1.0"}) == 110

class FakePlayer(MV.Player):
    """A Player wired to a tiny fake world instead of the screen."""
    def __init__(self, blocks):
        self.stop = threading.Event(); self.inp = MV.Input(0, self.stop); self.scr = None
        self.opts = {}; self.dpp = 0.15; self.vfov = 70; self.rect = (0, 0, 1920, 1080)
        self.yaw = 0.0; self.pitch = 0.0; self.dbg = {}; self.dbg_at = 0; self.ocr_ok = True; self.f3_by_me = False
        self.progress = lambda m: None; self.count = 0; self.last_frame = None; self.blocks = list(blocks); self.ticks = 0
    def frame(self): return frame()
    def read(self, force=False):
        self.ticks += 1
        b = self.blocks[0] if self.blocks else None
        if self.inp.buttons and self.ticks % 3 == 0 and self.blocks: self.blocks.pop(0)  # holding attack breaks the block after a few reads
        return {"block": b, "yaw": self.yaw, "pitch": self.pitch, "pos": (0, 64, 0)}
    def sleep(self, s): self.check()

def test_mine_target_closed_loop():
    p = FakePlayer(["oak_log", "air"]); assert p.mine_target(want=r"_log$") and p.count == 1
    p = FakePlayer(["bedrock"]); assert not p.mine_target()                           # never digs bedrock / lava / chests
    p = FakePlayer(["stone"]); assert not p.mine_target(want=r"_log$")                # wrong block: leaves it

def test_look_to_and_pitch_clamp():
    p = FakePlayer([]); p.look_to(yaw=90, pitch=30); assert abs(p.yaw - 90) < 1 and abs(p.pitch - 30) < 1
    p.turn(0, 200); assert p.pitch <= 89.5

def test_viewer_commands_whitelist():
    import stream_live as SL
    SL.init(ap_parse=AP.parse)
    assert SL.viewer_command("!wood")[1] == ["skill:chop_wood:16"]
    assert SL.viewer_command("!diamonds")[1] == ["skill:find_ore:diamond"]
    assert SL.viewer_command("!food is in slot 1") is None                            # viewers can't change your hotbar config
    assert SL.viewer_command("!delete system32") is None and SL.viewer_command("hello") is None

if __name__ == "__main__":
    n = 0
    for k, v in list(globals().items()):
        if k.startswith("test_"): v(); n += 1; print("ok", k)
    print(f"{n} tests passed")
