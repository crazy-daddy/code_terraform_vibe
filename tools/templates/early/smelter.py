# =============================================================================
# Early Game Self-Contained Smelter Controller (no external lib imports)
# Smelts ore into ingots with default stock floors, supporting degraded mode
# =============================================================================
def ceil(val):
    ival = int(val)
    return ival + (1 if val > ival else 0)

STORE = "inventory"
FLOORS = {"iron_ingot": 50, "silicon": 50}  # minimum stock per ingot
BATCH = 10                                   # units to commit to before re-choosing
IDLE_SLEEP = 2
POLL = 1

research = get_component("research")
inventory = get_component("inventory")
comms = get_component("comms")

if comms is None:
    print("[smelter] DEGRADED: no Signal Bus — maintaining FLOORS only")
else:
    print("[smelter] Signal Bus online — reading factory.needs, publishing factory.ore")

if not research.is_unlocked("research_auto_feeders"):
    print("[smelter] Auto Feeders not researched — port transfers will not move anything")

makes = {}
for recipe in self.list_recipes():
    makes[recipe.output_item] = recipe
print("[smelter]", len(makes), "recipes:", list(makes.keys()))

def demand():
    wanted = {}
    if comms is not None:
        needs = comms.latest("factory.needs")
        if needs is not None:
            for item in needs.keys():
                wanted[item] = needs[item]
    for item in FLOORS.keys():
        short = FLOORS[item] - inventory.count(item)
        if short > wanted.get(item, 0):
            wanted[item] = short
    return wanted

def ore_for(recipe):
    for item in recipe.inputs.keys():
        pair = {}
        pair["item"] = item
        pair["per_craft"] = recipe.inputs[item]
        return pair
    return None

def choose(wanted):
    best = None
    best_units = 0
    ore_short = {}
    for ingot in wanted.keys():
        units = wanted[ingot]
        if units <= 0 or ingot not in makes:
            continue
        recipe = makes[ingot]
        ore = ore_for(recipe)
        if ore is None:
            continue
        crafts = ceil(units / recipe.output_count)
        ore_needed = crafts * ore["per_craft"]
        ore_have = inventory.count(ore["item"]) + self.get_input_count()
        if ore_have < ore["per_craft"]:
            ore_short[ore["item"]] = ore_short.get(ore["item"], 0) + ore_needed - ore_have
            continue
        if ore_have < ore_needed:
            ore_short[ore["item"]] = ore_short.get(ore["item"], 0) + ore_needed - ore_have
        if best is None or units > best_units:
            best = recipe
            best_units = units

    result = {}
    result["recipe"] = best
    result["units"] = best_units
    result["ore_short"] = ore_short
    return result

def connect_ports():
    for port in [self.input, self.output]:
        if port.connected_id() != STORE:
            result = port.connect(STORE)
            if result.status != "ok":
                print("[smelter] connect:", result.message)
                return False
    return True

def drain():
    moved = 0
    for stack in self.output.stacks():
        result = self.output.send(stack.id, stack.count, stack.properties, "exact")
        if result.status != "ok":
            print("[smelter] drain", stack.id, ":", result.message)
        else:
            moved = moved + result.moved
    return moved

def flush_input_to_store():
    ok = True
    for stack in self.input.stacks():
        result = self.input.eject(STORE, stack.id, stack.count)
        if result.status != "ok":
            print("[smelter] eject", stack.id, ":", result.message)
            ok = False
    return ok

def select(recipe):
    if self.get_recipe() == recipe.id:
        return True
    if self.is_running():
        return False
    drain()
    if self.get_output_count() > 0:
        return False
    if not flush_input_to_store():
        return False
    result = self.set_recipe(recipe.id)
    if result.status != "ok":
        print("[smelter] set_recipe", recipe.id, ":", result.message)
        return False
    print("[smelter] recipe ->", recipe.name)
    return True

def feed(recipe, units_left):
    ore = ore_for(recipe)
    crafts_left = ceil(units_left / recipe.output_count)
    want_in = crafts_left * ore["per_craft"]
    room = self.input.capacity() - self.input.count()
    pull = min(want_in - self.input.count(), room, inventory.count(ore["item"]))
    if pull <= 0:
        return
    result = self.input.take(ore["item"], pull)
    if result.status != "ok":
        print("[smelter] take", ore["item"], ":", result.message)

def publish(ore_short, state, detail):
    if comms is None:
        return
    comms.broadcast("factory.ore", ore_short)
    status = {}
    status["state"] = state
    status["detail"] = detail
    status["recipe"] = self.get_recipe()
    status["progress"] = round(self.get_progress(), 2)
    comms.broadcast("factory.status.smelter", status)

last_note = ""

while True:
    if not connect_ports():
        sleep(IDLE_SLEEP)
        continue

    drain()

    pick = choose(demand())
    recipe = pick["recipe"]

    if recipe is None:
        publish(pick["ore_short"], "idle", "")
        note = str(pick["ore_short"])
        if note != last_note:
            if len(pick["ore_short"]) > 0:
                print("[smelter] waiting for ore:", pick["ore_short"])
            else:
                print("[smelter] floors satisfied — idle")
            last_note = note
        sleep(IDLE_SLEEP)
        continue
    last_note = ""

    if not select(recipe):
        sleep(IDLE_SLEEP)
        continue

    goal = min(BATCH, pick["units"])
    made = 0
    print("[smelter] batch:", goal, "x", recipe.output_item)
    publish(pick["ore_short"], "smelting", recipe.output_item)

    while made < goal:
        feed(recipe, goal - made)
        sleep(POLL)
        made = made + drain()
        if self.get_input_count() == 0 and not self.is_running():
            if inventory.count(ore_for(recipe)["item"]) == 0:
                print("[smelter] out of", ore_for(recipe)["item"], "after", made, "units")
                break

    made = made + drain()
    print("[smelter] batch done:", made, "x", recipe.output_item)

