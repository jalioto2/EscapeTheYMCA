# Health, medkits, and restarting

Player health, medkits, and death/restart use Unreal Engine 5.8 Blueprints and UMG widgets. The gameplay has no additional runtime plugin dependencies.

## Player behavior

- A new life starts with 100 health. The health bar appears above the existing flashlight battery bar at the bottom left.
- Positive damage reduces health, clamped at zero. Negative damage and nonpositive healing do nothing.
- Medkits restore 25 health by default, up to the maximum. A medkit remains available when the player is already healthy or dead, or when its configured healing amount is invalid.
- At zero health, the player stops moving, loses input and pickup collision, and switches the flashlight off. The world pauses and a Game Over screen appears. Restart has keyboard focus and also accepts a mouse click.
- Restart reloads the current map. Health, battery, input, the HUD, and placed pickups reset. It does not send the player to a hard-coded map.

One medkit is placed near Player Start in each existing map: `Lvl_FirstPerson` and `Ribhav_testing`, at approximately `(260, -160, 212)`. These placements use World Partition external actor files; include both new external actor packages when sharing the change. The `.umap` files themselves are unchanged.

## Integrating enemies and other pickups

For an enemy attack or damage volume, use Unreal's **Apply Damage** node with the player as **Damaged Actor** and a positive **Base Damage**. `BP_FirstPersonCharacter.Event AnyDamage` forwards it to `BPC_Health`, refreshes the HUD, and handles death once. Do not call the component directly from an enemy, since the character owns those presentation and death transitions.

For another healing item, call **TryHeal(Amount)** on `BP_FirstPersonCharacter`. Its **RestoredHealth** output is the actual amount restored. Consume the item only when that output is greater than zero. `BP_MedkitPickup` demonstrates this through a sphere overlap restricted to Pawns, followed by a player cast.

Set **MaxHealth** on the character's `HealthComponent` to change starting health; Begin Play initializes current health to that maximum and clamps the maximum to at least 1. Set **HealAmount** on individual medkit instances to change healing.

## Assets

| Asset | Responsibility |
| --- | --- |
| `FirstPerson/Blueprints/BPC_Health` | Health bounds, damage, healing, dead state, normalized health percentage |
| `FirstPerson/Blueprints/BP_FirstPersonCharacter` | Standard damage event, healing interface, HUD refresh, death transition |
| `FirstPerson/Blueprints/BP_MedkitPickup` | Overlap pickup; consumes only after successful healing |
| `FirstPerson/UI/WBP_FlashlightHUD` | Existing battery interface plus health bar and responsive bottom-left layout |
| `FirstPerson/UI/WBP_GameOver` | Focused Restart button and reload of the current map |
| `FirstPerson/Materials/MI_MedkitCase`, `MI_MedkitCross` | White case and red cross, using the existing flat-color material |

The original flashlight toggle, drain timer, battery capacity, recharge amount, and battery pickup Blueprint are preserved. The character's existing `Regarge_battery` event retains its name and signature, with a dead-player guard. Recharging an empty flashlight still leaves it off until F is pressed. The battery widget's development print was removed while extending the HUD.

## Verification

For a manual check, open `Ribhav_testing` and press Play. The map includes both a medkit and a battery pickup. Press F to check the flashlight toggle and battery drain.

While Play is running, release the mouse with Shift+F1 and open Output Log. With its input set to Cmd, run the following to reduce health from 100 to 50:

```text
py import unreal; unreal.GameplayStatics.apply_damage(unreal.GameplayStatics.get_player_character(unreal.EditorLevelLibrary.get_pie_worlds(False)[0], 0), 50.0, None, None, None)
```

Walk into the medkit to restore 25 health. If already overlapping it when damage is applied, step away and re-enter. At full health, the medkit should remain available. To test death, run the same command with `1000.0` instead of `50.0`, then click Restart. Confirm that the same map reloads with full health and battery, working flashlight controls, and the medkit restored.

The manual damage command and automated script require the editor plugins listed below. Gameplay itself does not require them.

`Tools/Unreal/health_smoke_test.py` runs integration checks in real Play In Editor. It uses standard damage calls, actual pickup overlaps, Enhanced Input injection, the Restart button's click delegate, and actual level travel. It changes only PIE actors and state; it does not edit or save level assets.

Open either map and stop Play mode. With **Python Editor Script Plugin** and **Editor Scripting Utilities** available in the editor session, execute the script through **Tools > Execute Python Script**, or run this in the Python console with the appropriate absolute path. These test tools can be enabled for one launch with `-EnablePlugins=PythonScriptPlugin,EditorScriptingUtilities`.

```python
exec(open(r"<project>/Tools/Unreal/health_smoke_test.py").read())
```

The script starts and stops PIE automatically, logs every check, and writes `Saved/Tests/health_smoke_test.json`. It covers initialization, damage and healing boundaries, full-health pickup preservation, invalid healing amounts, battery pickup compatibility, flashlight toggling/drain/depletion, death, keyboard focus, duplicate-death prevention, restart, pickup restoration, stale HUD removal, and input after restart.

All 47 checks passed on each map in Unreal Engine 5.8.2 using `-nullrhi`, including a fresh editor load of the saved assets. All five feature Blueprints compiled without errors or warnings. These checks verify gameplay and widget state; rendered appearance still requires a visual playthrough. Enemies and damage volumes can integrate through Apply Damage.
