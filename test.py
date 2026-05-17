import config

d = [m for key, m in config.WEEKLY_MISSIONS.items() if not m["auto_track"] and m["status"] == "Active"]
print(d['key'])
