"""Arcane Code Editor prototype using Panda3D.

This script implements a conceptual text-to-magic system. The left side of the
window provides a code editor where players can write Python code describing a
spell. The right side renders a small 3D scene in Panda3D showing the results.

The available API for spell code is:
    create_orb(force_value)
    use_fire(orb)
    use_water(orb)
    apply_force_to(entity, force_value)
    on_event(event_type, callback)
    player               # object exposing mana and elemental reserves

Spell code is executed in a restricted namespace for safety.
"""

# The Panda3D window is embedded inside a Tkinter UI.  This approach keeps the
# script self contained: only ``panda3d`` is required as an external dependency.

import tkinter as tk
from collections import defaultdict
from typing import Callable, Dict, List

# Panda3D imports. ``loadPrcFileData`` is used before ``ShowBase`` is created so
# that the default window is not opened until it can be embedded in Tk.
from panda3d.core import Vec3, WindowProperties, CardMaker, loadPrcFileData
from direct.showbase.ShowBase import ShowBase


# ---------------------------------------------------------------------------
# Basic game entities
# ---------------------------------------------------------------------------
class Entity:
    """Simple physics entity.

    Every object that a spell can act on is represented by an ``Entity``.  Each
    entity owns a Panda3D ``NodePath`` and a velocity vector that is updated in
    the physics loop.
    """

    def __init__(self, name: str, node):
        self.name = name
        self.node = node
        self.velocity = Vec3(0, 0, 0)


class Player(Entity):
    """Player entity with mana and elemental reserves."""

    def __init__(self, node):
        super().__init__("player", node)
        self.mana = 100
        self.fire = 50
        self.water = 50
        # Body parts are also entities so spells can target them directly.
        self.hands = Entity("hands", node)
        self.feet = Entity("feet", node)


