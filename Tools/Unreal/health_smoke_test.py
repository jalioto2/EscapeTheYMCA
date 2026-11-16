"""Run inside Unreal Editor 5.8 with Python Editor Script Plugin and
Editor Scripting Utilities enabled for the editor session.
Open either game map, stop PIE, then run: py "<path>/health_smoke_test.py"
Exercises real Blueprint events, overlap collision, Enhanced Input, UMG and map travel.
Only PIE actors/state are modified. Results: Saved/Tests/health_smoke_test.json.
"""
import json
import time
import traceback
from pathlib import Path
import unreal

class HealthSmokeTest:
    def __init__(self):
        self.editor = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
        if self.editor.is_in_play_in_editor():
            raise RuntimeError('Stop Play mode before running the health smoke test.')
        self.step = 0
        self.ready_at = time.monotonic()
        self.deadline = self.ready_at + 90
        self.results = []
        self.state = {}
        self.report = Path(unreal.Paths.project_saved_dir()) / 'Tests/health_smoke_test.json'
        self.handle = unreal.register_slate_post_tick_callback(self.tick)
        self.editor.editor_request_begin_play()

    def check(self, condition, name, details=None):
        if not condition:
            raise AssertionError(f'{name}: {details}')
        self.results.append({'check': name, 'passed': True, 'details': details})
        unreal.log('HEALTH TEST PASS: ' + name)

    def next(self, delay=0.15):
        self.step += 1
        self.ready_at = time.monotonic() + delay

    def bp_class(self, name):
        return unreal.BlueprintEditorLibrary.generated_class(unreal.load_asset('/Game/FirstPerson/Blueprints/' + name))

    def actors(self, world, name):
        return list(unreal.GameplayStatics.get_all_actors_of_class(world, self.bp_class(name)))

    def flashlight(self, world):
        action = unreal.load_asset('/Game/Input/Actions/IA_Flashlight')
        subsystems = [s for s in unreal.ObjectIterator(unreal.EnhancedInputLocalPlayerSubsystem) if s.get_world() == world]
        if len(subsystems) != 1:
            raise AssertionError('Expected one local Enhanced Input subsystem, got ' + str(len(subsystems)))
        subsystems[0].inject_input_vector_for_action(action, unreal.Vector(1, 0, 0), [], [])

    def spawn(self, world, name, location, properties=None):
        transform = unreal.Transform(location=location)
        api = unreal.get_default_object(unreal.GameplayStatics)
        actor = api.call_method('BeginDeferredActorSpawnFromClass', (
            world, self.bp_class(name), transform, unreal.SpawnActorCollisionHandlingMethod.ALWAYS_SPAWN,
            None, unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))
        for key, value in (properties or {}).items():
            actor.set_editor_property(key, value)
        return api.call_method('FinishSpawningActor', (actor, transform, unreal.SpawnActorScaleMethod.MULTIPLY_WITH_ROOT))

    def damage(self, player, amount):
        return unreal.GameplayStatics.apply_damage(player, amount, player.get_controller(), player, None)

    def finish(self, error=None):
        unreal.unregister_slate_post_tick_callback(self.handle)
        payload = {'passed': error is None, 'checks': self.results, 'error': error,
                   'engine_version': unreal.SystemLibrary.get_engine_version(), 'map': self.state.get('map')}
        self.report.parent.mkdir(parents=True, exist_ok=True)
        self.report.write_text(json.dumps(payload, indent=2))
        if error:
            unreal.log_error('HEALTH SMOKE TEST FAILED: ' + error)
        else:
            unreal.log('HEALTH SMOKE TEST PASSED: ' + str(len(self.results)) + ' checks. ' + str(self.report))
        self.editor.editor_request_end_play()

    def tick(self, delta):
        try:
            if time.monotonic() > self.deadline:
                raise TimeoutError('Health smoke test timed out at step ' + str(self.step))
            if time.monotonic() < self.ready_at:
                return
            worlds = unreal.EditorLevelLibrary.get_pie_worlds(False)
            if not worlds:
                return
            world = worlds[0]
            player = unreal.GameplayStatics.get_player_character(world, 0)
            if not player:
                return
            hc = player.get_editor_property('HealthComponent')
            hud = player.get_editor_property('BatteryHUD')
            if not hc or not hud:
                return
            health = hc.get_editor_property('Health')
            battery = player.get_editor_property('Battery')
            pc = player.get_controller()
            light = player.get_editor_property('SpotLight')
            pos = player.get_actor_location()
            pickup_pos = unreal.Vector(pos.x, pos.y, pos.z - 70)

            if self.step == 0:
                if not self.state.get('input_ready'):
                    unreal.WidgetLibrary.set_input_mode_game_only(pc, False)
                    unreal.WidgetLibrary.set_focus_to_game_viewport()
                    self.state['input_ready'] = True
                    self.ready_at = time.monotonic() + .25
                    return
                self.state['map'] = unreal.GameplayStatics.get_current_level_name(world, True)
                self.check(health == 100 and hc.get_editor_property('MaxHealth') == 100, 'Fresh spawn has 100/100 health')
                self.check(99 <= battery <= 100, 'Fresh spawn has full battery', battery)
                self.check(hud.get_editor_property('PB_Health').percent == 1, 'Health HUD initializes to full')
                self.check(player.get_editor_property('is_light_on') and light.is_visible(), 'Flashlight starts on')
                self.state['placed_medkits'] = len(self.actors(world, 'BP_MedkitPickup'))
                self.check(self.state['placed_medkits'] >= 1, 'Map contains a placed medkit')
                self.flashlight(world)
                self.next()
            elif self.step == 1:
                self.check(not player.get_editor_property('is_light_on') and not light.is_visible(), 'Existing F action switches flashlight off')
                player.call_method('Regarge_battery', (60.0 - player.get_editor_property('Battery'),))
                player.call_method('RefreshBatteryHUD')
                self.next(0.65)
            elif self.step == 2:
                self.check(abs(battery - 60) < .001, 'Battery does not drain while flashlight is off')
                self.damage(player, 25)
                self.check(hc.get_editor_property('Health') == 75 and hud.get_editor_property('PB_Health').percent == .75, 'Standard ApplyDamage updates health and HUD')
                self.damage(player, -20)
                self.check(hc.get_editor_property('Health') == 75, 'Negative damage does not heal')
                self.check(player.call_method('TryHeal', (10.0,)) == 10 and hc.get_editor_property('Health') == 85, 'Healing returns actual amount restored')
                self.check(player.call_method('TryHeal', (500.0,)) == 15 and hc.get_editor_property('Health') == 100, 'Healing clamps at maximum')
                self.check(player.call_method('TryHeal', (-20.0,)) == 0 and player.call_method('TryHeal', (0.0,)) == 0, 'Nonpositive healing is ignored')
                actor = self.spawn(world, 'BP_MedkitPickup', pickup_pos)
                self.state['full_medkit_name'] = actor.get_name()
                self.next()
            elif self.step == 3:
                matches = [a for a in self.actors(world, 'BP_MedkitPickup') if a.get_name() == self.state['full_medkit_name']]
                self.check(len(matches) == 1 and health == 100, 'Overlap at full health preserves medkit')
                self.damage(player, 70)
                player.set_actor_location(unreal.Vector(pos.x, pos.y + 450, pos.z), False, True)
                player.set_actor_location(pos, False, True)
                self.next()
            elif self.step == 4:
                self.check(health == 55, 'Actual medkit overlap heals 25', health)
                self.check(not any(a.get_name() == self.state['full_medkit_name'] for a in self.actors(world, 'BP_MedkitPickup')), 'Successful medkit pickup is destroyed')
                self.check(battery == 60 and not player.get_editor_property('is_light_on'), 'Medkit preserves battery and flashlight state')
                self.check(player.call_method('TryHeal', (100.0,)) == 45 and player.call_method('TryHeal', (25.0,)) == 0, 'Healing caps and full-health healing returns zero')
                self.damage(player, 25)
                actor = self.spawn(world, 'BP_MedkitPickup', pickup_pos, {'HealAmount': -25.0})
                self.state['invalid_medkit_name'] = actor.get_name()
                player.call_method('Regarge_battery', (40.0 - player.get_editor_property('Battery'),))
                player.call_method('RefreshBatteryHUD')
                self.spawn(world, 'BP_BatteryPickup', pickup_pos)
                self.next()
            elif self.step == 5:
                self.check(health == 75 and any(a.get_name() == self.state['invalid_medkit_name'] for a in self.actors(world, 'BP_MedkitPickup')), 'Invalid medkit amount is harmless and does not consume pickup')
                self.check(abs(battery - 55) < .001 and abs(hud.get_editor_property('PB_battery').percent - .55) < .001, 'Existing battery pickup recharges 15 and updates its HUD', battery)
                player.call_method('Regarge_battery', (95.0 - player.get_editor_property('Battery'),))
                self.spawn(world, 'BP_BatteryPickup', pickup_pos)
                self.next()
            elif self.step == 6:
                self.check(battery == 100, 'Battery pickup still clamps to maximum')
                self.flashlight(world)
                self.next()
            elif self.step == 7:
                self.check(player.get_editor_property('is_light_on') and light.is_visible(), 'Existing F action switches flashlight back on')
                self.state['drain_battery'] = battery
                self.state['drain_time'] = unreal.SystemLibrary.get_game_time_in_seconds(world)
                self.next(.85)
            elif self.step == 8:
                elapsed = unreal.SystemLibrary.get_game_time_in_seconds(world) - self.state['drain_time']
                drained = self.state['drain_battery'] - battery
                self.check(drained > 0 and abs(drained - 2 * elapsed) <= .45, 'Existing flashlight drain remains 2 units per second', {'elapsed': elapsed, 'drained': drained})
                player.call_method('Regarge_battery', (.2 - player.get_editor_property('Battery'),))
                player.call_method('RefreshBatteryHUD')
                self.next(.35)
            elif self.step == 9:
                self.check(battery == 0 and not player.get_editor_property('is_light_on') and not light.is_visible(), 'Empty battery clamps to zero and switches light off')
                self.check(hud.get_editor_property('PB_battery').percent == 0, 'Battery HUD reaches empty')
                self.flashlight(world)
                self.next()
            elif self.step == 10:
                self.check(not player.get_editor_property('is_light_on'), 'F cannot enable an empty flashlight')
                self.spawn(world, 'BP_BatteryPickup', pickup_pos)
                self.next()
            elif self.step == 11:
                self.check(battery == 15 and not player.get_editor_property('is_light_on'), 'Battery pickup restores empty flashlight without toggling it')
                self.flashlight(world)
                self.next()
            elif self.step == 12:
                self.check(player.get_editor_property('is_light_on'), 'Recharged flashlight can be switched on')
                self.damage(player, 10000)
                self.check(hc.get_editor_property('Health') == 0 and hc.get_editor_property('IsDead'), 'Lethal damage clamps health at zero')
                self.check(hud.get_editor_property('PB_Health').percent == 0, 'Health HUD reaches empty')
                self.check(not player.get_editor_property('is_light_on') and not light.is_visible(), 'Death switches flashlight off')
                self.check(not player.get_actor_enable_collision() and player.get_component_by_class(unreal.CharacterMovementComponent).movement_mode == unreal.MovementMode.MOVE_NONE, 'Death disables movement and pickup collision')
                screen = player.get_editor_property('GameOverWidget')
                self.check(screen is not None and screen.is_in_viewport(), 'Game Over widget is visible')
                self.check(unreal.GameplayStatics.is_game_paused(world) and pc.show_mouse_cursor, 'Death pauses world and exposes UI cursor')
                self.state['screen'] = str(screen)
                self.state['dead_battery'] = player.get_editor_property('Battery')
                self.next()
            elif self.step == 13:
                self.check(player.get_editor_property('GameOverWidget').get_editor_property('RestartButton').has_keyboard_focus(), 'Restart button receives keyboard focus')
                self.damage(player, 1000)
                self.check(str(player.get_editor_property('GameOverWidget')) == self.state['screen'], 'Repeated lethal damage does not create another death screen')
                self.check(player.call_method('TryHeal', (100.0,)) == 0 and hc.get_editor_property('Health') == 0, 'Dead player cannot be healed')
                player.call_method('Regarge_battery', (50.0,))
                self.check(player.get_editor_property('Battery') == self.state['dead_battery'], 'Dead player rejects legacy battery recharge')
                self.flashlight(world)
                self.next()
            elif self.step == 14:
                self.check(not player.get_editor_property('is_light_on') and battery == self.state['dead_battery'], 'Dead player cannot toggle light or drain battery')
                self.state['old_world'] = str(world)
                button = player.get_editor_property('GameOverWidget').get_editor_property('RestartButton')
                button.on_clicked.broadcast()
                self.next(.2)
            elif self.step == 15:
                if str(world) == self.state['old_world']:
                    return
                self.check(unreal.GameplayStatics.get_current_level_name(world, True) == self.state['map'], 'Restart stays in the current map', self.state['map'])
                self.check(health == 100 and 98 <= battery <= 100, 'Restart creates a fresh player with full health and battery', {'health': health, 'battery': battery})
                self.check(not hc.get_editor_property('IsDead') and not player.get_editor_property('DeathHandled'), 'Restart clears death flags')
                self.check(not unreal.GameplayStatics.is_game_paused(world) and not pc.show_mouse_cursor and player.get_actor_enable_collision(), 'Restart restores gameplay mode and collision')
                self.check(len(self.actors(world, 'BP_MedkitPickup')) == self.state['placed_medkits'], 'Restart restores placed pickups and removes runtime pickups')
                self.check(hud.get_editor_property('PB_Health').percent == 1 and player.get_editor_property('GameOverWidget') is None, 'Restart resets HUD and removes game-over screen')
                visible = [u.get_class().get_name() for u in unreal.ObjectIterator(unreal.UserWidget) if u.is_in_viewport()]
                self.check(visible.count('WBP_FlashlightHUD_C') == 1 and 'WBP_GameOver_C' not in visible, 'Restart leaves exactly one HUD and no stale game-over overlay', visible)
                self.check(player.get_editor_property('is_light_on') and light.is_visible(), 'Restart restores initial flashlight state')
                self.flashlight(world)
                self.next()
            elif self.step == 16:
                self.check(not player.get_editor_property('is_light_on'), 'Flashlight input works after restart')
                self.finish()
        except Exception:
            self.finish(traceback.format_exc())

_health_smoke_test = HealthSmokeTest()
