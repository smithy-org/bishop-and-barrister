import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jev_client as j

state = "A player says: Blood Moon makes Urborg a Mountain but Urborg was there first so all lands stay Swamps."
q = {
    "s": j.choice("Do the official rules settle this?", {"settled": "The official rules decide it", "gap": "They are silent", "contested": "They support two readings"}),
    "n": j.noul("Does an official rule contradict the player's claim?"),
}
r = j.call(state, q)
print(json.dumps(r))
