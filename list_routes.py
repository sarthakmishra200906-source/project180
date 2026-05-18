import importlib
m = importlib.import_module('server.app')
app = m.app
for r in sorted(str(rule) for rule in app.url_map.iter_rules()):
    print(r)