class Orb(Entity):
    """Spell-created entity used as a conduit for magic."""

    def __init__(self, node):
        super().__init__("orb", node)
        self.element = None  # "fire" or "water"


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
class MagicEditor(ShowBase):
    """Combined Tk/Panda3D application implementing the prototype editor."""

    def __init__(self):
        # Prevent Panda3D from opening a window until we embed it in Tk.
        loadPrcFileData("", "window-type none")
        ShowBase.__init__(self, windowType="none")

        # -------------------------- Tkinter UI ----------------------------
        self.root = tk.Tk()
        self.root.title("Arcane Code Editor")

        # Left side: code editor and controls
        self.left = tk.Frame(self.root)
        self.left.pack(side="left", fill="both", expand=True)

        self.code = tk.Text(self.left, width=60)
        self.code.insert(
            "1.0",
            "# Example spell\n"
            "orb = create_orb((10, 0, 15))\n"
            "use_fire(orb)\n",
        )
        self.code.pack(fill="both", expand=True)

        # Stats and cast button
        self.mana_var = tk.StringVar()
        self.fire_var = tk.StringVar()
        self.water_var = tk.StringVar()
        tk.Label(self.left, textvariable=self.mana_var).pack(anchor="w")
        tk.Label(self.left, textvariable=self.fire_var).pack(anchor="w")
        tk.Label(self.left, textvariable=self.water_var).pack(anchor="w")

        tk.Button(self.left, text="Cast Spell", command=self.cast_spell).pack(
            pady=4
        )
        self.msg_var = tk.StringVar()
        tk.Label(self.left, textvariable=self.msg_var, fg="red").pack(anchor="w")

        # Right side: container for the Panda3D window
        self.right = tk.Frame(self.root, width=640, height=480)
        self.right.pack(side="right", fill="both", expand=True)
        self.root.update_idletasks()  # Realize the frame to obtain a window id

        # ----------------------- Panda3D scene -----------------------------
        props = WindowProperties()
        props.setParentWindow(self.right.winfo_id())
        self.openDefaultWindow(props=props)

        self.setup_scene()

        # Event handlers registered by spell code
        self.event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.orbs: List[Orb] = []

        # Update label text for the first time
        self.update_stats()

        # Integrate the Tk event loop with Panda3D's task manager
        self.root.after(10, self.tk_loop)

    # ------------------------------------------------------------------
    # Scene setup and physics
    # ------------------------------------------------------------------
    def setup_scene(self):
        """Create the ground plane, player model and camera controls."""

        # Ground
        cm = CardMaker("ground")
        cm.setFrame(-20, 20, -20, 20)
        ground_np = self.render.attachNewNode(cm.generate())
        ground_np.setHpr(0, -90, 0)
        ground_np.setColor(0.5, 0.5, 0.5, 1)
        self.ground = Entity("ground", ground_np)

        # Player represented by a small sphere
        player_np = self.loader.loadModel("models/smiley")
        player_np.reparentTo(self.render)
        player_np.setScale(0.5)
        player_np.setPos(0, 0, 0.5)
        self.player = Player(player_np)

        # Simple camera control using Panda3D's default trackball
        self.disableMouse()
        self.camera.setPos(0, -25, 15)
        self.camera.lookAt(0, 0, 0)

        # Register physics update task
        self.taskMgr.add(self.update_physics, "update_physics")

    def update_physics(self, task):
        """Advance simple physics for all orbs."""

        dt = globalClock.getDt()
        to_remove = []
        for orb in self.orbs:
            # Apply velocity
            orb.node.setPos(orb.node.getPos() + orb.velocity * dt)
            # Friction slows the orb down over time
            orb.velocity *= 0.98
            # Collision with ground
            if orb.node.getZ() <= 0:
                orb.node.setZ(0)
                self.trigger_event("impact", orb, self.ground)
                # Stop the orb after impact
                orb.velocity = Vec3(0, 0, 0)
        return task.cont

    # ------------------------------------------------------------------
    # Spell API exposed to user code
    # ------------------------------------------------------------------
    def create_orb(self, force_value) -> Orb:
        """Create a new orb and apply an initial force."""

        if self.player.mana < 10:
            raise RuntimeError("Not enough mana to create orb")
        self.player.mana -= 10

        model = self.loader.loadModel("models/smiley")
        model.reparentTo(self.render)
        model.setScale(0.3)
        model.setPos(self.player.node.getPos() + Vec3(0, 2, 1))

        orb = Orb(model)
        orb.velocity = self._parse_vec(force_value)
        self.orbs.append(orb)
        return orb

    def use_fire(self, orb: Orb):
        if self.player.fire < 5:
            raise RuntimeError("Not enough fire energy")
        self.player.fire -= 5
        orb.element = "fire"
        orb.node.setColor(1, 0.3, 0.2, 1)

    def use_water(self, orb: Orb):
        if self.player.water < 5:
            raise RuntimeError("Not enough water energy")
        self.player.water -= 5
        orb.element = "water"
        orb.node.setColor(0.3, 0.3, 1, 1)

    def apply_force_to(self, entity: Entity, force_value):
        entity.velocity += self._parse_vec(force_value)

    def on_event(self, event_type: str, callback: Callable):
        self.event_handlers[event_type].append(callback)

    # ------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------
    def _parse_vec(self, value) -> Vec3:
        """Accept a tuple/list/Vec3 and return a ``Vec3`` instance."""
        if isinstance(value, Vec3):
            return value
        return Vec3(*value)

    def trigger_event(self, event_type: str, *args):
        for cb in self.event_handlers.get(event_type, []):
            try:
                cb(*args)
            except Exception as exc:
                # Errors in event handlers should not crash the game
                print(f"Error in event handler: {exc}")

    def update_stats(self):
        self.mana_var.set(f"Mana: {self.player.mana}")
        self.fire_var.set(f"Fire: {self.player.fire}")
        self.water_var.set(f"Water: {self.player.water}")

    # ------------------------------------------------------------------
    # Spell execution
    # ------------------------------------------------------------------
    def cast_spell(self):
        """Execute the code currently in the editor in a restricted namespace."""

        code = self.code.get("1.0", tk.END)
        allowed_builtins = {"range": range, "min": min, "max": max}
        safe_globals = {"__builtins__": allowed_builtins, "player": self.player}
        safe_globals.update(
            {
                "create_orb": self.create_orb,
                "use_fire": self.use_fire,
                "use_water": self.use_water,
                "apply_force_to": self.apply_force_to,
                "on_event": self.on_event,
            }
        )
        try:
            exec(code, safe_globals, {})
            self.msg_var.set("Spell cast successfully")
        except Exception as exc:
            self.msg_var.set(f"Error: {exc}")
        self.update_stats()

    # ------------------------------------------------------------------
    # Tk / Panda3D integration loop
    # ------------------------------------------------------------------
    def tk_loop(self):
        """Update Tk and Panda3D at regular intervals."""
        self.root.update()
        self.taskMgr.step()
        self.root.after(10, self.tk_loop)


# ---------------------------------------------------------------------------
# Launch the application
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = MagicEditor()
    app.tk_loop()
